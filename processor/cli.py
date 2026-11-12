"""Batch standardization entrypoint for the Dataset Processor Module."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from reproject_laea import reproject_to_laea  # noqa: E402
from pyramid_builder import build_pyramid  # noqa: E402
from tile_writer import write_ptile, write_json_sidecar  # noqa: E402

import numpy as np


def _resolve_shape(shape_arg):
    if not shape_arg:
        return (512, 512)
    if isinstance(shape_arg, int):
        return (int(shape_arg), int(shape_arg))
    vals = list(shape_arg)
    if len(vals) == 1:
        return (int(vals[0]), int(vals[0]))
    return (int(vals[0]), int(vals[1]))


def process_one(src_npy, src_meta, body, domain, lat0, lon0, out_base, channels=1, out_shape=(512, 512)):
    src = np.load(src_npy)
    if src.ndim == 2:
        src_chw = src[None, ...]
    elif src.ndim == 3:
        src_chw = src
    else:
        raise ValueError(f"Expected 2D or 3D array in {src_npy}, got shape {src.shape}")

    meta = {}
    if src_meta and os.path.exists(src_meta):
        with open(src_meta, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            meta = loaded

    H_in, W_in = src_chw.shape[-2], src_chw.shape[-1]
    raw_lats = meta.get("lats")
    raw_lons = meta.get("lons")
    lats = np.asarray(raw_lats if raw_lats is not None else np.linspace(-5, 5, H_in), dtype=float)
    lons = np.asarray(raw_lons if raw_lons is not None else np.linspace(-5, 5, W_in), dtype=float)
    raw_res = meta.get("base_resolution_m")
    base_res = float(raw_res if raw_res is not None else 30.0)
    R = {"earth": 6371000, "moon": 1737400, "mars": 3389500}[body.lower()]
    H0, W0 = _resolve_shape(out_shape)

    # Reproject every channel onto the canonical 30 m/px local LAEA grid
    reproj = [
        reproject_to_laea(
            src_chw[c],
            lats,
            lons,
            lat0,
            lon0,
            body=body,
            out_shape=(H0, W0),
            resolution_m=30.0,
        )
        for c in range(src_chw.shape[0])
    ]
    out_grid = np.stack(reproj, axis=0).astype(np.float32)

    # Build 5-octave Gaussian pyramid; base_resolution_m masks finer octaves on coarse inputs
    octaves_data = build_pyramid(out_grid, base_resolution_m=base_res, num_octaves=5)
    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)
    write_ptile(
        out_base + ".ptile",
        body,
        domain,
        5,
        out_grid.shape[0],
        H0,
        W0,
        base_res,
        lat0,
        lon0,
        octaves_data=octaves_data,
    )
    ch_names = meta.get("channel_names") or [f"ch{i}" for i in range(out_grid.shape[0])]
    write_json_sidecar(
        out_base + ".json",
        {
            "tile_id": os.path.basename(out_base),
            "proj4_laea": f"+proj=laea +lat_0={lat0} +lon_0={lon0} +R={R}",
            "channel_names": ch_names,
            "source_datasets": meta.get("source_datasets") or [],
            "acquisition_window": meta.get("acquisition_window") or "",
            "quality_mask_stats": meta.get("quality_mask_stats") or {},
            "body": body.upper(),
            "domain": domain,
            "center_lat_deg": lat0,
            "center_lon_deg": lon0,
            "base_resolution_m": base_res,
            "base_height": H0,
            "base_width": W0,
            "num_octaves": 5,
            "num_channels": out_grid.shape[0],
        },
    )
    return out_base


def main():
    ap = argparse.ArgumentParser(description="Batch standardization entrypoint")
    ap.add_argument("--manifest", required=True, help="JSON manifest listing tiles")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--shape", type=int, nargs="+", default=[512, 512], help="Output H [W] base shape (default: 512 512)")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)
    default_shape = _resolve_shape(args.shape)
    results = []
    for entry in manifest.get("tiles", []):
        out_base = os.path.join(args.out_dir, entry["tile_id"])
        entry_shape = entry.get("shape") or entry.get("shape_hw") or default_shape
        process_one(
            entry["src_npy"],
            entry.get("src_meta"),
            entry["body"],
            entry["domain"],
            entry["lat0"],
            entry["lon0"],
            out_base,
            entry.get("channels", 1),
            out_shape=entry_shape,
        )
        results.append(entry["tile_id"])
    print(json.dumps({"processed": results}))


if __name__ == "__main__":
    main()
