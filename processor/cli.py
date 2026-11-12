"""Batch standardization entrypoint for the Dataset Processor Module."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from reproject_laea import reproject_to_laea
from pyramid_builder import build_pyramid
from tile_writer import write_ptile, write_json_sidecar

import numpy as np


def process_one(src_npy, src_meta, body, domain, lat0, lon0, out_base, channels):
    src = np.load(src_npy)
    meta = json.load(open(src_meta)) if os.path.exists(src_meta) else {}
    lats = np.array(meta.get("lats", np.linspace(-5, 5, src.shape[0])))
    lons = np.array(meta.get("lons", np.linspace(-5, 5, src.shape[1])))
    base_res = float(meta.get("base_resolution_m", 30.0))
    R = {"earth": 6371000, "moon": 1737400, "mars": 3389500}[body.lower()]
    H0, W0 = 512, 512
    out_grid = reproject_to_laea(src, lats, lons, lat0, lon0, body=body,
                                 out_shape=(H0, W0), resolution_m=30.0)
    # channel handling: if 2D, add channel axis
    if out_grid.ndim == 2:
        out_grid = out_grid[None, ...]
    # build pyramid per channel
    octaves_per_channel = []
    # pyramid_builder expects (C,H,W)
    octs = build_pyramid(out_grid, base_resolution_m=base_res, num_octaves=5)
    # octs: list of (C,H,W)
    octaves_data = octs
    write_ptile(out_base + ".ptile", body, domain, 5, out_grid.shape[0],
                H0, W0, base_res, lat0, lon0, octaves_data=octaves_data)
    write_json_sidecar(out_base + ".json", {
        "tile_id": os.path.basename(out_base),
        "proj4_laea": f"+proj=laea +lat_0={lat0} +lon_0={lon0} +R={R}",
        "channel_names": meta.get("channel_names", [f"ch{i}" for i in range(out_grid.shape[0])]),
        "source_datasets": meta.get("source_datasets", []),
        "acquisition_window": meta.get("acquisition_window", ""),
        "quality_mask_stats": meta.get("quality_mask_stats", {}),
        "body": body.upper(),
        "domain": domain,
        "center_lat_deg": lat0,
        "center_lon_deg": lon0,
        "base_resolution_m": base_res,
        "base_height": H0,
        "base_width": W0,
        "num_octaves": 5,
        "num_channels": out_grid.shape[0],
    })
    return out_base


def main():
    ap = argparse.ArgumentParser(description="Batch standardization entrypoint")
    ap.add_argument("--manifest", required=True, help="JSON manifest listing tiles")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    manifest = json.load(open(args.manifest))
    results = []
    for entry in manifest.get("tiles", []):
        out_base = os.path.join(args.out_dir, entry["tile_id"])
        process_one(entry["src_npy"], entry.get("src_meta"), entry["body"],
                    entry["domain"], entry["lat0"], entry["lon0"], out_base,
                    entry.get("channels", 1))
        results.append(entry["tile_id"])
    print(json.dumps({"processed": results}))


if __name__ == "__main__":
    main()
