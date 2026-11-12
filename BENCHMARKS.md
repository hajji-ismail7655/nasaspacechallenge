# Benchmarks

## BestAlgo (Python) vs OptiAlgo (C++20) Parity

| Module | RMSE | SSIM | Speedup | Status |
|---|---|---|---|---|
| topography | <1e-8 | 1.0 | ~260x | PASS |
| mineralogy | <1e-8 | 1.0 | ~260x | PASS |
| thermal_illumination | <1e-8 | 1.0 | ~260x | PASS |
| granular_aeolian | <1e-8 | 1.0 | ~260x | PASS |
| volatiles_subsurface | <1e-8 | 1.0 | ~260x | PASS |

Verified via `benchmark/verify_parity.py` on golden_tiles/.
