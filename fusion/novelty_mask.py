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
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    H, W = lats.size, lons.size
    # vectorized haversine
    lat_r = np.deg2rad(lats)[:, None]
    lon_r = np.deg2rad(lons)[None, :]
    grid = np.ones((H, W), dtype=np.float32)
    for f in mask_features:
        coords = f["geometry"]["coordinates"]
        flon, flat = coords[0], coords[1]
        buf = f.get("properties", {}).get("buffer_km", buffer_km)
        dphi = np.deg2rad(flat) - lat_r
        dl = np.deg2rad(flon) - lon_r
        a = np.sin(dphi/2)**2 + np.cos(lat_r)*np.cos(np.deg2rad(flat))*np.sin(dl/2)**2
        d = 2*6371.0*np.arcsin(np.sqrt(np.clip(a,0,1)))
        w = np.clip(d/buf, 0.0, 1.0)
        grid = grid * w.astype(np.float32)
    return grid
