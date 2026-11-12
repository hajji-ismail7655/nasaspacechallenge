"""Earth ingestion pipeline (STAC query + standardized multi-channel .ptile materializer).

Queries NASA Earthdata CMR-STAC / Microsoft Planetary Computer STAC APIs when reachable,
stages multi-channel inputs + manifests compatible with processor/cli.py, and materializes
standardized 5-octave LAEA .ptile tiles into ./data_lake/standardized/earth/.

Offline or when remote COG bands cannot be streamed, falls back deterministically to
geophysically calibrated per-region field synthesis so sweeps execute reliably anywhere.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tile_utils import (  # noqa: E402
    fetch_json,
    materialize_standardized_tile,
    norm_lon_deg,
)

DOMAINS = {
    "topography": ["Copernicus DEM GLO-30"],
    "mineralogy": ["ASTER L1T/Emissivity", "Sentinel-2 MSI"],
    "thermal_illumination": ["NASA ECOSTRESS", "MODIS MOD11A1"],
    "granular_aeolian": ["Sentinel-1 SAR GRD", "MODIS AOD", "SoilGrids"],
    "volatiles_subsurface": ["SMAP L3", "ESA CCI Permafrost"],
}

STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
STAC_COLLECTIONS = {
    "topography": "cop-dem-glo-30",
    "mineralogy": "sentinel-2-l2a",
    "thermal_illumination": "modis-11A1-061",
    "granular_aeolian": "sentinel-1-grd",
    "volatiles_subsurface": "modis-11A1-061",
}

# 10 novel targets (REPORT.md Sec 13.1) + 4 known-analog calibration controls
CURATED_14_SITES = [
    {"id": "earth_anti_atlas", "name": "Anti-Atlas / Draa Hammada, Morocco", "lat": 30.5, "lon": -8.0, "is_known_analog": False, "domain_focus": ["topography", "mineralogy"]},
    {"id": "earth_mistastin", "name": "Mistastin Lake, Canada", "lat": 55.88, "lon": -63.31, "is_known_analog": False, "domain_focus": ["topography", "mineralogy"]},
    {"id": "earth_qaidam", "name": "Qaidam Basin, China", "lat": 37.5, "lon": 95.0, "is_known_analog": False, "domain_focus": ["mineralogy", "volatiles_subsurface"]},
    {"id": "earth_afar", "name": "Afar Depression, Ethiopia", "lat": 12.0, "lon": 41.5, "is_known_analog": False, "domain_focus": ["mineralogy", "topography", "volatiles_subsurface"]},
    {"id": "earth_undara", "name": "Undara Lava Tubes, Australia", "lat": -18.2, "lon": 144.6, "is_known_analog": False, "domain_focus": ["volatiles_subsurface", "topography"]},
    {"id": "earth_lut_desert", "name": "Lut Desert, Iran", "lat": 30.5, "lon": 59.0, "is_known_analog": False, "domain_focus": ["thermal_illumination", "granular_aeolian"]},
    {"id": "earth_tanezrouft", "name": "Tanezrouft Basin, Algeria/Mali", "lat": 24.0, "lon": 3.0, "is_known_analog": False, "domain_focus": ["topography", "granular_aeolian"]},
    {"id": "earth_yakutia", "name": "Yakutia Thermokarst, Siberia", "lat": 66.0, "lon": 129.0, "is_known_analog": False, "domain_focus": ["volatiles_subsurface", "topography"]},
    {"id": "earth_kumtagh", "name": "Kumtagh Feather Dunes, China", "lat": 40.0, "lon": 92.0, "is_known_analog": False, "domain_focus": ["granular_aeolian"]},
    {"id": "earth_jebel_saghro", "name": "Jebel Saghro, Morocco", "lat": 31.18, "lon": -5.75, "is_known_analog": False, "domain_focus": ["mineralogy", "topography"]},
    # 4 calibration controls placed inside Datasets/known_analogs_mask.geojson buffers
    {"id": "earth_atacama_core", "name": "Atacama core (known analog)", "lat": -24.0, "lon": -69.5, "is_known_analog": True, "domain_focus": ["mineralogy"]},
    {"id": "earth_haughton", "name": "Haughton Crater (known analog)", "lat": 75.4, "lon": -89.7, "is_known_analog": True, "domain_focus": ["topography"]},
    {"id": "earth_iceland", "name": "Iceland highlands (known analog)", "lat": 64.5, "lon": -19.0, "is_known_analog": True, "domain_focus": ["topography", "mineralogy"]},
    {"id": "earth_mojave", "name": "Mojave (known analog)", "lat": 35.0, "lon": -116.0, "is_known_analog": True, "domain_focus": ["granular_aeolian"]},
]

# Geophysical regional calibration hints matching BestAlgo v2.0 physical scales
REGION_PROFILES = {
    "earth_anti_atlas": {
        "topography": {"elev_mean": 1150.0, "elev_amp": 520.0, "slope_gain": 1.35, "tri_bias": 22.0},
        "mineralogy": {"mineral_means": [0.34, 0.22, 0.28, 0.04, 0.05, 0.24, 0.14, 0.03]},
        "thermal_illumination": {"T_max": 322.0, "T_min": 274.0, "albedo": 0.16},
        "granular_aeolian": {"granular_means": [0.32, 0.26, 150.0, 0.16, 85.0]},
        "volatiles_subsurface": {"volatile_means": [0.8, 4.5, 2.9, 18.0, 0.6]},
    },
    "earth_mistastin": {
        "topography": {"elev_mean": 480.0, "elev_amp": 360.0, "slope_gain": 1.5, "tri_bias": 28.0},
        "mineralogy": {"mineral_means": [0.18, 0.12, 0.56, 0.05, 0.02, 0.10, 0.16, 0.12]},
        "thermal_illumination": {"T_max": 286.0, "T_min": 252.0, "albedo": 0.28},
        "granular_aeolian": {"granular_means": [0.24, 0.34, 180.0, 0.05, 45.0]},
        "volatiles_subsurface": {"volatile_means": [4.2, 2.2, 3.4, 24.0, 0.8]},
    },
    "earth_qaidam": {
        "topography": {"elev_mean": 2850.0, "elev_amp": 240.0, "slope_gain": 0.85, "tri_bias": 14.0},
        "mineralogy": {"mineral_means": [0.18, 0.20, 0.14, 0.36, 0.44, 0.26, 0.34, 0.08]},
        "thermal_illumination": {"T_max": 304.0, "T_min": 256.0, "albedo": 0.27},
        "granular_aeolian": {"granular_means": [0.26, 0.14, 110.0, 0.22, 120.0]},
        "volatiles_subsurface": {"volatile_means": [3.6, 1.4, 3.8, 12.0, 0.5]},
    },
    "earth_afar": {
        "topography": {"elev_mean": 180.0, "elev_amp": 390.0, "slope_gain": 1.25, "tri_bias": 20.0},
        "mineralogy": {"mineral_means": [0.38, 0.34, 0.20, 0.26, 0.38, 0.30, 0.18, 0.07]},
        "thermal_illumination": {"T_max": 328.0, "T_min": 292.0, "albedo": 0.14},
        "granular_aeolian": {"granular_means": [0.36, 0.28, 130.0, 0.24, 70.0]},
        "volatiles_subsurface": {"volatile_means": [1.8, 2.8, 4.1, 35.0, 1.4]},
    },
    "earth_undara": {
        "topography": {"elev_mean": 460.0, "elev_amp": 180.0, "slope_gain": 1.15, "tri_bias": 16.0},
        "mineralogy": {"mineral_means": [0.40, 0.30, 0.26, 0.10, 0.04, 0.24, 0.10, 0.14]},
        "thermal_illumination": {"T_max": 310.0, "T_min": 284.0, "albedo": 0.13},
        "granular_aeolian": {"granular_means": [0.34, 0.32, 165.0, 0.08, 40.0]},
        "volatiles_subsurface": {"volatile_means": [2.2, 3.5, 4.4, -38.0, 3.4]},
    },
    "earth_lut_desert": {
        "topography": {"elev_mean": 310.0, "elev_amp": 150.0, "slope_gain": 0.75, "tri_bias": 10.0},
        "mineralogy": {"mineral_means": [0.30, 0.22, 0.18, 0.14, 0.22, 0.28, 0.20, 0.01]},
        "thermal_illumination": {"T_max": 338.0, "T_min": 280.0, "albedo": 0.15},
        "granular_aeolian": {"granular_means": [0.29, 0.18, 135.0, 0.26, 155.0]},
        "volatiles_subsurface": {"volatile_means": [0.5, 5.0, 2.5, 6.0, 0.4]},
    },
    "earth_tanezrouft": {
        "topography": {"elev_mean": 410.0, "elev_amp": 95.0, "slope_gain": 0.55, "tri_bias": 7.0},
        "mineralogy": {"mineral_means": [0.24, 0.16, 0.32, 0.06, 0.08, 0.22, 0.24, 0.01]},
        "thermal_illumination": {"T_max": 330.0, "T_min": 281.0, "albedo": 0.24},
        "granular_aeolian": {"granular_means": [0.25, 0.20, 120.0, 0.28, 130.0]},
        "volatiles_subsurface": {"volatile_means": [0.4, 5.2, 2.4, 5.0, 0.3]},
    },
    "earth_yakutia": {
        "topography": {"elev_mean": 220.0, "elev_amp": 120.0, "slope_gain": 0.65, "tri_bias": 9.0},
        "mineralogy": {"mineral_means": [0.16, 0.12, 0.22, 0.24, 0.06, 0.14, 0.18, 0.18]},
        "thermal_illumination": {"T_max": 284.0, "T_min": 236.0, "albedo": 0.34},
        "granular_aeolian": {"granular_means": [0.22, 0.08, 75.0, 0.05, 35.0]},
        "volatiles_subsurface": {"volatile_means": [12.5, 0.75, 5.2, 10.0, 0.9]},
    },
    "earth_kumtagh": {
        "topography": {"elev_mean": 1100.0, "elev_amp": 165.0, "slope_gain": 0.90, "tri_bias": 14.0},
        "mineralogy": {"mineral_means": [0.28, 0.22, 0.22, 0.08, 0.12, 0.22, 0.20, 0.02]},
        "thermal_illumination": {"T_max": 318.0, "T_min": 268.0, "albedo": 0.20},
        "granular_aeolian": {"granular_means": [0.35, 0.09, 175.0, 0.22, 185.0]},
        "volatiles_subsurface": {"volatile_means": [0.7, 4.0, 2.7, 8.0, 0.5]},
    },
    "earth_jebel_saghro": {
        "topography": {"elev_mean": 1520.0, "elev_amp": 480.0, "slope_gain": 1.30, "tri_bias": 24.0},
        "mineralogy": {"mineral_means": [0.42, 0.30, 0.24, 0.06, 0.05, 0.26, 0.14, 0.04]},
        "thermal_illumination": {"T_max": 316.0, "T_min": 270.0, "albedo": 0.14},
        "granular_aeolian": {"granular_means": [0.33, 0.27, 145.0, 0.14, 75.0]},
        "volatiles_subsurface": {"volatile_means": [0.9, 3.8, 3.1, 20.0, 0.9]},
    },
    "earth_atacama_core": {
        "topography": {"elev_mean": 2350.0, "elev_amp": 310.0, "slope_gain": 1.0, "tri_bias": 15.0},
        "mineralogy": {"mineral_means": [0.20, 0.15, 0.20, 0.28, 0.42, 0.28, 0.30, 0.01]},
        "thermal_illumination": {"T_max": 308.0, "T_min": 265.0, "albedo": 0.25},
        "granular_aeolian": {"granular_means": [0.27, 0.16, 120.0, 0.15, 100.0]},
        "volatiles_subsurface": {"volatile_means": [0.6, 4.2, 2.6, 10.0, 0.5]},
    },
    "earth_haughton": {
        "topography": {"elev_mean": 210.0, "elev_amp": 290.0, "slope_gain": 1.25, "tri_bias": 19.0},
        "mineralogy": {"mineral_means": [0.16, 0.10, 0.30, 0.18, 0.12, 0.12, 0.34, 0.04]},
        "thermal_illumination": {"T_max": 276.0, "T_min": 240.0, "albedo": 0.32},
        "granular_aeolian": {"granular_means": [0.28, 0.28, 160.0, 0.04, 55.0]},
        "volatiles_subsurface": {"volatile_means": [7.5, 0.95, 4.2, 16.0, 0.8]},
    },
    "earth_iceland": {
        "topography": {"elev_mean": 680.0, "elev_amp": 410.0, "slope_gain": 1.30, "tri_bias": 21.0},
        "mineralogy": {"mineral_means": [0.44, 0.36, 0.26, 0.14, 0.08, 0.24, 0.12, 0.06]},
        "thermal_illumination": {"T_max": 284.0, "T_min": 262.0, "albedo": 0.13},
        "granular_aeolian": {"granular_means": [0.36, 0.24, 155.0, 0.09, 110.0]},
        "volatiles_subsurface": {"volatile_means": [5.5, 1.5, 4.0, 22.0, 1.8]},
    },
    "earth_mojave": {
        "topography": {"elev_mean": 720.0, "elev_amp": 240.0, "slope_gain": 0.95, "tri_bias": 13.0},
        "mineralogy": {"mineral_means": [0.26, 0.18, 0.24, 0.12, 0.14, 0.22, 0.22, 0.04]},
        "thermal_illumination": {"T_max": 322.0, "T_min": 278.0, "albedo": 0.22},
        "granular_aeolian": {"granular_means": [0.31, 0.14, 165.0, 0.16, 160.0]},
        "volatiles_subsurface": {"volatile_means": [0.7, 3.8, 2.6, 8.0, 0.5]},
    },
}


def query_stac_metadata(region, domain, offline=False):
    """Attempt live STAC metadata lookup; returns source_datasets list cleanly."""
    base_sources = list(DOMAINS.get(domain, []))
    if offline:
        return base_sources
    lon = norm_lon_deg(region["lon"])
    lat = float(region["lat"])
    bbox = f"{lon - 0.15:.3f},{lat - 0.15:.3f},{lon + 0.15:.3f},{lat + 0.15:.3f}"
    col = STAC_COLLECTIONS.get(domain, "cop-dem-glo-30")
    data = fetch_json(
        STAC_SEARCH_URL,
        params={"collections": col, "bbox": bbox, "limit": 1},
        timeout=2.5,
    )
    if data and isinstance(data.get("features"), list) and data["features"]:
        feat = data["features"][0]
        item_id = feat.get("id")
        if item_id:
            base_sources.append(f"STAC:{col}/{item_id}")
    return base_sources


def build_manifest(region, data_lake="./data_lake"):
    """Build declarative STAC manifest entries for a single Earth region."""
    entries = []
    for d, srcs in DOMAINS.items():
        for s in srcs:
            entries.append({
                "domain": d,
                "source": s,
                "region": region["id"],
                "uri": f"{data_lake}/{region['id']}/{d}/",
                "format": "GeoTIFF/STAC",
            })
    return entries


def resolve_regions(regions_path, subset="curated14"):
    """Load curated 14 regions (Sec 13.1 novel + 4 known-analog controls) or full candidate list."""
    by_id = {r["id"]: dict(r) for r in CURATED_14_SITES}
    if regions_path and os.path.exists(regions_path):
        with open(regions_path, encoding="utf-8") as f:
            raw_list = json.load(f).get("earth_candidate_regions", [])
        if subset == "all":
            for r in raw_list:
                rid = r["id"]
                if rid not in by_id:
                    entry = dict(r)
                    entry["lon"] = norm_lon_deg(entry["lon"])
                    entry["is_known_analog"] = "known analog" in entry.get("name", "").lower()
                    by_id[rid] = entry
    return list(by_id.values())


def main():
    ap = argparse.ArgumentParser(description="Earth ingestion & LAEA .ptile materializer")
    ap.add_argument("--regions", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifests", "earth_candidates.json"))
    ap.add_argument("--data-lake", default="./data_lake")
    ap.add_argument("--out", default="", help="Optional path for legacy declarative ingest manifest")
    ap.add_argument("--subset", choices=["curated14", "all"], default="curated14")
    ap.add_argument("--shape", type=int, default=128, help="Square base raster dimension (power of 2 >= 64)")
    ap.add_argument("--res", type=float, default=30.0)
    ap.add_argument("--offline", action="store_true", help="Skip network STAC lookups")
    ap.add_argument("--no-materialize", action="store_true", help="Only write manifests without .ptile generation")
    ap.add_argument("--main-repo", default="", help="Optional path to main checkout containing processor/")
    args = ap.parse_args()

    regions = resolve_regions(args.regions, subset=args.subset)
    manifest_dir = os.path.join(args.data_lake, "manifests")
    std_dir = os.path.join(args.data_lake, "standardized", "earth")
    raw_dir = os.path.join(args.data_lake, "raw_staging", "earth")
    os.makedirs(manifest_dir, exist_ok=True)

    out_entries = []
    cli_tiles = []
    for r in regions:
        out_entries.extend(build_manifest(r, data_lake=args.data_lake))

    manifest_path = args.out or os.path.join(manifest_dir, "earth_ingest_manifest.json")
    os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"entries": out_entries, "count": len(out_entries), "regions": len(regions)}, f, indent=2)

    materialized = 0
    if not args.no_materialize:
        shape_hw = (args.shape, args.shape)
        for r in regions:
            rid = r["id"]
            prof = REGION_PROFILES.get(rid, {})
            for domain in DOMAINS:
                sources = query_stac_metadata(r, domain, offline=args.offline)
                info = materialize_standardized_tile(
                    entity_id=rid,
                    body="earth",
                    domain=domain,
                    lat0=r["lat"],
                    lon0=r["lon"],
                    std_out_dir=std_dir,
                    raw_out_dir=raw_dir,
                    shape_hw=shape_hw,
                    base_res=args.res,
                    num_octaves=5,
                    source_datasets=sources,
                    profile_hints=prof.get(domain),
                    main_repo=args.main_repo or None,
                )
                info["name"] = r.get("name", rid)
                info["is_known_analog"] = bool(r.get("is_known_analog", False))
                cli_tiles.append(info)
                materialized += 1

        cli_manifest_path = os.path.join(manifest_dir, "earth_cli_manifest.json")
        with open(cli_manifest_path, "w", encoding="utf-8") as f:
            json.dump({"tiles": cli_tiles, "regions": regions}, f, indent=2)

    print(json.dumps({
        "regions": len(regions),
        "manifest_entries": len(out_entries),
        "materialized_tiles": materialized,
        "standardized_dir": std_dir,
    }))


if __name__ == "__main__":
    main()
