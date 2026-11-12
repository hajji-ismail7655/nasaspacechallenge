"""FastAPI backend for the Analog Discovery WebGIS dashboard."""
import io
import json
import os
import re
import struct
import subprocess

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

app = FastAPI(title="Cross-Planetary Terrestrial Analog Discovery Engine")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(BASE, "app", "static")
DATA = os.path.join(BASE, "data_lake")
os.makedirs(STATIC, exist_ok=True)

TARGETS = [
    "moon_shackleton_degerlache",
    "moon_malapert_massif",
    "moon_aristarchus_plateau",
    "moon_marius_hills_skylight",
    "mars_jezero_western_fan",
    "mars_arcadia_planitia",
    "mars_arsia_mons_pits",
    "mars_bagnold_dunes",
]

ALLOWED_DOMAINS = {
    "composite",
    "topography",
    "mineralogy",
    "thermal_illumination",
    "granular_aeolian",
    "volatiles_subsurface",
}
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_HDR_STRUCT = struct.Struct("<IIIIIIII ddd ffff 56s")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


def _is_safe_token(value: str) -> bool:
    return bool(value and _SAFE_TOKEN_RE.fullmatch(value))


def _inside_data(path: str) -> bool:
    real_data = os.path.realpath(DATA)
    real_path = os.path.realpath(path)
    try:
        return os.path.commonpath([real_path, real_data]) == real_data
    except ValueError:
        return False


def _read_hmap_octave(hmap_path: str, oi: int):
    import numpy as np

    with open(hmap_path, "rb") as f:
        raw = f.read()
    if len(raw) < 128:
        raise ValueError("Truncated .hmap header")
    hdr = _HDR_STRUCT.unpack(raw[:128])
    num_octaves = hdr[4]
    bh, bw = hdr[6], hdr[7]
    if oi < 0 or oi >= num_octaves:
        oi = 0
    off = 128
    for k in range(oi):
        hk = max(1, bh >> k)
        wk = max(1, bw >> k)
        off += 2 * hk * wk * 4
    hk = max(1, bh >> oi)
    wk = max(1, bw >> oi)
    n = 2 * hk * wk
    end = off + n * 4
    if end > len(raw):
        raise ValueError("Truncated .hmap octave payload")
    arr = np.frombuffer(raw[off:end], dtype=np.float32).reshape(2, hk, wk)
    return arr[0].copy(), arr[1].copy()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    p = os.path.join(STATIC, "index.html")
    if os.path.exists(p):
        return FileResponse(p)
    return JSONResponse({"error": "index.html not found"}, status_code=404)


@app.get("/targets")
def targets():
    return JSONResponse({"targets": TARGETS})


@app.get("/octaves")
def octaves():
    return JSONResponse({"octaves_m": [30, 60, 120, 240, 480]})


@app.get("/novelty-mask")
def novelty_mask_toggle(enabled: bool = True):
    return JSONResponse({
        "enabled": enabled,
        "description": "Toggle 150km known-analog suppression buffers",
    })


@app.get("/api/discoveries")
def discoveries(target_id: str = "", novelty_masked: bool = True):
    fname = "ranked_novel_discoveries.json" if novelty_masked else "ranked_unmasked_calibration.json"
    path = os.path.join(DATA, "results", fname)
    sites = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            sites = data.get("sites", data if isinstance(data, list) else [])
        except Exception:
            sites = []
    if target_id:
        sites = [s for s in sites if s.get("target_id") == target_id or s.get("target") == target_id]
    return JSONResponse({"sites": sites})


@app.get("/api/geojson/known-analogs")
def known_analogs():
    for p in (
        os.path.join(BASE, "Datasets", "known_analogs_mask.geojson"),
        os.path.join(BASE, "known_analogs_mask.geojson"),
    ):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return JSONResponse(json.load(f))
    for ref in ("origin/Datasets:known_analogs_mask.geojson", "Datasets:known_analogs_mask.geojson"):
        try:
            raw = subprocess.check_output(
                ["git", "-C", BASE, "show", ref],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            return JSONResponse(json.loads(raw))
        except Exception:
            continue
    return JSONResponse({"type": "FeatureCollection", "features": []})


def _locate_hmap(site_id: str, target_id: str, domain: str):
    target_name = f"{site_id}_{target_id}_{domain}.hmap"
    exact = os.path.join(DATA, "results", target_name)
    if os.path.exists(exact) and _inside_data(exact):
        return exact
    if not os.path.isdir(DATA):
        return None
    for root, _, files in os.walk(DATA):
        for fn in files:
            if fn == target_name:
                cand = os.path.join(root, fn)
                if _inside_data(cand):
                    return cand
    return None


@app.get("/api/heatmap/{site_id}/{target_id}/{domain}/{octave}.png")
def heatmap(site_id: str, target_id: str, domain: str, octave: str):
    if not (_is_safe_token(site_id) and _is_safe_token(target_id) and domain in ALLOWED_DOMAINS):
        return JSONResponse({"error": "Invalid heatmap parameters"}, status_code=400)
    try:
        oi = int(octave)
    except ValueError:
        return JSONResponse({"error": "Invalid octave index"}, status_code=400)
    if oi < 0 or oi >= 16:
        oi = 0

    import numpy as np
    from PIL import Image

    hmap_path = _locate_hmap(site_id, target_id, domain)
    try:
        if hmap_path is not None:
            sim, conf = _read_hmap_octave(hmap_path, oi)
        elif domain == "composite":
            # Compute fallback composite across any available domain .hmap files
            sims = []
            confs = []
            for dom in sorted(ALLOWED_DOMAINS - {"composite"}):
                dp = _locate_hmap(site_id, target_id, dom)
                if dp is not None:
                    s_d, c_d = _read_hmap_octave(dp, oi)
                    sims.append(s_d)
                    confs.append(c_d)
            if not sims:
                return Response(status_code=404)
            mh = min(a.shape[0] for a in sims)
            mw = min(a.shape[1] for a in sims)
            num = np.zeros((mh, mw), dtype=np.float64)
            den = np.zeros((mh, mw), dtype=np.float64)
            for s_d, c_d in zip(sims, confs):
                s_c = np.nan_to_num(s_d[:mh, :mw], nan=0.0)
                c_c = np.nan_to_num(c_d[:mh, :mw], nan=0.0)
                v = c_c > 0
                num = np.where(v, num + s_c, num)
                den = np.where(v, den + 1.0, den)
            sim = np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0).astype(np.float32)
            conf = np.where(den > 0, 1.0, 0.0).astype(np.float32)
        else:
            return Response(status_code=404)

        sim = np.clip(np.nan_to_num(sim, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0)
        conf = np.clip(np.nan_to_num(conf, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0)

        r = (255.0 * sim).astype("uint8")
        g = (255.0 * (1.0 - sim) * 0.5).astype("uint8")
        b = (255.0 * (1.0 - sim)).astype("uint8")
        a = np.where(conf > 0, (255.0 * (0.35 + 0.65 * conf)), 0.0).clip(0, 255).astype("uint8")
        rgba = np.stack([r, g, b, a], axis=-1)
        img = Image.fromarray(rgba, "RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        return Response(status_code=500, content=str(e))


@app.get("/breakdown/{site_id}")
def breakdown(site_id: str, path: str = Query(default=""), target_id: str = Query(default="")):
    if not _is_safe_token(site_id):
        return JSONResponse({"site_id": site_id, "error": "invalid site_id"}, status_code=400)
    target_path = path
    if not target_path and target_id and _is_safe_token(target_id):
        target_path = os.path.join(DATA, "results", f"{site_id}_{target_id}_breakdown.json")
    if target_path:
        rp = os.path.realpath(target_path)
        if not _inside_data(rp):
            return JSONResponse({"site_id": site_id, "error": "path outside data_lake"}, status_code=403)
        if os.path.exists(rp):
            try:
                with open(rp, encoding="utf-8") as f:
                    data = json.load(f)
                return JSONResponse({"site_id": site_id, "breakdown": data})
            except Exception as e:
                return JSONResponse({"site_id": site_id, "error": str(e)}, status_code=400)
    return JSONResponse({"site_id": site_id, "breakdown": "provide ?path= to _breakdown.json"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
