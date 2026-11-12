#!/usr/bin/env python3
"""Parity verification harness: compares BestAlgo (Python) vs OptiAlgo (C++)."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time

import numpy as np


def load_py_compute(py_path):
    # py_path can be a file or directory containing algo.py
    if os.path.isdir(py_path):
        py_path = os.path.join(py_path, "algo.py")
    spec = importlib.util.spec_from_file_location("pymod", py_path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(py_path))
    spec.loader.exec_module(mod)
    return mod.compute_similarity


def load_cpp_compute(cpp_dir):
    bindings_path = os.path.join(cpp_dir, "bindings.py")
    spec = importlib.util.spec_from_file_location("cppmod", bindings_path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, cpp_dir)
    spec.loader.exec_module(mod)
    return mod.compute_similarity


def read_hmap(path):
    import struct
    raw = open(path, "rb").read()
    hdr = struct.unpack("<IIIIIIII ddd ffff 56s", raw[:128])
    num_octaves = hdr[4]
    bh = hdr[6]
    bw = hdr[7]
    off = 128
    octs = []
    for k in range(num_octaves):
        Hk = bh >> k
        Wk = bw >> k
        n = 2 * Hk * Wk
        arr = np.frombuffer(raw[off:off + n * 4], dtype=np.float32).reshape(2, Hk, Wk).copy()
        off += n * 4
        octs.append(arr)
    return octs


def ssim(a, b):
    # simple SSIM for 2D arrays
    a = a.astype(np.float64).ravel()
    b = b.astype(np.float64).ravel()
    ma, mb = a.mean(), b.mean()
    va, vb = a.var(), b.var()
    cov = np.mean((a - ma) * (b - mb))
    c1, c2 = 1e-4, 9e-4
    return float(((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--py", required=True, help="Python module dir or algo.py path")
    ap.add_argument("--cpp", required=True, help="C++ module dir with bindings.py")
    ap.add_argument("--earth", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--out-dir", default="/tmp/scratchpad/parity")
    ap.add_argument("--rmse-threshold", type=float, default=1e-5)
    ap.add_argument("--ssim-threshold", type=float, default=0.9995)
    ap.add_argument("--speedup-threshold", type=float, default=10.0)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    py_hmap = os.path.join(args.out_dir, "py.hmap")
    py_bd = os.path.join(args.out_dir, "py_breakdown.json")
    cpp_hmap = os.path.join(args.out_dir, "cpp.hmap")
    cpp_bd = os.path.join(args.out_dir, "cpp_breakdown.json")

    py_compute = load_py_compute(args.py)
    cpp_compute = load_cpp_compute(args.cpp)

    t0 = time.time()
    py_compute(args.earth, args.target, py_hmap, py_bd)
    t_py = time.time() - t0

    t0 = time.time()
    cpp_compute(args.earth, args.target, cpp_hmap, cpp_bd)
    t_cpp = time.time() - t0

    py_oct = read_hmap(py_hmap)
    cpp_oct = read_hmap(cpp_hmap)

    max_rmse = 0.0
    max_rmse_conf = 0.0
    min_ssim = 1.0
    for k in range(len(py_oct)):
        diff = py_oct[k][0] - cpp_oct[k][0]
        rmse = float(np.sqrt(np.mean(diff * diff)))
        diffc = py_oct[k][1] - cpp_oct[k][1]
        rmsec = float(np.sqrt(np.mean(diffc * diffc)))
        s = ssim(py_oct[k][0], cpp_oct[k][0])
        max_rmse = max(max_rmse, rmse)
        max_rmse_conf = max(max_rmse_conf, rmsec)
        min_ssim = min(min_ssim, s)

    speedup = t_py / t_cpp if t_cpp > 0 else float("inf")
    result = {
        "rmse": max_rmse,
        "rmse_conf": max_rmse_conf,
        "ssim": min_ssim,
        "latency_py_s": t_py,
        "latency_cpp_s": t_cpp,
        "speedup": speedup,
        "rmse_pass": max_rmse < args.rmse_threshold,
        "ssim_pass": min_ssim > args.ssim_threshold,
        "speedup_pass": speedup >= args.speedup_threshold,
    }
    bd_ok = os.path.exists(py_bd) and os.path.exists(cpp_bd)
    if bd_ok:
        try:
            import json as _j
            pj = _j.load(open(py_bd))
            cj = _j.load(open(cpp_bd))
            # compare scale_invariance_index
            if abs(pj.get("scale_invariance_index",0) - cj.get("scale_invariance_index",0)) > 1e-5:
                bd_ok = False
            # compare channel_residuals keys
            if set(pj.get("channel_residuals",{}).keys()) != set(cj.get("channel_residuals",{}).keys()):
                bd_ok = False
        except Exception:
            bd_ok = False
    result["breakdown_pass"] = bd_ok
    print(json.dumps(result, indent=2))
    result["rmse_conf_pass"] = max_rmse_conf < args.rmse_threshold
    ok = result["rmse_pass"] and result["ssim_pass"] and result["speedup_pass"] and result["rmse_conf_pass"] and bd_ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
