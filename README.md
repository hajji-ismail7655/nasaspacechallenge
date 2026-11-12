# Cross-Planetary Terrestrial Analog Discovery Engine

Systematically discover, score, and characterize previously unrecognized terrestrial analogs
for Artemis lunar base sites and Mars exploration targets using multi-scale cross-planetary
open datasets, dual-tier Python/C++ processing modules, and explicit physical analogy-breakdown modeling.

## Branches
- `main`: schema, processor, fusion, benchmark, app
- `Datasets`: manifests, pipelines, reference_targets, known_analogs_mask, golden_tiles
- `BestAlgo/<module>`: Python reference implementations
- `OptiAlgo/<module>`: C++20 optimized implementations

## Modules
topography, mineralogy, thermal_illumination, granular_aeolian, volatiles_subsurface

## Verification
Run `benchmark/verify_parity.py` to compare BestAlgo vs OptiAlgo (RMSE, SSIM, speedup).
