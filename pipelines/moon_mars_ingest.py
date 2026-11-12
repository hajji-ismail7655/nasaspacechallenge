"""Moon & Mars ingestion pipeline (declarative PDS manifest generator)."""
import argparse
import json
import os

TARGETS = {
    "moon_shackleton_degerlache": {"body": "MOON", "datasets": ["LOLA", "Diviner", "Mini-RF", "M3"]},
    "moon_malapert_massif": {"body": "MOON", "datasets": ["LOLA", "Diviner"]},
    "moon_aristarchus_plateau": {"body": "MOON", "datasets": ["Kaguya TC/MI", "M3", "Diviner"]},
    "moon_marius_hills_skylight": {"body": "MOON", "datasets": ["LROC NAC", "GRAIL", "Mini-RF"]},
    "mars_jezero_western_fan": {"body": "MARS", "datasets": ["CTX/HiRISE DEM", "CRISM", "THEMIS"]},
    "mars_arcadia_planitia": {"body": "MARS", "datasets": ["MOLA/CTX DEM", "SHARAD", "GRS/HEND", "THEMIS"]},
    "mars_arsia_mons_pits": {"body": "MARS", "datasets": ["HiRISE", "THEMIS diurnal TIR"]},
    "mars_bagnold_dunes": {"body": "MARS", "datasets": ["HiRISE", "CRISM", "MCS"]},
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="manifests/moon_mars_ingest_manifest.json")
    args = ap.parse_args()
    out = []
    for tid, info in TARGETS.items():
        for ds in info["datasets"]:
            out.append({"target": tid, "body": info["body"], "dataset": ds,
                        "uri": f"./data_lake/targets/{tid}/{ds}/", "format": "PDS/STAC"})
    json.dump({"entries": out, "count": len(out)}, open(args.out, "w"), indent=2)
    print(json.dumps({"entries": len(out)}))

if __name__ == "__main__":
    main()
