"""Shared STAC/PDS query, physical fallback raster synthesis, LAEA reprojection,
and 5-octave .ptile materialization helpers for Datasets/pipelines.
"""
import hashlib
import json
import math
import os
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request

NODATA = -9999.0
MAGIC_PTIL = 0x4C495450
CONTRACT_VERSION = 1
HEADER_STRUCT = struct.Struct("<IIIIIIII ddd ffff 56s")
OCTAVE_RESOLUTIONS = [30.0, 60.0, 120.0, 240.0, 480.0]

BODIES = {
    "earth": {"id": 1, "radius_m": 6371000.0, "gravity": 9.80665, "pressure": 101325.0, "radiation": 2.4},
    "moon": {"id": 2, "radius_m": 1737400.0, "gravity": 1.622, "pressure": 3e-10, "radiation": 250.0},
    "mars": {"id": 3, "radius_m": 3389500.0, "gravity": 3.72076, "pressure": 610.0, "radiation": 230.0},
}

DOMAIN_IDS = {
    "topography": 1,
    "mineralogy": 2,
    "thermal_illumination": 3,
    "granular_aeolian": 4,
    "volatiles_subsurface": 5,
}

CHANNEL_NAMES = {
    "topography": [
        "elevation_z", "slope_theta", "aspect_psi",
        "TRI", "TPI", "profile_curvature_kappa_p",
    ],
    "mineralogy": [
        "mafic_pyroxene", "olivine", "plagioclase_anorthosite", "phyllosilicate_clay",
        "sulfate", "iron_oxide", "silica_carbonate_tir", "ndvi_biosphere_mask",
    ],
    "thermal_illumination": ["T_max", "T_min", "delta_T", "albedo", "ATI"],
    "granular_aeolian": [
        "radar_cpr", "rock_abundance", "grain_diameter_d50", "dust_aod", "dune_crest_spacing",
    ],
    "volatiles_subsurface": [
        "weh_wt_percent", "ice_table_depth_m", "dielectric_permittivity",
        "bouguer_gradient_mgal_km", "pit_aspect_ratio",
    ],
}

# Physical reference means & scales matching OptiAlgo (C++20) v2.0 REFS
CHANNEL_REFS = {
    "topography": [
        (500.0, 1000.0), (15.0, 15.0), (180.0, 103.9),
        (50.0, 50.0), (0.0, 50.0), (0.0, 0.01),
    ],
    "mineralogy": [(0.2, 0.15)] * 7 + [(0.1, 0.1)],
    "thermal_illumination": [(300.0, 50.0), (250.0, 50.0), (50.0, 30.0), (0.2, 0.1), (0.5, 0.3)],
    "granular_aeolian": [(0.3, 0.2), (0.1, 0.1), (100.0, 100.0), (0.1, 0.1), (100.0, 100.0)],
    "volatiles_subsurface": [(5.0, 5.0), (1.0, 1.0), (3.0, 2.0), (0.0, 50.0), (2.0, 2.0)],
}

OFFICIAL_EARTH_RESOURCES = {
    "NASA Earthdata Search": "https://search.earthdata.nasa.gov/",
    "NASA Worldview": "https://worldview.earthdata.nasa.gov/",
    "ESA Copernicus Data Space": "https://dataspace.copernicus.eu/",
    "ESA Open Science Catalog": "https://opensciencedata.esa.int/",
    "CSA RADARSAT-1": "https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1",
    "CSA RCM": "https://donnees-data.asc-csa.gc.ca/en/dataset/rcm",
    "JAXA G-Portal": "https://gportal.jaxa.jp/gpr/index/index",
}

OFFICIAL_MOON_MARS_RESOURCES = {
    "NASA PDS": "https://pds.nasa.gov/",
    "NASA LRO": "https://pds-geosciences.wustl.edu/missions/lro/",
    "NASA LRO Diviner": "https://pds-geosciences.wustl.edu/missions/lro/diviner.htm",
}

PROVENANCE_REAL_ORBITAL_COG = "REAL_ORBITAL_COG"
PROVENANCE_CALIBRATED_FALLBACK = "CALIBRATED_FALLBACK"


def build_channel_provenance(domain, external_grid=None, external_channels=None, channel_provenance=None):
    """Build per-channel provenance mapping (REAL_ORBITAL_COG vs CALIBRATED_FALLBACK)."""
    valid_tags = {PROVENANCE_REAL_ORBITAL_COG, PROVENANCE_CALIBRATED_FALLBACK}
    explicit = channel_provenance or {}
    ext_ch = external_channels or {}
    prov = {}
    for idx, ch_name in enumerate(CHANNEL_NAMES[domain]):
        tag = explicit.get(ch_name, explicit.get(idx))
        if tag in valid_tags:
            prov[ch_name] = tag
        elif external_grid is not None:
            prov[ch_name] = PROVENANCE_REAL_ORBITAL_COG
        elif (ch_name in ext_ch and ext_ch[ch_name] is not None) or (idx in ext_ch and ext_ch[idx] is not None):
            prov[ch_name] = PROVENANCE_REAL_ORBITAL_COG
        else:
            prov[ch_name] = PROVENANCE_CALIBRATED_FALLBACK
    return prov


def norm_lon_deg(lon):
    """Normalize longitude into [-180.0, 180.0)."""
    return ((float(lon) + 180.0) % 360.0) - 180.0


def fetch_json(url, params=None, timeout=3.0):
    """Query an HTTP JSON endpoint cleanly, returning None on network/HTTP errors."""
    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "CrossPlanetaryAnalogEngine/2.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _try_import_processor(main_repo=None):
    """Locate processor.{reproject_laea, pyramid_builder, tile_writer} if available."""
    candidates = []
    if main_repo:
        candidates.append(os.path.abspath(main_repo))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.extend([os.getcwd(), os.path.dirname(here), os.path.dirname(os.path.dirname(here))])
    for base in candidates:
        proc_dir = os.path.join(base, "processor")
        if os.path.isdir(proc_dir) and proc_dir not in sys.path:
            sys.path.insert(0, base)
    try:
        from processor.reproject_laea import reproject_to_laea
        from processor.pyramid_builder import build_pyramid
        from processor.tile_writer import write_ptile, write_json_sidecar
        return reproject_to_laea, build_pyramid, write_ptile, write_json_sidecar
    except Exception:
        return None, None, None, None


def _laea_inverse_np(np, x, y, lat0_deg, lon0_deg, R):
    rho = np.sqrt(x * x + y * y)
    c = 2.0 * np.arcsin(np.clip(rho / (2.0 * R), -1.0, 1.0))
    lat0 = math.radians(lat0_deg)
    lon0 = math.radians(lon0_deg)
    sin_c = np.sin(c)
    cos_c = np.cos(c)
    safe_rho = np.where(rho == 0, 1.0, rho)
    lat = np.arcsin(np.clip(cos_c * math.sin(lat0) + (y * sin_c * math.cos(lat0)) / safe_rho, -1.0, 1.0))
    lon = lon0 + np.arctan2(x * sin_c, rho * math.cos(lat0) * cos_c - y * math.sin(lat0) * sin_c)
    lon = np.where(rho == 0, lon0, lon)
    return np.rad2deg(lat), np.rad2deg(lon)


def _bilinear_reproject_fallback(np, source_2d, src_lats, src_lons, lat0, lon0, body, out_shape, res_m):
    """Pure-NumPy spherical LAEA bilinear reprojection matching processor/reproject_laea.py."""
    R = BODIES[body.lower()]["radius_m"]
    H, W = out_shape
    xs = (np.arange(W, dtype=np.float64) - W / 2.0 + 0.5)[None, :] * res_m
    ys = (H / 2.0 - 0.5 - np.arange(H, dtype=np.float64))[:, None] * res_m
    X = np.broadcast_to(xs, (H, W))
    Y = np.broadcast_to(ys, (H, W))
    tlat, tlon = _laea_inverse_np(np, X, Y, lat0, lon0, R)

    lats = np.asarray(src_lats, dtype=np.float64)
    lons = np.asarray(src_lons, dtype=np.float64)
    arr = np.asarray(source_2d, dtype=np.float64)
    if lats[0] > lats[-1]:
        lats = lats[::-1]
        arr = arr[::-1, :]
    lo, hi = float(lons.min()), float(lons.max())
    for _ in range(5):
        m = tlon < lo
        if not m.any():
            break
        tlon = np.where(m, tlon + 360.0, tlon)
    for _ in range(5):
        m = tlon > hi
        if not m.any():
            break
        tlon = np.where(m, tlon - 360.0, tlon)

    in_bounds = (tlat >= lats[0]) & (tlat <= lats[-1]) & (tlon >= lo) & (tlon <= hi)
    fi = np.interp(tlat.ravel(), lats, np.arange(lats.size, dtype=np.float64)).reshape(H, W)
    fj = np.interp(tlon.ravel(), lons, np.arange(lons.size, dtype=np.float64)).reshape(H, W)
    i0 = np.clip(np.floor(fi).astype(np.int64), 0, lats.size - 2)
    j0 = np.clip(np.floor(fj).astype(np.int64), 0, lons.size - 2)
    di = fi - i0
    dj = fj - j0

    valid = (arr != NODATA).astype(np.float64)
    filled = np.where(arr != NODATA, arr, 0.0)
    w00 = (1.0 - di) * (1.0 - dj)
    w01 = (1.0 - di) * dj
    w10 = di * (1.0 - dj)
    w11 = di * dj
    num = (w00 * filled[i0, j0] + w01 * filled[i0, j0 + 1] +
           w10 * filled[i0 + 1, j0] + w11 * filled[i0 + 1, j0 + 1])
    den = (w00 * valid[i0, j0] + w01 * valid[i0, j0 + 1] +
           w10 * valid[i0 + 1, j0] + w11 * valid[i0 + 1, j0 + 1])
    ok = in_bounds & (den > 1e-6)
    out = np.where(ok, num / np.where(ok, den, 1.0), NODATA)
    return out.astype(np.float32)


def _gaussian_blur_2d_np(np, arr, sigma):
    """Pure-NumPy separable reflected Gaussian blur for standalone Datasets execution."""
    if sigma <= 0:
        return arr.astype(np.float32)
    rad = max(1, int(math.ceil(3.0 * sigma)))
    x = np.arange(-rad, rad + 1, dtype=np.float64)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    tmp = np.pad(arr.astype(np.float64), ((0, 0), (rad, rad)), mode="reflect")
    blurred_x = np.apply_along_axis(lambda r: np.convolve(r, k, mode="valid"), 1, tmp)
    tmp2 = np.pad(blurred_x, ((rad, rad), (0, 0)), mode="reflect")
    blurred_xy = np.apply_along_axis(lambda c: np.convolve(c, k, mode="valid"), 0, tmp2)
    return blurred_xy.astype(np.float32)


def _build_pyramid_fallback(np, tile_chw, base_res, num_octaves=5, sigma_base=0.85):
    C, H, W = tile_chw.shape
    out = []
    for k in range(num_octaves):
        oct_res = 30.0 * (2 ** k)
        Hk, Wk = max(1, H >> k), max(1, W >> k)
        if oct_res + 1e-6 < base_res:
            out.append(np.full((C, Hk, Wk), NODATA, dtype=np.float32))
            continue
        sigma = sigma_base * (2 ** k)
        filtered = np.empty((C, H, W), dtype=np.float32)
        for c in range(C):
            ch = tile_chw[c]
            mask = (ch != NODATA).astype(np.float32)
            filled = np.where(mask > 0, ch, 0.0)
            sm = _gaussian_blur_2d_np(np, filled, sigma)
            w = _gaussian_blur_2d_np(np, mask, sigma)
            ok = (mask > 0) | (w > 1e-6)
            val = np.where(w > 1e-6, sm / np.where(w > 1e-6, w, 1.0), NODATA)
            filtered[c] = np.where(ok, val, NODATA).astype(np.float32)
        dec = filtered[:, ::(2 ** k), ::(2 ** k)]
        arr = np.full((C, Hk, Wk), NODATA, dtype=np.float32)
        h, w = min(Hk, dec.shape[1]), min(Wk, dec.shape[2])
        arr[:, :h, :w] = dec[:, :h, :w]
        out.append(arr)
    return out


def _write_ptile_fallback(np, path, body, domain, num_octaves, num_channels,
                          H0, W0, base_res, lat0, lon0, octaves_data):
    binfo = BODIES[body.lower()]
    header = HEADER_STRUCT.pack(
        MAGIC_PTIL, CONTRACT_VERSION, binfo["id"], DOMAIN_IDS[domain],
        num_octaves, num_channels, H0, W0, float(base_res), float(lat0), float(lon0),
        float(NODATA), float(binfo["gravity"]), float(binfo["pressure"]),
        float(binfo["radiation"]), b"\x00" * 56,
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(header)
        for k in range(num_octaves):
            Hk, Wk = max(1, H0 >> k), max(1, W0 >> k)
            arr = octaves_data[k] if k < len(octaves_data) else np.full((num_channels, Hk, Wk), NODATA, dtype=np.float32)
            f.write(np.ascontiguousarray(arr, dtype=np.float32).reshape(num_channels, Hk, Wk).tobytes())


def synthesize_geophysical_grid(entity_id, body, domain, shape_hw, profile_hints=None):
    """Synthesize deterministic, physically plausible multi-channel source grids.

    Uses spatial Fourier modes, topographic ridges/craters, and physical coupling
    (e.g., slope/aspect from elevation, delta_T = T_max - T_min) with ~1.5% edge nodata.
    """
    import numpy as np

    H, W = shape_hw
    C = len(CHANNEL_NAMES[domain])
    hints = profile_hints or {}
    seed_bytes = hashlib.sha256(f"{entity_id}:{body}:{domain}".encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(seed_bytes[:8], "little"))

    y = np.linspace(-1.0, 1.0, H, dtype=np.float64)[:, None]
    x = np.linspace(-1.0, 1.0, W, dtype=np.float64)[None, :]
    phase1 = rng.uniform(0.0, 2.0 * math.pi)
    phase2 = rng.uniform(0.0, 2.0 * math.pi)
    ridge = (
        0.55 * np.sin(3.2 * math.pi * x + phase1) * np.cos(2.4 * math.pi * y + phase2)
        + 0.30 * np.cos(7.5 * math.pi * (x * 0.7 + y * 0.7))
        + 0.15 * np.sin(15.0 * math.pi * (x - 0.5 * y))
    )
    crater_r = np.sqrt((x - rng.uniform(-0.25, 0.25)) ** 2 + (y - rng.uniform(-0.25, 0.25)) ** 2)
    crater = -np.exp(-((crater_r / 0.28) ** 2)) + 0.35 * np.exp(-(((crater_r - 0.30) / 0.08) ** 2))
    base_field = 0.65 * ridge + 0.35 * crater + rng.normal(0.0, 0.08, (H, W))

    arr = np.zeros((C, H, W), dtype=np.float32)

    if domain == "topography":
        elev_mean = float(hints.get("elev_mean", 650.0))
        elev_amp = float(hints.get("elev_amp", 420.0))
        elev = elev_mean + elev_amp * base_field
        dy, dx = np.gradient(elev, 30.0, 30.0)
        grad = np.sqrt(dx * dx + dy * dy)
        slope_gain = float(hints.get("slope_gain", 1.2))
        slope = np.clip(np.rad2deg(np.arctan(grad * slope_gain)), 0.0, 65.0)
        aspect = (np.rad2deg(np.arctan2(-dx, dy)) + 360.0) % 360.0
        tri = np.abs(dx) * 30.0 + np.abs(dy) * 30.0 + float(hints.get("tri_bias", 12.0))
        tpi = elev - np.mean(elev)
        d2y, d2x = np.gradient(grad, 30.0, 30.0)
        prof_curv = np.clip(d2x + d2y, -0.05, 0.05)
        arr = np.stack([elev, slope, aspect, tri, tpi, prof_curv], axis=0).astype(np.float32)
    elif domain == "mineralogy":
        means = hints.get("mineral_means", [0.22, 0.18, 0.20, 0.08, 0.08, 0.16, 0.12, 0.02])
        for c in range(C):
            jitter = rng.normal(0.0, 0.035, (H, W))
            spatial = means[c] + 0.08 * (ridge if c % 2 == 0 else -crater) + jitter
            hi_lim = 0.95 if c < 7 else 0.85
            arr[c] = np.clip(spatial, 0.0, hi_lim).astype(np.float32)
    elif domain == "thermal_illumination":
        t_max_m = float(hints.get("T_max", 315.0 if body == "earth" else (340.0 if body == "moon" else 280.0)))
        t_min_m = float(hints.get("T_min", 272.0 if body == "earth" else (110.0 if body == "moon" else 175.0)))
        alb_m = float(hints.get("albedo", 0.22))
        t_max = t_max_m + 14.0 * ridge + rng.normal(0.0, 2.5, (H, W))
        t_min = t_min_m + 10.0 * crater + rng.normal(0.0, 2.0, (H, W))
        t_min = np.minimum(t_min, t_max - 5.0)
        delta_t = t_max - t_min
        albedo = np.clip(alb_m - 0.04 * ridge + rng.normal(0.0, 0.015, (H, W)), 0.03, 0.85)
        ati = np.clip((1.0 - albedo) * 35.0 / np.maximum(delta_t, 5.0), 0.05, 1.5)
        arr = np.stack([t_max, t_min, delta_t, albedo, ati], axis=0).astype(np.float32)
    elif domain == "granular_aeolian":
        defaults = hints.get("granular_means", [0.28, 0.12, 140.0, 0.14, 95.0])
        scales = [0.06, 0.04, 45.0, 0.04, 30.0]
        mins = [0.02, 0.0, 10.0, 0.01, 5.0]
        for c in range(C):
            val = defaults[c] + scales[c] * base_field + rng.normal(0.0, scales[c] * 0.25, (H, W))
            arr[c] = np.maximum(val, mins[c]).astype(np.float32)
    elif domain == "volatiles_subsurface":
        defaults = hints.get("volatile_means", [2.5, 1.8, 3.2, 8.0, 1.1])
        scales = [1.2, 0.5, 0.8, 12.0, 0.6]
        for c in range(C):
            val = defaults[c] + scales[c] * (crater if c == 4 else base_field) + rng.normal(0.0, scales[c] * 0.2, (H, W))
            if c in (0, 1, 2, 4):
                val = np.maximum(val, 0.05)
            arr[c] = val.astype(np.float32)

    # Mark a tiny deterministic border nodata strip (~1.5%) to exercise nodata masks cleanly
    arr[:, :2, :] = NODATA
    return arr


def materialize_standardized_tile(
    entity_id,
    body,
    domain,
    lat0,
    lon0,
    std_out_dir,
    raw_out_dir,
    shape_hw=(512, 512),
    base_res=30.0,
    num_octaves=5,
    source_datasets=None,
    profile_hints=None,
    external_grid=None,
    external_channels=None,
    channel_provenance=None,
    official_resources=None,
    main_repo=None,
):
    """Stage raw multi-channel .npy + manifest metadata and materialize 5-octave .ptile/.json."""
    import numpy as np

    reproject_to_laea, build_pyramid, write_ptile, write_json_sidecar = _try_import_processor(main_repo)

    if isinstance(shape_hw, int):
        H = W = int(shape_hw)
    else:
        H, W = int(shape_hw[0]), int(shape_hw[1])
    lat0 = float(lat0)
    lon0 = norm_lon_deg(lon0) if body.lower() == "earth" else float(lon0)
    R = BODIES[body.lower()]["radius_m"]
    binfo = BODIES[body.lower()]

    if external_grid is not None:
        raw_chw = np.asarray(external_grid, dtype=np.float32).copy()
    else:
        raw_chw = synthesize_geophysical_grid(entity_id, body, domain, (H, W), profile_hints)

    if external_channels:
        for idx, ch_name in enumerate(CHANNEL_NAMES[domain]):
            ch_arr = external_channels.get(ch_name, external_channels.get(idx))
            if ch_arr is not None:
                raw_chw[idx] = np.asarray(ch_arr, dtype=np.float32)

    C = raw_chw.shape[0]
    prov_map = build_channel_provenance(
        domain,
        external_grid=external_grid,
        external_channels=external_channels,
        channel_provenance=channel_provenance,
    )
    prov_values = set(prov_map.values())
    if prov_values == {PROVENANCE_REAL_ORBITAL_COG}:
        prov_mode = PROVENANCE_REAL_ORBITAL_COG
    elif prov_values == {PROVENANCE_CALIBRATED_FALLBACK}:
        prov_mode = PROVENANCE_CALIBRATED_FALLBACK
    else:
        prov_mode = "MIXED_COG_AND_FALLBACK"

    resolved_resources = (
        dict(official_resources)
        if official_resources is not None
        else dict(OFFICIAL_EARTH_RESOURCES if body.lower() == "earth" else OFFICIAL_MOON_MARS_RESOURCES)
    )

    # Geographic coordinate grid spanning ~1.3x the metric footprint for reprojection
    half_deg_lat = max(0.08, math.degrees((H * base_res * 0.65) / R))
    cos_lat = max(0.15, math.cos(math.radians(max(-85.0, min(85.0, lat0)))))
    half_deg_lon = max(0.08, half_deg_lat / cos_lat)
    src_lats = np.linspace(lat0 - half_deg_lat, lat0 + half_deg_lat, H, dtype=np.float64)
    src_lons = np.linspace(lon0 - half_deg_lon, lon0 + half_deg_lon, W, dtype=np.float64)

    os.makedirs(raw_out_dir, exist_ok=True)
    os.makedirs(std_out_dir, exist_ok=True)

    tile_stem = f"{entity_id}_{domain}"
    raw_npy = os.path.join(raw_out_dir, tile_stem + ".npy")
    raw_meta = os.path.join(raw_out_dir, tile_stem + ".json")
    np.save(raw_npy, raw_chw)

    valid_fraction = float(np.mean(raw_chw != NODATA))
    raw_meta_obj = {
        "tile_id": tile_stem,
        "lats": src_lats.tolist(),
        "lons": src_lons.tolist(),
        "base_resolution_m": float(base_res),
        "channel_names": CHANNEL_NAMES[domain],
        "source_datasets": source_datasets or [],
        "official_resources": resolved_resources,
        "channel_provenance": prov_map,
        "acquisition_window": "2024-01-01/2025-12-31",
        "quality_mask_stats": {
            "valid_fraction": round(valid_fraction, 4),
            "provenance_mode": prov_mode,
            "channel_provenance": prov_map,
        },
    }
    with open(raw_meta, "w", encoding="utf-8") as f:
        json.dump(raw_meta_obj, f, indent=2)

    # Reproject all C channels onto local metric LAEA grid
    reproj_channels = []
    for c in range(C):
        if reproject_to_laea is not None:
            ch_grid = reproject_to_laea(
                raw_chw[c], src_lats, src_lons, lat0, lon0,
                body=body, out_shape=(H, W), resolution_m=base_res,
            )
        else:
            ch_grid = _bilinear_reproject_fallback(
                np, raw_chw[c], src_lats, src_lons, lat0, lon0, body, (H, W), base_res
            )
        reproj_channels.append(ch_grid)
    laea_chw = np.stack(reproj_channels, axis=0).astype(np.float32)

    if build_pyramid is not None:
        octaves_data = build_pyramid(laea_chw, base_resolution_m=base_res, num_octaves=num_octaves)
    else:
        octaves_data = _build_pyramid_fallback(np, laea_chw, base_res=base_res, num_octaves=num_octaves)

    ptile_path = os.path.join(std_out_dir, tile_stem + ".ptile")
    json_path = os.path.join(std_out_dir, tile_stem + ".json")

    if write_ptile is not None:
        write_ptile(
            ptile_path, body, domain, num_octaves, C, H, W,
            base_res, lat0, lon0, nodata_value=NODATA,
            radiation_msv_yr=binfo["radiation"], octaves_data=octaves_data,
        )
    else:
        _write_ptile_fallback(
            np, ptile_path, body, domain, num_octaves, C, H, W,
            base_res, lat0, lon0, octaves_data,
        )

    sidecar = {
        "tile_id": tile_stem,
        "entity_id": entity_id,
        "proj4_laea": f"+proj=laea +lat_0={lat0} +lon_0={lon0} +R={int(R)} +units=m",
        "channel_names": CHANNEL_NAMES[domain],
        "source_datasets": source_datasets or [],
        "official_resources": resolved_resources,
        "channel_provenance": prov_map,
        "acquisition_window": "2024-01-01/2025-12-31",
        "quality_mask_stats": {
            "valid_fraction": round(float(np.mean(laea_chw != NODATA)), 4),
            "fallback_mode": prov_mode != PROVENANCE_REAL_ORBITAL_COG,
            "provenance_mode": prov_mode,
            "channel_provenance": prov_map,
        },
        "body": body.upper(),
        "domain": domain,
        "center_lat_deg": lat0,
        "center_lon_deg": lon0,
        "bbox": [
            round(lat0 - half_deg_lat, 5),
            round(lon0 - half_deg_lon, 5),
            round(lat0 + half_deg_lat, 5),
            round(lon0 + half_deg_lon, 5),
        ],
        "base_resolution_m": float(base_res),
        "base_height": H,
        "base_width": W,
        "num_octaves": num_octaves,
        "num_channels": C,
        "gravity_ms2": binfo["gravity"],
        "surface_pressure_pa": binfo["pressure"],
        "radiation_msv_yr": binfo["radiation"],
    }
    if write_json_sidecar is not None:
        write_json_sidecar(json_path, sidecar)
    else:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sidecar, f, indent=2)

    return {
        "tile_id": tile_stem,
        "entity_id": entity_id,
        "body": body.lower(),
        "domain": domain,
        "lat0": lat0,
        "lon0": lon0,
        "channels": C,
        "shape_hw": [H, W],
        "provenance_mode": prov_mode,
        "channel_provenance": prov_map,
        "src_npy": raw_npy,
        "src_meta": raw_meta,
        "ptile_path": ptile_path,
        "json_path": json_path,
    }
