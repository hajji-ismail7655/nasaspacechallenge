"""Generate 300-dpi publication figures from Phase 3 discovery sweep results."""
import argparse
import json
import os
import struct

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OCTAVE_RES = [30, 60, 120, 240, 480]
HEADER_STRUCT = struct.Struct("<IIIIIIII ddd ffff 56s")


def _read_composite_octave_means(hmap_path):
    """Return list of mean similarity per octave from a 2-channel composite .hmap."""
    if not hmap_path or not os.path.exists(hmap_path):
        return None
    with open(hmap_path, "rb") as f:
        data = f.read()
    if len(data) < 128:
        return None
    hdr = HEADER_STRUCT.unpack(data[:128])
    num_octaves, num_channels, bh, bw = hdr[4], hdr[5], hdr[6], hdr[7]
    off = 128
    means = []
    for k in range(num_octaves):
        hk = max(1, bh >> k)
        wk = max(1, bw >> k)
        n = num_channels * hk * wk
        arr = np.frombuffer(data[off:off + n * 4], dtype=np.float32).reshape(num_channels, hk, wk)
        off += n * 4
        sim = arr[0]
        conf = arr[1] if num_channels > 1 else np.ones_like(sim)
        valid = conf > 0
        means.append(float(np.mean(sim[valid])) if valid.any() else 0.0)
    return means[:len(OCTAVE_RES)]


def _extract_flag_metrics(breakdown_path):
    """Extract gravity factor, pressure gap, radiation delta, and thermal floor delta."""
    metrics = {"gravity": 1.0, "pressure_kpa": 0.0, "radiation": 0.0, "thermal_k": 0.0}
    if not breakdown_path or not os.path.exists(breakdown_path):
        return metrics
    with open(breakdown_path, encoding="utf-8") as f:
        bd = json.load(f)
    for flag in bd.get("physical_breakdown_flags", []):
        name = flag.get("flag", "")
        if name == "GRAVITY_SCALING":
            metrics["gravity"] = float(flag.get("gravity_scaling_factor", 1.0))
        elif name == "ATMOSPHERE_GAP":
            metrics["pressure_kpa"] = float(flag.get("atmospheric_pressure_gap_pa", 0.0)) / 1000.0
        elif name == "RADIATION_DELTA":
            metrics["radiation"] = float(flag.get("radiation_delta_msv_yr", 0.0))
        elif name == "CRYOGENIC_FLOOR_DELTA":
            metrics["thermal_k"] = abs(float(flag.get("thermal_floor_delta_k", 0.0)))
    return metrics


def make_fig1(novel_sites, out_path):
    """Fig 1: Multi-octave (30m-480m) similarity curves across Top 5 novel sites."""
    top5 = novel_sites[:5]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1.5, 1]})
    for row in top5:
        label = f"{row['site_id']} -> {row['target_id']}"
        means = _read_composite_octave_means(row.get("composite_hmap_path"))
        if not means:
            base = float(row.get("composite_score", 0.0))
            means = [base] * len(OCTAVE_RES)
        ax1.plot(OCTAVE_RES[:len(means)], means, marker="o", linewidth=2, label=label)
    ax1.set_xscale("log", base=2)
    ax1.set_xticks(OCTAVE_RES)
    ax1.set_xticklabels([f"{r}m" for r in OCTAVE_RES])
    ax1.set_xlabel("Spatial Octave Resolution (m/px)")
    ax1.set_ylabel("Mean Composite Similarity")
    ax1.set_title("Multi-Scale Similarity Curves (Top 5 Novel Analogs)")
    ax1.set_ylim(0, 1.05)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=7.5, loc="lower left")

    labels = [f"{r['site_id']}\n({r['target_id'][:14]})" for r in top5]
    si_vals = [float(r.get("scale_invariance_index", 0.0)) for r in top5]
    y = np.arange(len(top5))
    ax2.barh(y, si_vals, color="#2b6cb0")
    ax2.set_yticks(y)
    ax2.set_yticklabels(labels, fontsize=8)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 1.05)
    ax2.set_xlabel("Scale-Invariance Index")
    ax2.set_title("Scale-Invariance Index")
    ax2.grid(True, axis="x", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def make_fig2(unmasked_sites, novel_sites, out_path):
    """Fig 2: Unmasked calibration vs 150 km novelty-masked rankings."""
    top_unmasked = unmasked_sites[:10]
    top_novel = novel_sites[:10]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2), sharex=True)

    for ax, rows, title in [
        (ax1, top_unmasked, "Unmasked Calibration (Controls Unsuppressed)"),
        (ax2, top_novel, "Novelty-Masked (150 km Known-Analog Suppression)"),
    ]:
        labels = [f"{r['site_id']} -> {r['target_id'][:12]}" for r in rows]
        scores = [float(r.get("composite_score", 0.0)) for r in rows]
        colors = ["#c53030" if r.get("is_known_analog") else "#2f855a" for r in rows]
        y = np.arange(len(rows))
        ax.barh(y, scores, color=colors)
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlim(0, 1.0)
        ax.set_xlabel("Composite Score")
        ax.set_title(title)
        ax.grid(True, axis="x", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def make_fig3(novel_sites, out_path):
    """Fig 3: Physical breakdown deltas across Top 3 case-study sites."""
    top3 = novel_sites[:3]
    names = [f"{r['site_id']}\n({r['target_id']})" for r in top3]
    metrics = [_extract_flag_metrics(r.get("breakdown_path")) for r in top3]

    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.5))
    specs = [
        (axes[0, 0], "gravity", "Gravity Scaling Ratio (g_target / g_earth)", "#3182ce"),
        (axes[0, 1], "pressure_kpa", "Atmospheric Pressure Gap (kPa)", "#dd6b20"),
        (axes[1, 0], "radiation", "Radiation Delta (mSv/yr)", "#805ad5"),
        (axes[1, 1], "thermal_k", "Cryogenic Floor Delta |ΔT_min| (K)", "#319795"),
    ]
    x = np.arange(len(top3))
    for ax, key, title, color in specs:
        vals = [m[key] for m in metrics]
        ax.bar(x, vals, color=color, width=0.55)
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontsize=7.5)
        ax.set_title(title, fontsize=9.5)
        ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Generate 300-dpi publication figures from sweep results")
    ap.add_argument("--results-dir", default="./data_lake/results")
    ap.add_argument("--out-dir", default="./docs/figures")
    args = ap.parse_args()

    novel_p = os.path.join(args.results_dir, "ranked_novel_discoveries.json")
    unmasked_p = os.path.join(args.results_dir, "ranked_unmasked_calibration.json")
    with open(novel_p, encoding="utf-8") as f:
        novel_sites = json.load(f).get("sites", [])
    with open(unmasked_p, encoding="utf-8") as f:
        unmasked_sites = json.load(f).get("sites", [])

    os.makedirs(args.out_dir, exist_ok=True)
    make_fig1(novel_sites, os.path.join(args.out_dir, "fig1_multiscale_similarity.png"))
    make_fig2(unmasked_sites, novel_sites, os.path.join(args.out_dir, "fig2_novelty_suppression_lift.png"))
    make_fig3(novel_sites, os.path.join(args.out_dir, "fig3_physical_breakdown_deltas.png"))
    print("Generated 3 publication figures in", args.out_dir)


if __name__ == "__main__":
    main()
