"""Common I/O + standardized local-distribution similarity for BestAlgo modules."""
import json
import os
import struct
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

HEADER_STRUCT = struct.Struct("<IIIIIIII ddd ffff 56s")
assert HEADER_STRUCT.size == 128
MAGIC_PTIL = 0x4C495450
MAGIC_HMAP = 0x50414D48
NODATA = -9999.0

BODY_NAMES = {1: "earth", 2: "moon", 3: "mars"}


def read_ptile(path):
    with open(path, "rb") as f:
        raw = f.read(128)
    (magic, version, body, domain, num_octaves, num_channels,
     base_height, base_width, base_res, center_lat, center_lon,
     nodata, grav, pres, rad, reserved) = HEADER_STRUCT.unpack(raw)
    if magic != MAGIC_PTIL:
        raise ValueError("Bad magic %s in %s" % (hex(magic), path))
    if version != 1:
        raise ValueError("Bad version %d" % version)
    with open(path, "rb") as f:
        data = f.read()
    octaves = []
    off = 128
    for k in range(num_octaves):
        Hk = base_height >> k
        Wk = base_width >> k
        n = num_channels * Hk * Wk
        block = data[off:off + n * 4]
        off += n * 4
        arr = np.frombuffer(block, dtype=np.float32).reshape(num_channels, Hk, Wk).copy()
        octaves.append(arr)
    meta_path = path.replace(".ptile", ".json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    header = {
        "magic": magic, "version": version, "body": body, "domain": domain,
        "num_octaves": num_octaves, "num_channels": num_channels,
        "base_height": base_height, "base_width": base_width,
        "base_resolution_m": base_res, "center_lat_deg": center_lat,
        "center_lon_deg": center_lon, "nodata_value": nodata,
        "gravity_ms2": grav, "surface_pressure_pa": pres,
        "radiation_msv_yr": rad,
    }
    return header, octaves, meta


def write_hmap(path, num_octaves, base_height, base_width, num_channels=2,
               octaves_data=None, body=1, domain=1, center_lat=0.0,
               center_lon=0.0, base_res=30.0, nodata=-9999.0,
               gravity=9.80665, pressure=101325.0, radiation=0.0):
    if octaves_data is None:
        octaves_data = []
    header = HEADER_STRUCT.pack(
        MAGIC_HMAP, 1, body, domain, num_octaves, num_channels,
        base_height, base_width, float(base_res), float(center_lat),
        float(center_lon), float(nodata),
        float(gravity), float(pressure), float(radiation), b"\x00" * 56,
    )
    with open(path, "wb") as f:
        f.write(header)
        for k in range(num_octaves):
            Hk = base_height >> k
            Wk = base_width >> k
            if k < len(octaves_data) and octaves_data[k] is not None:
                arr = np.ascontiguousarray(octaves_data[k], dtype=np.float32).reshape(num_channels, Hk, Wk)
            else:
                arr = np.zeros((num_channels, Hk, Wk), dtype=np.float32)
            f.write(arr.tobytes())


def write_breakdown(path, breakdown):
    with open(path, "w") as f:
        json.dump(breakdown, f, indent=2)


def normalize_channels(arr, refs):
    """arr: (C,H,W) float32; refs: list of (mu,sigma) length C. Nodata -> nan."""
    C, H, W = arr.shape
    out = np.full((C, H, W), np.nan, dtype=np.float32)
    for c in range(C):
        mu, sig = refs[c]
        ch = arr[c].astype(np.float64)
        valid = ch != NODATA
        z = (ch[valid] - mu) / sig
        z = np.clip(z, -5.0, 5.0)
        out[c][valid] = z.astype(np.float32)
    return out


def texture_energy(ch):
    """Mean local finite-difference gradient magnitude per pixel (H,W)."""
    gx = np.zeros_like(ch, dtype=np.float64)
    gy = np.zeros_like(ch, dtype=np.float64)
    gx[:, 1:] = np.abs(ch[:, 1:] - ch[:, :-1])
    gy[1:, :] = np.abs(ch[1:, :] - ch[:-1, :])
    mag = np.sqrt(gx * gx + gy * gy)
    return mag


def target_signature(norm_arr):
    """norm_arr: (C,H,W) normalized (nan for nodata). Returns dict per channel."""
    C, H, W = norm_arr.shape
    mean = np.zeros(C, dtype=np.float64)
    std = np.zeros(C, dtype=np.float64)
    quants = np.zeros((C, 5), dtype=np.float64)  # Q10,Q25,Q50,Q75,Q90
    tex = np.zeros(C, dtype=np.float64)
    for c in range(C):
        ch = norm_arr[c]
        valid = ~np.isnan(ch)
        vals = ch[valid]
        if vals.size > 0:
            mean[c] = float(np.mean(vals))
            std[c] = float(np.std(vals))
            quants[c] = np.percentile(vals, [10, 25, 50, 75, 90])
        t = texture_energy(np.where(valid, ch, 0.0))
        if valid.any():
            tex[c] = float(np.mean(t[valid]))
    return {"mean": mean, "std": std, "quantiles": quants, "texture": tex}


def local_windows(norm_arr, r):
    """Compute per-pixel local quantiles, texture, f_valid, std for normalized (C,H,W).
    Returns: quantiles (H,W,C,5), texture (H,W,C), f_valid (H,W), std_local (H,W,C)."""
    C, H, W = norm_arr.shape
    win = 2 * r + 1
    pad = r
    # padded arrays (nan pad)
    padded = np.pad(norm_arr, ((0, 0), (pad, pad), (pad, pad)), mode="constant", constant_values=np.nan)
    # sliding window view: (H, W, win, win, C)? We'll do per channel
    quantiles = np.zeros((H, W, C, 5), dtype=np.float32)
    texture = np.zeros((H, W, C), dtype=np.float32)
    f_valid = np.zeros((H, W), dtype=np.float32)
    std_local = np.zeros((H, W, C), dtype=np.float32)

    # texture energy full image
    tex_full = np.zeros((C, H, W), dtype=np.float64)
    for c in range(C):
        ch = np.where(np.isnan(norm_arr[c]), 0.0, norm_arr[c])
        tex_full[c] = texture_energy(ch)

    for c in range(C):
        ch = norm_arr[c]  # (H,W)
        valid = (~np.isnan(ch)).astype(np.float32)
        # f_valid via sliding window mean of valid mask
        vpad = np.pad(valid, (pad, pad), mode="constant", constant_values=0.0)
        vview = sliding_window_view(vpad, (win, win))  # (H,W,win,win)
        fv = vview.reshape(H, W, -1).mean(axis=2)
        f_valid = np.maximum(f_valid, 0)  # keep
        f_valid += 0  # placeholder
        # store per-channel f_valid? f_valid is same across channels if valid mask per channel differs. Use per-channel and combine later? We'll compute f_valid per channel and take min across channels.
        # For simplicity, track f_valid as min across channels
        # quantiles per window
        chpad = np.pad(ch, (pad, pad), mode="constant", constant_values=np.nan)
        wview = sliding_window_view(chpad, (win, win))  # (H,W,win,win)
        wflat = wview.reshape(H * W, win * win)
        # nanpercentile
        with np.errstate(all='ignore'):
            qs = np.nanpercentile(wflat, [10, 25, 50, 75, 90], axis=1)  # (5, H*W)
        qs = np.where(np.isnan(qs), 0.0, qs)
        quantiles[:, :, c, :] = qs.T.reshape(H, W, 5)
        # std local
        # mean and mean^2
        # std over valid pixels only
        vflat = np.where(np.isnan(wflat), 0.0, wflat)
        vcount = (~np.isnan(wflat)).sum(axis=1).astype(np.float64)
        m = np.where(vcount > 0, vflat.sum(axis=1) / np.where(vcount > 0, vcount, 1.0), 0.0)
        m2 = np.where(vcount > 0, (vflat * vflat).sum(axis=1) / np.where(vcount > 0, vcount, 1.0), 0.0)
        sd = np.sqrt(np.maximum(m2 - m * m, 0.0))
        std_local[:, :, c] = sd.reshape(H, W)
        # texture local mean
        texpad = np.pad(tex_full[c], (pad, pad), mode="constant", constant_values=0.0)
        tview = sliding_window_view(texpad, (win, win))
        texture[:, :, c] = tview.reshape(H, W, -1).mean(axis=2)
        # f_valid per channel: combine as min
        if c == 0:
            f_valid = fv
        else:
            f_valid = np.minimum(f_valid, fv)
    return quantiles, texture, f_valid, std_local


def compute_sim_conf(earth_norm, target_sig, r):
    """Returns (sim_map, conf_map) float32 (H,W)."""
    C, H, W = earth_norm.shape
    quantiles, texture, f_valid, std_local = local_windows(earth_norm, r)
    # target quantiles/texture/std
    tq = target_sig["quantiles"]  # (C,5)
    tt = target_sig["texture"]     # (C,)
    ts = target_sig["std"]         # (C,)
    # W1 per channel: mean abs quantile diff
    # quantiles: (H,W,C,5); tq: (C,5) -> broadcast (1,1,C,5)
    tq_b = tq[None, None, :, :]  # (1,1,C,5)
    w1 = np.mean(np.abs(quantiles - tq_b), axis=3)  # (H,W,C)
    # texture mismatch
    tt_b = tt[None, None, :]  # (1,1,C)
    deltaE = np.abs(texture - tt_b) / (texture + tt_b + 1e-6)  # (H,W,C)
    # D per pixel
    D = np.mean(0.75 * w1 + 0.25 * deltaE, axis=2)  # (H,W)
    sim = np.exp(-D).astype(np.float32)
    # conf
    std_diff = np.mean(np.abs(std_local - ts[None, None, :]), axis=2)  # (H,W)
    conf = (f_valid * (1.0 / (1.0 + std_diff))).astype(np.float32)
    # nodata center -> 0
    # center pixel nodata check: any channel nan at center
    center_nodata = np.isnan(earth_norm).any(axis=0)  # (H,W)
    sim = np.where(center_nodata, 0.0, sim)
    conf = np.where(center_nodata, 0.0, conf)
    # f_valid < 0.25 -> 0
    sim = np.where(f_valid < 0.25, 0.0, sim)
    conf = np.where(f_valid < 0.25, 0.0, conf)
    return sim, conf
