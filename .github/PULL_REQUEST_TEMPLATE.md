## Pull Request Summary

- **Target core branch:** `main` | `Datasets` | `BestAlgo/<domain>` | `OptiAlgo/<domain>`
- **Source branch:** `experimental/<feature-or-fix>`
- **Scope:** <!-- Brief description of the feature, port, or fix -->

---

## Pre-Merge Checklist (Repository Invariants)

- [ ] **Branch discipline:** Changes originate from `experimental/<feature-or-fix>` and target a single core branch (`main`, `Datasets`, `BestAlgo/<domain>`, or `OptiAlgo/<domain>`).
- [ ] **Zero raw rasters / binaries:** No `data_lake/`, `*.tif`, `*.tiff`, `*.img`, `*.cub`, `*.h5`, `*.nc`, `*.so`, or `*.o` files are tracked.
- [ ] **Immutable binary contract:** `schema/tile_contract.h` (128-byte `PTIL`/`HMAP` header) is unchanged and matches all 12 core branches.
- [ ] **Verification gates:**
  - Python: `python3 -m py_compile` passes on modified `.py` files.
  - C++20 (`OptiAlgo/*`): `bash build.sh`, `benchmark/verify_parity.py` (`RMSE < 1e-5`, `SSIM > 0.9995`, `>= 10x` speedup, breakdown parity), and `benchmark/run_asan.sh` (exit `0`) pass.
  - WebGIS / Sweep (`main`): `fusion/run_discovery_sweep.py` and `uvicorn app.main:app` endpoints return HTTP `200`.
- [ ] **Cross-audit & cleanup:** Peer/coordinator audit passed; delete the `experimental/*` branch after merge verification.
