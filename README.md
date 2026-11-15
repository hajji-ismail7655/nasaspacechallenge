# Cross-Planetary Terrestrial Analog Discovery Engine

Systematically discover, score, and characterize previously unrecognized terrestrial analogs
for Artemis lunar base sites and Mars exploration targets using multi-scale cross-planetary
open datasets, dual-tier Python/C++ processing modules, and explicit physical analogy-breakdown modeling.

## Integrated Pipeline and UI

```bash
# Install Python runtime and geospatial dependencies once.
python3 -m pip install -r requirements.txt

# 1. Acquire and stage Phase 2 inputs (real COG channels where supported;
#    unsupported channels are explicitly marked as calibrated fallback).
python3 pipelines/phase2_real_ingest.py --shape 512 --out data_lake/phase2

# 2. Standardize to 512x512, five-octave PTILEs split for the sweep.
python3 processor/cli.py --manifest data_lake/phase2/phase2_processor_manifest.json --out-dir data_lake/standardized --shape 512 --split-by-body

# 3. Build all five C++ modules, then run the complete 14 Earth x 8 target sweep.
for module in topography mineralogy thermal_illumination granular_aeolian volatiles_subsurface; do (cd "OptiAlgo/$module" && bash build.sh); done
python3 fusion/run_discovery_sweep.py --backend cpp --earth-dir data_lake/standardized/earth --target-dir data_lake/standardized/targets --out-dir data_lake/results

# 4. Start the API, then start either frontend in another terminal.
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd analog-discovery-engine
npm ci
npm run dev -- --host 0.0.0.0
```

Frontend1 reads `VITE_API_BASE_URL` when set and otherwise connects to
`http://localhost:8000`. Discovery scores are for fixed Moon/Mars targets in the
precomputed sweep. Picker coordinates provide visual context; arbitrary points
and areas are not scored by this dataset. A completed discovery sweep is
required for scored results.

Frontend2 is included as an alternate UI. It uses the same backend scores and
labels its thermal colors and markers as illustrative preview data because the
API does not serve thermal accuracy grids yet.

```bash
cd Frontend2
npm ci
npm run dev -- --host 0.0.0.0
```

## Branches
- `fullproject`: combined working branch based on the latest `main`
- `Datasets`: manifests, pipelines, reference_targets, known_analogs_mask, golden_tiles
- `BestAlgo/<module>` and `OptiAlgo/<module>`: Python references and C++20 modules
- `analog-discovery-engine/`: Frontend1, the primary guided frontend
- `Frontend2/`: alternate guided frontend connected to the same API

## Modules
topography, mineralogy, thermal_illumination, granular_aeolian, volatiles_subsurface

## Verification
Run `benchmark/verify_parity.py` to verify parity (RMSE, SSIM, speedup, breakdown), `scripts/audit_repo.py` to verify branch invariants, `pytest -v tests/` (or `python3 -m unittest discover -s tests -v`) for unit/API checks, and `scripts/generate_figures.py` for `docs/figures/`. To combine independently executed sweep chunks, use `scripts/merge_sweep_chunks.py` with each chunk directory and `--expected-pairs 112`.
