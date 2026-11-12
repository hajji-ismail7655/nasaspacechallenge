"""Known-analog suppression mask application."""
import json
import os
import math
import numpy as np


def load_mask(path):
    if not os.path.exists(path):
        return []
    data = json.load(open(path))
    return data.get("features", [])


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def apply_suppression(lat, lon, mask_features, buffer_km=150.0):
    """Return weight factor [0,1] for a location given known-analog buffers."""
    w = 1.0
    for f in mask_features:
        coords = f["geometry"]["coordinates"]
        # [lon, lat]
        flon, flat = coords[0], coords[1]
        buf = f.get("properties", {}).get("buffer_km", buffer_km)
        d = haversine_km(lat, lon, flat, flon)
        if d < buf:
            # down-weight: 0 at center, 1 at buffer edge
            w *= min(1.0, d / buf)
    return float(w)


def apply_mask_grid(lats, lons, mask_features, buffer_km=150.0):
    H, W = len(lats), len(lons)
    grid = np.ones((H, W), dtype=np.float32)
    for i in range(H):
        for j in range(W):
            grid[i, j] = apply_suppression(float(lats[i]), float(lons[j]), mask_features, buffer_km)
    return grid
