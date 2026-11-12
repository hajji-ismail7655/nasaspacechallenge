"""BestAlgo/topography reference implementation."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_ptile, write_hmap, write_breakdown, safe_mean, NODATA

CHANNEL_NAMES = ["elevation_z", "slope_theta", "aspect_psi", "TRI", "TPI", "profile_curvature_kappa_p"]


def _cosine_sim(earth_vec, target_vec):
    a = earth_vec.astype(np.float64)
    b = target_vec.astype(np.float64)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return 0.0, 0.0
    cos = float(np.dot(a, b) / (na * nb))
    sim = (cos + 1.0) / 2.0
    sim = min(1.0, max(0.0, sim))
    # confidence: inverse of relative difference
    diff = np.abs(a - b)
    rel = float(np.mean(diff / (np.abs(a) + np.abs(b) + 1e-6)))
    conf = 1.0 / (1.0 + rel)
    conf = min(1.0, max(0.0, conf))
    return sim, conf


import numpy as np


def compute_similarity(earth_tile_path, target_tile_path, out_hmap_path, out_breakdown_path):
    eh, eoct, emeta = read_ptile(earth_tile_path)
    th, toct, tmeta = read_ptile(target_tile_path)

    num_octaves = min(eh["num_octaves"], th["num_octaves"])
    base_height = eh["base_height"]
    base_width = eh["base_width"]
    num_channels = min(eh["num_channels"], th["num_channels"])

    octaves_out = []
    per_octave_mean = []
    for k in range(num_octaves):
        e = eoct[k][:num_channels]
        t = toct[k][:num_channels]
        Hk, Wk = e.shape[1], e.shape[2]
        # align target size to earth size if needed
        if t.shape[1:] != (Hk, Wk):
            # nearest resize
            from scipy.ndimage import zoom
            zf = (1, Hk / t.shape[1], Wk / t.shape[2])
            t = zoom(t, zf, order=0)
        sim_map = np.zeros((Hk, Wk), dtype=np.float32)
        conf_map = np.zeros((Hk, Wk), dtype=np.float32)
        for i in range(Hk):
            for j in range(Wk):
                ev = e[:, i, j]
                tv = t[:, i, j]
                if np.any(ev == NODATA) or np.any(tv == NODATA):
                    sim_map[i, j] = 0.0
                    conf_map[i, j] = 0.0
                    continue
                s, c = _cosine_sim(ev, tv)
                sim_map[i, j] = s
                conf_map[i, j] = c
        oct_arr = np.stack([sim_map, conf_map], axis=0).astype(np.float32)
        octaves_out.append(oct_arr)
        m = sim_map[sim_map != 0]
        per_octave_mean.append(float(np.mean(sim_map)) if sim_map.size else 0.0)

    # scale invariance index (global)
    if len(per_octave_mean) > 1:
        si = 1.0 - float(np.std(per_octave_mean))
    else:
        si = 1.0
    si = min(1.0, max(0.0, si))

    # channel residuals
    channel_names = emeta.get("channel_names", CHANNEL_NAMES)
    if len(channel_names) < num_channels:
        channel_names = channel_names + [f"ch{i}" for i in range(len(channel_names), num_channels)]
    channel_residuals = {}
    for ci in range(num_channels):
        cname = channel_names[ci] if ci < len(channel_names) else f"ch{ci}"
        e_vals = np.concatenate([eoct[k][ci].ravel() for k in range(num_octaves)])
        t_vals = np.concatenate([toct[k][ci].ravel() for k in range(num_octaves)])
        em = e_vals[e_vals != NODATA]
        tm = t_vals[t_vals != NODATA]
        emean = float(np.mean(em)) if em.size else 0.0
        tmean = float(np.mean(tm)) if tm.size else 0.0
        pooled = np.sqrt((np.var(em) if em.size else 0) + (np.var(tm) if tm.size else 0) + 1e-12)
        zdiv = (emean - tmean) / pooled if pooled > 0 else 0.0
        channel_residuals[cname] = {"earth_mean": emean, "target_mean": tmean, "z_divergence": float(zdiv)}

    # physical breakdown flags
    flags = []
    # gravity scaling
    eg = eh["gravity_ms2"]; tg = th["gravity_ms2"]
    flags.append({"flag": "GRAVITY_SCALING", "gravity_scaling_factor": float(tg / eg if eg else 1.0),
                  "details": f"Earth g={eg} vs target g={tg}"})
    flags.append({"flag": "ATMOSPHERE_GAP", "atmospheric_pressure_gap_pa": float(abs(eh["surface_pressure_pa"] - th["surface_pressure_pa"]))})
    flags.append({"flag": "RADIATION_DELTA", "radiation_delta_msv_yr": float(abs(eh["radiation_msv_yr"] - th["radiation_msv_yr"]))})
    if th["body"] in (2,) and eh["body"] == 1:
        flags.append({"flag": "NO_ATMOSPHERE_TARGET", "details": "Target body has no atmosphere; convective heat loss absent."})

    breakdown = {
        "scale_invariance_index": si,
        "channel_residuals": channel_residuals,
        "physical_breakdown_flags": flags,
    }

    write_hmap(out_hmap_path, num_octaves, base_height, base_width, num_channels=2,
               octaves_data=octaves_out, body=eh["body"], domain=eh["domain"],
               center_lat=eh["center_lat_deg"], center_lon=eh["center_lon_deg"],
               base_res=eh["base_resolution_m"])
    write_breakdown(out_breakdown_path, breakdown)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("earth_tile_path")
    ap.add_argument("target_tile_path")
    ap.add_argument("out_hmap_path")
    ap.add_argument("out_breakdown_path")
    args = ap.parse_args()
    compute_similarity(args.earth_tile_path, args.target_tile_path, args.out_hmap_path, args.out_breakdown_path)
    print(json.dumps({"status": "ok"}))
