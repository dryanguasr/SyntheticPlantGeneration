"""Small opt-in visual review, independent of frozen generation campaigns.

Three blue daytime conditions and one hazy condition; sparse overmature surface
assignments on existing complete organs. All fractions are preview engineering
choices, not estimates of prevalence in a real crop.
"""
import hashlib
import math
from .capture_skies import sky_condition_for_view

VERSION = 'blue-sky-sparse-overmature-review/1'


def sample_conditions():
    recipes = (
        ('scene_027_view_021', 'clear_blue', 'field', 12., -35., 2.0),
        ('scene_027_view_010', 'clear_blue', 'field', -7., 40., 4.5),
        ('scene_028_view_008', 'clear_blue', 'field', 18., -110., 2.5),
        ('scene_028_view_010', 'hazy_clear', 'diffuse', 5., -65., 9.),
    )
    rows = []
    for view, sky, light, elevation, azimuth, angle in recipes:
        scene, index = int(view[6:9]), int(view[-3:])
        c = sky_condition_for_view(scene, index, 20261111)
        c.update(sky_type=sky, diagnostic_light=light,
                 elevation_offset_deg=elevation, azimuth_offset_deg=azimuth,
                 exposure_offset_ev=0., sun_angle_deg=angle,
                 aerosol_density=.025 if sky == 'clear_blue' else .8,
                 sky_air_density=.65 if sky == 'clear_blue' else .9,
                 sky_ozone_density=1.5 if sky == 'clear_blue' else 1.1,
                 analytic_sky_saturation=1.25 if sky == 'clear_blue' else 1.05,
                 analytic_sky_value=.9 if sky == 'clear_blue' else 1.,
                 sky_schedule_version=VERSION,
                 sky_provenance='engineering_heuristic; blue/hazy small approval sample, not measured weather')
        if scene == 28:
            c['fill_energy_w'] = 120. if sky == 'clear_blue' else 80.
        rows.append(dict(source_view=view, scene_id=view[:9], condition=c))
    return rows


def sparse_assignments(ids, views, seed=20261111, fraction=.03):
    """Retain all IDs and a reproducible small minority of overmature surfaces.

    Reserve a few sufficiently visible examples for review; then distribute the
    remainder independently of light. Cap visible minority at five percent in
    each source view. Visibility does not alter geometry or camera.
    """
    ids = sorted(set(ids))
    if not ids or not 0 < fraction <= .05:
        raise ValueError('Nonempty IDs and minority fraction in (0,.05] required')
    def rank(i, stream):
        return hashlib.sha256(f'{seed}:{stream}:{i}'.encode()).hexdigest()
    visible = [{i['instance_id'] for i in r['instances']} for r in views]
    caps = [max(1, math.floor(len(v) * .05)) for v in visible]
    selected = set()
    target = max(1, round(len(ids) * fraction))
    def add(i):
        if i not in ids or i in selected:
            return
        if all(len(selected & v) + int(i in v) <= cap for v, cap in zip(visible, caps)):
            selected.add(i)
    for row in views:
        large = sorted(row['instances'], key=lambda i: -i['visible_pixels'])[:24]
        for item in sorted(large, key=lambda i: rank(i['instance_id'], row['view_id']))[:3]:
            if len(selected) < target:
                add(item['instance_id'])
    for i in sorted(ids, key=lambda i: rank(i, 'minority')):
        if len(selected) >= target:
            break
        add(i)
    return {i: dict(class_id=2 if i in selected else int(int(rank(i, 'other')[:8], 16) % 2),
                    appearance_only=True, assignment_version=VERSION) for i in ids}
