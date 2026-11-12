#!/usr/bin/env python3
"""Generate a synthetic golden tile with nodata patches for regression testing."""
import json
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from processor.tile_writer import write_ptile

OUT = os.path.join(os.path.dirname(__file__), "nodata_fixture")
os.makedirs(OUT, exist_ok=True)

H, W = 64, 64
rng = np.random.default_rng(7)
for body, domain, tid in [("earth", "topography", "nodata_earth_topo"),
                          ("moon", "topography", "nodata_moon_topo")]:
    C = 6
    octs = []
    for k in range(5):
        hk, wk = H >> k, W >> k
        arr = (rng.standard_normal((C, hk, wk)) * 0.5 + 0.1).astype(np.float32)
        # inject nodata block in top-left quadrant
        arr[:, :hk//4, :wk//4] = -9999.0
        # inject a zero-vector pixel
        if hk > 2 and wk > 2:
            arr[:, 2, 2] = 0.0
        octs.append(arr)
    write_ptile(os.path.join(OUT, tid + ".ptile"), body, domain, 5, C, H, W, 30.0, 0.0, 0.0, octaves_data=octs)
    json.dump({"tile_id": tid, "proj4_laea": "+proj=laea +lat_0=0 +lon_0=0",
               "channel_names": ["elevation_z","slope_theta","aspect_psi","TRI","TPI","profile_curvature_kappa_p"],
               "source_datasets": [], "acquisition_window": "", "quality_mask_stats": {},
               "body": body.upper(), "domain": domain, "center_lat_deg": 0.0, "center_lon_deg": 0.0,
               "base_resolution_m": 30.0, "base_height": H, "base_width": W,
               "num_octaves": 5, "num_channels": C},
              open(os.path.join(OUT, tid + ".json"), "w"))
    print("wrote", tid)
