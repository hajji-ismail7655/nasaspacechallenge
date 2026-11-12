"""Earth ingestion pipeline (declarative STAC manifest generator).

Pulls from NASA Earthdata / Copernicus / USGS STAC APIs and writes
manifests only (no raw rasters committed). Bulk data lands in ./data_lake/.
"""
import argparse
import json
import os
import hashlib

DOMAINS = {
    "topography": ["Copernicus DEM GLO-30"],
    "mineralogy": ["ASTER L1T/Emissivity", "Sentinel-2 MSI"],
    "thermal_illumination": ["NASA ECOSTRESS", "MODIS MOD11A1"],
    "granular_aeolian": ["Sentinel-1 SAR GRD", "MODIS AOD", "SoilGrids"],
    "volatiles_subsurface": ["SMAP L3", "ESA CCI Permafrost"],
}

def build_manifest(region, data_lake="./data_lake"):
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default="manifests/earth_candidates.json")
    ap.add_argument("--out", default="manifests/earth_ingest_manifest.json")
    args = ap.parse_args()
    regions = json.load(open(args.regions))["earth_candidate_regions"]
    out = []
    for r in regions:
        out.extend(build_manifest(r))
    json.dump({"entries": out, "count": len(out)}, open(args.out, "w"), indent=2)
    print(json.dumps({"entries": len(out)}))

if __name__ == "__main__":
    main()
