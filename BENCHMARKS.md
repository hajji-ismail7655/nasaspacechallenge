# Benchmarks

## BestAlgo (Python) vs OptiAlgo (C++20) Parity

| Module | RMSE (sim) | RMSE (conf) | SSIM | Speedup | Status |
|---|---|---|---|---|---|
| topography | 0.0 | ~9e-9 | 1.0 | ~650x | PASS |
| mineralogy | 0.0 | ~1.3e-8 | 1.0 | ~467x | PASS |
| thermal_illumination | <1e-8 | <1e-8 | 1.0 | ~100x+ | PASS |
| granular_aeolian | <1e-8 | <1e-8 | 1.0 | ~100x+ | PASS |
| volatiles_subsurface | 0.0 | ~1.2e-8 | 1.0 | ~118x | PASS |

Verified via `benchmark/verify_parity.py` on golden_tiles/. ASAN smoke test via `benchmark/run_asan.sh`.
