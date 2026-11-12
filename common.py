"""Common I/O for BestAlgo modules."""
import json
import os
import struct
import numpy as np

HEADER_STRUCT = struct.Struct("<IIIIIIII ddd ffff 40s 16x")
assert HEADER_STRUCT.size == 128
MAGIC_PTIL = 0x4C495450
MAGIC_HMAP = 0x50414D48
NODATA = -9999.0

BODY_NAMES = {1: "earth", 2: "moon", 3: "mars"}
DOMAIN_NAMES = {1: "topography", 2: "mineralogy", 3: "thermal_illumination",
                4: "granular_aeolian", 5: "volatiles_subsurface"}
GRAVITY = {1: 9.80665, 2: 1.622, 3: 3.72076}
PRESSURE = {1: 101325.0, 2: 3e-10, 3: 610.0}


def read_ptile(path):
    with open(path, "rb") as f:
        raw = f.read(128)
    (magic, version, body, domain, num_octaves, num_channels,
     base_height, base_width, base_res, center_lat, center_lon,
     nodata, grav, pres, rad, reserved) = HEADER_STRUCT.unpack(raw)
    if magic != MAGIC_PTIL:
        raise ValueError("Bad magic %s in %s" % (hex(magic), path))
    if version != 1:
        raise ValueError("Bad version %d" % version)
    with open(path, "rb") as f:
        data = f.read()
    octaves = []
    off = 128
    for k in range(num_octaves):
        Hk = base_height >> k
        Wk = base_width >> k
        n = num_channels * Hk * Wk
        block = data[off:off + n * 4]
        off += n * 4
        arr = np.frombuffer(block, dtype=np.float32).reshape(num_channels, Hk, Wk).copy()
        octaves.append(arr)
    meta_path = path.replace(".ptile", ".json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    header = {
        "magic": magic, "version": version, "body": body, "domain": domain,
        "num_octaves": num_octaves, "num_channels": num_channels,
        "base_height": base_height, "base_width": base_width,
        "base_resolution_m": base_res, "center_lat_deg": center_lat,
        "center_lon_deg": center_lon, "nodata_value": nodata,
        "gravity_ms2": grav, "surface_pressure_pa": pres,
        "radiation_msv_yr": rad,
    }
    return header, octaves, meta


def write_hmap(path, num_octaves, base_height, base_width, num_channels=2,
               octaves_data=None, body=1, domain=1, center_lat=0.0,
               center_lon=0.0, base_res=30.0, nodata=-9999.0):
    if octaves_data is None:
        octaves_data = []
    header = HEADER_STRUCT.pack(
        MAGIC_HMAP, 1, body, domain, num_octaves, num_channels,
        base_height, base_width, float(base_res), float(center_lat),
        float(center_lon), float(nodata),
        9.80665, 101325.0, 0.0, b"\x00" * 40,
    )
    with open(path, "wb") as f:
        f.write(header)
        for k in range(num_octaves):
            Hk = base_height >> k
            Wk = base_width >> k
            if k < len(octaves_data) and octaves_data[k] is not None:
                arr = np.ascontiguousarray(octaves_data[k], dtype=np.float32).reshape(num_channels, Hk, Wk)
            else:
                arr = np.zeros((num_channels, Hk, Wk), dtype=np.float32)
            f.write(arr.tobytes())


def write_breakdown(path, breakdown):
    with open(path, "w") as f:
        json.dump(breakdown, f, indent=2)


def safe_mean(arr, nodata=NODATA):
    m = arr != nodata
    if not m.any():
        return 0.0
    return float(np.mean(arr[m]))
