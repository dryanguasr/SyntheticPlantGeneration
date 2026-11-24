"""Explicit ambient-radiance color correction, independent of morphology.

The coefficient is a visual engineering choice checked on a neutral probe, not
a measured atmospheric spectrum. Sun direction, intensity and camera sky stay
independent of this chroma-only adjustment.
"""
from dataclasses import dataclass,asdict
import math

VERSION='daylight-ambient-chroma-balance/1'
LUMA=(.2126,.7152,.0722)


@dataclass(frozen=True)
class DaylightBalance:
    neutral_mix:float
    parameter_status:str='engineering_heuristic_checked_with_neutral_probe'
    camera_sky_policy:str='preserve original sky and horizon'
    texture_policy:str='preserve all pigment, albedo, roughness and normal maps'

    def to_dict(self):return dict(version=VERSION,**asdict(self))


def radiance_balance(rgb,neutral_mix):
    if len(rgb)!=3 or not all(math.isfinite(c) and c>=0 for c in rgb):
        raise ValueError('Three finite nonnegative linear channels required')
    if not math.isfinite(neutral_mix) or not 0<=neutral_mix<=1:
        raise ValueError('Mix in [0,1] required')
    luminance=sum(c*w for c,w in zip(rgb,LUMA))
    return tuple((1-neutral_mix)*c+neutral_mix*luminance for c in rgb)


def balance_for_condition(condition):
    return DaylightBalance(.85 if condition['sky_type']=='clear_blue' else .25)
