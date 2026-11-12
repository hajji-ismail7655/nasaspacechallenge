"""FastAPI backend for the Analog Discovery WebGIS dashboard."""
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, FileResponse, Response
import os
import json
import struct

app = FastAPI(title="Cross-Planetary Terrestrial Analog Discovery Engine")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(BASE, "app", "static")
DATA = os.path.join(BASE, "data_lake")
os.makedirs(STATIC, exist_ok=True)

TARGETS = [
    "moon_shackleton_degerlache", "moon_malapert_massif",
    "moon_aristarchus_plateau", "moon_marius_hills_skylight",
    "mars_jezero_western_fan", "mars_arcadia_planitia",
    "mars_arsia_mons_pits", "mars_bagnold_dunes"
]

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
    return JSONResponse({"enabled": enabled, "description": "Toggle 150km known-analog suppression buffers"})

@app.get("/api/discoveries")
def discoveries(target_id: str = "", novelty_masked: bool = True):
    fname = "ranked_novel_discoveries.json" if novelty_masked else "ranked_unmasked_calibration.json"
    path = os.path.join(DATA, "results", fname)
    sites = []
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            sites = data.get("sites", data if isinstance(data, list) else [])
        except Exception:
            sites = []
    if target_id:
        sites = [s for s in sites if s.get("target_id") == target_id or s.get("target") == target_id]
    return JSONResponse({"sites": sites})

@app.get("/api/geojson/known-analogs")
def known_analogs():
    p = os.path.join(BASE, "Datasets", "known_analogs_mask.geojson")
    if not os.path.exists(p):
        p = os.path.join(BASE, "known_analogs_mask.geojson")
    if os.path.exists(p):
        with open(p) as f:
            return JSONResponse(json.load(f))
    return JSONResponse({"type": "FeatureCollection", "features": []})

@app.get("/api/heatmap/{site_id}/{target_id}/{domain}/{octave}.png")
def heatmap(site_id: str, target_id: str, domain: str, octave: str):
    hmap_path = os.path.join(DATA, "results", "%s_%s_%s.hmap" % (site_id, target_id, domain))
    if not os.path.exists(hmap_path):
        for root,_,files in os.walk(DATA):
            for fn in files:
                if fn.endswith(".hmap") and site_id in fn and domain in fn:
                    hmap_path = os.path.join(root, fn); break
            if os.path.exists(hmap_path):
                break
    if not os.path.exists(hmap_path):
        return Response(status_code=404)
    try:
        raw = open(hmap_path, "rb").read()
        hdr = struct.unpack("<IIIIIIII ddd ffff 56s", raw[:128])
        num_octaves = hdr[4]; bh = hdr[6]; bw = hdr[7]
        oi = int(octave)
        if oi < 0 or oi >= num_octaves:
            oi = 0
        off = 128
        for k in range(oi):
            Hk = bh >> k; Wk = bw >> k
            if Hk == 0: Hk = 1
            if Wk == 0: Wk = 1
            off += 2 * Hk * Wk * 4
        Hk = bh >> oi; Wk = bw >> oi
        if Hk == 0: Hk = 1
        if Wk == 0: Wk = 1
        n = 2 * Hk * Wk
        import numpy as np
        arr = np.frombuffer(raw[off:off+n*4], dtype=np.float32).reshape(2, Hk, Wk)
        sim = arr[0]; conf = arr[1]
        from PIL import Image
        import numpy as np
        r = (255 * sim).astype('uint8')
        g = (255 * (1-sim) * 0.5).astype('uint8')
        b = (255 * (1-sim)).astype('uint8')
        a = (255 * conf).astype('uint8')
        a = np.where(conf > 0, a, 0).astype('uint8')
        rgba = np.stack([r, g, b, a], axis=-1)
        img = Image.fromarray(rgba, "RGBA")
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        return Response(status_code=500, content=str(e))

@app.get("/breakdown/{site_id}")
def breakdown(site_id: str, path: str = Query(default="")):
    if path:
        rp = os.path.realpath(path)
        if not rp.startswith(os.path.realpath(DATA)):
            return JSONResponse({"site_id": site_id, "error": "path outside data_lake"}, status_code=403)
        if os.path.exists(rp):
            try:
                with open(rp) as f:
                    data = json.load(f)
                return JSONResponse({"site_id": site_id, "breakdown": data})
            except Exception as e:
                return JSONResponse({"site_id": site_id, "error": str(e)}, status_code=400)
    return JSONResponse({"site_id": site_id, "breakdown": "provide ?path= to _breakdown.json"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
