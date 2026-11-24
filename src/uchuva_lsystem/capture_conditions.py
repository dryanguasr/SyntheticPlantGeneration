"""Balanced capture-only variation without coupling light to view depth."""
import random
from .capture_plan import condition_for_view


def balanced_condition_for_view(scene_index,view_index,seed=20261029):
    condition=condition_for_view(scene_index,view_index,seed)
    lights=['field','diffuse','shade']
    random.Random(f'{seed}:light_depth_balance:{scene_index}').shuffle(lights)
    # Every consecutive three-view block contains all lights. Rotating the
    # assignment by block also gives each depth every light within nine views.
    condition['diagnostic_light']=lights[(view_index%3+view_index//3)%3]
    condition['light_schedule_version']='balanced_depth_light/2'
    condition['capture_seed']=seed
    return condition
