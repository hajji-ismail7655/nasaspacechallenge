# Benchmarks (v2.0)

## BestAlgo (Python) vs OptiAlgo (C++20) Parity

Golden-tile metrics below use the named Earth/target pair. Thermal illumination uses the Earth tile as both inputs because the dataset contains no separate thermal target.

| Module | Golden pair | RMSE (similarity) | RMSE (confidence) | SSIM | Speedup | Status |
|---|---|---:|---:|---:|---:|---|
| topography | Earth Anti-Atlas -> Mars Arcadia Planitia | 9.31e-9 | 5.06e-8 | 1.000000 | 37.92x | PASS |
| mineralogy | Earth Danakil -> Moon Aristarchus Plateau | 1.39e-8 | 3.46e-8 | 1.000000 | 21.01x | PASS |
| thermal_illumination | Earth LUT Desert -> itself | 2.11e-8 | 4.78e-8 | 1.000000 | 24.89x | PASS |
| granular_aeolian | Earth Tanezrouft -> Mars Bagnold Dunes | 1.64e-8 | 3.38e-8 | 1.000000 | 22.97x | PASS |
| volatiles_subsurface | Earth Undara -> Mars Arsia Mons Pits | 1.44e-8 | 2.34e-8 | 1.000000 | 21.04x | PASS |

**v2.0 algorithm**: standardized local-distribution matching (physical-bounds z-score, target signature, Wasserstein-1 quantile distance plus texture energy, minimum valid-fraction constraint, and nodata handling).

**v2.0 parity status**: all five C++20 ports pass `benchmark/verify_parity.py` against their Python references. Similarity and confidence RMSE are below 1e-5, SSIM exceeds 0.9995, measured speedup exceeds 10x, and breakdown checks pass. Topography also passes the Earth-to-Moon golden pair (similarity RMSE 9.22e-9, confidence RMSE 4.54e-8, speedup 21.68x). Fixture parity checks pass for all five modules.

**ASAN/UBSan status**: all 11 configured fixture and golden-tile smoke cases pass with exit code 0. The runner compiles with `-fsanitize=address,undefined -fopenmp -std=c++20` and preloads libasan before running the ctypes harness. Run `bash benchmark/run_asan.sh <module> <earth.ptile> <target.ptile>`.
