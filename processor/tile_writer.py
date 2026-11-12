"""64-byte aligned .ptile binary serializer.

Emits separate .ptile + .json pairs per FeatureDomain.
"""
import json
import os
import struct
from typing import List, Dict, Any

import numpy as np

HEADER_STRUCT = struct.Struct("<IIIIIIII ddd ffff 56s")
assert HEADER_STRUCT.size == 128, HEADER_STRUCT.size

MAGIC_PTIL = 0x4C495450
MAGIC_HMAP = 0x50414D48
CONTRACT_VERSION = 1

BODY_MAP = {"earth": 1, "moon": 2, "mars": 3, "EARTH": 1, "MOON": 2, "MARS": 3}
DOMAIN_MAP = {
    "topography": 1, "mineralogy": 2, "thermal_illumination": 3,
    "granular_aeolian": 4, "volatiles_subsurface": 5,
}

GRAVITY = {"earth": 9.80665, "moon": 1.622, "mars": 3.72076,
           "EARTH": 9.80665, "MOON": 1.622, "MARS": 3.72076}
PRESSURE = {"earth": 101325.0, "moon": 3e-10, "mars": 610.0,
            "EARTH": 101325.0, "MOON": 3e-10, "MARS": 610.0}


def write_ptile(path: str, body: str, domain: str, num_octaves: int,
                num_channels: int, base_height: int, base_width: int,
                base_resolution_m: float, center_lat_deg: float,
                center_lon_deg: float, nodata_value: float = -9999.0,
                radiation_msv_yr: float = 0.0,
                octaves_data: List[np.ndarray] = None,
                magic: int = MAGIC_PTIL) -> None:
    """Write a .ptile file.

    octaves_data: list of np.ndarray shape (num_channels, H_k, W_k) float32.
    """
    if octaves_data is None:
        octaves_data = []
    body_i = BODY_MAP[str(body).lower()] if str(body).lower() in BODY_MAP else BODY_MAP[str(body).upper()]
    domain_i = DOMAIN_MAP[domain]
    grav = GRAVITY[str(body).upper()] if str(body).upper() in GRAVITY else GRAVITY[str(body).lower()]
    pres = PRESSURE[str(body).upper()] if str(body).upper() in PRESSURE else PRESSURE[str(body).lower()]

    header = HEADER_STRUCT.pack(
        magic, CONTRACT_VERSION, body_i, domain_i, num_octaves, num_channels,
        base_height, base_width, float(base_resolution_m), float(center_lat_deg),
        float(center_lon_deg), float(nodata_value), float(grav), float(pres),
        float(radiation_msv_yr), b"\x00" * 56,
    )
    assert len(header) == 128

    with open(path, "wb") as f:
        f.write(header)
        for k in range(num_octaves):
            arr = octaves_data[k] if k < len(octaves_data) else None
            Hk = base_height >> k
            Wk = base_width >> k
            if arr is None:
                arr = np.full((num_channels, Hk, Wk), nodata_value, dtype=np.float32)
            arr = np.ascontiguousarray(arr, dtype=np.float32).reshape(num_channels, Hk, Wk)
            f.write(arr.tobytes())


def write_json_sidecar(path: str, metadata: Dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)


def read_header(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        raw = f.read(128)
    magic, version, body, domain, num_octaves, num_channels, bh, bw, res, lat, lon, nodata, grav, pres, rad, reserved = HEADER_STRUCT.unpack(raw)
    return {
        "magic": magic, "version": version, "body": body, "domain": domain,
        "num_octaves": num_octaves, "num_channels": num_channels,
        "base_height": bh, "base_width": bw, "base_resolution_m": res,
        "center_lat_deg": lat, "center_lon_deg": lon, "nodata_value": nodata,
        "gravity_ms2": grav, "surface_pressure_pa": pres, "radiation_msv_yr": rad,
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--out", required=True, help="base path without extension")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--channels", type=int, default=1)
    ap.add_argument("--shape", type=int, nargs=2, default=[512, 512])
    ap.add_argument("--res", type=float, default=30.0)
    ap.add_argument("--octaves", type=int, default=5)
    args = ap.parse_args()
    H, W = args.shape
    _R = {"earth":6371000,"moon":1737400,"mars":3389500}[args.body.lower()]
    octs = [np.zeros((args.channels, H >> k, W >> k), dtype=np.float32) for k in range(args.octaves)]
    write_ptile(args.out + ".ptile", args.body, args.domain, args.octaves, args.channels,
                H, W, args.res, args.lat, args.lon, octaves_data=octs)
    meta = {
        "tile_id": os.path.basename(args.out),
        "proj4_laea": f"+proj=laea +lat_0={args.lat} +lon_0={args.lon} +R={_R} +units=m",
        "channel_names": [f"ch{i}" for i in range(args.channels)],
        "source_datasets": [],
        "acquisition_window": "",
        "quality_mask_stats": {},
        "body": args.body.upper(),
        "domain": args.domain,
        "center_lat_deg": args.lat,
        "center_lon_deg": args.lon,
        "base_resolution_m": args.res,
        "base_height": H,
        "base_width": W,
        "num_octaves": args.octaves,
        "num_channels": args.channels,
    }
    write_json_sidecar(args.out + ".json", meta)
    print(json.dumps({"out": args.out + ".ptile"}))


if __name__ == "__main__":
    import json
    main()