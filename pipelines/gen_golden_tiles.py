"""Generate deterministic golden_tiles for parity/contract testing."""
import json
import os
import numpy as np

sys_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, sys_path)
from processor.tile_writer import write_ptile, write_json_sidecar

OUT = os.path.join(sys_path, "golden_tiles")
os.makedirs(OUT, exist_ok=True)

CHANNELS = {
    "topography": 6,
    "mineralogy": 8,
    "thermal_illumination": 5,
    "granular_aeolian": 5,
    "volatiles_subsurface": 5,
}
BODIES = {
    "earth": (9.80665, 101325.0),
    "moon": (1.622, 3e-10),
    "mars": (3.72076, 610.0),
}

tiles = [
    ("earth", "topography", "earth_anti_atlas", 30.5, 352.0),
    ("earth", "mineralogy", "earth_danakil", 14.0, 40.3),
    ("earth", "thermal_illumination", "earth_lut_desert", 30.5, 59.0),
    ("earth", "granular_aeolian", "earth_tanezrouft", 24.0, 3.0),
    ("earth", "volatiles_subsurface", "earth_undara", -18.2, 144.6),
    ("moon", "topography", "moon_malapert_massif", -85.0, 0.0),
    ("moon", "mineralogy", "moon_aristarchus_plateau", 23.7, 312.5),
    ("mars", "topography", "mars_arcadia_planitia", 40.0, 170.0),
    ("mars", "granular_aeolian", "mars_bagnold_dunes", -4.7, 137.4),
    ("mars", "volatiles_subsurface", "mars_arsia_mons_pits", -9.0, 239.0),
]

rng = np.random.default_rng(42)
for body, domain, tid, lat, lon in tiles:
    C = CHANNELS[domain]
    H, W = 256, 256
    octs = []
    for k in range(5):
        hk, wk = H >> k, W >> k
        arr = rng.standard_normal((C, hk, wk)).astype(np.float32) * 0.5
        # add a gradient so not trivial
        arr += (np.arange(hk)[:, None] * 0.01)[None, :, :]
        octs.append(arr)
    base = os.path.join(OUT, tid + "_" + domain)
    write_ptile(base + ".ptile", body, domain, 5, C, H, W, 30.0, lat, lon, octaves_data=octs)
    write_json_sidecar(base + ".json", {
        "tile_id": tid + "_" + domain,
        "proj4_laea": f"+proj=laea +lat_0={lat} +lon_0={lon}",
        "channel_names": [f"ch{i}" for i in range(C)],
        "source_datasets": [],
        "acquisition_window": "2024-01-01/2024-12-31",
        "quality_mask_stats": {"valid_fraction": 0.99},
        "body": body.upper(),
        "domain": domain,
        "center_lat_deg": lat,
        "center_lon_deg": lon,
        "base_resolution_m": 30.0,
        "base_height": H,
        "base_width": W,
        "num_octaves": 5,
        "num_channels": C,
    })
    print("wrote", base)

# total size
total = 0
for f in os.listdir(OUT):
    total += os.path.getsize(os.path.join(OUT, f))
print("total bytes", total, total/1e6, "MB")
