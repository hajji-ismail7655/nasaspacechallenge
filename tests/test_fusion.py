"""Unit tests for fusion/* modules and C++20 OptiAlgo pipeline defaults."""
import inspect
import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
for p in (REPO_ROOT, TESTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from _fallback_shims import ensure_deps  # noqa: E402

ensure_deps()

import numpy as np  # noqa: E402
from fusion.breakdown_synthesizer import synthesize_site_dossier, write_dossier  # noqa: E402
from fusion.engine import composite_similarity, fuse, scale_invariance_filter  # noqa: E402
from fusion.mission_mapper import MISSION_TESTS, map_site  # noqa: E402
from fusion.novelty_mask import apply_mask_grid, apply_suppression, haversine_km  # noqa: E402
from fusion.run_discovery_sweep import (  # noqa: E402
    DOMAINS,
    MAGIC_HMAP,
    _index_standardized_tiles,
    read_hmap_header_and_octaves,
    run_sweep,
    write_composite_hmap,
)


class TestFusionPipeline(unittest.TestCase):
    def test_composite_similarity_excludes_zero_conf_and_scale_invariance_nodata(self):
        # Module A has conf=1.0 and sim=0.8 everywhere; Module B has conf=0.0 at [0,0]
        sim_a = np.full((2, 4, 4), 1.0, dtype=np.float32)
        sim_a[0] = 0.8
        sim_b = np.full((2, 4, 4), 1.0, dtype=np.float32)
        sim_b[0] = 0.4
        sim_b[1, 0, 0] = 0.0  # zero confidence at pixel (0, 0)

        comp = composite_similarity({"a": [sim_a, sim_a], "b": [sim_b, sim_b]})
        self.assertAlmostEqual(float(comp[0][0, 0]), 0.8, places=4)
        self.assertAlmostEqual(float(comp[0][1, 1]), 0.6, places=4)

        # Constant identical octaves -> std=0, mean>0 -> I_scale = 1.0
        _, i_scale = scale_invariance_filter(comp)
        self.assertAlmostEqual(float(i_scale[1, 1]), 1.0, places=4)

        # All-zero/nodata region -> I_scale must be clamped to 0.0
        zero_octs = {0: np.zeros((4, 4), dtype=np.float32), 1: np.zeros((2, 2), dtype=np.float32)}
        fused = fuse({"a": [zero_octs[0], zero_octs[1]]})
        self.assertAlmostEqual(float(fused["scale_invariance_index"][0, 0]), 0.0, places=5)

    def test_novelty_mask_ramp_and_grid(self):
        features = [
            {
                "type": "Feature",
                "properties": {"name": "Atacama core", "buffer_km": 150.0},
                "geometry": {"type": "Point", "coordinates": [-69.5, -24.0]},
            }
        ]
        self.assertAlmostEqual(haversine_km(0.0, 0.0, 0.0, 0.0), 0.0, places=5)
        self.assertAlmostEqual(apply_suppression(-24.0, -69.5, features), 0.0, places=5)
        # ~75 km north (~0.674 deg) -> weight near 0.5
        mid_w = apply_suppression(-23.326, -69.5, features)
        self.assertGreater(mid_w, 0.4)
        self.assertLess(mid_w, 0.6)
        # Far outside 150 km (e.g. Morocco Anti-Atlas) -> unsuppressed 1.0
        self.assertAlmostEqual(apply_suppression(30.5, -8.0, features), 1.0, places=5)

        grid = apply_mask_grid([-24.0, 30.5], [-69.5, -8.0], features)
        self.assertEqual(grid.shape, (2, 2))
        self.assertAlmostEqual(float(grid[0, 0]), 0.0, places=4)
        self.assertAlmostEqual(float(grid[1, 1]), 1.0, places=4)

    def test_mission_mapper_and_dossier(self):
        self.assertEqual(len(MISSION_TESTS), 8)
        for tid in MISSION_TESTS:
            self.assertNotEqual(map_site(tid), "Generic analog field validation")
        self.assertEqual(map_site("unknown_target"), "Generic analog field validation")

        with tempfile.TemporaryDirectory() as tmp:
            dossier = synthesize_site_dossier(
                site_id="earth_anti_atlas",
                coords={"lat": 30.5, "lon": -8.0},
                module_scores={"topography": 0.91},
                breakdowns={"topography": {"scale_invariance_index": 0.95}},
                mission_test=map_site("moon_shackleton_degerlache"),
            )
            out_json = os.path.join(tmp, "dossier.json")
            write_dossier(out_json, dossier)
            with open(out_json, encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["site_id"], "earth_anti_atlas")
            self.assertEqual(loaded["scale_range"], "30m-480m")

    def test_cpp_backend_default_and_composite_hmap_roundtrip(self):
        sig = inspect.signature(run_sweep)
        self.assertEqual(sig.parameters["backend"].default, "cpp")
        self.assertFalse(sig.parameters["fallback_python"].default)
        self.assertEqual(len(DOMAINS), 5)

        with tempfile.TemporaryDirectory() as tmp:
            # Verify write_composite_hmap / read_hmap_header_and_octaves binary contract
            hmap_path = os.path.join(tmp, "earth_anti_atlas_moon_malapert_massif_composite.hmap")
            hdr_ref = {
                "body": 1,
                "num_octaves": 5,
                "base_height": 16,
                "base_width": 16,
                "base_resolution_m": 30.0,
                "center_lat_deg": 30.5,
                "center_lon_deg": -8.0,
                "nodata_value": -9999.0,
                "gravity_ms2": 9.80665,
                "surface_pressure_pa": 101325.0,
                "radiation_msv_yr": 2.4,
            }
            comp_octs = {k: np.full((16 >> k, 16 >> k), 0.75, dtype=np.float32) for k in range(5)}
            i_scale = np.ones((1, 1), dtype=np.float32)
            write_composite_hmap(hmap_path, hdr_ref, comp_octs, i_scale)
            hdr, octs = read_hmap_header_and_octaves(hmap_path)
            self.assertEqual(hdr["num_octaves"], 5)
            self.assertEqual(hdr["num_channels"], 2)
            self.assertEqual(len(octs), 5)
            self.assertAlmostEqual(float(octs[0][0, 0, 0]), 0.75, places=4)
            self.assertAlmostEqual(float(octs[0][1, 0, 0]), 1.0, places=4)

            # Verify _index_standardized_tiles groups domain tiles properly
            ptile_stub = os.path.join(tmp, "earth_anti_atlas_topography.ptile")
            with open(ptile_stub, "wb") as f:
                f.write(b"\x00" * 128)
            idx = _index_standardized_tiles(tmp)
            self.assertIn("earth_anti_atlas", idx)
            self.assertIn("topography", idx["earth_anti_atlas"]["domains"])
            self.assertTrue(MAGIC_HMAP == 0x50414D48)


if __name__ == "__main__":
    unittest.main()
