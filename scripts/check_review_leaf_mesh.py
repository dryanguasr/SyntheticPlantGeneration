"""Small Blender-only mesh/UV check for the opt-in photo-review leaf."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import bpy
from uchuva_lsystem.blender_geometry import _create_leaf_blade

material = bpy.data.materials.new('review_check')
results = []
for shape in ('ovate_cordate', 'ovate_cordate_acuminate'):
    for relief in (.06, .12, .17):
        leaf = _create_leaf_blade(
            name=f'check_{shape}_{relief}', location=(0, 0, 0),
            direction=(0, 1, -.3), length=1, width=.75,
            material=material, edge_phase=.7, gravity_sag=.08,
            shape=shape, margin='irregular', curl=.15, twist_deg=20,
            edge_damage=0, surface_relief=relief)
        mesh = leaf.data
        assert all(math.isfinite(v) for point in mesh.vertices for v in point.co)
        assert all(face.area > 1e-12 for face in mesh.polygons)
        assert all(0 <= c <= 1 for uv in mesh.uv_layers['leaf_uv'].data for c in uv.uv)
        edge_uses = {}
        for face in mesh.polygons:
            for edge in face.edge_keys:
                edge_uses[edge] = edge_uses.get(edge, 0) + 1
        assert max(edge_uses.values()) <= 2
        tip = [v for v in mesh.vertices if abs(v.co.y - 1) < 1e-6]
        assert len(tip) == 1
        results.append(dict(shape=shape, relief=relief, vertices=len(mesh.vertices),
                            faces=len(mesh.polygons), minimum_face_area=min(f.area for f in mesh.polygons)))
destination = ROOT / 'outputs/integral_diagnosis_20261014/leaf_mesh_check_v1.json'
with destination.open('x') as stream:
    json.dump({'passed': True, 'cases': results,
               'limitation': 'Local leaf mesh only; does not validate plant intersections.'}, stream, indent=2)
print('LEAF_MESH_CHECK_PASSED', len(results), flush=True)
