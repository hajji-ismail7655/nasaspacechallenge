# Technical Report — Cross-Planetary Terrestrial Analog Discovery Engine

**Coordinator-authored report (parallel track).** This document describes the architecture, pipeline, data contracts, and implementation of the system across all 12 branches.

---

## 1. System Overview

The engine discovers, scores, and characterizes previously unrecognized terrestrial analogs for Artemis lunar base sites and Mars exploration targets. It combines multi-scale cross-planetary open datasets, a dual-tier Python (reference) / C++20 (optimized) processing pipeline, explicit physical analogy-breakdown modeling, and an interactive WebGIS.

**Non-negotiable invariants:**
1. Zero raw rasters in git (`Datasets` branch stores only manifests, scripts, checksums, `<50 MB` golden tiles).
2. Equal-area metric standardization: Earth (R=6371.0 km), Moon (R=1737.4 km), Mars (R=3389.5 km) never compared in lat/lon; all patches projected to local Lambert Azimuthal Equal-Area (LAEA) metric grids.
3. Domain separation until fusion (topography, mineralogy, thermal/illumination, granular/aeolian, volatiles/subsurface).
4. Strict Python-to-C++ parity gate: RMSE < 1e-5, SSIM > 0.9995, ≥10× speedup, zero-copy mmap, no heap alloc in kernels, ASAN clean.
5. Scientific completeness: multi-scale similarity heatmaps + Analogy Breakdown Vector + Artemis/Mars engineering test mapping.

---

## 2. Repository Topology & Branch Governance

| Branch | Purpose |
|---|---|
| `main` | `schema/`, `processor/`, `fusion/`, `benchmark/`, `app/`, orchestration |
| `Datasets` | `manifests/`, `pipelines/`, `reference_targets/`, `known_analogs_mask.geojson`, `golden_tiles/` |
| `BestAlgo/<module>` | Python reference implementation per domain |
| `OptiAlgo/<module>` | C++20 optimized port per domain |

Modules: `topography`, `mineralogy`, `thermal_illumination`, `granular_aeolian`, `volatiles_subsurface`.

All 12 branches share an identical `schema/tile_contract.h` hash (phase-0 exit gate).

---

## 3. Canonical Data Contracts

### 3.1 Binary Contract (`schema/tile_contract.h`)

Every `.ptile` (input) and `.hmap` (output) file begins with a 128-byte, 64-byte-aligned `TileBinaryHeader`:

- `magic`: `PTIL_MAGIC` (0x4C495450) or `HMAP_MAGIC` (0x50414D48)
- `version`: `CONTRACT_VERSION` (1)
- `body`: `BODY_EARTH=1, BODY_MOON=2, BODY_MARS=3`
- `domain`: `DOMAIN_TOPOGRAPHY=1 … DOMAIN_VOLATILES_SUBSURFACE=5`
- `num_octaves`, `num_channels`, `base_height`, `base_width`
- `base_resolution_m` (e.g. 30.0), `center_lat_deg`, `center_lon_deg`
- `nodata_value` (-9999.0f), `gravity_ms2`, `surface_pressure_pa`, `radiation_msv_yr`
- `reserved[56]` (explicit zero-padding to 128 bytes)

**Payload layout** (immediately after header): for octave k in [0, num_octaves):
- H_k = base_height >> k, W_k = base_width >> k
- block = num_channels × H_k × W_k × sizeof(float)
- memory order: C-contiguous `[octave][channel][row][col]`, float32.

For `.hmap`, `num_channels = 2`: channel 0 = `similarity_score ∈ [0,1]`, channel 1 = `confidence_mask ∈ [0,1]`.

### 3.2 Sidecar JSON

- `<tile_id>.json`: `proj4_laea`, `channel_names`, `source_datasets` (DOIs/mission IDs), `acquisition_window`, `quality_mask_stats`, plus header mirror fields.
- `<tile_id>_<module>.hmap` + `_breakdown.json`: `scale_invariance_index`, `channel_residuals` (per-channel earth_mean/target_mean/z_divergence), `physical_breakdown_flags` (gravity scaling, atmosphere gap, radiation delta, thermal floor, biosphere overprint, etc.).

---

## 4. Dataset Processor Module (`main/processor/`)

### 4.1 `reproject_laea.py`
Projects raw rasters onto local LAEA metric grids (default 512×512 @ 30 m/px = 15.36 km footprint).

- `laea_forward(lat, lon, lat0, lon0, R)` / `laea_inverse(x, y, …)` using spherical LAEA formulas with planetary radius R.
- `reproject_to_laea(source, src_lats, src_lons, lat0, lon0, body, out_shape, resolution_m)`:
  - Builds target pixel centers in meters, inverse-projects to lat/lon.
  - Wraps target longitudes into source longitude range (handles 0–360 vs -180–180).
  - Linear interpolation on filled (nodata→0) values, normalized by a validity mask (nearest-neighbor interpolated) to avoid nodata smear.

### 4.2 `pyramid_builder.py`
Builds `num_octaves` (default 5) octaves at 30/60/120/240/480 m:
- For each octave k: Gaussian filter with σ = 0.85·2^k applied to the base tile, then 2^k decimation.
- Nodata-aware (normalized convolution): nodata pixels replaced by 0, weighted by Gaussian of validity mask.
- Coarse inputs (base_resolution_m > octave resolution): finer octaves set to `-9999.0` nodata; only physically valid octaves populated.

### 4.3 `tile_writer.py`
- `write_ptile(...)`: packs 128-byte header + per-octave float32 payload (C-contiguous).
- `write_json_sidecar(...)`: metadata JSON.
- `read_header(...)`: parse header.
- CLI `main()`: generates a synthetic tile for testing.

### 4.4 `cli.py`
Batch standardization entrypoint: reads a JSON manifest of tiles, reprojects each at 30 m/px, builds pyramid, writes `.ptile` + `.json` per domain.

---

## 5. Datasets Branch (`Datasets/`)

### 5.1 Ingestion Pipelines
- `pipelines/earth_ingest.py`: declarative STAC manifest generator for 310 entries across 31 Earth candidate regions × 5 domains (topography/mineralogy/thermal/granular/volatiles). Sources: Copernicus DEM GLO-30, ASTER, Sentinel-2, ECOSTRESS, MODIS, Sentinel-1 SAR, SMAP, etc. Bulk data lands in `./data_lake/` (gitignored).
- `pipelines/moon_mars_ingest.py`: PDS manifest for 8 reference targets × their datasets.
- `pipelines/gen_golden_tiles.py`: deterministic generator for 10 golden tiles (20.6 MB total), all 5 domains, 3 bodies.

### 5.2 Reference Targets (8)
Moon: Shackleton–de Gerlache (Artemis III), Malapert Massif (comms), Aristarchus Plateau (ISRU), Marius Hills Skylight (subsurface habitat).
Mars: Jezero Western Fan, Arcadia Planitia (ISRU ice), Arsia Mons Pits, Bagnold Dunes (aeolian/mobility).

### 5.3 Earth Candidate Grid
31+ regions emphasizing arid, volcanic, polar, impact, karst/lava-tube terrains (Anti-Atlas, Lut Desert, Qaidam, Afar, Puna, Undara, Jeju, Canadian Arctic, Yakutia, etc.).

### 5.4 Known-Analog Suppression Mask
`known_analogs_mask.geojson`: 150 km buffers around Atacama, McMurdo, Haughton, Iceland, Mauna Kea/Kilauea, Mojave, Death Valley, Rio Tinto, Svalbard.

### 5.5 Golden Tiles
10 deterministic `.ptile` + `.json` pairs (256×256 base, 5 octaves), covering all 5 domains across Earth/Moon/Mars. `manifests/checksums.json` stores SHA-256 + sizes.

---

## 6. Reference Algorithm Architecture (v2.0 Local-Distribution Matching)

All five domain modules implement v2.0 standardized local-distribution matching (`BestAlgo/<module>/algo.py` serves as the verification reference; production sweeps run exclusively on `OptiAlgo/*` C++20):
```python
compute_similarity(earth_tile_path, target_tile_path, out_hmap_path, out_breakdown_path) -> None
```

### Algorithm (v2.0)
For each octave `k in [0..4]` (`30, 60, 120, 240, 480 m/px`):
- **Physical-bounds z-score normalization**: Each channel is standardized against physical reference bounds and clipped to `[-5, 5]`; `-9999.0f` nodata is preserved as `NaN`.
- **Target octave signature**: Computes per-channel target `mean`, `std`, exact linear quantiles `[Q10, Q25, Q50, Q75, Q90]`, and finite-difference texture energy on native target dimensions (zero spatial stretching; DEF-01 zoom removed).
- **Sliding-window local distribution**: Over window radius `r_k = max(3, 15 >> k)` (`31×31` at `30 m` down to `7×7` at `480 m`), computes Wasserstein-1 quantile distance `W1 = (1/5) sum |q_e - q_t|` and normalized texture mismatch `deltaE = |E_e - E_t| / (E_e + E_t + 1e-6)`:
  - `D = (1/C) sum_c (0.75 * W1_c + 0.25 * deltaE_c)`
  - `sim = exp(-D)`
  - `conf = f_valid / (1 + (1/C) sum_c |sigma_e - sigma_t|)` where `f_valid` is the minimum valid pixel fraction across channels (`sim = 0, conf = 0` when center pixel is nodata, `f_valid < 0.25`, or target octave is all-nodata).
- **Domain-specific channels & flags**:
  - `topography`: 6 stored channels + runtime low-angle solar illumination proxy `sin(slope_rad) * cos(aspect_rad)` as channel 6 (7 effective similarity channels); emits `NO_ATMOSPHERE_TARGET` for Moon.
  - `mineralogy`: 8 channels; evaluates channel-7 `NDVI` on the **Earth candidate** (`eoct` / `eraw[7]`, DEF-04 fixed) to emit `BIOSPHERE_OVERPRINT` (`Moon NDVI > 0.15` or `Mars NDVI > 0.25`) or `ASTROBIOLOGY_EXTREMOPHILE_ANALOG` (`Mars 0.05 < NDVI <= 0.25`).
  - `thermal_illumination`: 5 channels; emits `CRYOGENIC_FLOOR_DELTA` (`Earth T_min - Target T_min`) and `THERMAL_TEST_CHAMBER_CORRECTION`.
  - `granular_aeolian`: 5 channels; emits `GRAVITY_ADJUSTED_SALTATION` (`u*_t` scaling with `sqrt(g)`).
  - `volatiles_subsurface`: 5 channels; emits `SUBSURFACE_VOID_SCORING`.

**Scale-invariance index**: `1 - std(per-octave valid mean sim)` clamped to `[0, 1]`.

---

## 7. OptiAlgo (C++20 Production Engine) Modules

Each module (`OptiAlgo/<module>`):
- `include/distribution_v2.hpp`: shared v2.0 C++20 local-distribution kernel.
- `include/<module>.h` & `src/<module>.cpp`: C ABI `extern "C" int32_t run_module(earth, target, out_hmap, out_breakdown)`.
- `bindings.py`: `ctypes` wrapper exposing `compute_similarity(...)` (auto-builds `.so` if missing).
- `build.sh`: `g++ -O3 -march=native -fopenmp -std=c++20 -shared -fPIC`.

### Implementation details
- **Zero-copy I/O**: `open()` + `mmap(PROT_READ, MAP_PRIVATE)` for inputs; `ftruncate()` + `mmap(PROT_READ|PROT_WRITE, MAP_SHARED)` for output.
- **No heap allocation in hot loops**: per-pixel windows use fixed stack/thread-local buffers; OpenMP `#pragma omp parallel for collapse(2)` with `std::nth_element` quantile selection.
- **No spatial stretching**: native target octave signatures replace v1 `ti = i * th_Hk / Hk` indexing.
- **Breakdown JSON**: `scale_invariance_index`, `channel_residuals` (`earth_mean`, `target_mean`, `z_divergence`), and `physical_breakdown_flags` (with Earth-side `eraw[7].mean` NDVI check).

### Parity & ASAN gate results (verified post-DEF-04/DEF-01)
| Module | Golden pair | RMSE (sim) | RMSE (conf) | SSIM | Speedup | ASAN/UBSan |
|---|---|---:|---:|---:|---:|---|
| topography | Earth Anti-Atlas -> Mars Arcadia | 9.31e-9 | 5.06e-8 | 1.000000 | 13.00x | PASS (`rc=0`) |
| mineralogy | Earth Danakil -> Moon Aristarchus | 1.39e-8 | 3.46e-8 | 1.000000 | 41.41x | PASS (`rc=0`) |
| thermal_illumination | Earth LUT Desert -> itself | 2.11e-8 | 4.78e-8 | 1.000000 | 10.10x | PASS (`rc=0`) |
| granular_aeolian | Earth Tanezrouft -> Mars Bagnold | 1.64e-8 | 3.38e-8 | 1.000000 | 41.19x | PASS (`rc=0`) |
| volatiles_subsurface | Earth Undara -> Mars Arsia Mons | 1.44e-8 | 2.34e-8 | 1.000000 | 38.14x | PASS (`rc=0`) |

---

## 8. Fusion Module (`main/fusion/`)

### `engine.py`
- `composite_similarity(module_scores, weights)`: weighted composite per octave, renormalizing over valid (non-zero/nodata) modules per pixel.
- `scale_invariance_filter(composite)`: I_scale = 1 − StdDev_σ(S_total); invalidates all-zero regions (I_scale=0).
- `fuse(...)`: returns `{composite, filtered, scale_invariance_index}`.

### `novelty_mask.py`
- `apply_suppression(lat, lon, mask_features)`: down-weights locations within 150 km of known analogs.
- `apply_mask_grid(lats, lons, mask_features)`: vectorized grid of suppression weights.

### `breakdown_synthesizer.py`
- `synthesize_site_dossier(...)`: assembles site_id, coordinates, module scores, breakdown, mission test.

### `mission_mapper.py`
- Maps 8 reference targets to specific Artemis/Mars engineering tests (e.g., "Autonomous Lidar Hazard Detection under 1.5° grazing illumination", "High-Ti basaltic regolith beneficiation").

---

## 9. Benchmark & Verification (`main/benchmark/`)

### `verify_parity.py`
CLI: `--py`, `--cpp`, `--earth`, `--target`, `--out-dir`.
- Loads Python and C++ `compute_similarity` via importlib/ctypes.
- Runs both, reads `.hmap` outputs, computes RMSE (ch0 + ch1), SSIM, latency, speedup.
- Gates: RMSE < 1e-5, SSIM > 0.9995, speedup ≥ 10×, breakdown_pass (scale_invariance_index + channel keys match).
- Exit code 0 on pass.

### `run_asan.sh`
Compiles C++ with `-fsanitize=address,undefined`, runs ctypes smoke test on provided tiles.

---

## 10. Interactive WebGIS Dashboard (`main/app/`)

FastAPI + Leaflet + Chart.js WebGIS dashboard (`app/main.py` & `app/static/index.html`):
- `GET /`: serves interactive Leaflet + Chart.js WebGIS map UI (target selector, domain selector, `30 m–480 m` octave slider, `150 km` novelty toggle, and physical breakdown drawer).
- `GET /health`: service health and data-lake availability.
- `GET /targets`: returns the 8 Moon/Mars reference targets.
- `GET /octaves`: returns `[30, 60, 120, 240, 480]`.
- `GET /novelty-mask`: toggles `150 km` known-analog suppression (`enabled=true|false`).
- `GET /api/discoveries`: ranked analog discoveries per `target_id` and `novelty_masked` flag.
- `GET /api/geojson/known-analogs`: GeoJSON overlay of `150 km` known-analog suppression buffers.
- `GET /api/heatmap/{site_id}/{target_id}/{domain}/{octave}.png`: renders RGBA PNG heatmap overlay from `.hmap` tiles.
- `GET /breakdown/{site_id}`: returns per-channel residuals, physical breakdown flags, and mission protocols.

---

## 11. Execution DAG (Phase Summary)

- **Phase 0**: Bootstrap (dirs, .gitignore, schema commit, 12 branches).
- **Phase 1**: Dataset processor (main) + Moon/Mars targets + Earth candidate grid (Datasets) in parallel.
- **Phase 2**: 5 Python reference modules in parallel.
- **Phase 3**: 5 C++ optimized modules in parallel, gated by parity.
- **Phase 4**: Global sweep, composite fusion, novelty ranking, breakdown synthesis, mission mapping.
- **Phase 5**: WebGIS dashboard, documentation (README, METHODOLOGY, BENCHMARKS).

---

## 12. Invariants Enforcement

| Invariant | Enforcement |
|---|---|
| Zero raw rasters in git | `.gitignore` blocks `*.tif`, `*.img`, `*.cub`, `*.h5`, `*.nc`, `data_lake/`; Datasets stores only manifests/scripts/checksums/golden_tiles. |
| Equal-area metric | `reproject_laea.py` projects to LAEA with planetary radius; no lat/lon in outputs. |
| Domain separation | Separate `.ptile` per domain; independent pipelines; late fusion only. |
| Python/C++ parity | `verify_parity.py` gates RMSE/SSIM/speedup/mmap/ASAN. |
| Scientific completeness | Multi-scale heatmaps + breakdown vector + mission test mapping in fusion. |

---

## 13. Empirical Discovery Findings & Case Studies (v2.0)

### 13.1 Top 10 Previously Unrecognized Earth Analog Sites (pending Phase C sweep)

| Rank | Site | Target Analog | Composite Score | Scale-Invariance | Novelty Weight | Primary Use Case |
|---|---|---|---|---|---|---|
| 1 | Anti-Atlas / Draa Hammada, Morocco | Moon (Shackleton Rim) | pending | pending | pending | Lunar polar illumination & regolith |
| 2 | Mistastin Lake, Canada | Moon (Malapert) | pending | pending | pending | Anorthositic highland analog |
| 3 | Qaidam Basin, China | Mars (Jezero) | pending | pending | pending | Sulfate/clay evaporite analog |
| 4 | Afar Depression, Ethiopia | Mars (Jezero) | pending | pending | pending | Hydrothermal sulfates & basalts |
| 5 | Undara Lava Tubes, Australia | Moon (Marius Hills) / Mars (Arsia Mons) | pending | pending | pending | Subsurface habitat analog |
| 6 | Lut Desert, Iran | Mars (Arcadia) | pending | pending | pending | Thermal extremes & basaltic regolith |
| 7 | Tanezrouft Basin, Algeria/Mali | Moon (Malapert) | pending | pending | pending | Hyper-arid flat gravel plains |
| 8 | Yakutia Thermokarst, Siberia | Mars (Arcadia) | pending | pending | pending | Permafrost ice-table analog |
| 9 | Kumtagh Feather Dunes, China | Mars (Bagnold Dunes) | pending | pending | pending | Aeolian bedform analog |
| 10 | Jebel Saghro, Morocco | Moon (Aristarchus) | pending | pending | pending | Alkaline volcanic plateau |

*Scores pending execution of Phase C global sweep (`fusion/run_discovery_sweep.py --backend cpp` via C++20 `OptiAlgo/*`) on real standardized tiles.*

### 13.2 Deep-Dive Scientific Case Studies

**Case Study 1: Anti-Atlas / Draa Hammada, Morocco (Artemis Lunar Analog)**
- Multi-scale physical similarities: basaltic/quartzitic desert pavement, impact-like scarps, low-angle illumination regimes.
- Breakdown limits: gravity 1g vs 0.165g, atmospheric pressure 101325 Pa vs 3e-10 Pa, radiation delta, thermal floor delta (~190 K gap vs lunar PSRs).
- Engineering test protocol: Autonomous Lidar Hazard Detection & Avoidance under 1.5 deg grazing illumination; high-Ti regolith beneficiation.

**Case Study 2: Qaidam Basin, China (Mars Jezero Analog)**
- Multi-scale similarities: sulfate/clay evaporites, wind-sculpted ridges, fluvio-lacustrine morphology.
- Breakdown limits: gravity 1g vs 0.379g, CO2 atmosphere 610 Pa vs 101325 Pa, radiation, thermal.
- Engineering test protocol: Astrobiology sampling & deltaic stratigraphy analysis; rover mobility on evaporite surfaces.

**Case Study 3: Undara Lava Tubes, Australia (Subsurface Habitat Analog)**
- Multi-scale similarities: basaltic lava tube skylights, collapse pit geometry, thermal damping at pit floors.
- Breakdown limits: gravity, atmosphere, radiation, thermal.
- Engineering test protocol: Subsurface lava-tube robotic mesh-network navigation; ISRU water-ice excavation.

### 13.3 v2.0 Algorithm Summary
The v2.0 engine replaces pixel-to-pixel raw cosine similarity with feature-standardized, scale-matched local-distribution comparison:
- Physical-bounds z-score normalization (clip [-5, 5])
- Target octave statistical signature (mean, std, 5 quantiles, texture energy)
- Sliding-window Wasserstein-1 quantile distance + texture-gradient mismatch
- Confidence with valid-fraction and std matching
- Dual-mode Mars/Moon NDVI handling (biosphere overprint vs extremophile analog)
- Topography illumination proxy (sin(slope)*cos(aspect))
