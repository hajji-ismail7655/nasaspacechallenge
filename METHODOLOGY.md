# Methodology (v2.0)

## Cross-Planetary Terrestrial Analog Discovery Engine

### 1. Equal-Area Metric Standardization
All spatial data projected to local Lambert Azimuthal Equal-Area (LAEA) metric grids
using planetary radii: Earth 6371.0 km, Moon 1737.4 km, Mars 3389.5 km.
No lat/lon comparison.

### 2. Multi-Scale Octaves
5 octaves: 30, 60, 120, 240, 480 m/px via Gaussian anti-aliasing (sigma=0.85*2^k)
prior to 2^k decimation. Coarser inputs populate valid higher octaves; finer octaves
set to nodata (-9999.0).

### 3. Domain Separation
Five isolated domains: topography, mineralogy, thermal_illumination, granular_aeolian,
volatiles_subsurface. Each processed independently before late fusion.

### 4. v2.0 Standardized Local-Distribution Matching (Phase A)
Replaces pixel-to-pixel raw cosine similarity with feature-standardized, scale-matched
local-distribution comparison:

**Channel Standardization**: Every valid pixel in channel c is z-scored using fixed
physical reference constants (mu_ref, sigma_ref) per domain, clipped to [-5, 5].
Nodata pixels preserved as NaN.

**Target Octave Signature**: For each valid octave, extract per-channel:
- Standardized mean and std
- 5-point quantile vector [Q10, Q25, Q50, Q75, Q90]
- Spatial texture energy (mean local finite-difference gradient magnitude)

**Local-Window Distribution Matching**: Sliding window (radius r_k = max(3, 15>>k),
producing 31x31 at 30m scaling to 7x7 at 480m). For each Earth pixel:
- f_valid = min over channels of valid pixel fraction in window
- If center nodata, f_valid < 0.25, or target octave all-nodata: sim=0, conf=0
- Per-channel Wasserstein-1 distance: W1 = (1/5) sum |q_e - q_t|
- Texture mismatch: deltaE = |E_e - E_t| / (E_e + E_t + 1e-6)
- D = (1/C) sum_c (0.75*W1_c + 0.25*deltaE_c)
- sim = exp(-D)
- conf = f_valid * 1/(1 + (1/C) sum |sigma_e - sigma_t|)

**Elimination of spatial stretching**: Target signature is an octave distribution,
not a pixel grid. Earth and Target compare at identical physical meter-per-pixel
resolutions with zero spatial index stretching.

### 5. Dual-Mode Biosphere Handling (mineralogy)
- Moon targets: NDVI > 0.15 → BIOSPHERE_OVERPRINT flag (classification; sim multiplier reserved for v2.1)
- Mars targets: NDVI > 0.25 → BIOSPHERE_OVERPRINT flag; 0.05 < NDVI <= 0.25 with elevated
  clays/sulfates/carbonates → ASTROBIOLOGY_EXTREMOPHILE_ANALOG flag (affinity boost reserved for v2.1)

### 6. Topography Illumination Proxy
Explicit low-angle illumination proxy sin(slope)*cos(aspect) appended as an
additional feature channel (using raw slope/aspect in degrees converted to radians).

### 7. Parity Gate
Python reference (BestAlgo) vs C++ optimized (OptiAlgo): RMSE<1e-5, SSIM>0.9995,
>=10x speedup, zero-copy mmap, no heap alloc in kernels, ASAN clean.
Breakdown JSON parity: scale_invariance_index within 1e-5, matching channel_residuals keys and values.

### 8. Scientific Completeness (Similarity + Breakdown + Mission Utility)
No candidate site valid without multi-scale similarity heatmaps, quantitative
Analogy Breakdown Vector, and explicit Artemis/Mars engineering test mapping.