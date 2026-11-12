"""BestAlgo/topography reference implementation (v2.0 standardized distribution matching)."""
import json
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (read_ptile, write_hmap, write_breakdown, NODATA,
                    normalize_channels, target_signature, compute_sim_conf)

CHANNEL_NAMES = ["elevation_z", "slope_theta", "aspect_psi", "TRI", "TPI", "profile_curvature_kappa_p"]
# Physical reference constants (mu, sigma) per channel + illumination proxy
REFS = [
    (500.0, 1000.0),   # elevation_z (m)
    (15.0, 15.0),       # slope_theta (deg)
    (180.0, 103.9),     # aspect_psi (deg)
    (50.0, 50.0),       # TRI
    (0.0, 50.0),        # TPI
    (0.0, 0.01),        # profile_curvature
    (0.0, 0.5),         # illumination proxy sin(slope)*cos(aspect)
]


def compute_similarity(earth_tile_path, target_tile_path, out_hmap_path, out_breakdown_path):
    eh, eoct, emeta = read_ptile(earth_tile_path)
    th, toct, tmeta = read_ptile(target_tile_path)

    num_octaves = min(eh["num_octaves"], th["num_octaves"])
    base_height = eh["base_height"]
    base_width = eh["base_width"]
    num_channels = min(eh["num_channels"], th["num_channels"])

    octaves_out = []
    per_octave_mean = []
    raw_channel_residuals = {("ch%d" % c): {"earth_mean": 0.0, "target_mean": 0.0, "z_divergence": 0.0}
                            for c in range(num_channels)}

    for k in range(num_octaves):
        e_raw = eoct[k][:num_channels].astype(np.float64)
        t_raw = toct[k][:num_channels].astype(np.float64)
        # resize target to earth shape if needed (nearest)
        if t_raw.shape[1:] != e_raw.shape[1:]:
            from scipy.ndimage import zoom
            zf = (1, e_raw.shape[1] / t_raw.shape[1], e_raw.shape[2] / t_raw.shape[2])
            t_raw = zoom(t_raw, zf, order=0)
        # raw residuals (preserve unnormalized)
        for c in range(num_channels):
            ev = e_raw[c][e_raw[c] != NODATA] if False else e_raw[c].ravel()
            # filter nodata
            em = e_raw[c].ravel(); em = em[em != NODATA]
            tm = t_raw[c].ravel(); tm = tm[tm != NODATA]
            raw_channel_residuals["ch%d" % c]["earth_mean"] = float(np.mean(em)) if em.size else 0.0
            raw_channel_residuals["ch%d" % c]["target_mean"] = float(np.mean(tm)) if tm.size else 0.0
            pooled = float(np.sqrt((np.var(em) if em.size else 0.0) + (np.var(tm) if tm.size else 0.0) + 1e-12))
            raw_channel_residuals["ch%d" % c]["z_divergence"] = float(
                (raw_channel_residuals["ch%d" % c]["earth_mean"] - raw_channel_residuals["ch%d" % c]["target_mean"]) / pooled) if pooled > 0 else 0.0

        # normalize
        e_norm = normalize_channels(e_raw.astype(np.float32), REFS[:num_channels])
        t_norm = normalize_channels(t_raw.astype(np.float32), REFS[:num_channels])
        # append illumination proxy channel (sin(slope)*cos(aspect)) for topography
        # slope idx 1, aspect idx 2
        sl = e_norm[1]; asp = e_norm[2]
        proxy_e = np.sin(sl) * np.cos(asp)
        proxy_e = np.where(np.isnan(sl) | np.isnan(asp), np.nan, proxy_e).astype(np.float64)
        proxy_e = np.clip(proxy_e / 0.5, -5.0, 5.0).astype(np.float32)
        proxy_e = np.where(np.isnan(sl) | np.isnan(asp), np.nan, proxy_e).astype(np.float32)
        slt = t_norm[1]; aspt = t_norm[2]
        proxy_t = np.sin(slt) * np.cos(aspt)
        proxy_t = np.where(np.isnan(slt) | np.isnan(aspt), np.nan, proxy_t).astype(np.float64)
        proxy_t = np.clip(proxy_t / 0.5, -5.0, 5.0).astype(np.float32)
        proxy_t = np.where(np.isnan(slt) | np.isnan(aspt), np.nan, proxy_t).astype(np.float32)
        e_norm = np.concatenate([e_norm, proxy_e[None, ...]], axis=0)
        t_norm = np.concatenate([t_norm, proxy_t[None, ...]], axis=0)

        # target signature
        tsig = target_signature(t_norm)
        # window radius
        r = max(3, 15 >> k)
        sim_map, conf_map = compute_sim_conf(e_norm, tsig, r)

        oct_arr = np.stack([sim_map, conf_map], axis=0).astype(np.float32)
        octaves_out.append(oct_arr)
        valid = conf_map > 0
        per_octave_mean.append(float(np.mean(sim_map[valid])) if valid.any() else 0.0)

    if len(per_octave_mean) > 1:
        si = 1.0 - float(np.std(per_octave_mean))
    else:
        si = 1.0
    si = min(1.0, max(0.0, si))

    # flags
    eg = eh["gravity_ms2"]; tg = th["gravity_ms2"]
    flags = []
    flags.append({"flag": "GRAVITY_SCALING", "gravity_scaling_factor": float(tg / eg if eg else 1.0),
                  "details": "Earth g=%s vs target g=%s" % (eg, tg)})
    flags.append({"flag": "ATMOSPHERE_GAP", "atmospheric_pressure_gap_pa": float(abs(eh["surface_pressure_pa"] - th["surface_pressure_pa"]))})
    flags.append({"flag": "RADIATION_DELTA", "radiation_delta_msv_yr": float(abs(eh["radiation_msv_yr"] - th["radiation_msv_yr"]))})
    if th["body"] == 2 and eh["body"] == 1:
        flags.append({"flag": "NO_ATMOSPHERE_TARGET", "details": "Target body has no atmosphere; convective heat loss absent."})

    breakdown = {
        "scale_invariance_index": si,
        "channel_residuals": raw_channel_residuals,
        "physical_breakdown_flags": flags,
    }

    write_hmap(out_hmap_path, num_octaves, base_height, base_width, num_channels=2,
               octaves_data=octaves_out, body=eh["body"], domain=eh["domain"],
               center_lat=eh["center_lat_deg"], center_lon=eh["center_lon_deg"],
               base_res=eh["base_resolution_m"],
               gravity=eh["gravity_ms2"], pressure=eh["surface_pressure_pa"],
               radiation=eh["radiation_msv_yr"])
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
