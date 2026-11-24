"""Opt-in grey, papery drying over the preserved vein-led pigment field.

All optical coefficients are engineering heuristics. No morphology, alpha or
physiological age is inferred from this visual model.
"""
from dataclasses import asdict, dataclass
from .calyx_dry_refinement import (
    DryPlan, surface_plan as prior_plan, simulate, vein_graph, SNAPSHOTS,
    dry_fibres, color_surface as prior_color,
)

VERSION = 'calyx-ash-papery-drying/1'


@dataclass(frozen=True)
class AshPlan(DryPlan):
    texture_revision: str = VERSION

    def to_dict(self):
        return dict(version=VERSION, **asdict(self))


def surface_plan(class_id, index, seed):
    return AshPlan(**{**asdict(prior_plan(class_id, index, seed)), 'texture_revision': VERSION})


def grey_drying(rgb, pigment, severity, coherent, grain, gains):
    """Desaturate already pigmented tissue in the frozen profile's color space.

    Compensate the existing profile's yellow bias in the baked map, without
    changing that profile. Preserve luminance and the diffusion front; drying
    never seeds pigment in untouched tissue. A mild cool cast stays mottled.
    """
    import numpy as np
    c = np.clip(np.asarray(rgb) / 255., 0, 1)
    linear = np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)
    gain = np.asarray(gains, dtype=float)
    if gain.shape != (3,) or np.any(gain <= 0):
        raise ValueError('Three positive frozen profile gains required')
    effective = linear * gain
    luminance = effective @ np.array((.2126, .7152, .0722))
    cool = np.stack((.96 + .025 * coherent, .985 + .015 * coherent,
                     1.055 + .045 * coherent), axis=2)
    # Normalize the cool tint to preserve the pigment's original luminance.
    cool /= (cool @ np.array((.2126, .7152, .0722)))[:, :, None]
    dry = luminance[:, :, None] * cool
    weight = np.clip(np.asarray(pigment), 0, 1) ** .8 * severity * .97
    target = effective * (1 - weight[:, :, None]) + dry * weight[:, :, None]
    # Irregular tiny dry flecks; no pale blanket and no remote pigment source.
    flecks = np.clip(np.asarray(grain) * 35., -.35, .35)
    target *= (1 + .30 * weight * flecks)[:, :, None]
    c = np.clip(target / gain, 0, 1)
    return 255 * np.where(c <= .0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - .055)


def color_surface(veins, orders, pigment, coherent, grain, class_id, *,
                  severity=0., bleached=False, gains=(1., 1., 1.)):
    rgb = prior_color(veins, orders, pigment, coherent, grain, class_id,
                      severity=severity, bleached=bleached)
    if class_id != 2 or severity == 0:
        return rgb
    return grey_drying(rgb, pigment, severity, coherent, grain, gains)
