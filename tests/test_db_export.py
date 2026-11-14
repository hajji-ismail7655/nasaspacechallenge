"""Tests for db/export_to_db.py SQLite ETL exporter."""
import hashlib
import json
import os
import sqlite3
import struct
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from db.export_to_db import export_sqlite  # noqa: E402

_HDR_STRUCT = struct.Struct("<IIIIIIII ddd ffff 56s")
_MAGIC_PTIL = 0x4C495450


def _write_minimal_ptile(path, body_id, lat, lon, grav, pres, rad):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    hdr = _HDR_STRUCT.pack(
        _MAGIC_PTIL, 1, body_id, 1, 1, 1, 4, 4,
        30.0, lat, lon, -9999.0, grav, pres, rad, b"\x00" * 56,
    )
    payload = b"\x00" * (4 * 4 * 4)
    with open(path, "wb") as f:
        f.write(hdr + payload)
    return hashlib.sha256(hdr + payload).hexdigest()


class TestDbExport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self._tmp.name, "data_lake")
        self.db_path = os.path.join(self._tmp.name, "out", "analog_engine.db")

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_populates_targets_mask_tiles_and_pairs(self):
        earth_ptile = os.path.join(self.data_dir, "standardized", "earth", "earth_anti_atlas_topography.ptile")
        earth_json = earth_ptile[:-6] + ".json"
        earth_sha = _write_minimal_ptile(earth_ptile, 1, 30.5, -8.0, 9.80665, 101325.0, 2.4)
        with open(earth_json, "w", encoding="utf-8") as f:
            json.dump({
                "body": "EARTH",
                "region_id": "earth_anti_atlas",
                "domain": "topography",
                "base_height": 512,
                "base_width": 512,
                "base_resolution_m": 30.0,
                "num_octaves": 5,
                "num_channels": 6,
                "channel_provenance": {"elevation_z": "CALIBRATED_FALLBACK"},
            }, f)

        moon_ptile = os.path.join(
            self.data_dir, "standardized", "targets", "moon_shackleton_degerlache_topography.ptile"
        )
        moon_json = moon_ptile[:-6] + ".json"
        moon_sha = _write_minimal_ptile(moon_ptile, 2, -89.5, 0.0, 1.622, 3e-10, 250.0)
        with open(moon_json, "w", encoding="utf-8") as f:
            json.dump({
                "body": "MOON",
                "target_id": "moon_shackleton_degerlache",
                "domain": "topography",
                "base_height": 512,
                "base_width": 512,
                "base_resolution_m": 30.0,
                "num_octaves": 5,
                "num_channels": 6,
                "channel_provenance": {"elevation_z": "CALIBRATED_FALLBACK"},
            }, f)

        results_dir = os.path.join(self.data_dir, "results")
        os.makedirs(results_dir, exist_ok=True)
        bd_path = os.path.join(results_dir, "earth_anti_atlas_moon_shackleton_degerlache_breakdown.json")
        with open(bd_path, "w", encoding="utf-8") as f:
            json.dump({
                "channel_residuals": {"elevation_z": 0.12},
                "physical_breakdown_flags": ["GRAVITY_SCALING_DIFF"],
            }, f)
        with open(os.path.join(results_dir, "ranked_novel_discoveries.json"), "w", encoding="utf-8") as f:
            json.dump({
                "backend": "cpp",
                "sites": [{
                    "site_id": "earth_anti_atlas",
                    "target_id": "moon_shackleton_degerlache",
                    "lat": 30.5,
                    "lon": -8.0,
                    "bbox": [-8.5, 30.0, -7.5, 31.0],
                    "is_known_analog": False,
                    "novelty_weight": 1.0,
                    "unmasked_composite_score": 0.89,
                    "novel_composite_score": 0.89,
                    "scale_invariance_index": 0.94,
                    "domain_scores": {"topography": 0.91},
                    "operational_test_protocol": "Autonomous Lidar Hazard Detection",
                    "breakdown_path": bd_path,
                }],
            }, f)

        summary = export_sqlite(self.data_dir, self.db_path)
        self.assertEqual(summary["targets"], 8)
        self.assertEqual(summary["known_analogs_mask"], 10)
        self.assertEqual(summary["standardized_tiles"], 2)
        self.assertEqual(summary["analog_pairs"], 1)

        conn = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0], 8)
            row = conn.execute(
                """SELECT name, body, lat, lon, gravity_ms2, radiation_msv_yr, official_portals
                   FROM targets WHERE target_id = ?""",
                ("moon_shackleton_degerlache",),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], "MOON")
            self.assertAlmostEqual(row[2], -89.5, places=4)
            self.assertAlmostEqual(row[3], 0.0, places=4)
            self.assertAlmostEqual(row[4], 1.622, places=3)
            self.assertAlmostEqual(row[5], 250.0, places=2)
            portals = json.loads(row[6])
            self.assertIsInstance(portals, list)
            self.assertGreater(len(portals), 0)

            self.assertEqual(conn.execute("SELECT COUNT(*) FROM known_analogs_mask").fetchone()[0], 10)
            mask_row = conn.execute(
                "SELECT name, buffer_km, geojson_feature FROM known_analogs_mask WHERE analog_id = ?",
                ("atacama_core",),
            ).fetchone()
            self.assertIsNotNone(mask_row)
            self.assertEqual(mask_row[0], "Atacama core")
            self.assertAlmostEqual(mask_row[1], 150.0, places=4)
            feat = json.loads(mask_row[2])
            self.assertEqual(feat["geometry"]["type"], "Point")
            self.assertEqual(feat["geometry"]["coordinates"], [-69.5, -24.0])

            tile_rows = dict(
                conn.execute("SELECT tile_id, ptile_uri || '|' || sha256 FROM standardized_tiles").fetchall()
            )
            self.assertEqual(
                tile_rows["earth_anti_atlas_topography"],
                f"s3://analog-data-lake/standardized/earth/earth_anti_atlas_topography.ptile|{earth_sha}",
            )
            self.assertEqual(
                tile_rows["moon_shackleton_degerlache_topography"],
                f"s3://analog-data-lake/standardized/targets/moon_shackleton_degerlache_topography.ptile|{moon_sha}",
            )

            self.assertEqual(conn.execute("SELECT COUNT(*) FROM earth_regions").fetchone()[0], 1)
            pair_row = conn.execute(
                "SELECT pair_id, composite_hmap_uri, overlay_png_prefix, backend FROM analog_pairs"
            ).fetchone()
            self.assertEqual(pair_row[0], "earth_anti_atlas__moon_shackleton_degerlache")
            self.assertEqual(
                pair_row[1],
                "s3://analog-data-lake/results/earth_anti_atlas_moon_shackleton_degerlache_composite.hmap",
            )
            self.assertEqual(
                pair_row[2],
                "s3://analog-data-lake/overlays/earth_anti_atlas/moon_shackleton_degerlache",
            )
            self.assertEqual(pair_row[3], "cpp")
        finally:
            conn.close()

    def test_export_with_custom_targets_and_mask_files(self):
        custom_targets = os.path.join(self._tmp.name, "custom_targets.json")
        custom_mask = os.path.join(self._tmp.name, "custom_mask.geojson")
        with open(custom_targets, "w", encoding="utf-8") as f:
            json.dump({
                "reference_targets": [{
                    "id": "mars_custom_site",
                    "name": "Custom Mars Site",
                    "body": "MARS",
                    "lat": 12.25,
                    "lon": -45.5,
                    "official_portals": ["https://pds.nasa.gov/"],
                }],
            }, f)
        with open(custom_mask, "w", encoding="utf-8") as f:
            json.dump({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {"name": "Custom Test Basin", "buffer_km": 75.0},
                    "geometry": {"type": "Point", "coordinates": [10.0, 20.0]},
                }],
            }, f)

        summary = export_sqlite(
            self.data_dir,
            self.db_path,
            targets_path=custom_targets,
            known_analogs_path=custom_mask,
        )
        self.assertEqual(summary["targets"], 1)
        self.assertEqual(summary["known_analogs_mask"], 1)

        conn = sqlite3.connect(self.db_path)
        try:
            trow = conn.execute(
                "SELECT target_id, name, body, lat, lon, gravity_ms2, radiation_msv_yr FROM targets"
            ).fetchone()
            self.assertEqual(trow[0], "mars_custom_site")
            self.assertEqual(trow[1], "Custom Mars Site")
            self.assertEqual(trow[2], "MARS")
            self.assertAlmostEqual(trow[3], 12.25, places=4)
            self.assertAlmostEqual(trow[4], -45.5, places=4)
            self.assertAlmostEqual(trow[5], 3.72076, places=4)
            self.assertAlmostEqual(trow[6], 230.0, places=2)

            mrow = conn.execute(
                "SELECT analog_id, name, buffer_km FROM known_analogs_mask"
            ).fetchone()
            self.assertEqual(mrow, ("custom_test_basin", "Custom Test Basin", 75.0))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
