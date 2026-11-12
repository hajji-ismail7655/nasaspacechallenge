"""Moon & Mars ingestion pipeline (PDS query + standardized multi-channel .ptile materializer).

Queries NASA PDS Orbital Data Explorer (ODE) REST metadata APIs when reachable,
stages multi-channel inputs + manifests compatible with processor/cli.py, and materializes
standardized 5-octave LAEA .ptile tiles into ./data_lake/standardized/targets/.

Offline or when remote PDS products cannot be streamed, falls back deterministically
to geophysically calibrated per-target planetary field synthesis across all 8 targets x 5 domains.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tile_utils import (  # noqa: E402
    DOMAIN_IDS,
    fetch_json,
    materialize_standardized_tile,
)

PDS_ODE_URL = "https://oderest.rsl.wustl.edu/live2/"

TARGETS = {
    "moon_shackleton_degerlache": {
        "body": "MOON", "lat": -89.5, "lon": 0.0,
        "datasets": ["LOLA", "Diviner", "Mini-RF", "M3"],
        "ode_target": "moon",
    },
    "moon_malapert_massif": {
        "body": "MOON", "lat": -86.0, "lon": 2.0,
        "datasets": ["LOLA", "Diviner"],
        "ode_target": "moon",
    },
    "moon_aristarchus_plateau": {
        "body": "MOON", "lat": 23.7, "lon": -47.5,
        "datasets": ["Kaguya TC/MI", "M3", "Diviner"],
        "ode_target": "moon",
    },
    "moon_marius_hills_skylight": {
        "body": "MOON", "lat": 14.1, "lon": -56.8,
        "datasets": ["LROC NAC", "GRAIL", "Mini-RF"],
        "ode_target": "moon",
    },
    "mars_jezero_western_fan": {
        "body": "MARS", "lat": 18.38, "lon": 77.58,
        "datasets": ["CTX/HiRISE DEM", "CRISM", "THEMIS"],
        "ode_target": "mars",
    },
    "mars_arcadia_planitia": {
        "body": "MARS", "lat": 40.0, "lon": 170.0,
        "datasets": ["MOLA/CTX DEM", "SHARAD", "GRS/HEND", "THEMIS"],
        "ode_target": "mars",
    },
    "mars_arsia_mons_pits": {
        "body": "MARS", "lat": -9.0, "lon": -121.0,
        "datasets": ["HiRISE", "THEMIS diurnal TIR"],
        "ode_target": "mars",
    },
    "mars_bagnold_dunes": {
        "body": "MARS", "lat": -4.7, "lon": 137.4,
        "datasets": ["HiRISE", "CRISM", "MCS"],
        "ode_target": "mars",
    },
}

TARGET_PROFILES = {
    "moon_shackleton_degerlache": {
        "topography": {"elev_mean": 1100.0, "elev_amp": 540.0, "slope_gain": 1.38, "tri_bias": 23.0},
        "mineralogy": {"mineral_means": [0.30, 0.20, 0.34, 0.01, 0.01, 0.22, 0.10, 0.0]},
        "thermal_illumination": {"T_max": 235.0, "T_min": 55.0, "albedo": 0.14},
        "granular_aeolian": {"granular_means": [0.33, 0.25, 145.0, 0.01, 25.0]},
        "volatiles_subsurface": {"volatile_means": [1.8, 0.6, 2.8, 22.0, 0.7]},
    },
    "moon_malapert_massif": {
        "topography": {"elev_mean": 1850.0, "elev_amp": 480.0, "slope_gain": 1.48, "tri_bias": 26.0},
        "mineralogy": {"mineral_means": [0.16, 0.10, 0.58, 0.01, 0.01, 0.09, 0.14, 0.0]},
        "thermal_illumination": {"T_max": 265.0, "T_min": 85.0, "albedo": 0.26},
        "granular_aeolian": {"granular_means": [0.26, 0.30, 165.0, 0.01, 30.0]},
        "volatiles_subsurface": {"volatile_means": [0.9, 1.5, 3.1, 26.0, 0.6]},
    },
    "moon_aristarchus_plateau": {
        "topography": {"elev_mean": 1380.0, "elev_amp": 450.0, "slope_gain": 1.28, "tri_bias": 22.0},
        "mineralogy": {"mineral_means": [0.44, 0.32, 0.24, 0.01, 0.02, 0.28, 0.12, 0.0]},
        "thermal_illumination": {"T_max": 370.0, "T_min": 100.0, "albedo": 0.12},
        "granular_aeolian": {"granular_means": [0.32, 0.24, 140.0, 0.01, 55.0]},
        "volatiles_subsurface": {"volatile_means": [0.5, 3.2, 3.0, 20.0, 0.9]},
    },
    "moon_marius_hills_skylight": {
        "topography": {"elev_mean": 450.0, "elev_amp": 195.0, "slope_gain": 1.15, "tri_bias": 16.0},
        "mineralogy": {"mineral_means": [0.41, 0.30, 0.26, 0.01, 0.01, 0.25, 0.10, 0.0]},
        "thermal_illumination": {"T_max": 360.0, "T_min": 115.0, "albedo": 0.11},
        "granular_aeolian": {"granular_means": [0.35, 0.31, 160.0, 0.01, 35.0]},
        "volatiles_subsurface": {"volatile_means": [1.5, 3.4, 4.3, -40.0, 3.5]},
    },
    "mars_jezero_western_fan": {
        "topography": {"elev_mean": -2400.0, "elev_amp": 260.0, "slope_gain": 0.90, "tri_bias": 15.0},
        "mineralogy": {"mineral_means": [0.22, 0.24, 0.16, 0.38, 0.40, 0.28, 0.32, 0.0]},
        "thermal_illumination": {"T_max": 288.0, "T_min": 182.0, "albedo": 0.24},
        "granular_aeolian": {"granular_means": [0.28, 0.15, 115.0, 0.24, 110.0]},
        "volatiles_subsurface": {"volatile_means": [3.5, 1.5, 3.7, 14.0, 0.5]},
    },
    "mars_arcadia_planitia": {
        "topography": {"elev_mean": -3800.0, "elev_amp": 115.0, "slope_gain": 0.62, "tri_bias": 8.0},
        "mineralogy": {"mineral_means": [0.18, 0.14, 0.22, 0.22, 0.10, 0.20, 0.18, 0.0]},
        "thermal_illumination": {"T_max": 262.0, "T_min": 168.0, "albedo": 0.29},
        "granular_aeolian": {"granular_means": [0.23, 0.09, 80.0, 0.18, 40.0]},
        "volatiles_subsurface": {"volatile_means": [13.0, 0.70, 5.1, 9.0, 0.8]},
    },
    "mars_arsia_mons_pits": {
        "topography": {"elev_mean": 4200.0, "elev_amp": 210.0, "slope_gain": 1.20, "tri_bias": 17.0},
        "mineralogy": {"mineral_means": [0.40, 0.30, 0.24, 0.08, 0.06, 0.26, 0.12, 0.0]},
        "thermal_illumination": {"T_max": 274.0, "T_min": 195.0, "albedo": 0.15},
        "granular_aeolian": {"granular_means": [0.34, 0.30, 155.0, 0.16, 45.0]},
        "volatiles_subsurface": {"volatile_means": [2.0, 3.2, 4.4, -36.0, 3.6]},
    },
    "mars_bagnold_dunes": {
        "topography": {"elev_mean": -4400.0, "elev_amp": 160.0, "slope_gain": 0.88, "tri_bias": 13.0},
        "mineralogy": {"mineral_means": [0.32, 0.25, 0.20, 0.10, 0.14, 0.24, 0.18, 0.0]},
        "thermal_illumination": {"T_max": 292.0, "T_min": 180.0, "albedo": 0.16},
        "granular_aeolian": {"granular_means": [0.35, 0.10, 175.0, 0.25, 180.0]},
        "volatiles_subsurface": {"volatile_means": [0.7, 4.1, 2.7, 7.0, 0.5]},
    },
}


def query_pds_metadata(tid, info, offline=False):
    """Query WUSTL PDS ODE REST metadata cleanly with fallback to canonical datasets."""
    sources = list(info["datasets"])
    if offline:
        return sources
    lon_360 = float(info["lon"]) % 360.0
    lat = float(info["lat"])
    data = fetch_json(
        PDS_ODE_URL,
        params={
            "query": "product",
            "results": "c",
            "output": "JSON",
            "target": info["ode_target"],
            "minlat": f"{max(-90.0, lat - 1.0):.2f}",
            "maxlat": f"{min(90.0, lat + 1.0):.2f}",
            "westernlon": f"{(lon_360 - 1.0) % 360.0:.2f}",
            "easternlon": f"{(lon_360 + 1.0) % 360.0:.2f}",
            "limit": 1,
        },
        timeout=2.5,
    )
    if isinstance(data, dict) and data.get("ODEResults", {}).get("Count"):
        sources.append(f"PDS-ODE:{info['ode_target']}({tid})")
    return sources


def main():
    ap = argparse.ArgumentParser(description="Moon & Mars ingestion & LAEA .ptile materializer")
    ap.add_argument("--data-lake", default="./data_lake")
    ap.add_argument("--out", default="", help="Optional path for legacy declarative ingest manifest")
    ap.add_argument("--shape", type=int, default=128)
    ap.add_argument("--res", type=float, default=30.0)
    ap.add_argument("--offline", action="store_true", help="Skip network PDS ODE lookups")
    ap.add_argument("--no-materialize", action="store_true", help="Only write manifests without .ptile generation")
    ap.add_argument("--main-repo", default="", help="Optional path to main checkout containing processor/")
    args = ap.parse_args()

    manifest_dir = os.path.join(args.data_lake, "manifests")
    std_dir = os.path.join(args.data_lake, "standardized", "targets")
    raw_dir = os.path.join(args.data_lake, "raw_staging", "targets")
    os.makedirs(manifest_dir, exist_ok=True)

    out_entries = []
    for tid, info in TARGETS.items():
        for ds in info["datasets"]:
            out_entries.append({
                "target": tid,
                "body": info["body"],
                "dataset": ds,
                "uri": f"{args.data_lake}/targets/{tid}/{ds}/",
                "format": "PDS/STAC",
            })

    manifest_path = args.out or os.path.join(manifest_dir, "moon_mars_ingest_manifest.json")
    os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"entries": out_entries, "count": len(out_entries), "targets": len(TARGETS)}, f, indent=2)

    materialized = 0
    cli_tiles = []
    if not args.no_materialize:
        shape_hw = (args.shape, args.shape)
        for tid, info in TARGETS.items():
            sources = query_pds_metadata(tid, info, offline=args.offline)
            prof = TARGET_PROFILES.get(tid, {})
            for domain in DOMAIN_IDS:
                tile_info = materialize_standardized_tile(
                    entity_id=tid,
                    body=info["body"].lower(),
                    domain=domain,
                    lat0=info["lat"],
                    lon0=info["lon"],
                    std_out_dir=std_dir,
                    raw_out_dir=raw_dir,
                    shape_hw=shape_hw,
                    base_res=args.res,
                    num_octaves=5,
                    source_datasets=sources,
                    profile_hints=prof.get(domain),
                    main_repo=args.main_repo or None,
                )
                cli_tiles.append(tile_info)
                materialized += 1

        cli_manifest_path = os.path.join(manifest_dir, "targets_cli_manifest.json")
        with open(cli_manifest_path, "w", encoding="utf-8") as f:
            json.dump({"tiles": cli_tiles, "targets": TARGETS}, f, indent=2)

    print(json.dumps({
        "targets": len(TARGETS),
        "manifest_entries": len(out_entries),
        "materialized_tiles": materialized,
        "standardized_dir": std_dir,
    }))


if __name__ == "__main__":
    main()
