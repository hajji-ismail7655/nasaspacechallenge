"""Anti-aliased Gaussian octave generator.

Builds 5 octaves (30,60,120,240,480 m) via Gaussian (sigma=0.85*2^k)
pre-filtering then 2x decimation. Coarser inputs populate valid higher
octaves and set unavailable finer octaves to nodata.
"""
import json
from typing import List, Tuple, Optional

import numpy as np
from scipy.ndimage import gaussian_filter

NODATA = -9999.0
OCTAVE_RESOLUTIONS = [30.0, 60.0, 120.0, 240.0, 480.0]


def build_pyramid(tile: np.ndarray,
                  base_resolution_m: float,
                  num_octaves: int = 5,
                  sigma_base: float = 0.85,
                  nodata: float = NODATA) -> List[np.ndarray]:
    """Return list of num_octaves arrays (each (C,H,W) or (H,W)).

    tile: input array, shape (C,H,W) or (H,W), at base_resolution_m.
    """
    is_channelled = tile.ndim == 3
    if not is_channelled:
        tile = tile[None, ...]
    C, H, W = tile.shape
    valid_mask = tile != nodata  # may be partial; treat all as valid for filtering

    # Determine which octaves are physically valid given input resolution.
    # An octave at resolution r is valid if r >= base_resolution_m (within tolerance).
    out: List[Optional[np.ndarray]] = []
    cur = tile.astype(np.float32).copy()
    cur_res = base_resolution_m
    for k in range(num_octaves):
        target_res = base_resolution_m * (2 ** k)
        if cur_res > target_res * 1.05 and k > 0:
            # input too coarse for this (finer) octave -> nodata
            Hk, Wk = (H >> k) if k < 8 else 1, (W >> k) if k < 8 else 1
            # actually finer than input: mark nodata
            Hk = max(1, H >> k)
            Wk = max(1, W >> k)
            arr = np.full((C, Hk, Wk), nodata, dtype=np.float32)
            out.append(arr)
            continue
        # gaussian filter sigma = 0.85 * 2^k (in pixels of current grid)
        sigma = sigma_base * (2 ** k)
        filtered = np.empty_like(cur)
        for c in range(C):
            ch = cur[c]
            # replace nodata with 0 for filtering then restore mask
            mask = ch != nodata
            filled = np.where(mask, ch, 0.0)
            sm = gaussian_filter(filled, sigma=sigma)
            # normalize by weight where mask
            w = gaussian_filter(mask.astype(np.float32), sigma=sigma)
            with np.errstate(divide="ignore", invalid="ignore"):
                val = np.where(w > 1e-6, sm / np.where(w > 1e-6, w, 1.0), nodata)
            val = np.where(mask | (w > 1e-6), val, nodata)
            filtered[c] = val.astype(np.float32)
        # decimate 2x for next octave
        dec = filtered[:, ::2, ::2].copy() if (filtered.shape[1] > 1 and filtered.shape[2] > 1) else filtered
        out.append(filtered.copy())
        cur = dec
        cur_res = target_res
    # If input resolution coarser than 30m, finer octaves (below input) already handled above by cur_res check? 
    # Ensure first octave validity: if base_resolution_m > 30, octave0 (30m) is invalid -> nodata
    # Re-evaluate: mark octaves whose resolution < base_resolution_m as nodata
    for k in range(num_octaves):
        res = base_resolution_m  # placeholder; actual octave res = 30*2^k
        pass

    # Correct validity: an octave at 30*2^k m is only valid if 30*2^k >= base_resolution_m
    corrected = []
    for k in range(num_octaves):
        oct_res = 30.0 * (2 ** k)
        if oct_res + 1e-6 < base_resolution_m:
            Hk = max(1, H >> k)
            Wk = max(1, W >> k)
            corrected.append(np.full((C, Hk, Wk), nodata, dtype=np.float32))
        else:
            # resize to expected dims H>>k, W>>k
            arr = out[k]
            Hk = max(1, H >> k)
            Wk = max(1, W >> k)
            if arr.shape[1:] != (Hk, Wk):
                # pad/crop
                a = np.full((C, Hk, Wk), nodata, dtype=np.float32)
                h = min(Hk, arr.shape[1]); w = min(Wk, arr.shape[2])
                a[:, :h, :w] = arr[:, :h, :w]
                arr = a
            corrected.append(arr)
    out = corrected

    if not is_channelled:
        out = [o[0] for o in out]
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help=".npy tile (C,H,W) or (H,W)")
    ap.add_argument("--base-res", type=float, required=True)
    ap.add_argument("--out", required=True, help="output .npy (object array of octaves)")
    ap.add_argument("--num-octaves", type=int, default=5)
    args = ap.parse_args()
    tile = np.load(args.input)
    octs = build_pyramid(tile, args.base_res, num_octaves=args.num_octaves)
    # save as list via npy of object array
    np.save(args.out, np.array(octs, dtype=object), allow_pickle=True)
    print(json.dumps({"out": args.out, "num_octaves": len(octs), "shapes": [list(o.shape) for o in octs]}))


if __name__ == "__main__":
    import json
    main()
