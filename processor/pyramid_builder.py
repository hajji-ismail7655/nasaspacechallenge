"""Anti-aliased Gaussian octave generator.

Builds 5 octaves (30,60,120,240,480 m) via Gaussian (sigma=0.85*2^k)
pre-filtering then 2^k decimation from the base tile. Coarser inputs populate
valid higher octaves and set unavailable finer octaves to nodata.
"""
import json
from typing import List

import numpy as np
from scipy.ndimage import gaussian_filter

NODATA = -9999.0
OCTAVE_RESOLUTIONS = [30.0, 60.0, 120.0, 240.0, 480.0]


def build_pyramid(tile, base_resolution_m, num_octaves=5, sigma_base=0.85, nodata=NODATA):
    is_channelled = tile.ndim == 3
    if not is_channelled:
        tile = tile[None, ...]
    C, H, W = tile.shape
    tile = tile.astype(np.float32).copy()

    out = []
    for k in range(num_octaves):
        oct_res = 30.0 * (2 ** k)
        # octave valid only if its resolution >= input base resolution
        if oct_res + 1e-6 < base_resolution_m:
            Hk = max(1, H >> k)
            Wk = max(1, W >> k)
            out.append(np.full((C, Hk, Wk), nodata, dtype=np.float32))
            continue
        # filter base with sigma = sigma_base * 2^k, then decimate 2^k
        sigma = sigma_base * (2 ** k)
        Hk = max(1, H >> k)
        Wk = max(1, W >> k)
        filtered = np.empty((C, H, W), dtype=np.float32)
        for c in range(C):
            ch = tile[c]
            mask = ch != nodata
            filled = np.where(mask, ch, 0.0)
            sm = gaussian_filter(filled, sigma=sigma)
            w = gaussian_filter(mask.astype(np.float32), sigma=sigma)
            with np.errstate(divide="ignore", invalid="ignore"):
                val = np.where(w > 1e-6, sm / np.where(w > 1e-6, w, 1.0), nodata)
            val = np.where(mask | (w > 1e-6), val, nodata)
            filtered[c] = val.astype(np.float32)
        dec = filtered[:, ::(2**k), ::(2**k)]
        # ensure shape Hk x Wk
        arr = np.full((C, Hk, Wk), nodata, dtype=np.float32)
        h = min(Hk, dec.shape[1]); w = min(Wk, dec.shape[2])
        arr[:, :h, :w] = dec[:, :h, :w]
        out.append(arr)

    if not is_channelled:
        out = [o[0] for o in out]
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-res", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--num-octaves", type=int, default=5)
    args = ap.parse_args()
    tile = np.load(args.input)
    octs = build_pyramid(tile, args.base_res, num_octaves=args.num_octaves)
    np.save(args.out, np.array(octs, dtype=object), allow_pickle=True)
    print(json.dumps({"out": args.out, "num_octaves": len(octs), "shapes": [list(o.shape) for o in octs]}))


if __name__ == "__main__":
    main()
