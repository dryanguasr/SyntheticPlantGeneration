"""Pure contracts for the paired appearance experiment, independent of plant load."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

VERSION = "appearance-factorial/1"
CLASSES = ("Pintona", "Madura", "Sobremadura")
BANKS = {"B": ("previous", "previous"), "L": ("candidate", "previous"),
         "T": ("previous", "candidate"), "LT": ("candidate", "candidate")}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def component_seed(seed, component, identity=""):
    """Stable independent streams; never use Python's process-dependent hash()."""
    return int(hashlib.sha256(f"{seed}:{component}:{identity}".encode()).hexdigest()[:8], 16)


def initial_profiles():
    """Explicit candidates for human review, not calibrated reflectance or labels."""
    return {
        "version": VERSION, "human_review": "pending", "seed": 20261026,
        "plant_preset": "trained_trellis_audit_v2", "load_policy": "architecture_driven",
        "classes": list(CLASSES), "class_semantics": "calyx appearance; fruit maturity unknown",
        "reference_policy": "real training only; supplied illustration qualitative",
        "color_management": {"view_transform": "AgX", "look": "None", "gamma": 1.0},
        "lighting": {
            "previous": {"world_strength": .3, "sun_energy": 1.5, "sun_angle_deg": 4.,
                         "exposure_ev": 0., "fill_energy": 0., "sun_elevation_deg": 32.,
                         "sun_azimuth_deg": 125., "sky": "MULTIPLE_SCATTERING",
                         "provenance": "measured code configuration in frozen renders/render.py"},
            "candidate": {"world_strength": .8, "sun_energy": .8, "sun_angle_deg": 15.,
                          "exposure_ev": .25, "fill_energy": 35., "sun_elevation_deg": 45.,
                          "sun_azimuth_deg": 125., "sky": "MULTIPLE_SCATTERING",
                          "provenance": "engineering_heuristic; inspect organ and background separately"},
        },
        "diagnostic_lights": {
            "diffuse": {"world_strength": .8, "sun_energy": .35, "sun_angle_deg": 18., "exposure_ev": .25},
            "field": {"world_strength": .6, "sun_energy": 1.5, "sun_angle_deg": 5., "exposure_ev": 0.},
            "shade": {"world_strength": .45, "sun_energy": .2, "sun_angle_deg": 18., "exposure_ev": .25},
        },
        "materials": {
            "previous": {"implementation": "v142 archived shader behavior", "class_presets":
                         ["calyx_transition_v1", "calyx_straw_v1", "calyx_dry_v1"]},
            "candidate": {"class_presets": ["calyx_transition_v1", "calyx_straw_v1", "calyx_straw_v2"],
                          "normal_strength": .24, "micro_strength": .12, "micro_distance": .001,
                          "roughness_min": .82, "roughness_max": .96,
                          "vein_factor": .55, "vein_power": .8,
                          "vein_colors_linear": [[.065,.085,.025,1],[.15,.12,.035,1],[.18,.115,.025,1]],
                          "albedo_multiplier_linear": [[1.,1.,1.],[1.08,1.02,.83],[1.10,.94,.68]],
                          "wear_fraction": 0., "wear_independent_of_class": True,
                          "provenance": "manual_initial_guess; no mandatory brown deterioration"},
        },
        "render": {"width": 960, "height": 720, "samples": 24, "engine": "CYCLES",
                   "device": "OPTIX", "denoise": True, "organ_emission": False},
        "context": {"modes": ["canopy_close", "ground_tangle"],
                    "class_independent": True, "paired_geometry": True},
        "calibration": {"rounds_max": 2, "focal_views": 18, "context_views": 32},
    }


def resolved_profile(profiles, bank, diagnostic_light=None):
    light, material = BANKS[bank]
    lighting = deepcopy(profiles["lighting"][light])
    if diagnostic_light is not None:
        lighting.update(profiles["diagnostic_lights"][diagnostic_light])
    return {"bank": bank, "lighting": lighting, "material_mode": material,
            "materials": deepcopy(profiles["materials"][material]),
            "color_management": deepcopy(profiles["color_management"])}


def calibration_schedule():
    rows = []
    for class_id in range(3):
        for light in ("diffuse", "field", "shade"):
            for bank in ("B", "T"):
                rows.append(dict(view_id=f"focal_c{class_id}_{light}_{bank}", kind="focal",
                                 plant_index=0, class_id=class_id, light=light, bank=bank, view=0))
    for plant in range(4):
        for view in range(2):
            for bank in BANKS:
                rows.append(dict(view_id=f"plant_{plant:02d}_view{view}_{bank}", kind="context",
                                 plant_index=plant, class_id=None, light=None, bank=bank, view=view))
    assert len(rows) == 50
    return rows
