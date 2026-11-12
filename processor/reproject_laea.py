"""Planetary radius-aware LAEA metric gridder.

Reprojects raw rasters (Earth EPSG:4326, Moon IAU:30100, Mars IAU:49900)
onto local Lambert Azimuthal Equal-Area metric grids. No geographic
(lat/lon) comparison is ever emitted: output grids are metric (meters).
"""
import argparse
import json
import math
from typing import Tuple, Optional

import numpy as np
from scipy.interpolate import RegularGridInterpolator

# Planetary radii (meters)
RADII = {
    "earth": 6371000.0,
    "moon": 1737400.0,
    "mars": 3389500.0,
}

BODY_RADIUS = {"EARTH": 6371000.0, "MOON": 1737400.0, "MARS": 3389500.0}


def laea_forward(lat_deg: np.ndarray, lon_deg: np.ndarray,
                 lat0_deg: float, lon0_deg: float, R: float) -> Tuple[np.ndarray, np.ndarray]:
    """Forward LAEA: (lat,lon) degrees -> (x,y) meters."""
    lat = np.deg2rad(lat_deg)
    lon = np.deg2rad(lon_deg)
    lat0 = np.deg2rad(lat0_deg)
    lon0 = np.deg2rad(lon0_deg)
    dlon = lon - lon0
    cos_c = np.sin(lat0) * np.sin(lat) + np.cos(lat0) * np.cos(lat) * np.cos(dlon)
    cos_c = np.clip(cos_c, -1.0, 1.0)
    c = np.arccos(cos_c)
    # avoid div by zero at center
    k = np.where(c == 0, 1.0, np.sin(c) / c)
    x = R * k * np.cos(lat) * np.sin(dlon)
    y = R * k * (np.cos(lat0) * np.sin(lat) - np.sin(lat0) * np.cos(lat) * np.cos(dlon))
    return x, y


def laea_inverse(x: np.ndarray, y: np.ndarray,
                 lat0_deg: float, lon0_deg: float, R: float) -> Tuple[np.ndarray, np.ndarray]:
    """Inverse LAEA: (x,y) meters -> (lat,lon) degrees."""
    rho = np.sqrt(x * x + y * y)
    c = 2.0 * np.arcsin(np.clip(rho / (2.0 * R), -1.0, 1.0))
    lat0 = np.deg2rad(lat0_deg)
    lon0 = np.deg2rad(lon0_deg)
    sin_c = np.sin(c)
    cos_c = np.cos(c)
    # handle rho==0
    with np.errstate(divide="ignore", invalid="ignore"):
        lat = np.arcsin(np.clip(cos_c * np.sin(lat0) + (y * sin_c * np.cos(lat0)) / np.where(rho == 0, 1.0, rho), -1.0, 1.0))
    lon = lon0 + np.arctan2(x * sin_c, rho * np.cos(lat0) * cos_c - y * np.sin(lat0) * sin_c)
    lon = np.where(rho == 0, lon0, lon)
    return np.rad2deg(lat), np.rad2deg(lon)


def reproject_to_laea(source: np.ndarray,
                      src_lats: np.ndarray,
                      src_lons: np.ndarray,
                      lat0: float,
                      lon0: float,
                      body: str = "earth",
                      out_shape: Tuple[int, int] = (512, 512),
                      resolution_m: float = 30.0,
                      method: str = "linear",
                      nodata: float = -9999.0) -> np.ndarray:
    """Resample a source raster onto a local LAEA metric grid.

    source: 2D array (nlat, nlon) in C order with src_lats (descending or
            ascending) and src_lons (ascending).
    Returns: 2D array (out_shape) in meters, nodata where out of range.
    """
    R = BODY_RADIUS[body.upper()]
    H, W = out_shape
    # build target pixel centers in meters (row 0 = north, y decreases downward)
    X = np.broadcast_to((np.arange(W) - W / 2.0 + 0.5)[None, :], (H, W)).copy() * resolution_m
    Y = np.broadcast_to((H / 2.0 - 0.5 - np.arange(H))[:, None], (H, W)).copy() * resolution_m

    tlat, tlon = laea_inverse(X.ravel(), Y.ravel(), lat0, lon0, R)
    tlat = tlat.reshape(H, W)
    tlon = tlon.reshape(H, W)

    # normalize lon to src range
    src_lats = np.asarray(src_lats, dtype=float)
    src_lons = np.asarray(src_lons, dtype=float)
    # ensure ascending lats for interpolator
    if src_lats[0] > src_lats[-1]:
        src_lats = src_lats[::-1]
        source = source[::-1, :]
    # wrap target longitudes into source longitude range
    tlon_w = tlon.copy()
    if src_lons.size > 1:
        lo, hi = float(src_lons.min()), float(src_lons.max())
        for _ in range(5):
            mask = tlon_w < lo
            if not mask.any():
                break
            tlon_w[mask] += 360.0
        for _ in range(5):
            mask = tlon_w > hi
            if not mask.any():
                break
            tlon_w[mask] -= 360.0

    filled = np.where(source != nodata, source, 0.0).astype(np.float64)
    valid = (source != nodata).astype(np.float64)
    interp = RegularGridInterpolator(
        (src_lats, src_lons), filled, method=method,
        bounds_error=False, fill_value=0.0
    )
    vinterp = RegularGridInterpolator(
        (src_lats, src_lons), valid, method=method,
        bounds_error=False, fill_value=0.0
    )
    pts = np.stack([tlat.ravel(), tlon_w.ravel()], axis=-1)
    out = interp(pts).reshape(H, W)
    vout = vinterp(pts).reshape(H, W)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(vout > 1e-6, out / np.where(vout > 1e-6, vout, 1.0), nodata)
    out = np.where(vout > 1e-6, out, nodata).astype(np.float32)
    return out


def main():
    ap = argparse.ArgumentParser(description="Reproject raster to local LAEA grid")
    ap.add_argument("--body", choices=["earth", "moon", "mars"], default="earth")
    ap.add_argument("--lat0", type=float, required=True)
    ap.add_argument("--lon0", type=float, required=True)
    ap.add_argument("--src", type=str, help="Path to source .npy (2D) with sidecar .json listing lats/lons")
    ap.add_argument("--out", type=str, required=True)
    ap.add_argument("--shape", type=int, nargs=2, default=[512, 512])
    ap.add_argument("--res", type=float, default=30.0)
    args = ap.parse_args()

    if args.src:
        src = np.load(args.src)
        meta_path = args.src.replace(".npy", ".json")
        meta = json.load(open(meta_path)) if __import__("os").path.exists(meta_path) else {}
        lats = np.array(meta.get("lats", np.linspace(-10, 10, src.shape[0])))
        lons = np.array(meta.get("lons", np.linspace(-10, 10, src.shape[1])))
    else:
        # synthetic demo
        lats = np.linspace(-5, 5, 128)
        lons = np.linspace(-5, 5, 128)
        src = (np.sin(np.deg2rad(lats)[:, None] * 10) * np.cos(np.deg2rad(lons)[None, :] * 10)).astype(np.float32)

    out = reproject_to_laea(src, lats, lons, args.lat0, args.lon0,
                            body=args.body, out_shape=tuple(args.shape), resolution_m=args.res)
    np.save(args.out, out)
    print(json.dumps({"out": args.out, "shape": list(out.shape)}))


if __name__ == "__main__":
    main()
