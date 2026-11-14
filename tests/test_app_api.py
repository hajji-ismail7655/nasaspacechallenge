"""API & repository audit integration tests for app/main.py and scripts/audit_repo.py."""
import json
import os
import struct
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
from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from scripts.audit_repo import EXPECTED_TILE_CONTRACT_SHA256, run_audit  # noqa: E402


def _write_test_hmap(path, bh=8, bw=8, num_octaves=5):
    hdr = struct.pack(
        "<IIIIIIII ddd ffff 56s",
        0x50414D48, 1, 1, 1, num_octaves, 2, bh, bw,
        30.0, 30.5, -8.0, -9999.0, 9.80665, 101325.0, 2.4, b"\x00" * 56,
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(hdr)
        for k in range(num_octaves):
            hk = max(1, bh >> k)
            wk = max(1, bw >> k)
            block = np.zeros((2, hk, wk), dtype=np.float32)
            block[0] = 0.85
            block[1] = 1.0
            f.write(block.tobytes())


def _make_client(app):
    try:
        return TestClient(app)
    except TypeError:
        import asyncio
        import httpx

        class _CompatClient:
            def get(self, url, **kwargs):
                async def _req():
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://testserver",
                    ) as ac:
                        return await ac.get(url, **kwargs)
                return asyncio.run(_req())

        return _CompatClient()


class TestAppApiAndAudit(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_data = app_main.DATA
        app_main.DATA = self._tmp.name
        results_dir = os.path.join(self._tmp.name, "results")
        os.makedirs(results_dir, exist_ok=True)

        sample_site = {
            "site_id": "earth_anti_atlas",
            "target_id": "moon_malapert_massif",
            "composite_score": 0.88,
            "scale_invariance_index": 0.94,
            "novelty_weight": 1.0,
        }
        with open(os.path.join(results_dir, "ranked_novel_discoveries.json"), "w", encoding="utf-8") as f:
            json.dump({"sites": [sample_site]}, f)
        with open(os.path.join(results_dir, "ranked_unmasked_calibration.json"), "w", encoding="utf-8") as f:
            json.dump({"sites": [sample_site]}, f)

        bd_path = os.path.join(results_dir, "earth_anti_atlas_moon_malapert_massif_breakdown.json")
        with open(bd_path, "w", encoding="utf-8") as f:
            json.dump({"scale_invariance_index": 0.94, "channel_residuals": {}, "physical_breakdown_flags": []}, f)
        self._bd_path = bd_path

        _write_test_hmap(os.path.join(results_dir, "earth_anti_atlas_moon_malapert_massif_topography.hmap"))
        self.client = _make_client(app_main.app)

    def tearDown(self):
        app_main.DATA = self._orig_data
        self._tmp.cleanup()

    def test_core_endpoints_and_security_headers(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")

        self.assertEqual(len(self.client.get("/targets").json()["targets"]), 8)
        self.assertEqual(self.client.get("/octaves").json(), {"octaves_m": [30, 60, 120, 240, 480]})
        self.assertFalse(self.client.get("/novelty-mask?enabled=false").json()["enabled"])
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_discoveries_geojson_and_breakdown_guards(self):
        disc = self.client.get("/api/discoveries?target_id=moon_malapert_massif&novelty_masked=true")
        self.assertEqual(disc.status_code, 200)
        self.assertEqual(len(disc.json()["sites"]), 1)

        gj = self.client.get("/api/geojson/known-analogs")
        self.assertEqual(gj.status_code, 200)
        self.assertEqual(gj.json().get("type"), "FeatureCollection")

        ok_bd = self.client.get("/breakdown/earth_anti_atlas?target_id=moon_malapert_massif")
        self.assertEqual(ok_bd.status_code, 200)
        self.assertAlmostEqual(ok_bd.json()["breakdown"]["scale_invariance_index"], 0.94)

        bad_token = self.client.get("/breakdown/bad$token")
        self.assertEqual(bad_token.status_code, 400)

        outside = self.client.get("/breakdown/earth_anti_atlas?path=/etc/passwd")
        self.assertEqual(outside.status_code, 403)

    def test_heatmap_png_rendering_and_validation(self):
        png_res = self.client.get("/api/heatmap/earth_anti_atlas/moon_malapert_massif/topography/0.png")
        self.assertEqual(png_res.status_code, 200)
        self.assertTrue(png_res.content.startswith(b"\x89PNG\r\n\x1a\n"))

        # Composite fallback averages available domain .hmap files
        comp_res = self.client.get("/api/heatmap/earth_anti_atlas/moon_malapert_massif/composite/0.png")
        self.assertEqual(comp_res.status_code, 200)
        self.assertTrue(comp_res.content.startswith(b"\x89PNG\r\n\x1a\n"))

        bad_dom = self.client.get("/api/heatmap/earth_anti_atlas/moon_malapert_massif/invalid_domain/0.png")
        self.assertEqual(bad_dom.status_code, 400)

        missing = self.client.get("/api/heatmap/earth_anti_atlas/moon_malapert_massif/mineralogy/0.png")
        self.assertEqual(missing.status_code, 404)

    def test_repo_audit_passes_all_12_branches(self):
        report = run_audit(repo_root=REPO_ROOT, prefer_origin=False)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["tile_contract"]["expected_sha256"], EXPECTED_TILE_CONTRACT_SHA256)
        self.assertEqual(report["tile_contract"]["branches_checked"], 12)
        self.assertTrue(report["datasets"]["pass"])
        self.assertTrue(report["cpp_defaults"]["pass"])


if __name__ == "__main__":
    unittest.main()
