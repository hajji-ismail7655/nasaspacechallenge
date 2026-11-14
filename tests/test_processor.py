"""Unit tests for processor/* standardization modules and Datasets _tile_utils contract."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
for p in (REPO_ROOT, TESTS_DIR, os.path.join(REPO_ROOT, "processor")):
    if p not in sys.path:
        sys.path.insert(0, p)

from _fallback_shims import ensure_deps  # noqa: E402

ensure_deps()

import numpy as np  # noqa: E402
from processor.cli import _resolve_shape, process_one  # noqa: E402
from processor.pyramid_builder import NODATA, build_pyramid  # noqa: E402
from processor.reproject_laea import RADII, laea_forward, laea_inverse, reproject_to_laea  # noqa: E402
from processor.tile_writer import (  # noqa: E402
    HEADER_STRUCT,
    MAGIC_PTIL,
    read_header,
    write_json_sidecar,
    write_ptile,
)


class TestProcessorPipeline(unittest.TestCase):
    def test_header_struct_size_and_ptile_roundtrip_512(self):
        self.assertEqual(HEADER_STRUCT.size, 128)
        with tempfile.TemporaryDirectory() as tmp:
            ptile_path = os.path.join(tmp, "moon_sample.ptile")
            octs = [np.zeros((2, 512 >> k, 512 >> k), dtype=np.float32) for k in range(5)]
            write_ptile(
                ptile_path,
                body="moon",
                domain="topography",
                num_octaves=5,
                num_channels=2,
                base_height=512,
                base_width=512,
                base_resolution_m=30.0,
                center_lat_deg=-86.0,
                center_lon_deg=2.0,
                radiation_msv_yr=250.0,
                octaves_data=octs,
            )
            hdr = read_header(ptile_path)
            self.assertEqual(hdr["magic"], MAGIC_PTIL)
            self.assertEqual(hdr["version"], 1)
            self.assertEqual(hdr["body"], 2)
            self.assertEqual(hdr["domain"], 1)
            self.assertEqual(hdr["base_height"], 512)
            self.assertEqual(hdr["base_width"], 512)
            self.assertAlmostEqual(hdr["gravity_ms2"], 1.622, places=4)
            self.assertAlmostEqual(hdr["surface_pressure_pa"], 3e-10, places=12)

            expected_payload = sum(2 * (512 >> k) * (512 >> k) * 4 for k in range(5))
            self.assertEqual(os.path.getsize(ptile_path), 128 + expected_payload)

    def test_small_tile_octave_clamping(self):
        with tempfile.TemporaryDirectory() as tmp:
            ptile_path = os.path.join(tmp, "tiny.ptile")
            octs = [np.zeros((1, max(1, 4 >> k), max(1, 4 >> k)), dtype=np.float32) for k in range(5)]
            write_ptile(ptile_path, "mars", "mineralogy", 5, 1, 4, 4, 30.0, 18.38, 77.58, octaves_data=octs)
            hdr = read_header(ptile_path)
            self.assertEqual(hdr["body"], 3)
            self.assertEqual(hdr["domain"], 2)
            expected_payload = sum(1 * max(1, 4 >> k) * max(1, 4 >> k) * 4 for k in range(5))
            self.assertEqual(os.path.getsize(ptile_path), 128 + expected_payload)

    def test_laea_forward_inverse_roundtrip_and_lon_wrap(self):
        for body, r in RADII.items():
            x, y = laea_forward(np.array([25.5]), np.array([40.25]), 25.0, 40.0, r)
            lat_b, lon_b = laea_inverse(x, y, 25.0, 40.0, r)
            self.assertAlmostEqual(lat_b.tolist()[0], 25.5, places=4, msg=body)
            self.assertAlmostEqual(lon_b.tolist()[0], 40.25, places=4, msg=body)

        # Source spans [350, 354] deg E (0-360 convention) centered near lon0=-8 ([-180,180])
        lats = np.linspace(29.0, 32.0, 16)
        lons = np.linspace(350.0, 354.0, 16)
        src = np.full((16, 16), 42.0, dtype=np.float32)
        src[0, :] = NODATA
        reproj = reproject_to_laea(src, lats, lons, lat0=30.5, lon0=-8.0, body="earth", out_shape=(16, 16), resolution_m=30.0)
        self.assertEqual(reproj.shape, (16, 16))
        center_val = reproj[8, 8]
        self.assertAlmostEqual(float(center_val), 42.0, places=3)

    def test_pyramid_builder_coarse_resolution_masks_finer_octaves(self):
        tile = np.ones((2, 16, 16), dtype=np.float32) * 5.0
        octs = build_pyramid(tile, base_resolution_m=120.0, num_octaves=5)
        self.assertEqual(len(octs), 5)
        # 30m and 60m octaves finer than 120m input must be nodata
        self.assertAlmostEqual(float(octs[0][0, 0, 0]), NODATA, places=2)
        self.assertAlmostEqual(float(octs[1][0, 0, 0]), NODATA, places=2)
        # 120m, 240m, 480m octaves remain valid near 5.0
        self.assertAlmostEqual(float(octs[2][0, 0, 0]), 5.0, places=2)
        self.assertEqual(octs[4].shape, (2, 1, 1))

    def test_cli_resolve_shape_defaults_512_and_process_one(self):
        self.assertEqual(_resolve_shape(None), (512, 512))
        self.assertEqual(_resolve_shape([256]), (256, 256))
        self.assertEqual(_resolve_shape([64, 128]), (64, 128))

        with tempfile.TemporaryDirectory() as tmp:
            npy_path = os.path.join(tmp, "raw.npy")
            meta_path = os.path.join(tmp, "raw.json")
            out_base = os.path.join(tmp, "std", "earth_test_topography")
            np.save(npy_path, np.ones((2, 16, 16), dtype=np.float32) * 10.0)
            write_json_sidecar(
                meta_path,
                {
                    "lats": np.linspace(29.5, 31.5, 16).tolist(),
                    "lons": np.linspace(-9.0, -7.0, 16).tolist(),
                    "base_resolution_m": 30.0,
                    "channel_names": ["elevation_z", "slope_theta"],
                    "source_datasets": ["Copernicus DEM GLO-30"],
                    "acquisition_window": "2024-01-01/2025-12-31",
                    "quality_mask_stats": {"valid_fraction": 1.0},
                },
            )
            process_one(npy_path, meta_path, "earth", "topography", 30.5, -8.0, out_base, channels=2, out_shape=(16, 16))
            self.assertTrue(os.path.exists(out_base + ".ptile"))
            self.assertTrue(os.path.exists(out_base + ".json"))
            with open(out_base + ".json", encoding="utf-8") as f:
                sidecar = json.load(f)
            self.assertEqual(sidecar["base_height"], 16)
            self.assertEqual(sidecar["base_width"], 16)
            self.assertIn("+R=6371000", sidecar["proj4_laea"])

    def test_datasets_tile_utils_provenance_and_512_contract(self):
        for ref in ("origin/Datasets:pipelines/_tile_utils.py", "Datasets:pipelines/_tile_utils.py"):
            proc = subprocess.run(
                ["git", "-C", REPO_ROOT, "show", ref],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                src = proc.stdout
                break
        else:
            self.skipTest("Datasets branch not available in git repository")
            return

        with tempfile.TemporaryDirectory() as tmp:
            mod_path = os.path.join(tmp, "_tile_utils.py")
            with open(mod_path, "w", encoding="utf-8") as f:
                f.write(src)
            spec = importlib.util.spec_from_file_location("datasets_tile_utils", mod_path)
            tu = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tu)

            self.assertEqual(len(tu.OFFICIAL_EARTH_RESOURCES), 7)
            self.assertEqual(len(tu.OFFICIAL_MOON_MARS_RESOURCES), 3)
            prov = tu.build_channel_provenance("mineralogy", external_channels={"olivine": [[1.0]]})
            self.assertEqual(prov["olivine"], tu.PROVENANCE_REAL_ORBITAL_COG)
            self.assertEqual(prov["mafic_pyroxene"], tu.PROVENANCE_CALIBRATED_FALLBACK)
            self.assertEqual(len(prov), 8)


if __name__ == "__main__":
    unittest.main()
