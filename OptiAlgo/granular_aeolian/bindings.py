"""ctypes bindings for granular_aeolian C++ module."""
import ctypes
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(_DIR, "libgranular_aeolian.so")

# Auto-build if missing
if not os.path.exists(_LIB):
    import subprocess
    src = os.path.join(_DIR, "src", "granular_aeolian.cpp")
    subprocess.run([
        "g++", "-O3", "-march=native", "-fopenmp", "-std=c++20", "-shared", "-fPIC",
        "-I", os.path.join(_DIR, "include"),
        src, "-o", _LIB
    ], check=True)

_lib = ctypes.CDLL(_LIB)

_lib.run_module.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
_lib.run_module.restype = ctypes.c_int32


def compute_similarity(earth_tile_path, target_tile_path, out_hmap_path, out_breakdown_path):
    rc = _lib.run_module(
        earth_tile_path.encode(), target_tile_path.encode(),
        out_hmap_path.encode(), out_breakdown_path.encode())
    if rc != 0:
        raise RuntimeError("run_module returned %d" % rc)
