# Cross-Planetary Terrestrial Analog Discovery Engine

Systematically discover, score, and characterize previously unrecognized terrestrial analogs
for Artemis lunar base sites and Mars exploration targets using multi-scale cross-planetary
open datasets, dual-tier Python/C++ processing modules, and explicit physical analogy-breakdown modeling.

## Quickstart (3 commands)

```bash
# 1. Run Parity & ASAN Verification
python3 benchmark/verify_parity.py --py BestAlgo/topography --cpp OptiAlgo/topography --earth benchmark/nodata_fixture/nodata_earth_topo.ptile --target benchmark/nodata_fixture/nodata_moon_topo.ptile

# 2. Run Discovery Sweep on Standardized Tiles (C++20 OptiAlgo backend)
python3 fusion/run_discovery_sweep.py --backend cpp --earth-dir ./data_lake/standardized/earth --target-dir ./data_lake/standardized/targets --out-dir ./data_lake/results/

# 3. Launch Interactive WebGIS Dashboard
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Branches
- `main`: schema, processor, fusion, benchmark, app, docs
- `Datasets`: manifests, pipelines, reference_targets, known_analogs_mask, golden_tiles
- `BestAlgo/<module>`: Python reference implementations (v2.0)
- `OptiAlgo/<module>`: C++20 optimized implementations

## Modules
topography, mineralogy, thermal_illumination, granular_aeolian, volatiles_subsurface

## Verification
Run `benchmark/verify_parity.py` to verify BestAlgo vs OptiAlgo parity (RMSE, SSIM, speedup, breakdown), `pytest -v tests/` for unit/API checks, and `scripts/generate_figures.py` for `docs/figures/`.