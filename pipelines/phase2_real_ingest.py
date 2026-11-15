"""Prepare auditable 512x512 Phase 2 inputs for the C++ PTILE processor.

Copernicus DEM and MODIS LST COGs are used only for channels they directly
support. Unsupported channels are generated from the existing calibrated
profiles and explicitly marked CALIBRATED_FALLBACK. Planetary target channels
remain fallbacks until a practical, region-subset PDS raster endpoint is wired
in; the USGS global LOLA/MOLA mosaics are uncompressed strip TIFFs, not COGs.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _tile_utils import CHANNEL_NAMES, NODATA, synthesize_geophysical_grid  # noqa: E402
from earth_ingest import CURATED_14_SITES, REGION_PROFILES  # noqa: E402
from moon_mars_ingest import TARGETS, TARGET_PROFILES  # noqa: E402

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
DOMAINS = tuple(CHANNEL_NAMES)
UA = "CrossPlanetaryAnalogEngine/2.0 phase2-ingest"
SAS_TOKEN_CACHE: dict[str, str] = {}


def http_json(url: str, timeout: float = 25.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/geo+json, application/json", "User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            time.sleep(float(exc.headers.get("Retry-After", 2 * (attempt + 1))))


def stac_items(collection: str, bbox: tuple[float, float, float, float], limit: int = 16,
               datetime: str | None = None) -> list[dict]:
    params = {"collections": collection, "bbox": ",".join(f"{v:.7f}" for v in bbox), "limit": str(limit)}
    if datetime:
        params["datetime"] = datetime
    data = http_json(STAC + "?" + urllib.parse.urlencode(params))
    return data.get("features", [])


def sign_asset(href: str) -> str:
    parsed = urllib.parse.urlsplit(href)
    path_parts = parsed.path.strip("/").split("/")
    cache_key = parsed.netloc + "/" + (path_parts[0] if path_parts else "")
    if cache_key in SAS_TOKEN_CACHE:
        return href + ("&" if parsed.query else "?") + SAS_TOKEN_CACHE[cache_key]
    signed = http_json(SIGN + "?" + urllib.parse.urlencode({"href": href}))
    token = urllib.parse.urlsplit(signed["href"]).query
    if token:
        SAS_TOKEN_CACHE[cache_key] = token
    return signed["href"]


def geographic_extent(lat: float, lon: float, h: int, w: int, body: str) -> tuple[float, float, float, float]:
    radii = {"earth": 6371000.0, "moon": 1737400.0, "mars": 3389500.0}
    half_lat = max(0.08, math.degrees((h * 30.0 * 0.65) / radii[body]))
    cos_lat = max(0.15, math.cos(math.radians(max(-85.0, min(85.0, lat)))))
    half_lon = max(0.08, half_lat / cos_lat)
    west, east = lon - half_lon, lon + half_lon
    if body == "earth":
        west = ((west + 180.0) % 360.0) - 180.0
        east = ((east + 180.0) % 360.0) - 180.0
        if west > east:  # current curated Earth sites do not cross the antimeridian
            raise ValueError("antimeridian-spanning Earth tile is not supported")
    return west, lat - half_lat, east, lat + half_lat


def read_cog_grid(href: str, bbox: tuple[float, float, float, float], shape: tuple[int, int],
                  resampling_name: str = "bilinear", sas_token: str | None = None) -> tuple[np.ma.MaskedArray, dict]:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT

    resampling = Resampling.bilinear if resampling_name == "bilinear" else Resampling.nearest
    if sas_token:
        signed = href + ("&" if "?" in href else "?") + sas_token
    else:
        signed = sign_asset(href)
    transform = from_bounds(*bbox, shape[1], shape[0])
    with rasterio.open(signed) as src:
        scale = float(src.scales[0]) if src.scales else 1.0
        offset = float(src.offsets[0]) if src.offsets else 0.0
        with WarpedVRT(src, crs="EPSG:4326", transform=transform,
                       width=shape[1], height=shape[0], resampling=resampling,
                       nodata=NODATA) as vrt:
            data = vrt.read(1, masked=True).astype(np.float32)
        tags = src.tags()
        info = {"crs": str(src.crs), "dtype": src.dtypes[0], "scale": scale,
                "offset": offset, "nodata": src.nodata, "tags": tags}
    if scale != 1.0 or offset != 0.0:
        data = data * scale + offset
    return data, info


def read_copdem(lat: float, lon: float, bbox: tuple[float, float, float, float],
                shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    items = stac_items("cop-dem-glo-30", bbox, limit=20)
    out = np.full(shape, NODATA, dtype=np.float32)
    valid_out = np.zeros(shape, dtype=bool)
    used: list[dict] = []
    errors: list[str] = []
    for item in items:
        asset = item.get("assets", {}).get("data")
        if not asset or not asset.get("href"):
            continue
        try:
            grid, info = read_cog_grid(asset["href"], bbox, shape)
            vals = np.asarray(grid.data, dtype=np.float32)
            valid = ~np.ma.getmaskarray(grid) & np.isfinite(vals) & (vals != NODATA)
            take = valid & ~valid_out
            out[take] = vals[take]
            valid_out |= valid
            used.append({"item_id": item.get("id"), "collection": item.get("collection"),
                         "asset_key": "data", "href": asset["href"], "crs": info["crs"]})
            if valid_out.all():
                break
        except Exception as exc:
            errors.append(f"{item.get('id')}: {type(exc).__name__}: {exc}")
    if errors:
        print(json.dumps({"event": "copdem_asset_errors", "errors": errors[:4]}), flush=True)
    return out, valid_out, used


def derive_topography(dem: np.ndarray, valid: np.ndarray, fallback: np.ndarray,
                      bbox: tuple[float, float, float, float], lat: float,
                      profile: dict) -> tuple[np.ndarray, list[dict]]:
    h, w = dem.shape
    west, south, east, north = bbox
    dx_m = max(1e-6, math.radians((east - west) / w) * 6371000.0 * max(0.15, math.cos(math.radians(lat))))
    dy_m = max(1e-6, math.radians((north - south) / h) * 6371000.0)
    fallback_elev = fallback[0]
    elev_fill = float(np.mean(dem[valid])) if valid.any() else float(np.mean(fallback_elev))
    z = np.where(valid, dem, elev_fill).astype(np.float32)
    dy, dx = np.gradient(z, dy_m, dx_m)
    grad = np.hypot(dx, dy)
    slope = np.clip(np.degrees(np.arctan(grad)), 0.0, 65.0)
    aspect = (np.degrees(np.arctan2(-dx, dy)) + 360.0) % 360.0
    tri = np.abs(dx) * 30.0 + np.abs(dy) * 30.0 + float(profile.get("tri_bias", 12.0))
    tpi = z - elev_fill
    d2y, d2x = np.gradient(grad, dy_m, dx_m)
    curvature = np.clip(d2x + d2y, -0.05, 0.05)
    derived = np.stack([z, slope, aspect, tri, tpi, curvature]).astype(np.float32)
    merged = fallback.copy()
    merged[:, valid] = derived[:, valid]
    names = CHANNEL_NAMES["topography"]
    coverage = float(valid.mean())
    prov = [{"channel": name, "source_type": "REAL_ORBITAL_COG" if coverage > 0 else "CALIBRATED_FALLBACK",
             "product": "Copernicus DEM GLO-30", "collection": "cop-dem-glo-30",
             "asset_key": "data", "derivation": derivation,
             "valid_fraction": coverage, "fallback_fraction": 1.0 - coverage,
             "fallback_reason": None if coverage > 0 else "COG query/read returned no valid pixels"}
            for name, derivation in zip(names, [
                "Copernicus DEM elevation resampled to the source grid",
                "slope in degrees derived from the elevation surface",
                "aspect derived from the elevation gradient",
                "terrain ruggedness proxy derived from the elevation gradient",
                "elevation minus tile mean",
                "gradient curvature proxy derived from the elevation surface",
            ])]
    return merged, prov


def read_modis_lst(lat: float, lon: float, bbox: tuple[float, float, float, float],
                   shape: tuple[int, int]) -> tuple[dict[str, np.ndarray], dict | None]:
    try:
        items = stac_items("modis-11A1-061", bbox, limit=16,
                           datetime="2024-01-01T00:00:00Z/2024-12-31T23:59:59Z")
    except Exception as exc:
        print(json.dumps({"event": "modis_search_error", "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        return {}, None
    sas_token = None
    for candidate in items:
        href = candidate.get("assets", {}).get("LST_Day_1km", {}).get("href")
        if href:
            sign_asset(href)
            parsed_href = urllib.parse.urlsplit(href)
            sas_token = SAS_TOKEN_CACHE.get(parsed_href.netloc + "/" + parsed_href.path.strip("/").split("/")[0], "")
            break
    if not sas_token:
        return {}, None
    for item in items:
        assets = item.get("assets", {})
        required = ("LST_Day_1km", "LST_Night_1km", "QC_Day", "QC_Night")
        if not all(k in assets for k in required):
            continue
        try:
            arrays: dict[str, np.ndarray] = {}
            infos = {}
            for key in required[:2]:
                grid, info = read_cog_grid(assets[key]["href"], bbox, shape,
                                           "nearest" if key.startswith("QC_") else "bilinear", sas_token)
                arrays[key] = np.asarray(grid.data)
                arrays[key + "_valid"] = ~np.ma.getmaskarray(grid)
                infos[key] = info
            # read_cog_grid applies the raster band's 0.02 scale, so these arrays are Kelvin.
            day_raw, night_raw = arrays["LST_Day_1km"], arrays["LST_Night_1km"]
            day_data = arrays["LST_Day_1km_valid"] & (day_raw >= 150.0) & (day_raw <= 400.0)
            night_data = arrays["LST_Night_1km_valid"] & (night_raw >= 150.0) & (night_raw <= 400.0)
            if not day_data.any() and not night_data.any():
                continue
            for key in required[2:]:
                grid, info = read_cog_grid(assets[key]["href"], bbox, shape, "nearest", sas_token)
                arrays[key] = np.asarray(grid.data)
                arrays[key + "_valid"] = ~np.ma.getmaskarray(grid)
                infos[key] = info
            day_qc = arrays["QC_Day"].astype(np.uint16)
            night_qc = arrays["QC_Night"].astype(np.uint16)
            # MODIS mandatory QA 00=good and 01=other quality; 10/11 are rejected.
            day_good = day_data & arrays["QC_Day_valid"] & ((day_qc & 3) <= 1)
            night_good = night_data & arrays["QC_Night_valid"] & ((night_qc & 3) <= 1)
            if not day_good.any() and not night_good.any():
                continue
            arrays["day_k"] = day_raw.astype(np.float32)
            arrays["night_k"] = night_raw.astype(np.float32)
            arrays["day_good"] = day_good
            arrays["night_good"] = night_good
            return arrays, {"item_id": item.get("id"), "collection": item.get("collection"),
                            "assets": list(required), "day_valid_fraction": float(day_good.mean()),
                            "night_valid_fraction": float(night_good.mean()),
                            "temporal_note": "one daily Aqua observation; day/night are proxies, not annual extrema"}
        except Exception as exc:
            print(json.dumps({"event": "modis_item_error", "item": item.get("id"),
                              "error": f"{type(exc).__name__}: {exc}"}), flush=True)
    return {}, None


def make_earth_channels(region: dict, domain: str, shape: tuple[int, int],
                        data_dir: Path, use_thermal: bool) -> tuple[np.ndarray, dict]:
    rid = region["id"]
    lat, lon = float(region["lat"]), ((float(region["lon"]) + 180) % 360) - 180
    profile = REGION_PROFILES.get(rid, {}).get(domain, {})
    fallback = synthesize_geophysical_grid(rid, "earth", domain, shape, profile).astype(np.float32)
    bbox = geographic_extent(lat, lon, *shape, "earth")
    provenance = []
    used_sources: list[str] = []
    acquisition = "none (calibrated geophysical fallback)"

    if domain == "topography":
        dem, valid, used = read_copdem(lat, lon, bbox, shape)
        channels, provenance = derive_topography(dem, valid, fallback, bbox, lat, profile)
        for source in used:
            used_sources.append(f"Copernicus DEM GLO-30:{source['item_id']}")
            for prov in provenance:
                if prov["source_type"] == "REAL_ORBITAL_COG":
                    prov.setdefault("items", []).append(source["item_id"])
        if used:
            acquisition = "static Copernicus DEM GLO-30; STAC item IDs in channel provenance"
    elif domain == "thermal_illumination" and use_thermal:
        arrays, item = read_modis_lst(lat, lon, bbox, shape)
        channels = fallback.copy()
        names = CHANNEL_NAMES[domain]
        if item:
            day, night = arrays["day_k"], arrays["night_k"]
            day_good, night_good = arrays["day_good"], arrays["night_good"]
            channels[0, day_good] = day[day_good]
            channels[1, night_good] = night[night_good]
            both = day_good & night_good
            delta = day - night
            channels[2, both] = delta[both]
            used_sources.append(f"MODIS/Aqua MYD11A1 COG:{item['item_id']}")
            for i, name in enumerate(names):
                valid_fraction = [float(day_good.mean()), float(night_good.mean()), float(both.mean()), 0.0, 0.0][i]
                provenance.append({"channel": name,
                    "source_type": "REAL_ORBITAL_COG" if valid_fraction > 0 else "CALIBRATED_FALLBACK",
                    "product": "MODIS/Aqua MYD11A1.061", "collection": item["collection"],
                    "item_id": item["item_id"], "assets": item["assets"],
                    "derivation": ["daily daytime land-surface temperature; proxy for T_max",
                                   "daily nighttime land-surface temperature; proxy for T_min",
                                   "daily daytime minus nighttime land-surface temperature",
                                   "calibrated albedo profile; MODIS LST does not measure this channel",
                                   "calibrated fallback; not calculated from the mixed day/night and albedo inputs"][i],
                    "valid_fraction": valid_fraction, "fallback_fraction": 1.0 - valid_fraction,
                    "quality": "MODIS mandatory QA bits 0-1 equal good; fill values excluded"})
            acquisition = f"MODIS Aqua daily product {item['item_id']}"
        else:
            provenance = [{"channel": n, "source_type": "CALIBRATED_FALLBACK",
                           "reason": "No clear, quality-approved MODIS LST COG found for tile extent"}
                          for n in names]
        return channels, {"provenance": provenance, "sources": used_sources, "acquisition": acquisition,
                          "bbox": bbox, "lat": lat, "lon": lon}
    else:
        channels = fallback
        provenance = [{"channel": name, "source_type": "CALIBRATED_FALLBACK",
                       "reason": "No direct, scientifically appropriate orbital raster source is wired for this channel"}
                      for name in CHANNEL_NAMES[domain]]

    return channels, {"provenance": provenance, "sources": used_sources, "acquisition": acquisition,
                      "bbox": bbox, "lat": lat, "lon": lon}


def make_target_channels(target_id: str, info: dict, domain: str, shape: tuple[int, int]) -> tuple[np.ndarray, dict]:
    body = info["body"].lower()
    channels = synthesize_geophysical_grid(target_id, body, domain, shape,
                                           TARGET_PROFILES.get(target_id, {}).get(domain)).astype(np.float32)
    names = CHANNEL_NAMES[domain]
    provenance = [{"channel": name, "source_type": "CALIBRATED_FALLBACK",
                   "reason": "Regional PDS/ODE raster subset has not yet been acquired and standardized"}
                  for name in names]
    return channels, {"provenance": provenance, "sources": [],
                      "acquisition": "none (calibrated geophysical fallback)",
                      "bbox": geographic_extent(info["lat"], info["lon"], *shape, body),
                      "lat": float(info["lat"]), "lon": float(info["lon"])}


def stage_one(entity_id: str, body: str, domain: str, channels: np.ndarray,
              meta: dict, shape: tuple[int, int], root: Path) -> dict:
    raw_dir = root / "raw" / body
    raw_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{entity_id}_{domain}"
    npy = raw_dir / f"{stem}.npy"
    meta_path = raw_dir / f"{stem}.json"
    np.save(npy, np.ascontiguousarray(channels, dtype=np.float32))
    lat, lon = meta["lat"], meta["lon"]
    bbox = meta["bbox"]
    west, south, east, north = bbox
    lats = np.linspace(north, south, shape[0]).tolist()  # source rows are north-to-south
    lons = np.linspace(west, east, shape[1]).tolist()
    raw_meta = {
        "tile_id": stem, "entity_id": entity_id,
        "lats": lats, "lons": lons, "base_resolution_m": 30.0,
        "channel_names": CHANNEL_NAMES[domain],
        "channel_provenance": meta["provenance"],
        "source_datasets": meta["sources"],
        "acquisition_window": meta["acquisition"],
        "quality_mask_stats": {
            "valid_fraction": round(float(np.mean(np.all(channels != NODATA, axis=0))), 6),
            "channel_provenance_record_count": len(meta["provenance"]),
            "all_channels_real": all(p.get("source_type") == "REAL_ORBITAL_COG" for p in meta["provenance"]),
        },
    }
    meta_path.write_text(json.dumps(raw_meta, indent=2), encoding="utf-8")
    return {"tile_id": stem, "body": body, "domain": domain,
            "lat0": lat, "lon0": lon, "shape": list(shape),
            "src_npy": str(npy.resolve()), "src_meta": str(meta_path.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data_lake/phase2", help="output under scratch copy")
    parser.add_argument("--shape", type=int, default=512)
    parser.add_argument("--limit-entities", type=int, default=0, help="smoke-check only the first N entities per body")
    parser.add_argument("--earth-only", action="store_true")
    parser.add_argument("--targets-only", action="store_true")
    parser.add_argument("--skip-thermal", action="store_true")
    parser.add_argument("--domain", action="append", choices=DOMAINS,
                        help="process only selected domain(s); repeat for multiple domains")
    args = parser.parse_args()
    shape = (args.shape, args.shape)
    if args.shape < 64 or args.shape & (args.shape - 1):
        parser.error("--shape must be a power of two >= 64")
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    tiles = []
    started = time.time()
    do_earth = not args.targets_only
    do_targets = not args.earth_only
    domains = args.domain or DOMAINS

    if do_earth:
        regions = CURATED_14_SITES[:args.limit_entities or None]
        for region in regions:
            for domain in domains:
                try:
                    channels, meta = make_earth_channels(region, domain, shape, out_root, not args.skip_thermal)
                    entry = stage_one(region["id"], "earth", domain, channels, meta, shape, out_root)
                    tiles.append(entry)
                    print(json.dumps({"event": "staged", "body": "earth", "tile_id": entry["tile_id"],
                                      "channels": len(meta["provenance"]),
                                      "real_channels": sum(p.get("source_type") == "REAL_ORBITAL_COG" for p in meta["provenance"]),
                                      "sources": meta["sources"]}), flush=True)
                except Exception as exc:
                    print(json.dumps({"event": "tile_error", "body": "earth", "entity": region["id"],
                                      "domain": domain, "error": f"{type(exc).__name__}: {exc}"}), flush=True)
                    channels = synthesize_geophysical_grid(region["id"], "earth", domain, shape,
                        REGION_PROFILES.get(region["id"], {}).get(domain)).astype(np.float32)
                    fallback_meta = [{"channel": name, "source_type": "CALIBRATED_FALLBACK",
                                      "reason": f"Data request or standardization failed: {type(exc).__name__}: {exc}"}
                                     for name in CHANNEL_NAMES[domain]]
                    meta = {"provenance": fallback_meta, "sources": [],
                            "acquisition": "none (calibrated geophysical fallback)",
                            "bbox": geographic_extent(float(region["lat"]), float(region["lon"]), *shape, "earth"),
                            "lat": float(region["lat"]), "lon": ((float(region["lon"]) + 180) % 360) - 180}
                    entry = stage_one(region["id"], "earth", domain, channels, meta, shape, out_root)
                    tiles.append(entry)
                    print(json.dumps({"event": "fallback_staged", "body": "earth",
                                      "tile_id": entry["tile_id"]}), flush=True)

    if do_targets:
        target_items = list(TARGETS.items())[:args.limit_entities or None]
        for tid, info in target_items:
            for domain in domains:
                channels, meta = make_target_channels(tid, info, domain, shape)
                entry = stage_one(tid, info["body"].lower(), domain, channels, meta, shape, out_root)
                tiles.append(entry)
                print(json.dumps({"event": "staged", "body": info["body"].lower(),
                                  "tile_id": entry["tile_id"], "channels": len(meta["provenance"]),
                                  "real_channels": 0, "sources": []}), flush=True)

    manifest = out_root / "phase2_processor_manifest.json"
    manifest.write_text(json.dumps({"tiles": tiles}, indent=2), encoding="utf-8")
    counts = {"earth": sum(t["body"] == "earth" for t in tiles),
              "moon": sum(t["body"] == "moon" for t in tiles),
              "mars": sum(t["body"] == "mars" for t in tiles)}
    print(json.dumps({"result": "staged", "counts": counts, "total": len(tiles),
                      "manifest": str(manifest), "elapsed_seconds": round(time.time() - started, 2)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
