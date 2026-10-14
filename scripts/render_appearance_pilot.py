"""Seven review captures from an existing morphology-backed Blender plant.

No training labels: three calyx appearance hypotheses await human approval.
Run in Blender with --source, --morphology, --audit and a new --output folder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_lsystem.blender_scene import create_project_materials, create_material
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.validation import validate_morphology_tree

VERSION = 'calyx-appearance-review/1.1'
PALETTE = {'pintona': 'calyx_transition_v0', 'madura': 'calyx_straw_v1',
           'sobremadura': 'calyx_dry_v1'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'morphology', 'audit', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--focus-only', action='store_true')
    parser.add_argument('--frontal-fill', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    payload = json.loads(args.morphology.read_text(encoding='utf-8'))
    common = dict(script_version=VERSION, seed=payload['seed'],
                  parameter_preset=payload['parameter_preset'])

    def write(name, data):
        (args.output / name).write_text(json.dumps({**common, **data}, indent=2), encoding='utf-8')

    shutil.copy2(args.morphology, args.output / f'morphology_tree_seed_{payload["seed"]}.json')
    shutil.copy2(args.audit, args.output / 'source_mesh_contacts.json')
    write(f'validation_report_seed_{payload["seed"]}.json',
          validate_morphology_tree(Plant.from_dict(payload)))
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    scene = bpy.context.scene

    def geometry_hash():
        digest = hashlib.sha256()
        for obj in sorted(scene.objects, key=lambda o: o.name):
            if obj.type == 'MESH' and obj.get('uchuva_semantic_class'):
                digest.update(repr((obj.name, [list(r) for r in obj.matrix_world],
                                    [tuple(v.co) for v in obj.data.vertices],
                                    [tuple(p.vertices) for p in obj.data.polygons])).encode())
        return digest.hexdigest()

    before_geometry = geometry_hash()
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 960
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    for obj in list(scene.objects):
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)
    world = bpy.data.worlds.new('pilot_daylight')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (.65, .75, .9, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = .45
    scene.world = world
    light = bpy.data.lights.new('pilot_sun', 'SUN')
    light.energy = 2
    light.angle = .15
    obj = bpy.data.objects.new(light.name, light)
    scene.collection.objects.link(obj)
    obj.rotation_euler = (.45, -.6, -.5)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.02))
    ground = bpy.context.object
    ground.name = 'pilot_ground'
    ground.data.materials.append(create_material('pilot_soil', (.075, .045, .022, 1), .95))
    calyces = sorted([o for o in scene.objects if o.type == 'MESH'
                     and o.get('uchuva_semantic_class') == 'calyx'], key=lambda o: o.name)
    if not calyces:
        raise ValueError('Source has no identifiable calyces')
    bpy.context.view_layer.update()

    def center(o):
        return sum((o.matrix_world @ Vector(v) for v in o.bound_box), Vector()) / 8

    candidates = [o for o in calyces if 3 < center(o).z < 8]
    target = min(candidates or calyces, key=lambda o: center(o).y)
    focus = center(target)
    camera = scene.camera
    camera.data.type = 'PERSP'
    camera.data.lens = 48
    camera.data.dof.use_dof = False
    views = {'medio': (Vector((0, -16, 9)), Vector((0, 0, 5))),
             'detalle': (focus + Vector((0, -3.4, .5)), focus)}
    if args.frontal_fill:
        world.node_tree.nodes['Background'].inputs['Strength'].default_value = .8
        light = bpy.data.lights.new('pilot_frontal_fill', 'AREA')
        light.energy = 900
        light.size = 5
        obj = bpy.data.objects.new(light.name, light)
        scene.collection.objects.link(obj)
        obj.location = focus + Vector((-2, -4, 3))
        obj.rotation_euler = (focus-obj.location).to_track_quat('-Z', 'Y').to_euler()
        scene.view_settings.exposure = .5
    rows = []

    def render(name, view, hypothesis=None):
        tick = time.perf_counter()
        camera.location, aim = views[view]
        camera.rotation_euler = (aim-camera.location).to_track_quat('-Z', 'Y').to_euler()
        bpy.context.view_layer.update()
        scene.render.filepath = str(args.output / (name + '.png'))
        bpy.ops.render.render(write_still=True)
        rows.append(dict(file=name+'.png', view=view, hypothesis=hypothesis,
                         camera_matrix=[list(r) for r in camera.matrix_world],
                         seconds=time.perf_counter()-tick, sha256=sha(Path(scene.render.filepath))))
        write('captures.json', dict(captures=rows, status='in_progress'))
        print('PILOT_CAPTURE', name, rows[-1]['seconds'], flush=True)

    if not args.focus_only:
        for view in views:
            render('base_' + view, view)
    materials = create_project_materials(seed=payload['seed'])
    assignments = []
    for obj in calyces:
        # Independent of historical four-class/grade mapping; preserve it untouched.
        index = int(hashlib.sha256(obj.name.encode()).hexdigest()[:8], 16) % 3
        label = list(PALETTE)[index]
        obj.data.materials.clear()
        obj.data.materials.append(materials[PALETTE[label]])
        obj['pilot_appearance_hypothesis'] = label
        assignments.append(dict(object=obj.name, reproductive_instance_id=obj.get('uchuva_reproductive_instance_id'),
                                appearance_hypothesis=label, human_review='pending',
                                fruit_maturity='unknown'))
    if not args.focus_only:
        for view in views:
            render('textura_' + view, view)
    for label, preset in PALETTE.items():
        target.data.materials.clear()
        target.data.materials.append(materials[preset])
        target['pilot_appearance_hypothesis'] = label
        render('foco_' + label, 'detalle', label)
    write('appearance_review.json', dict(label_basis='calyx_appearance_user_confirmed',
          proposed_material_mapping=PALETTE, parameter_status='manual_initial_guess',
          assignments=assignments, controlled_target=target.name,
          controlled_variants='Only focal calyx material changes; geometry, camera and lighting fixed',
          training_enabled=False, human_review='pending'))
    # Restore the mixed candidate so the saved scene agrees with its assignments.
    label = next(r['appearance_hypothesis'] for r in assignments if r['object'] == target.name)
    target.data.materials.clear()
    target.data.materials.append(materials[PALETTE[label]])
    target['pilot_appearance_hypothesis'] = label
    assert before_geometry == geometry_hash(), 'Appearance experiment changed plant geometry'
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output / 'piloto_apariencia.blend'))
    write('captures.json', dict(captures=rows, status='complete', elapsed_seconds=time.perf_counter()-started,
          source_blend=str(args.source), source_blend_sha256=sha(args.source),
          morphology_sha256=sha(args.morphology), source_audit_sha256=sha(args.audit),
          runner_sha256=sha(Path(__file__)),
          plant_geometry_sha256=before_geometry, geometry_preserved=True,
          frontal_fill=args.frontal_fill, focus_only=args.focus_only,
          limitations=['Existing mesh collisions unresolved', 'No measured occlusion',
                      'Appearance labels pending human review', 'No training or transfer evaluation']))
    shutil.copy2(Path(__file__), args.output / 'runner_snapshot.py')


if __name__ == '__main__':
    main()
