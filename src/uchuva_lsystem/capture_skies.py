"""Capture-only weather schedule; no morphology or camera changes."""
import random
from .capture_conditions import balanced_condition_for_view


def sky_condition_for_view(scene_index,view_index,seed=20261030):
    condition=balanced_condition_for_view(scene_index,view_index,seed)
    skies=['clear_blue','hazy_clear','overcast']
    random.Random(f'{seed}:sky_depth_balance:{scene_index}').shuffle(skies)
    sky=skies[(view_index%3+view_index//3)%3]
    # Clear direct light, hazy diffuse light, and soft overcast illumination.
    condition.update(sky_type=sky,sky_schedule_version='sky_depth_balance/1',
        diagnostic_light={'clear_blue':'field','hazy_clear':'diffuse','overcast':'shade'}[sky],
        aerosol_density={'clear_blue':.15,'hazy_clear':1.5,'overcast':1.0}[sky],
        sky_air_density=1.0,sky_ozone_density=1.0,
        sun_angle_deg={'clear_blue':2.0,'hazy_clear':8.0,'overcast':18.0}[sky],
        sky_provenance='engineering_heuristic; procedural cloud-free atmosphere or inherited overcast panorama; not measured weather')
    # Wider daytime elevations are independent of plant/camera seeds.
    rng=random.Random(f'{seed}:sky_sun:{scene_index}:{view_index}')
    condition['elevation_offset_deg']=rng.uniform(-15.,23.)
    return condition
