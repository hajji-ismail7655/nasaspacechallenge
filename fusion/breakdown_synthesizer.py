"""Generates quantitative physical breakdown reports / site dossiers."""
import json
import os


def synthesize_site_dossier(site_id, coords, module_scores, breakdowns, mission_test):
    dossier = {
        "site_id": site_id,
        "coordinates": coords,
        "module_scores": module_scores,
        "analogy_breakdown": breakdowns,
        "operational_test_protocol": mission_test,
        "scale_range": "30m-480m",
    }
    return dossier


def write_dossier(path, dossier):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(dossier, f, indent=2)
