"""FastAPI backend for the Analog Discovery WebGIS dashboard."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import os

app = FastAPI(title="Cross-Planetary Terrestrial Analog Discovery Engine")

TARGETS = [
    "moon_shackleton_degerlache", "moon_malapert_massif",
    "moon_aristarchus_plateau", "moon_marius_hills_skylight",
    "mars_jezero_western_fan", "mars_arcadia_planitia",
    "mars_arsia_mons_pits", "mars_bagnold_dunes"
]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/targets")
def targets():
    return JSONResponse({"targets": TARGETS})


@app.get("/octaves")
def octaves():
    return JSONResponse({"octaves_m": [30, 60, 120, 240, 480]})


@app.get("/novelty-mask")
def novelty_mask_toggle(enabled: bool = True):
    return JSONResponse({"enabled": enabled, "description": "Toggle 150km known-analog suppression buffers"})


@app.get("/breakdown/{site_id}")
def breakdown(site_id: str):
    return JSONResponse({"site_id": site_id, "breakdown": "see _breakdown.json", "mission_test": site_id})
