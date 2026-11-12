# Benchmarks (v2.0)

## BestAlgo (Python) vs OptiAlgo (C++20) Parity

| Module | RMSE (sim) | RMSE (conf) | SSIM | Speedup | Status |
|---|---|---|---|---|---|
| topography | 0.0 (v1) / pending (v2) | ~9e-9 (v1) | 1.0 (v1) | ~650x (v1) | v1 PASS / v2 PENDING |
| mineralogy | 0.0 (v1) / pending (v2) | ~1.3e-8 (v1) | 1.0 (v1) | ~467x (v1) | v1 PASS / v2 PENDING |
| thermal_illumination | <1e-8 (v1) | <1e-8 (v1) | 1.0 (v1) | ~100x+ (v1) | v1 PASS / v2 PENDING |
| granular_aeolian | <1e-8 (v1) | <1e-8 (v1) | 1.0 (v1) | ~100x+ (v1) | v1 PASS / v2 PENDING |
| volatiles_subsurface | 0.0 (v1) / pending (v2) | ~1.2e-8 (v1) | 1.0 (v1) | ~118x (v1) | v1 PASS / v2 PENDING |

**v2.0 algorithm**: standardized local-distribution matching (physical-bounds z-score, target signature, Wasserstein-1 quantile distance + texture energy, min_c f_valid, nodata handling).

**v2.0 parity status**: BestAlgo (Python) v2 complete. OptiAlgo (C++) v2 port in progress (topography attempt builds/runs, parity tuning pending). Run `benchmark/verify_parity.py` and `benchmark/run_asan.sh` for verification.

**ASAN smoke test**: `bash benchmark/run_asan.sh <module> <earth.ptile> <target.ptile>` compiles with `-fsanitize=address,undefined -std=c++20` (note: add `-fopenmp` to match `bindings.py` OpenMP coverage) and runs `run_module` via ctypes. Exit code 0 = clean.