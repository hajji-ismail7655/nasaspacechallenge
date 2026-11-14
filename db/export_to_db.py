"""Export standardized .ptile metadata and Phase 3 C++ sweep results into SQLite (local) or SQL dump."""
import argparse
import glob
import hashlib
import json
import os
import sqlite3

SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS targets (
    target_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    gravity_ms2 REAL NOT NULL,
    surface_pressure_pa REAL NOT NULL,
    radiation_msv_yr REAL NOT NULL,
    official_portals TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS earth_regions (
    site_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    bbox TEXT NOT NULL,
    is_known_analog INTEGER NOT NULL,
    novelty_weight_150km REAL NOT NULL,
    official_portals TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS standardized_tiles (
    tile_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    region_or_target_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    base_height INTEGER NOT NULL,
    base_width INTEGER NOT NULL,
    base_resolution_m REAL NOT NULL,
    num_octaves INTEGER NOT NULL,
    num_channels INTEGER NOT NULL,
    provenance TEXT NOT NULL,
    ptile_uri TEXT NOT NULL,
    sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analog_pairs (
    pair_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    composite_score REAL NOT NULL,
    novel_composite_score REAL NOT NULL,
    scale_invariance_index REAL NOT NULL,
    novelty_weight REAL NOT NULL,
    domain_scores TEXT NOT NULL,
    channel_residuals TEXT NOT NULL,
    physical_breakdown_flags TEXT NOT NULL,
    operational_test_protocol TEXT NOT NULL,
    composite_hmap_uri TEXT NOT NULL,
    overlay_png_prefix TEXT NOT NULL,
    backend TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pairs_novel ON analog_pairs (target_id, novel_composite_score DESC);
"""


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def export_sqlite(data_dir, db_path, object_prefix="s3://analog-data-lake"):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SQLITE_DDL)

    std_tiles = 0
    for body_dir, body_name in [("earth", "EARTH"), ("targets", "TARGET")]:
        folder = os.path.join(data_dir, "standardized", body_dir)
        for ptile in sorted(glob.glob(os.path.join(folder, "*.ptile"))):
            sidecar = ptile[:-6] + ".json"
            meta = json.load(open(sidecar, encoding="utf-8")) if os.path.exists(sidecar) else {}
            tile_id = os.path.splitext(os.path.basename(ptile))[0]
            body = str(meta.get("body", body_name)).upper()
            if body == "TARGET":
                body = "MOON" if tile_id.startswith("moon_") else "MARS"
            region_id = meta.get("region_id") or meta.get("target_id") or tile_id.rsplit("_", 1)[0]
            domain = meta.get("domain", "topography")
            conn.execute(
                """INSERT OR REPLACE INTO standardized_tiles
                   (tile_id, body, region_or_target_id, domain, base_height, base_width,
                    base_resolution_m, num_octaves, num_channels, provenance, ptile_uri, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tile_id, body, region_id, domain,
                    int(meta.get("base_height", 512)), int(meta.get("base_width", 512)),
                    float(meta.get("base_resolution_m", 30.0)), int(meta.get("num_octaves", 5)),
                    int(meta.get("num_channels", 5)),
                    json.dumps(meta.get("channel_provenance", meta.get("official_resources", {}))),
                    f"{object_prefix}/standardized/{body_dir}/{os.path.basename(ptile)}",
                    _sha256(ptile),
                ),
            )
            std_tiles += 1

    results_dir = os.path.join(data_dir, "results")
    novel_p = os.path.join(results_dir, "ranked_novel_discoveries.json")
    pairs = 0
    if os.path.exists(novel_p):
        data = json.load(open(novel_p, encoding="utf-8"))
        backend = data.get("backend", "cpp")
        for row in data.get("sites", []):
            site_id = row["site_id"]
            target_id = row["target_id"]
            conn.execute(
                """INSERT OR REPLACE INTO earth_regions
                   (site_id, name, lat, lon, bbox, is_known_analog, novelty_weight_150km, official_portals)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    site_id, site_id, float(row.get("lat", 0.0)), float(row.get("lon", 0.0)),
                    json.dumps(row.get("bbox", [])), 1 if row.get("is_known_analog") else 0,
                    float(row.get("novelty_weight", 1.0)), "[]",
                ),
            )
            bd = {}
            bd_path = row.get("breakdown_path") or os.path.join(results_dir, f"{site_id}_{target_id}_breakdown.json")
            if os.path.exists(bd_path):
                bd = json.load(open(bd_path, encoding="utf-8"))
            conn.execute(
                """INSERT OR REPLACE INTO analog_pairs
                   (pair_id, site_id, target_id, composite_score, novel_composite_score,
                    scale_invariance_index, novelty_weight, domain_scores, channel_residuals,
                    physical_breakdown_flags, operational_test_protocol, composite_hmap_uri,
                    overlay_png_prefix, backend)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"{site_id}__{target_id}", site_id, target_id,
                    float(row.get("unmasked_composite_score", row.get("composite_score", 0.0))),
                    float(row.get("novel_composite_score", row.get("composite_score", 0.0))),
                    float(row.get("scale_invariance_index", 0.0)),
                    float(row.get("novelty_weight", 1.0)),
                    json.dumps(row.get("domain_scores", {})),
                    json.dumps(bd.get("channel_residuals", {})),
                    json.dumps(bd.get("physical_breakdown_flags", [])),
                    str(row.get("operational_test_protocol", "")),
                    f"{object_prefix}/results/{site_id}_{target_id}_composite.hmap",
                    f"{object_prefix}/overlays/{site_id}/{target_id}",
                    backend,
                ),
            )
            pairs += 1

    conn.commit()
    conn.close()
    return {"standardized_tiles": std_tiles, "analog_pairs": pairs, "db_path": db_path}


def main():
    ap = argparse.ArgumentParser(description="Export standardized data lake and sweep results to SQLite DB")
    ap.add_argument("--data-dir", default="./data_lake")
    ap.add_argument("--db-path", default="./data_lake/analog_engine.db")
    ap.add_argument("--object-prefix", default="s3://analog-data-lake")
    args = ap.parse_args()
    print(json.dumps(export_sqlite(args.data_dir, args.db_path, args.object_prefix), indent=2))


if __name__ == "__main__":
    main()
