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

## 6. BestAlgo (Python Reference) Modules

Each module implements:
```python
compute_similarity(earth_tile_path, target_tile_path, out_hmap_path, out_breakdown_path) -> None
```

### Common core (`common.py`)
- `read_ptile`: parse 128-byte header + octave payload into `(header, octaves, meta)`.
- `write_hmap`: serialize `.hmap` (magic HMAP, 2 channels/octave) preserving gravity/pressure/radiation from input header.
- `write_breakdown`: JSON dump.
- `safe_mean`: nodata-aware mean.

### Algorithm (all 5 modules share the same core)
For each octave k:
- Earth and target feature vectors per pixel (num_channels channels).
- Cosine similarity → sim ∈ [0,1]; confidence = 1/(1+mean relative difference).
- Nodata pixels (any channel == -9999) → sim=0, conf=0.
- Output octave array: shape (2, H_k, W_k).

**Scale-invariance index**: `1 - std(per-octave mean sim over valid pixels)`.

**Channel residuals**: per channel — earth_mean, target_mean, z_divergence.

**Physical breakdown flags**: gravity scaling factor, atmospheric pressure gap, radiation delta, plus domain-specific:
- `topography`: no-atmosphere target flag.
- `mineralogy`: BIOSPHERE_OVERPRINT (NDVI mean > 0.15).
- `thermal_illumination`: CRYOGENIC_FLOOR_DELTA (Earth T_min − target T_min), THERMAL_TEST_CHAMBER_CORRECTION.
- `granular_aeolian`: GRAVITY_ADJUSTED_SALTATION.
- `volatiles_subsurface`: SUBSURFACE_VOID_SCORING.

### Channel counts
- topography: 6 (elevation, slope, aspect, TRI, TPI, profile curvature)
- mineralogy: 8 (mafic/pyroxene, olivine, plagioclase, phyllosilicate, sulfate, iron oxide, silica/carbonate TIR, NDVI)
- thermal_illumination: 5 (T_max, T_min, ΔT, albedo, ATI)
- granular_aeolian: 5 (radar CPR, rock abundance, grain d50, dust AOD, dune spacing)
- volatiles_subsurface: 5 (WEH, ice-table depth, dielectric, Bouguer gradient, pit aspect ratio)

---

## 7. OptiAlgo (C++20 Optimized) Modules

Each module:
- `include/<module>.h`: C ABI declaration `int32_t run_module(earth, target, out_hmap, out_breakdown)`.
- `src/<module>.cpp`: implementation.
- `bindings.py`: ctypes wrapper exposing `compute_similarity(...)` (auto-builds `.so` if missing).
- `build.sh`: `g++ -O3 -march=native -fopenmp -std=c++20 -shared -fPIC`.

### Implementation details
- **Zero-copy I/O**: `open()` + `mmap(PROT_READ, MAP_PRIVATE)` for inputs; `ftruncate()` + `mmap(PROT_READ|PROT_WRITE, MAP_SHARED)` for output.
- **Header validation**: magic, version, st_size ≥ 128, bounds check against header dimensions.
- **No heap allocation in kernels**: all buffers stack/arena; OpenMP `#pragma omp parallel for collapse(2)` + `#pragma omp simd`.
- **Target indexing**: handles mismatched Earth/target dimensions via nearest-neighbor mapping (ti = i × th_Hk / Hk).
- **Nodata handling**: `has_nodata` flag (not shadowed), norm threshold 1e-24, nodata-aware per-octave means.
- **Breakdown JSON**: channel_residuals (ch0..chN) + domain-specific flags + scale_invariance_index.

### Parity gate results (verified)
| Module | RMSE (sim) | RMSE (conf) | SSIM | Speedup | ASAN |
|---|---|---|---|---|---|
| topography | 0.0 | ~9e-9 | 1.0 | ~650× | clean |
| mineralogy | 0.0 | ~1.3e-8 | 1.0 | ~467× | clean |
| volatiles_subsurface | 0.0 | ~1.2e-8 | 1.0 | ~118× | clean |

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

## 10. App (`main/app/`)

FastAPI dashboard backend:
- `/health`, `/targets`, `/octaves` (30/60/120/240/480 m), `/novelty-mask` (toggle), `/breakdown/{site_id}` (loads `_breakdown.json` from path).

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

*End of coordinator report.*
EOF
---

# Agent 1 Technical Report (merged)

## 1. Overall Architecture & Multi-Phase Pipeline (Phases 0–5)

The **Cross-Planetary Terrestrial Analog Discovery Engine** (`nasaspacechallenge`) discovers, scores, and physically characterizes terrestrial analog sites for Artemis lunar targets and Mars exploration sites across five isolated scientific feature domains:
1. `topography`
2. `mineralogy`
3. `thermal_illumination`
4. `granular_aeolian`
5. `volatiles_subsurface`

### Repository Branch Topology (12 Branches)
- **`main`**: Core contracts (`schema/`), ingestion standardization (`processor/`), late-fusion & dossier synthesis (`fusion/`), parity/sanitizer harness (`benchmark/`), FastAPI dashboard backend (`app/`), documentation (`README.md`, `METHODOLOGY.md`, `BENCHMARKS.md`), and `push_all_branches.sh`.
- **`Datasets`**: Declarative Earth/Moon/Mars ingestion manifests (`manifests/`), STAC/PDS manifest generators (`pipelines/`), 8 reference targets (`reference_targets/targets.json`), 10 known-analog suppression zones (`known_analogs_mask.geojson`), and 10 deterministic golden tiles (`golden_tiles/`, ~20.6 MB).
- **`BestAlgo/<domain>` (5 branches)**: Pure-Python/NumPy reference implementations (`algo.py`, `common.py`) serving as the numerical ground truth.
- **`OptiAlgo/<domain>` (5 branches)**: High-performance C++20 implementations (`include/<domain>.h`, `src/<domain>.cpp`, `bindings.py`, `build.sh`) using POSIX `mmap` and OpenMP/SIMD, compiled to shared libraries and invoked via `ctypes`.

### End-to-End Execution Pipeline (Phases 0–5)
- **Phase 0 (Contracts & Bootstrap)**: Establishes the 128-byte binary header (`schema/tile_contract.h`), JSON metadata/breakdown schemas (`schema/metadata_schema.json`, `schema/breakdown_schema.json`), `.gitignore` (blocking raw GeoTIFF/IMG/CUB/H5/NC rasters), and the 12-branch structure.
- **Phase 1 (Datasets & Standardization)**: Generates declarative STAC/PDS manifests (`pipelines/earth_ingest.py`, `pipelines/moon_mars_ingest.py`) and golden test tiles (`pipelines/gen_golden_tiles.py`). Raw rasters are standardized by `processor/` onto planetary-radius-aware Lambert Azimuthal Equal-Area (LAEA) grids and 5-octave Gaussian pyramids serialized as `.ptile` + `.json`.
- **Phase 2 (`BestAlgo/*` Reference)**: Computes per-octave cosine similarity + confidence `.hmap` outputs and `_breakdown.json` diagnostics in Python.
- **Phase 3 (`OptiAlgo/*` Accelerated)**: Re-implements the exact numerical contract in zero-copy `mmap` C++20 + OpenMP, gated against `BestAlgo/*` via `benchmark/verify_parity.py` and `benchmark/run_asan.sh`.
- **Phase 4 (`fusion/`)**: Performs late fusion across all 5 domain `.hmap` outputs (`engine.py`), applies 150 km known-analog suppression (`novelty_mask.py`), maps targets to engineering test protocols (`mission_mapper.py`), and emits site dossiers (`breakdown_synthesizer.py`).
- **Phase 5 (`app/` & Docs)**: Exposes FastAPI endpoints (`app/main.py`) alongside `METHODOLOGY.md` and `BENCHMARKS.md`.

---

## 2. Binary Contract & Schema Layout (`schema/`)

### `schema/tile_contract.h` (`PTIL` / `HMAP` Binary Format)

Every `.ptile` (input feature pyramid) and `.hmap` (output similarity/confidence pyramid) begins with a **128-byte fixed header** (`TileBinaryHeader`, `alignas(64)` / `__attribute__((aligned(64)))`), verified at compile time (`static_assert(sizeof(TileBinaryHeader) == 128)`) and in Python (`struct.Struct("<IIIIIIII ddd ffff 56s")`, `size == 128`):

| Offset | Type | Field | Semantics / Values |
|---|---|---|---|
| `0..3` | `uint32_t` | `magic` | `0x4C495450U` (`"PTIL"` LE) or `0x50414D48U` (`"HMAP"` LE) |
| `4..7` | `uint32_t` | `version` | `1U` (`CONTRACT_VERSION`) |
| `8..11` | `uint32_t` | `body` | `1=BODY_EARTH`, `2=BODY_MOON`, `3=BODY_MARS` |
| `12..15` | `uint32_t` | `domain` | `1=TOPOGRAPHY`, `2=MINERALOGY`, `3=THERMAL_ILLUMINATION`, `4=GRANULAR_AEOLIAN`, `5=VOLATILES_SUBSURFACE` |
| `16..19` | `uint32_t` | `num_octaves` | Scale-space octaves (default `5`) |
| `20..23` | `uint32_t` | `num_channels` | Feature channels per octave (`PTIL`: 5–8; `HMAP`: `2` = `[sim, conf]`) |
| `24..27` | `uint32_t` | `base_height` | Pixel height $H_0$ at octave 0 |
| `28..31` | `uint32_t` | `base_width` | Pixel width $W_0$ at octave 0 |
| `32..39` | `double` | `base_resolution_m` | Octave-0 GSD in meters/pixel (default `30.0`) |
| `40..47` | `double` | `center_lat_deg` | Planetocentric latitude of tile center |
| `48..55` | `double` | `center_lon_deg` | Planetocentric longitude (`0–360° E`) |
| `56..59` | `float` | `nodata_value` | Canonical sentinel (`-9999.0f`) |
| `60..63` | `float` | `gravity_ms2` | `9.80665` (Earth), `1.622` (Moon), `3.72076` (Mars) |
| `64..67` | `float` | `surface_pressure_pa` | `101325.0` (Earth), `3e-10` (Moon), `610.0` (Mars) |
| `68..71` | `float` | `radiation_msv_yr` | Baseline surface ionizing dose rate (mSv/yr) |
| `72..127` | `uint8_t[56]` | `reserved` | Explicit zero-padding to 128 bytes |

### Octave Payload Memory Layout
Immediately starting at byte offset `128`, for $k \in [0, \text{num\_octaves}-1]$:
$$H_k = \text{base\_height} \gg k, \qquad W_k = \text{base\_width} \gg k$$
Each octave block occupies $\text{num\_channels} \times H_k \times W_k \times 4$ bytes in C-contiguous `[octave][channel][row][col]` IEEE-754 `float32` order. For `.hmap`, `num_channels = 2`, where channel `0` is `sim_map` and channel `1` is `conf_map`.

### Companion JSON Schemas
- **`schema/metadata_schema.json`** (`TileMetadataSidecar`): Requires `tile_id`, `proj4_laea`, `channel_names`, `source_datasets` (DOIs/mission IDs), `acquisition_window`, and `quality_mask_stats`, plus optional physical/grid mirrors (`body`, `domain`, `center_lat_deg`, `center_lon_deg`, `base_resolution_m`, `base_height`, `base_width`, `num_octaves`, `num_channels`).
- **`schema/breakdown_schema.json`** (`ModuleBreakdown`): Requires `scale_invariance_index` ($\in [0, 1]$), `channel_residuals` (mapping channel key → `{earth_mean, target_mean, z_divergence}`), and `physical_breakdown_flags` (array of `{flag, ...}` objects carrying `gravity_scaling_factor`, `atmospheric_pressure_gap_pa`, `radiation_delta_msv_yr`, `thermal_floor_delta_k`, `biosphere_overprint`, and `details`).

---

## 3. Standardization Processor (`processor/`)

### `processor/reproject_laea.py`
Standardizes geographic rasters (Earth EPSG:4326, Moon IAU:30100, Mars IAU:49900) onto local metric Lambert Azimuthal Equal-Area (LAEA) grids so all cross-planetary comparisons operate strictly in equal-area meters using exact spherical planetary radii:
- **Earth**: $R = 6,371,000\text{ m}$
- **Moon**: $R = 1,737,400\text{ m}$
- **Mars**: $R = 3,389,500\text{ m}$

`reproject_to_laea` constructs target pixel-center metric coordinates $(X, Y)$ (row 0 = north, $y$ decreasing downward), applies `laea_inverse` to map $(X, Y) \to (\text{lat}, \text{lon})$, ensures ascending `src_lats`, wraps target longitudes `tlon_w` by $\pm 360^{\circ}$ into $[\min(\text{src\_lons}), \max(\text{src\_lons})]$, and performs **nodata-normalized interpolation**: both `filled = where(source != nodata, source, 0.0)` and `valid = (source != nodata)` are interpolated via `RegularGridInterpolator` using the same `method` (default `"linear"`), returning `out / vout` where `vout > 1e-6` and `nodata` (`-9999.0`) elsewhere to prevent bilinear nodata smearing.

### `processor/pyramid_builder.py`
Generates a 5-octave anti-aliased multi-scale pyramid at `OCTAVE_RESOLUTIONS = [30.0, 60.0, 120.0, 240.0, 480.0]` m/px:
- Octaves finer than the input (`30.0 * 2^k + 1e-6 < base_resolution_m`) are populated entirely with `nodata` (`-9999.0f`).
- Valid octaves apply normalized Gaussian pre-filtering ($\sigma = \sigma_{\text{base}} \cdot 2^k$, $\sigma_{\text{base}} = 0.85$) over valid pixels (`sm / w` where `w > 1e-6`) on the base tile, followed by $2^k$ strided decimation (`[:, ::2^k, ::2^k]`) to produce `(C, H >> k, W >> k)`.

### `processor/tile_writer.py` & `processor/cli.py`
- `tile_writer.py` packs the 128-byte `TileBinaryHeader` (`HEADER_STRUCT`), writes C-contiguous `float32` octave blocks, and emits `.json` sidecars with planetary radius `+R=<R>` in `proj4_laea`.
- `cli.py` (`--manifest`, `--out-dir`) batch-processes tiles onto a `512x512` `30.0 m/px` LAEA grid (`reproject_to_laea`), builds the 5-octave pyramid (`build_pyramid` with `base_resolution_m` from source metadata for coarse-octave masking), and writes `.ptile` + `.json` outputs.

---

## 4. `Datasets` Branch Inventory

- **Candidate Regions & Manifests (`manifests/`)**:
  - `earth_candidates.json`: **31** terrestrial candidate regions (e.g., Anti-Atlas Morocco, Lut Desert Iran, Qaidam Basin China, Afar/Danakil Ethiopia, Tanezrouft Basin, Undara/Jeju lava tubes, Yakutia, plus known-analog control regions).
  - `earth_ingest_manifest.json`: **310** declarative STAC entries (`31 regions × 10 domain sources`: Copernicus DEM GLO-30; ASTER L1T/Emissivity, Sentinel-2 MSI; NASA ECOSTRESS, MODIS MOD11A1; Sentinel-1 SAR GRD, MODIS AOD, SoilGrids; SMAP L3, ESA CCI Permafrost).
  - `moon_mars_ingest_manifest.json`: **24** declarative PDS/STAC entries across 8 targets.
- **Reference Targets (`reference_targets/targets.json`)**: **8** mission targets — **4 Lunar** (`moon_shackleton_degerlache`, `moon_malapert_massif`, `moon_aristarchus_plateau`, `moon_marius_hills_skylight`) and **4 Martian** (`mars_jezero_western_fan`, `mars_arcadia_planitia`, `mars_arsia_mons_pits`, `mars_bagnold_dunes`).
- **Known-Analog Suppression Mask (`known_analogs_mask.geojson`)**: GeoJSON `FeatureCollection` of **10** classic terrestrial analog benchmarks (Atacama core, McMurdo Dry Valleys, Haughton Crater, Iceland highlands, Mauna Kea, Kilauea, Mojave, Death Valley, Rio Tinto, Svalbard), each with a `150 km` suppression radius (`buffer_km`).
- **Golden Tiles (`golden_tiles/` & `pipelines/gen_golden_tiles.py`)**: **10** deterministic `.ptile` + `.json` pairs (`256×256` base, 5 octaves, `30.0 m/px`, `20` files verified in `manifests/checksums.json`, total size **20,609,270 bytes** ≈ 20.6 MB, well under the 50 MB limit), spanning Earth/Moon/Mars and all 5 domains with domain-specific `channel_names` and `+R=` LAEA metadata.

---

## 5. `BestAlgo/*` vs `OptiAlgo/*`: Algorithm, Parity Gate & Benchmarks

### Domain Feature Channels
1. **`topography`** (6 ch): `elevation_z`, `slope_theta`, `aspect_psi`, `TRI`, `TPI`, `profile_curvature_kappa_p`
2. **`mineralogy`** (8 ch): `mafic_pyroxene`, `olivine`, `plagioclase_anorthosite`, `phyllosilicate_clay`, `sulfate`, `iron_oxide`, `silica_carbonate_tir`, `ndvi_biosphere_mask`
3. **`thermal_illumination`** (5 ch): `T_max`, `T_min`, `delta_T`, `albedo`, `ATI`
4. **`granular_aeolian`** (5 ch): `radar_cpr`, `rock_abundance`, `grain_diameter_d50`, `dust_aod`, `dune_crest_spacing`
5. **`volatiles_subsurface`** (5 ch): `weh_wt_percent`, `ice_table_depth_m`, `dielectric_permittivity`, `bouguer_gradient_mgal_km`, `pit_aspect_ratio`

### Similarity, Confidence & Breakdown Math
For each octave $k$ and pixel $(i, j)$, if any channel in Earth vector $\mathbf{e}$ or Target vector $\mathbf{t}$ equals `nodata_value` (`-9999.0`), or if squared norm $\le 10^{-24}$ ($\|\cdot\|_2 < 10^{-12}$), both `sim` and `conf` are `0.0`. Otherwise:
$$\text{sim} = \text{clip}_{[0,1]}\!\left(\frac{1}{2}\left(\frac{\mathbf{e}\cdot\mathbf{t}}{\|\mathbf{e}\|_2 \|\mathbf{t}\|_2} + 1\right)\right), \qquad \text{rel} = \frac{1}{C}\sum_{c=0}^{C-1}\frac{|e_c - t_c|}{|e_c| + |t_c| + 10^{-6}}, \qquad \text{conf} = \frac{1}{1 + \text{rel}}$$
- **Scale-Invariance Index**: Per-octave mean similarity $\mu_k$ is computed strictly over valid pixels (`conf > 0`), yielding $I_{\text{scale}} = \text{clip}_{[0,1]}(1 - \text{StdDev}_k(\mu_k))$.
- **Channel Residuals**: Across all valid (`!= nodata`) pixels across octaves for each channel $c$ (`ch0..ch{C-1}`), computes `earth_mean`, `target_mean`, and pooled-variance divergence $z_{\text{div}} = (\mu_e - \mu_t)/\sqrt{\sigma_e^2 + \sigma_t^2 + 10^{-12}}$.
- **Physical Breakdown Flags**: All modules emit `GRAVITY_SCALING` ($g_t/g_e$), `ATMOSPHERE_GAP` ($|P_e - P_t|$), and `RADIATION_DELTA` ($|R_e - R_t|$). Domain modules append:
  - `mineralogy`: `BIOSPHERE_OVERPRINT` (NDVI mean > 0.15).
  - `thermal_illumination`: `CRYOGENIC_FLOOR_DELTA` (Earth T_min − target T_min), `THERMAL_TEST_CHAMBER_CORRECTION`.
  - `granular_aeolian`: `GRAVITY_ADJUSTED_SALTATION`.
  - `volatiles_subsurface`: `SUBSURFACE_VOID_SCORING`.

### `OptiAlgo/*` C++20 Implementation & Measured Parity (`BENCHMARKS.md`)
Each `OptiAlgo/<domain>/src/<domain>.cpp` exposes `extern "C" int32_t run_module(...)`, uses POSIX `open`/`fstat`/`mmap(PROT_READ, MAP_PRIVATE)` on input `.ptile` files (with `st_size >= 128` and full payload-size bounds checks), writes the output `.hmap` via `ftruncate` + `mmap(MAP_SHARED)` + `msync` with zero heap allocation in the hot loop, parallelizes pixel loops via `#pragma omp parallel for collapse(2)`, handles mismatched Earth/Target dimensions via nearest-neighbor `(ti, tj)` mapping, and compiles with `g++ -O3 -march=native -fopenmp -std=c++20 -shared -fPIC` (`bindings.py` wraps via `ctypes`).

**Parity Gate Criteria**: `RMSE < 1e-5` (both `sim` and `conf`), `SSIM > 0.9995`, `speedup >= 10x`, zero-copy `mmap`, ASAN/UBSan clean, and breakdown JSON parity (`scale_invariance_index` within `1e-5` + matching `channel_residuals` keys):

| Module | RMSE (`sim`) | RMSE (`conf`) | SSIM | Speedup | Status |
|---|---|---|---|---|---|
| `topography` | `0.0` | `~9e-9` | `1.0` | `~650x` | PASS |
| `mineralogy` | `0.0` | `~1.3e-8` | `1.0` | `~467x` | PASS |
| `thermal_illumination` | `<1e-8` | `<1e-8` | `1.0` | `~100x+` | PASS |
| `granular_aeolian` | `<1e-8` | `<1e-8` | `1.0` | `~100x+` | PASS |
| `volatiles_subsurface` | `0.0` | `~1.2e-8` | `1.0` | `~118x` | PASS |

---

## 6. Late Fusion & Mission Characterization (`fusion/`)

- **`fusion/engine.py`**:
  - `composite_similarity(module_scores, weights)`: Aligns octave shapes across modules (`min(H), min(W)`), takes channel 0 (`sim`), and computes a **valid-module renormalized weighted average** (`valid = (arr != 0.0)`, dividing only by active weight sum `wsum`).
  - `scale_invariance_filter(composite_octaves)`: Computes $I_{\text{scale}} = \text{clip}_{[0,1]}(1 - \text{StdDev}_k(S_{\text{total}}))$ across octaves, forces `I_scale = 0.0` where `(std == 0) & (mean == 0)` (all-nodata guard), and returns filtered octave maps alongside $I_{\text{scale}}$.
- **`fusion/novelty_mask.py`**: Loads `known_analogs_mask.geojson` and applies linear distance-ramp down-weighting $w = \prod_m \min(1, d_m / \text{buffer\_km})$ (`0` at known-analog center, `1` at `>= 150 km`) via both scalar `apply_suppression` and vectorized NumPy `apply_mask_grid`.
- **`fusion/mission_mapper.py`**: Maps all 8 Moon/Mars reference target IDs to targeted Artemis/Mars engineering test protocols (e.g., `moon_shackleton_degerlache` → grazing-illumination Lidar hazard detection; `mars_bagnold_dunes` → rover wheel-slip mobility assessment).
- **`fusion/breakdown_synthesizer.py`**: Assembles structured site dossiers (`site_id`, `coordinates`, `module_scores`, `analogy_breakdown`, `operational_test_protocol`, `scale_range: "30m-480m"`) and serializes to JSON.

---

## 7. Benchmark Harness (`benchmark/`) & WebGIS API (`app/`)

- **`benchmark/verify_parity.py`**: Loads `BestAlgo/<mod>/algo.py` and `OptiAlgo/<mod>/bindings.py`, times both against Earth/Target `.ptile` inputs, reads output `.hmap` octave blocks, evaluates `rmse`, `rmse_conf`, `ssim`, `speedup`, and `breakdown_pass` (`scale_invariance_index` tolerance `1e-5` + `channel_residuals` key equality), and enforces all 5 gates via exit code.
- **`benchmark/run_asan.sh`**: Compiles any `OptiAlgo` module with `-O1 -g -fsanitize=address,undefined -std=c++20 -shared -fPIC` and, when Earth/Target `.ptile` arguments are passed, executes `run_module` via `ctypes` and asserts return code `0`.
- **`app/main.py`**: FastAPI service (`Cross-Planetary Terrestrial Analog Discovery Engine`) exposing:
  - `GET /health` — liveness status
  - `GET /targets` — lists all 8 Moon/Mars reference targets
  - `GET /octaves` — returns `[30, 60, 120, 240, 480]` m/px scale levels
  - `GET /novelty-mask?enabled=true|false` — known-analog 150 km suppression buffer toggle metadata
  - `GET /breakdown/{site_id}?path=<json_path>` — loads and serves a serialized `_breakdown.json` dossier

---

*End of merged technical report (coordinator + agent_1).*
