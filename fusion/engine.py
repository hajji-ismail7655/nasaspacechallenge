"""Multi-module aggregator & scientific analyzer."""
import json
import os
import numpy as np


def composite_similarity(module_scores, weights=None):
    """Weighted composite similarity per target mission profile.

    module_scores: dict module_name -> list of octave arrays (2,H,W) or (H,W)
    weights: dict module_name -> weight (default equal)
    Returns: dict octave -> 2D array (H,W) similarity.
    """
    if weights is None:
        weights = {m: 1.0 for m in module_scores}
    total_w = sum(weights.get(m, 1.0) for m in module_scores)
    # align to min shape
    result = {}
    # assume all modules same octaves count
    n_oct = len(next(iter(module_scores.values())))
    for k in range(n_oct):
        # find common shape
        shapes = [module_scores[m][k].shape[-2:] for m in module_scores]
        H = min(s[0] for s in shapes)
        W = min(s[1] for s in shapes)
        comp = np.zeros((H, W), dtype=np.float64)
        wsum = np.zeros((H, W), dtype=np.float64)
        for m, octs in module_scores.items():
            arr = octs[k]
            if arr.ndim == 3:
                sim_arr = arr[0]
                conf_arr = arr[1] if arr.shape[0] > 1 else np.ones_like(arr[0])
            else:
                sim_arr = arr
                conf_arr = np.ones_like(arr)
            sim_arr = sim_arr[:H, :W].astype(np.float64)
            conf_arr = conf_arr[:H, :W]
            w = weights.get(m, 1.0)
            valid = conf_arr > 0
            comp = np.where(valid, comp + w * sim_arr, comp)
            wsum = np.where(valid, wsum + w, wsum)
        comp = np.where(wsum > 0, comp / np.where(wsum > 0, wsum, 1.0), 0.0)
        result[k] = comp.astype(np.float32)
    return result


def scale_invariance_filter(composite_octaves):
    """Multiply by Scale-Invariance Index I_scale = 1 - StdDev_sigma(S_total).

    Returns: dict octave -> 2D array (filtered similarity).
    """
    n_oct = len(composite_octaves)
    # stack
    shapes = [composite_octaves[k].shape for k in range(n_oct)]
    H = min(s[0] for s in shapes)
    W = min(s[1] for s in shapes)
    stack = np.stack([composite_octaves[k][:H, :W] for k in range(n_oct)], axis=0)  # (n_oct,H,W)
    std = np.std(stack, axis=0)
    mean = np.mean(stack, axis=0)
    I_scale = 1.0 - std
    # invalidate all-nodata (all-zero) regions
    I_scale = np.where((std == 0) & (mean == 0), 0.0, I_scale)
    I_scale = np.clip(I_scale, 0.0, 1.0)
    out = {}
    for k in range(n_oct):
        out[k] = (composite_octaves[k][:H, :W] * I_scale).astype(np.float32)
    return out, I_scale


def fuse(module_scores, weights=None):
    comp = composite_similarity(module_scores, weights)
    filtered, I_scale = scale_invariance_filter(comp)
    return {"composite": comp, "filtered": filtered, "scale_invariance_index": I_scale}
