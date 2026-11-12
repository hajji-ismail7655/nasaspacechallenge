# Methodology

## Cross-Planetary Terrestrial Analog Discovery Engine

### 1. Equal-Area Metric Standardization
All spatial data projected to local Lambert Azimuthal Equal-Area (LAEA) metric grids
using planetary radii: Earth 6371.0 km, Moon 1737.4 km, Mars 3389.5 km.
No lat/lon comparison.

### 2. Multi-Scale Octaves
5 octaves: 30, 60, 120, 240, 480 m/px via Gaussian anti-aliasing (sigma=0.85*2^k)
prior to 2x decimation. Coarser inputs populate valid higher octaves; finer octaves
set to nodata (-9999.0).

### 3. Domain Separation
Five isolated domains: topography, mineralogy, thermal_illumination, granular_aeolian,
volatiles_subsurface. Each processed independently before late fusion.

### 4. Similarity + Breakdown
Per-module cosine similarity of feature vectors across octaves, plus quantitative
Analogy Breakdown Vector (gravity, pressure, radiation, thermal floor, biosphere).

### 5. Parity Gate
Python reference (BestAlgo) vs C++ optimized (OptiAlgo): RMSE<1e-5, SSIM>0.9995,
>=10x speedup, zero-copy mmap, no heap alloc in kernels, ASAN clean.
