"""Export standardized .ptile metadata and Phase 3 C++ sweep results into SQLite (local) or SQL dump."""
import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
import struct
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HDR_STRUCT = struct.Struct("<IIIIIIII ddd ffff 56s")
_MAGIC_PTIL = 0x4C495450
_KNOWN_DOMAINS = (
    "topography",
    "mineralogy",
    "thermal_illumination",
    "granular_aeolian",
    "volatiles_subsurface",
)

BODY_PHYSICS = {
    "EARTH": {"gravity_ms2": 9.80665, "surface_pressure_pa": 101325.0, "radiation_msv_yr": 2.4},
    "MOON": {"gravity_ms2": 1.622, "surface_pressure_pa": 3e-10, "radiation_msv_yr": 250.0},
    "MARS": {"gravity_ms2": 3.72076, "surface_pressure_pa": 610.0, "radiation_msv_yr": 230.0},
}

DEFAULT_TARGET_COORDS = {
    "moon_shackleton_degerlache": (-89.5, 0.0, "MOON"),
    "moon_malapert_massif": (-86.0, 2.0, "MOON"),
    "moon_aristarchus_plateau": (23.7, -47.5, "MOON"),
    "moon_marius_hills_skylight": (14.1, -56.8, "MOON"),
    "mars_jezero_western_fan": (18.38, 77.58, "MARS"),
    "mars_arcadia_planitia": (40.0, 170.0, "MARS"),
    "mars_arsia_mons_pits": (-9.0, -121.0, "MARS"),
    "mars_bagnold_dunes": (-4.7, 137.4, "MARS"),
}

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
CREATE TABLE IF NOT EXISTS known_analogs_mask (
    analog_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    buffer_km REAL NOT NULL DEFAULT 150.0,
    geojson_feature TEXT NOT NULL
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


def _first_not_none(*vals):
    for val in vals:
        if val is not None:
            return val
    return None


def _strip_domain_suffix(tile_id):
    for dom in _KNOWN_DOMAINS:
        suffix = f"_{dom}"
        if tile_id.endswith(suffix):
            return tile_id[: -len(suffix)]
    return tile_id.rsplit("_", 1)[0]


def _read_ptile_header(path):
    try:
        with open(path, "rb") as f:
            raw = f.read(_HDR_STRUCT.size)
        if len(raw) < _HDR_STRUCT.size:
            return {}
        hdr = _HDR_STRUCT.unpack(raw)
        if hdr[0] != _MAGIC_PTIL:
            return {}
        return {
            "num_octaves": int(hdr[4]),
            "num_channels": int(hdr[5]),
            "base_height": int(hdr[6]),
            "base_width": int(hdr[7]),
            "base_resolution_m": float(hdr[8]),
            "lat": float(hdr[9]),
            "lon": float(hdr[10]),
            "gravity_ms2": float(hdr[12]),
            "surface_pressure_pa": float(hdr[13]),
            "radiation_msv_yr": float(hdr[14]),
        }
    except OSError:
        return {}


def _load_json_with_git_fallback(explicit_path, local_paths, git_refs):
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    candidates.extend(local_paths)
    for path in candidates:
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    for ref in git_refs:
        try:
            raw = subprocess.check_output(
                ["git", "-C", REPO_ROOT, "show", ref],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            return json.loads(raw)
        except Exception:
            continue
    return None


def export_sqlite(
    data_dir,
    db_path,
    object_prefix="s3://analog-data-lake",
    targets_path="",
    known_analogs_path="",
):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SQLITE_DDL)

        observed_target_meta = {}
        std_tiles = 0
        for body_dir, body_name in [("earth", "EARTH"), ("targets", "TARGET")]:
            folder = os.path.join(data_dir, "standardized", body_dir)
            for ptile in sorted(glob.glob(os.path.join(folder, "*.ptile"))):
                sidecar = ptile[:-6] + ".json"
                if os.path.exists(sidecar):
                    with open(sidecar, encoding="utf-8") as f:
                        meta = json.load(f)
                else:
                    meta = {}
                hdr_meta = _read_ptile_header(ptile)
                tile_id = os.path.splitext(os.path.basename(ptile))[0]
                body = str(meta.get("body", body_name)).upper()
                if body == "TARGET":
                    body = "MOON" if tile_id.startswith("moon_") else "MARS"
                region_id = (
                    meta.get("region_id")
                    or meta.get("target_id")
                    or _strip_domain_suffix(tile_id)
                )
                domain = meta.get("domain", "topography")
                if body_dir == "targets":
                    merged = dict(hdr_meta)
                    for key in (
                        "lat",
                        "lon",
                        "gravity_ms2",
                        "surface_pressure_pa",
                        "radiation_msv_yr",
                        "official_portals",
                    ):
                        if meta.get(key) is not None:
                            merged[key] = meta[key]
                    if merged:
                        observed_target_meta[region_id] = merged
                conn.execute(
                    """INSERT OR REPLACE INTO standardized_tiles
                       (tile_id, body, region_or_target_id, domain, base_height, base_width,
                        base_resolution_m, num_octaves, num_channels, provenance, ptile_uri, sha256)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        tile_id, body, region_id, domain,
                        int(_first_not_none(meta.get("base_height"), hdr_meta.get("base_height"), 512)),
                        int(_first_not_none(meta.get("base_width"), hdr_meta.get("base_width"), 512)),
                        float(_first_not_none(meta.get("base_resolution_m"), hdr_meta.get("base_resolution_m"), 30.0)),
                        int(_first_not_none(meta.get("num_octaves"), hdr_meta.get("num_octaves"), 5)),
                        int(_first_not_none(meta.get("num_channels"), hdr_meta.get("num_channels"), 5)),
                        json.dumps(meta.get("channel_provenance", meta.get("official_resources", {}))),
                        f"{object_prefix}/standardized/{body_dir}/{os.path.basename(ptile)}",
                        _sha256(ptile),
                    ),
                )
                std_tiles += 1

        targets_doc = _load_json_with_git_fallback(
            targets_path,
            [
                os.path.join(data_dir, "reference_targets", "targets.json"),
                os.path.join(data_dir, "targets.json"),
                os.path.join(REPO_ROOT, "Datasets", "reference_targets", "targets.json"),
                os.path.join(REPO_ROOT, "reference_targets", "targets.json"),
            ],
            [
                "origin/Datasets:reference_targets/targets.json",
                "Datasets:reference_targets/targets.json",
            ],
        )
        targets_count = 0
        if targets_doc is not None:
            if isinstance(targets_doc, list):
                target_items = targets_doc
            else:
                target_items = (
                    targets_doc.get("reference_targets")
                    or targets_doc.get("targets")
                    or []
                )
            for item in target_items:
                target_id = item.get("id") or item.get("target_id")
                if not target_id:
                    continue
                default_lat, default_lon, default_body = DEFAULT_TARGET_COORDS.get(
                    target_id,
                    (0.0, 0.0, "MOON" if str(target_id).startswith("moon_") else "MARS"),
                )
                body = str(item.get("body", default_body)).upper()
                obs = observed_target_meta.get(target_id, {})
                phys = BODY_PHYSICS.get(body, BODY_PHYSICS["MOON"])
                lat = float(_first_not_none(item.get("lat"), obs.get("lat"), default_lat))
                lon = float(_first_not_none(item.get("lon"), obs.get("lon"), default_lon))
                gravity = float(_first_not_none(item.get("gravity_ms2"), obs.get("gravity_ms2"), phys["gravity_ms2"]))
                pressure = float(
                    _first_not_none(item.get("surface_pressure_pa"), obs.get("surface_pressure_pa"), phys["surface_pressure_pa"])
                )
                radiation = float(
                    _first_not_none(item.get("radiation_msv_yr"), obs.get("radiation_msv_yr"), phys["radiation_msv_yr"])
                )
                portals = _first_not_none(item.get("official_portals"), obs.get("official_portals"), [])
                conn.execute(
                    """INSERT OR REPLACE INTO targets
                       (target_id, name, body, lat, lon, gravity_ms2, surface_pressure_pa,
                        radiation_msv_yr, official_portals)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        target_id,
                        str(item.get("name", target_id)),
                        body,
                        lat,
                        lon,
                        gravity,
                        pressure,
                        radiation,
                        json.dumps(portals),
                    ),
                )
                targets_count += 1

        mask_doc = _load_json_with_git_fallback(
            known_analogs_path,
            [
                os.path.join(data_dir, "known_analogs_mask.geojson"),
                os.path.join(REPO_ROOT, "Datasets", "known_analogs_mask.geojson"),
                os.path.join(REPO_ROOT, "known_analogs_mask.geojson"),
            ],
            [
                "origin/Datasets:known_analogs_mask.geojson",
                "Datasets:known_analogs_mask.geojson",
            ],
        )
        mask_count = 0
        if mask_doc is not None:
            for idx, feat in enumerate(mask_doc.get("features", [])):
                props = feat.get("properties") or {}
                name = str(props.get("name") or f"analog_{idx}")
                raw_id = props.get("analog_id") or props.get("id")
                analog_id = (
                    str(raw_id)
                    if raw_id
                    else (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or f"analog_{idx}")
                )
                buffer_val = props.get("buffer_km")
                buffer_km = float(buffer_val) if buffer_val is not None else 150.0
                conn.execute(
                    """INSERT OR REPLACE INTO known_analogs_mask
                       (analog_id, name, buffer_km, geojson_feature)
                       VALUES (?, ?, ?, ?)""",
                    (analog_id, name, buffer_km, json.dumps(feat)),
                )
                mask_count += 1

        results_dir = os.path.join(data_dir, "results")
        novel_p = os.path.join(results_dir, "ranked_novel_discoveries.json")
        pairs = 0
        if os.path.exists(novel_p):
            with open(novel_p, encoding="utf-8") as f:
                data = json.load(f)
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
                    with open(bd_path, encoding="utf-8") as f:
                        bd = json.load(f)
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
    finally:
        conn.close()
    return {
        "targets": targets_count,
        "known_analogs_mask": mask_count,
        "standardized_tiles": std_tiles,
        "analog_pairs": pairs,
        "db_path": db_path,
    }


def main():
    ap = argparse.ArgumentParser(description="Export standardized data lake and sweep results to SQLite DB")
    ap.add_argument("--data-dir", default="./data_lake")
    ap.add_argument("--db-path", default="./data_lake/analog_engine.db")
    ap.add_argument("--object-prefix", default="s3://analog-data-lake")
    ap.add_argument("--targets-json", default="", help="Optional path to reference_targets/targets.json")
    ap.add_argument("--known-analogs", default="", help="Optional path to known_analogs_mask.geojson")
    args = ap.parse_args()
    print(json.dumps(export_sqlite(
        args.data_dir,
        args.db_path,
        args.object_prefix,
        targets_path=args.targets_json,
        known_analogs_path=args.known_analogs,
    ), indent=2))


if __name__ == "__main__":
    main()
