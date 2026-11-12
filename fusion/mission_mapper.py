"""Maps analog profiles to Artemis/Mars engineering tests."""
MISSION_TESTS = {
    "moon_shackleton_degerlache": "Autonomous Lidar Hazard Detection & Avoidance under 1.5 deg grazing illumination",
    "moon_malapert_massif": "High-elevation line-of-sight comms/relay validation",
    "moon_aristarchus_plateau": "High-Ti basaltic regolith beneficiation & ilmenite reduction",
    "moon_marius_hills_skylight": "Subsurface lava-tube robotic mesh-network navigation",
    "mars_jezero_western_fan": "Astrobiology sampling & deltaic stratigraphy analysis",
    "mars_arcadia_planitia": "ISRU water-ice excavation & landing site validation",
    "mars_arsia_mons_pits": "Subsurface cave robotic exploration & thermal retention study",
    "mars_bagnold_dunes": "Rover mobility & wheel-slip hazard assessment on active dunes",
}


def map_site(mission_target_id):
    return MISSION_TESTS.get(mission_target_id, "Generic analog field validation")
