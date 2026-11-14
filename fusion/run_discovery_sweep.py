"""Phase C Cross-Planetary Analog Discovery Sweep.

Evaluates every standardized Earth region x Moon/Mars target pair across all 5
physical domains defaulting to the C++20 OptiAlgo backend (bindings.py, --backend cpp;
legacy Python reference mode --backend python is opt-in only for verification),
applies multi-module fusion and scale-invariance filtering (fusion/engine.py),
applies 150 km known-analog novelty suppression (fusion/novelty_mask.py), maps
operational engineering protocols (fusion/mission_mapper.py), and writes ranked
novel + unmasked calibration results plus merged breakdown dossiers.
"""
import argparse
import importlib.util
import json
import os
import struct
import subprocess
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from fusion.breakdown_synthesizer import synthesize_site_dossier, write_dossier  # noqa: E402
from fusion.engine import composite_similarity, scale_invariance_filter  # noqa: E402
from fusion.mission_mapper import map_site  # noqa: E402
from fusion.novelty_mask import apply_suppression, load_mask  # noqa: E402

DOMAINS = [
    "topography",
    "mineralogy",
    "thermal_illumination",
    "granular_aeolian",
    "volatiles_subsurface",
]
DOMAIN_IDS = {d: i + 1 for i, d in enumerate(DOMAINS)}
HEADER_STRUCT = struct.Struct("<IIIIIIII ddd ffff 56s")
MAGIC_HMAP = 0x50414D48
CONTRACT_VERSION = 1


def read_hmap_header_and_octaves(path):
    """Read a .hmap header dict and list of (2, Hk, Wk) float32 octave arrays."""
    with open(path, "rb") as f:
        data = f.read()
    hdr = HEADER_STRUCT.unpack(data[:128])
    num_octaves = hdr[4]
    num_channels = hdr[5]
    bh = hdr[6]
    bw = hdr[7]
    off = 128
    octaves = []
    for k in range(num_octaves):
        Hk = max(1, bh >> k)
        Wk = max(1, bw >> k)
        n = num_channels * Hk * Wk
        arr = np.frombuffer(data[off:off + n * 4], dtype=np.float32).reshape(num_channels, Hk, Wk).copy()
        off += n * 4
        octaves.append(arr)
    header = {
        "body": hdr[2],
        "domain": hdr[3],
        "num_octaves": num_octaves,
        "num_channels": num_channels,
        "base_height": bh,
        "base_width": bw,
        "base_resolution_m": hdr[8],
        "center_lat_deg": hdr[9],
        "center_lon_deg": hdr[10],
        "nodata_value": hdr[11],
        "gravity_ms2": hdr[12],
        "surface_pressure_pa": hdr[13],
        "radiation_msv_yr": hdr[14],
    }
    return header, octaves


def _resize_nearest_2d(arr, target_h, target_w):
    """Upsample/resize a 2D array to (target_h, target_w) via nearest-neighbor indices."""
    sh, sw = arr.shape
    if sh == target_h and sw == target_w:
        return arr
    ri = np.minimum((np.arange(target_h, dtype=np.int64) * sh) // target_h, sh - 1)
    ci = np.minimum((np.arange(target_w, dtype=np.int64) * sw) // target_w, sw - 1)
    return arr[ri[:, None], ci[None, :]]


def write_composite_hmap(path, header_ref, comp_octaves, i_scale):
    """Write a fused 2-channel composite .hmap (ch0=filtered sim, ch1=conf mask)."""
    num_octaves = header_ref["num_octaves"]
    bh = header_ref["base_height"]
    bw = header_ref["base_width"]
    hdr_bytes = HEADER_STRUCT.pack(
        MAGIC_HMAP, CONTRACT_VERSION, header_ref["body"], 0, num_octaves, 2,
        bh, bw, float(header_ref["base_resolution_m"]),
        float(header_ref["center_lat_deg"]), float(header_ref["center_lon_deg"]),
        float(header_ref["nodata_value"]), float(header_ref["gravity_ms2"]),
        float(header_ref["surface_pressure_pa"]), float(header_ref["radiation_msv_yr"]),
        b"\x00" * 56,
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(hdr_bytes)
        for k in range(num_octaves):
            Hk = max(1, bh >> k)
            Wk = max(1, bw >> k)
            sim_k = comp_octaves.get(k)
            if sim_k is None:
                block = np.zeros((2, Hk, Wk), dtype=np.float32)
            else:
                sim_full = np.clip(_resize_nearest_2d(sim_k, Hk, Wk), 0.0, 1.0).astype(np.float32)
                i_full = _resize_nearest_2d(i_scale, Hk, Wk).astype(np.float32)
                conf_full = np.where((sim_full > 0) | (i_full > 0), 1.0, 0.0).astype(np.float32)
                block = np.stack([sim_full, conf_full], axis=0).astype(np.float32)
            f.write(np.ascontiguousarray(block, dtype=np.float32).tobytes())


def _extract_git_branch_tree(branch_ref, dest_dir):
    """Extract a branch snapshot into dest_dir when not checked out on disk."""
    os.makedirs(dest_dir, exist_ok=True)
    marker = os.path.join(dest_dir, ".git_rev")
    rev = subprocess.check_output(
        ["git", "-C", _REPO_ROOT, "rev-parse", branch_ref],
        stderr=subprocess.DEVNULL, text=True,
    ).strip()
    if os.path.exists(marker) and open(marker, encoding="utf-8").read().strip() == rev:
        return dest_dir
    archive = subprocess.check_output(
        ["git", "-C", _REPO_ROOT, "archive", "--format=tar", branch_ref],
        stderr=subprocess.DEVNULL,
    )
    import io
    import tarfile
    dest_real = os.path.realpath(dest_dir)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tf:
        if sys.version_info >= (3, 12):
            tf.extractall(dest_dir, filter="data")
        else:
            safe_members = []
            for m in tf.getmembers():
                target = os.path.realpath(os.path.join(dest_dir, m.name))
                if target == dest_real or target.startswith(dest_real + os.sep):
                    safe_members.append(m)
            tf.extractall(dest_dir, members=safe_members)
    with open(marker, "w", encoding="utf-8") as f:
        f.write(rev)
    return dest_dir


def _load_compute_fn(domain, backend, algo_root=None, cache_root=None):
    """Resolve and load compute_similarity(earth, target, hmap, breakdown) for a domain."""
    folder = "OptiAlgo" if backend == "cpp" else "BestAlgo"
    entry_file = "bindings.py" if backend == "cpp" else "algo.py"
    candidates = []
    if algo_root:
        candidates.extend([
            os.path.join(algo_root, domain, entry_file),
            os.path.join(algo_root, folder, domain, entry_file),
        ])
    candidates.extend([
        os.path.join(_REPO_ROOT, folder, domain, entry_file),
        os.path.join(os.path.dirname(_REPO_ROOT), folder, domain, entry_file),
    ])

    target_path = next((p for p in candidates if os.path.exists(p)), None)
    if target_path is None:
        branch = f"origin/{folder}/{domain}"
        dest = os.path.join(cache_root or os.path.join(_REPO_ROOT, "data_lake", ".algo_cache"), folder, domain)
        try:
            _extract_git_branch_tree(branch, dest)
        except Exception:
            _extract_git_branch_tree(f"{folder}/{domain}", dest)
        target_path = os.path.join(dest, entry_file)

    if not os.path.exists(target_path):
        raise FileNotFoundError(f"Could not locate {folder}/{domain}/{entry_file}")

    mod_dir = os.path.dirname(target_path)
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
    spec = importlib.util.spec_from_file_location(f"sweep_{backend}_{domain}", target_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.compute_similarity


def _load_known_analogs(mask_path=None):
    """Resolve Datasets/known_analogs_mask.geojson locally or from origin/Datasets."""
    candidates = []
    if mask_path:
        candidates.append(mask_path)
    candidates.extend([
        os.path.join(_REPO_ROOT, "Datasets", "known_analogs_mask.geojson"),
        os.path.join(_REPO_ROOT, "known_analogs_mask.geojson"),
        os.path.join(os.path.dirname(_REPO_ROOT), "Datasets", "known_analogs_mask.geojson"),
    ])
    for p in candidates:
        if os.path.exists(p):
            return load_mask(p)
    for ref in ("origin/Datasets:known_analogs_mask.geojson", "Datasets:known_analogs_mask.geojson"):
        try:
            raw = subprocess.check_output(
                ["git", "-C", _REPO_ROOT, "show", ref],
                stderr=subprocess.DEVNULL, text=True,
            )
            return json.loads(raw).get("features", [])
        except Exception:
            continue
    return []


def _index_standardized_tiles(directory):
    """Group `<entity_id>_<domain>.ptile` files by entity_id with sidecar metadata."""
    indexed = {}
    if not os.path.isdir(directory):
        return indexed
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".ptile"):
            continue
        stem = fn[:-6]
        matched_domain = next((d for d in DOMAINS if stem.endswith("_" + d)), None)
        if not matched_domain:
            continue
        entity_id = stem[:-(len(matched_domain) + 1)]
        ptile_path = os.path.join(directory, fn)
        json_path = os.path.join(directory, stem + ".json")
        meta = {}
        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                meta = json.load(f)
        rec = indexed.setdefault(entity_id, {"domains": {}, "meta": {}})
        rec["domains"][matched_domain] = ptile_path
        if meta and not rec["meta"]:
            rec["meta"] = meta
    return indexed


def run_sweep(
    earth_dir,
    target_dir,
    out_dir,
    backend="cpp",
    fallback_python=False,
    algo_root=None,
    known_analogs_path=None,
    weights=None,
    sites=None,
    targets=None,
    max_pairs=0,
):
    """Execute full cross-planetary discovery sweep across Earth x Target pairs."""
    os.makedirs(out_dir, exist_ok=True)
    earth_tiles = _index_standardized_tiles(earth_dir)
    target_tiles = _index_standardized_tiles(target_dir)
    if sites:
        site_set = set(sites)
        earth_tiles = {k: v for k, v in earth_tiles.items() if k in site_set}
    if targets:
        target_set = set(targets)
        target_tiles = {k: v for k, v in target_tiles.items() if k in target_set}
    if not earth_tiles:
        raise FileNotFoundError(f"No standardized Earth .ptile tiles found in {earth_dir}")
    if not target_tiles:
        raise FileNotFoundError(f"No standardized Target .ptile tiles found in {target_dir}")

    mask_features = _load_known_analogs(known_analogs_path)
    cache_root = os.path.join(out_dir, ".algo_cache")
    runners = {}
    backend_used = {}
    for d in DOMAINS:
        try:
            runners[d] = _load_compute_fn(d, backend, algo_root=algo_root, cache_root=cache_root)
            backend_used[d] = backend
        except Exception:
            if backend == "cpp" and fallback_python:
                runners[d] = _load_compute_fn(d, "python", algo_root=algo_root, cache_root=cache_root)
                backend_used[d] = "python-fallback"
            else:
                raise

    entries = []
    for target_id, tinfo in sorted(target_tiles.items()):
        if max_pairs and len(entries) >= max_pairs:
            break
        mission_test = map_site(target_id)
        for site_id, einfo in sorted(earth_tiles.items()):
            if max_pairs and len(entries) >= max_pairs:
                break
            common_domains = [d for d in DOMAINS if d in einfo["domains"] and d in tinfo["domains"]]
            if not common_domains:
                continue

            emeta = einfo.get("meta", {})
            lat = float(emeta.get("center_lat_deg", 0.0))
            lon = float(emeta.get("center_lon_deg", 0.0))
            bbox = emeta.get("bbox", [round(lat - 0.15, 5), round(lon - 0.15, 5), round(lat + 0.15, 5), round(lon + 0.15, 5)])

            module_octaves = {}
            domain_scores = {}
            domain_breakdowns = {}
            merged_residuals = {}
            merged_flags = []
            seen_flags = set()
            ref_hdr = None

            for d in common_domains:
                hmap_path = os.path.join(out_dir, f"{site_id}_{target_id}_{d}.hmap")
                bd_path = os.path.join(out_dir, f"{site_id}_{target_id}_{d}_breakdown.json")
                try:
                    runners[d](einfo["domains"][d], tinfo["domains"][d], hmap_path, bd_path)
                except Exception:
                    if backend == "cpp" and fallback_python and backend_used[d] == "cpp":
                        runners[d] = _load_compute_fn(d, "python", algo_root=algo_root, cache_root=cache_root)
                        backend_used[d] = "python-fallback"
                        runners[d](einfo["domains"][d], tinfo["domains"][d], hmap_path, bd_path)
                    else:
                        raise

                hdr, octs = read_hmap_header_and_octaves(hmap_path)
                if ref_hdr is None:
                    ref_hdr = hdr
                module_octaves[d] = octs

                # Domain scalar score: mean similarity across octave 0 valid pixels (conf > 0)
                if octs:
                    sim0, conf0 = octs[0][0], octs[0][1]
                    v0 = conf0 > 0
                    domain_scores[d] = round(float(np.mean(sim0[v0])) if v0.any() else 0.0, 6)
                else:
                    domain_scores[d] = 0.0

                if os.path.exists(bd_path):
                    with open(bd_path, encoding="utf-8") as f:
                        bd = json.load(f)
                    domain_breakdowns[d] = bd
                    for ck, cv in bd.get("channel_residuals", {}).items():
                        merged_residuals[f"{d}.{ck}"] = cv
                    for fl in bd.get("physical_breakdown_flags", []):
                        fname = fl.get("flag")
                        if fname and fname not in seen_flags:
                            seen_flags.add(fname)
                            merged_flags.append(fl)

            active_weights = {d: (weights.get(d, 1.0) if weights else 1.0) for d in common_domains}
            comp_octs = composite_similarity(module_octaves, weights=active_weights)
            _, i_scale = scale_invariance_filter(comp_octs)

            # scale_invariance_filter crops to coarsest octave shape (H_min, W_min);
            # upsample i_scale per octave so full-resolution heatmaps and scalar means align.
            full_filtered_octs = {}
            for k, comp_k in comp_octs.items():
                i_scale_k = _resize_nearest_2d(i_scale, comp_k.shape[0], comp_k.shape[1]).astype(np.float32)
                full_filtered_octs[k] = (comp_k * i_scale_k).astype(np.float32)

            comp0 = comp_octs[0]
            i_scale_0 = _resize_nearest_2d(i_scale, comp0.shape[0], comp0.shape[1])
            filt0 = full_filtered_octs[0]
            valid_c = comp0 > 0
            composite_raw = float(np.mean(comp0[valid_c])) if valid_c.any() else 0.0
            si_val = float(np.mean(i_scale_0[valid_c])) if valid_c.any() else 0.0
            composite_filtered = float(np.mean(filt0[valid_c])) if valid_c.any() else 0.0

            comp_hmap_path = os.path.join(out_dir, f"{site_id}_{target_id}_composite.hmap")
            if ref_hdr is not None:
                write_composite_hmap(comp_hmap_path, ref_hdr, full_filtered_octs, i_scale)

            novelty_w = float(apply_suppression(lat, lon, mask_features, buffer_km=150.0)) if mask_features else 1.0
            novel_score = round(composite_filtered * novelty_w, 6)

            site_bd_path = os.path.join(out_dir, f"{site_id}_{target_id}_breakdown.json")
            dossier = synthesize_site_dossier(
                site_id=site_id,
                coords={"lat": lat, "lon": lon},
                module_scores=domain_scores,
                breakdowns=domain_breakdowns,
                mission_test=mission_test,
            )
            dossier.update({
                "target_id": target_id,
                "composite_score": round(composite_filtered, 6),
                "composite_raw": round(composite_raw, 6),
                "scale_invariance_index": round(si_val, 6),
                "novelty_weight": round(novelty_w, 6),
                "channel_residuals": merged_residuals,
                "physical_breakdown_flags": merged_flags,
                "backends_used": backend_used,
            })
            write_dossier(site_bd_path, dossier)

            entries.append({
                "site_id": site_id,
                "target_id": target_id,
                "coordinates": {"lat": lat, "lon": lon},
                "lat": lat,
                "lon": lon,
                "bbox": bbox,
                "composite_score": round(composite_filtered, 6),
                "composite": round(novel_score, 6),
                "novel_composite_score": novel_score,
                "unmasked_composite_score": round(composite_filtered, 6),
                "scale_invariance_index": round(si_val, 6),
                "scale_invariance": round(si_val, 6),
                "novelty_weight": round(novelty_w, 6),
                "is_known_analog": novelty_w < 0.999,
                "domain_scores": domain_scores,
                "use_case": mission_test,
                "operational_test_protocol": mission_test,
                "breakdown_path": os.path.abspath(site_bd_path),
                "composite_hmap_path": os.path.abspath(comp_hmap_path),
            })

    novel_ranked = []
    for row in sorted(entries, key=lambda r: (r["novel_composite_score"], r["scale_invariance_index"]), reverse=True):
        copy_row = dict(row)
        copy_row["composite_score"] = row["novel_composite_score"]
        copy_row["composite"] = row["novel_composite_score"]
        novel_ranked.append(copy_row)
    unmasked_ranked = []
    for row in sorted(entries, key=lambda r: (r["unmasked_composite_score"], r["scale_invariance_index"]), reverse=True):
        copy_row = dict(row)
        copy_row["composite_score"] = row["unmasked_composite_score"]
        copy_row["composite"] = row["unmasked_composite_score"]
        unmasked_ranked.append(copy_row)

    novel_path = os.path.join(out_dir, "ranked_novel_discoveries.json")
    unmasked_path = os.path.join(out_dir, "ranked_unmasked_calibration.json")
    with open(novel_path, "w", encoding="utf-8") as f:
        json.dump({
            "backend": backend,
            "backends_used": backend_used,
            "novelty_masked": True,
            "count": len(novel_ranked),
            "sites": novel_ranked,
        }, f, indent=2)
    with open(unmasked_path, "w", encoding="utf-8") as f:
        json.dump({
            "backend": backend,
            "backends_used": backend_used,
            "novelty_masked": False,
            "count": len(unmasked_ranked),
            "sites": unmasked_ranked,
        }, f, indent=2)

    return {
        "pairs_evaluated": len(entries),
        "earth_regions": len(earth_tiles),
        "targets": len(target_tiles),
        "backends_used": backend_used,
        "ranked_novel_discoveries": novel_path,
        "ranked_unmasked_calibration": unmasked_path,
    }


def main():
    ap = argparse.ArgumentParser(description="Run cross-planetary discovery sweep across standardized tiles")
    ap.add_argument("--backend", choices=["cpp", "python"], default="cpp", help="Execution backend (default: cpp for OptiAlgo C++20)")
    ap.add_argument("--fallback-python", action="store_true", help="Optional fallback to Python reference if an OptiAlgo C++20 backend is unavailable")
    ap.add_argument("--earth-dir", default="./data_lake/standardized/earth")
    ap.add_argument("--target-dir", default="./data_lake/standardized/targets")
    ap.add_argument("--out-dir", default="./data_lake/results")
    ap.add_argument("--algo-root", default="", help="Optional base path containing OptiAlgo/<mod> or BestAlgo/<mod>")
    ap.add_argument("--known-analogs", default="", help="Optional path to known_analogs_mask.geojson")
    ap.add_argument("--weights-json", default="", help="Optional JSON string or file path of per-domain fusion weights")
    ap.add_argument("--sites", default="", help="Optional comma-separated Earth site IDs filter")
    ap.add_argument("--targets", default="", help="Optional comma-separated target IDs filter")
    ap.add_argument("--max-pairs", type=int, default=0, help="Optional cap on Earth x Target pairs (0 = all)")
    args = ap.parse_args()

    weights = None
    if args.weights_json:
        if os.path.exists(args.weights_json):
            with open(args.weights_json, encoding="utf-8") as f:
                weights = json.load(f)
        else:
            weights = json.loads(args.weights_json)

    sites = [s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None
    targets = [t.strip() for t in args.targets.split(",") if t.strip()] if args.targets else None

    summary = run_sweep(
        earth_dir=args.earth_dir,
        target_dir=args.target_dir,
        out_dir=args.out_dir,
        backend=args.backend,
        fallback_python=args.fallback_python,
        algo_root=args.algo_root or None,
        known_analogs_path=args.known_analogs or None,
        weights=weights,
        sites=sites,
        targets=targets,
        max_pairs=args.max_pairs,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
