#!/usr/bin/env python3
"""Technical views of actual CAD geometry; never a native-simulator screenshot.

Blender and optional already-installed Pillow are presentation tools only.
Geometry, transforms, camera and input hashes are saved beside every render.
No CAD original or simulation collision mesh is edited by this renderer.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HOUSING = 'Gripper y engranaje:1'
ARM = 'Eslabon L:1'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def prepare(inventory_path, motion_path, output, target=None, brep_path=None):
    inventory, motion = read_json(inventory_path), read_json(motion_path)
    documents = {row['id']: row for row in inventory['documents']}
    assembly = next(row for row in documents.values() if row['source_path']=='gripper/Gripper ensamble.iam')
    if assembly['sha256'].lower() != motion['assembly_sha256'].lower():
        raise ValueError('CAD inventory and motion refer to different source assemblies')
    instances = []
    for occurrence in inventory['occurrences']:
        if occurrence['root_document_id'] != assembly['id'] or occurrence.get('suppressed'):
            continue
        document = documents[occurrence['document_id']]
        exported = document['exports'].get('obj', {})
        if exported.get('status') != 'exported':
            continue
        path = (inventory_path.parent/exported['uri']).resolve()
        if digest(path) != exported['sha256']:
            raise ValueError('Mesh differs from the frozen CAD inventory: '+str(path))
        role = 'housing' if occurrence['name']==HOUSING else 'arm' if occurrence['name']==ARM else 'context'
        instances.append({'name': occurrence['name'], 'role': role, 'path': str(path),
            'sha256': exported['sha256'], 'transform_m': occurrence['transform_root_m'],
            'source_document_sha256': document['sha256'],
            'chord_tolerance_m': exported['details']['chord_tolerance_m']})
    if not all(any(row['role']==role for row in instances) for role in ('housing','arm')):
        raise ValueError('Both actual CAD pieces are required')
    brep = read_json(brep_path) if brep_path else None
    if brep and (brep['status']!='COMPLETED' or not brep['source_files_unchanged']):
        raise ValueError('Completed native BRep extraction with unchanged originals is required')
    fine_samples = {round(row['driver_rad'],10):row for row in brep['pairs']} if brep else {}
    camera_target = target or (fine_samples[.1]['interference_geometry'][0]['centroid_m'] if brep else [.027,.002,0])
    identity = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]

    def fine_instances(q):
        rows=[]
        for item in [*fine_samples[q]['visualization_parts'],*fine_samples[q]['interference_geometry']]:
            role = 'arm' if item['role']=='link' else item['role']
            rows.append({'name':item.get('occurrence',role),'role':role,'path':str((brep_path.parent/item['uri']).resolve()),
                'sha256':item['sha256'],'transform_m':identity,'chord_tolerance_m':item.get('chord_tolerance_m',1e-6)})
        return rows

    if brep:
        instances = [row for row in instances if row['role']=='context']+fine_instances(0.)
    views = [{'name': 'general_q0', 'kind': 'overview', 'driver_rad': 0,
              'target_m': [0, -.006, .004], 'direction': [1.2, 3.5, 1.4], 'orthographic_scale_m': .175,
              'instances': instances}]
    for q in (0., .1):
        sample = next(row for row in motion['samples'] if abs(row['driver_rad']-q)<1e-12)
        pieces = []
        for instance in instances:
            if instance['role'] in ('housing','arm'):
                row = dict(instance)
                row['transform_m'] = sample['occurrence_transforms_m'][row['name']]
                pieces.append(row)
        views.append({'name': 'detalle_q0' if q==0 else 'detalle_q010', 'kind': 'detail', 'driver_rad': q,
                      'target_m': camera_target, 'direction': [.15, 4, .15], 'orthographic_scale_m': .018,
                      'instances': fine_instances(q) if brep else pieces, 'transparent': bool(brep)})
    manifest = {'schema_version': 'cad-interference-technical-render/1.0',
        'input_sha256': {str(path.resolve()): digest(path) for path in (inventory_path,motion_path)},
        'assembly_sha256': assembly['sha256'], 'views': views, 'source_units': 'metres',
        'presentation': {'roles': {'housing': 'blue', 'arm': 'orange', 'context': 'gray', 'intersection': 'red'},
                        'colors_are_diagnostic_not_CAD_appearances': True,
                        'native_simulator_capture': False, 'preliminary_coarse_mesh': not bool(brep)},
        'render': {'engine': 'CYCLES', 'device': 'CPU', 'threads': 2, 'samples': 16,
                   'width': 1100, 'height': 1000}}
    if brep:
        manifest['input_sha256'][str(brep_path)]=digest(brep_path)
        manifest['native_brep_metrics']={str(q):{'minimum_distance_m':row['minimum_distance_m'],
            'interference_volumes_m3':row['interference_volumes_m3']} for q,row in fine_samples.items()}
    dump(output/'render_manifest.json', manifest)
    return manifest


def blender_worker(manifest_path):
    import bpy
    from mathutils import Matrix, Vector
    manifest = read_json(manifest_path)
    output = manifest_path.parent

    def material(name, color, opacity=1):
        item = bpy.data.materials.new(name)
        item.diffuse_color = (*color, 1)
        item.use_nodes = True
        nodes = item.node_tree.nodes
        nodes.clear()
        surface = nodes.new('ShaderNodeBsdfPrincipled')
        surface.inputs['Base Color'].default_value = (*color, 1)
        surface.inputs['Roughness'].default_value = .5
        surface.inputs['Metallic'].default_value = .08
        result = nodes.new('ShaderNodeOutputMaterial')
        if opacity < 1:
            transparent = nodes.new('ShaderNodeBsdfTransparent')
            mix = nodes.new('ShaderNodeMixShader')
            mix.inputs[0].default_value = opacity
            item.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
            item.node_tree.links.new(surface.outputs[0], mix.inputs[2])
            item.node_tree.links.new(mix.outputs[0], result.inputs[0])
        else:
            item.node_tree.links.new(surface.outputs[0], result.inputs[0])
        return item

    def load_mesh(instance):
        path = Path(instance['path'])
        if digest(path) != instance['sha256']:
            raise ValueError('Render input mesh hash changed')
        vertices, faces = [], []
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            words = line.split()
            if words and words[0]=='v':
                vertices.append(tuple(float(value) for value in words[1:4]))
            elif words and words[0]=='f':
                faces.append(tuple(int(value.split('/')[0])-1 for value in words[1:]))
        mesh = bpy.data.meshes.new(instance['name'])
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(instance['name'], mesh)
        bpy.context.collection.objects.link(obj)
        obj.matrix_world = Matrix([instance['transform_m'][i:i+4] for i in range(0,16,4)])
        return obj

    for view in manifest['views']:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = manifest['render']['samples']
        scene.cycles.use_denoising = True
        scene.render.threads_mode = 'FIXED'
        scene.render.threads = manifest['render']['threads']
        scene.render.resolution_x = manifest['render']['width']
        scene.render.resolution_y = manifest['render']['height']
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        scene.render.film_transparent = True
        scene.view_settings.view_transform = 'Standard'
        scene.world = bpy.data.worlds.new('Technical studio')
        scene.world.use_nodes = True
        scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.82,.86,.92,1)
        scene.world.node_tree.nodes['Background'].inputs[1].default_value = .55
        colors = {'housing': (.035,.30,.70), 'arm': (1,.29,.035),
                  'context': (.48,.51,.55), 'intersection': (.90,.015,.025)}
        materials = {role: material(role, color, .22 if role=='housing' and view.get('transparent') else
                                   .55 if role=='arm' and view.get('transparent') else 1)
                     for role,color in colors.items()}
        cover_material=material('Context cover, presentation only',colors['context'],.10)
        for instance in view['instances']:
            obj = load_mesh(instance)
            obj.data.materials.append(cover_material if instance['name']=='Gripper 1:1' else materials[instance['role']])
        target = Vector(view['target_m'])
        direction = Vector(view['direction']).normalized()
        data = bpy.data.cameras.new('Matched orthographic camera')
        camera = bpy.data.objects.new('Matched orthographic camera', data)
        bpy.context.collection.objects.link(camera)
        camera.location = target+direction*.4
        camera.rotation_euler = (target-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = view['orthographic_scale_m']
        camera.data.clip_start, camera.data.clip_end = .0001, 10
        scene.camera = camera
        for name,location,power,size in [('key',[.12,.18,.20],.04,.15),('fill',[-.13,.10,.02],.02,.12),
                                         ('edge',[.02,-.15,.12],.03,.10)]:
            light_data = bpy.data.lights.new(name, 'AREA')
            light_data.energy, light_data.shape, light_data.size = power, 'DISK', size
            light = bpy.data.objects.new(name,light_data)
            bpy.context.collection.objects.link(light)
            light.location = Vector(location)+target
            light.rotation_euler = (target-light.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath = str(output/(view['name']+'.png'))
        bpy.ops.render.render(write_still=True)
        from bpy_extras.object_utils import world_to_camera_view
        point = world_to_camera_view(scene,camera,Vector(manifest['views'][1]['target_m']))
        view['target_pixel'] = [point.x*scene.render.resolution_x,(1-point.y)*scene.render.resolution_y]
        view['camera_matrix_world'] = [value for row in camera.matrix_world for value in row]
        view['image_sha256'] = digest(scene.render.filepath)
    dump(output/'render_manifest.json', manifest)


def compose(output, overview_only=False):
    from PIL import Image, ImageDraw, ImageFont
    manifest = read_json(output/'render_manifest.json')
    regular = 'C:/Windows/Fonts/arial.ttf'
    bold = 'C:/Windows/Fonts/arialbd.ttf'
    title = ImageFont.truetype(bold,40)
    body = ImageFont.truetype(regular,25)
    small = ImageFont.truetype(regular,21)
    blue,orange,red,ink = '#246eae','#e87522','#df2733','#233448'

    def panel(path):
        img = Image.open(path).convert('RGBA')
        background = Image.new('RGBA',img.size,'#eef2f6')
        background.alpha_composite(img)
        return background.convert('RGB')

    general = Image.new('RGB',(1500,1210),'white')
    drawing = ImageDraw.Draw(general)
    drawing.text((40,30),'Pinza CAD | ubicación de las piezas',font=title,fill=ink)
    general.paste(panel(output/'general_q0.png'),(200,120))
    for i,(label,color) in enumerate([('Carcasa',blue),('Eslabón L:1',orange),('Otras piezas', '#858b94')]):
        x=40+i*440
        drawing.rectangle((x,90,x+24,114),fill=color)
        drawing.text((x+36,87),label,font=body,fill=ink)
    point=manifest['views'][0].get('target_pixel')
    if point is None:
        # Same orthographic camera as the worker; this permits annotating the
        # completed overview while a later closeup is still rendering.
        view=manifest['views'][0]
        length=math.sqrt(sum(v*v for v in view['direction']))
        n=[v/length for v in view['direction']]
        r=[-n[1],n[0],0];length=math.hypot(r[0],r[1]);r=[v/length for v in r]
        up=[n[1]*r[2]-n[2]*r[1],n[2]*r[0]-n[0]*r[2],n[0]*r[1]-n[1]*r[0]]
        delta=[a-b for a,b in zip(manifest['views'][1]['target_m'],view['target_m'])]
        width,height=manifest['render']['width'],manifest['render']['height']
        point=[width*(.5+sum(a*b for a,b in zip(delta,r))/view['orthographic_scale_m']),
               height*.5-width*sum(a*b for a,b in zip(delta,up))/view['orthographic_scale_m']]
    dump(output/'general_annotation.json',{'target_assembly_m':manifest['views'][1]['target_m'],
        'target_raw_image_pixel':point,'annotation_scope':'Position of the q=.1 BRep interference projected onto the initial CAD overview'})
    point=(200+point[0],120+point[1])
    drawing.ellipse((point[0]-16,point[1]-16,point[0]+16,point[1]+16),outline=red,width=4)
    drawing.line((point[0]+16,point[1],1340,point[1],1340,980),fill=red,width=3)
    drawing.text((1060,995),'Zona revisada',font=body,fill=red)
    drawing.text((40,1135),'Posición CAD inicial q = 0. Tapa frontal translúcida para ubicar el eslabón.',font=small,fill=ink)
    drawing.text((40,1170),'Colores de diagnóstico. Vista técnica derivada del CAD; no es captura de Gazebo.',font=small,fill=ink)
    general.save(output/'01_ubicacion.png')
    if overview_only:
        return
    comparison = Image.new('RGB',(2240,1260),'white')
    drawing = ImageDraw.Draw(comparison)
    drawing.text((35,25),'Carcasa y eslabón | misma cámara y escala',font=title,fill=ink)
    for x,name,label,metric in [(20,'detalle_q0','q = 0 rad | 0°','Separación mínima BRep: 1,805 mm'),
                               (1120,'detalle_q010','q = 0,10 rad | 5,73°','Intersección BRep: 6,618 mm³')]:
        drawing.text((x+20,93),label,font=body,fill=ink)
        comparison.paste(panel(output/(name+'.png')),(x,145))
        drawing.text((x+20,1160),metric,font=body,fill=ink if name=='detalle_q0' else red)
    note = ('Carcasa azul y eslabón naranja translúcidos. Rojo: sólido de intersección BRep. '
            'Mallas de presentación a 1 µm; medida del BRep nativo.' if not manifest['presentation']['preliminary_coarse_mesh'] else
            'Vistas técnicas de CAD. Triangulación visual de 0,20 mm; la medida proviene del sólido BRep.')
    drawing.text((35,1220),note,font=small,fill=ink)
    comparison.save(output/'02_comparacion.png')


def main():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--inventory',type=Path)
    parser.add_argument('--motion',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--target',nargs=3,type=float)
    parser.add_argument('--brep',type=Path)
    parser.add_argument('--blender',type=Path,default=Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe'))
    args=parser.parse_args(argv)
    if args.worker:
        blender_worker(args.worker.resolve())
        return
    if not args.inventory or not args.motion or not args.output:
        parser.error('inventory, motion and output are required')
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    prepare(args.inventory.resolve(),args.motion.resolve(),output,args.target,args.brep.resolve() if args.brep else None)
    (output/'render_source.py').write_bytes(Path(__file__).read_bytes())
    with (output/'blender.log').open('w',encoding='utf-8') as log:
        subprocess.run([str(args.blender),'--background','--threads','2','--python',str(Path(__file__).resolve()),
                        '--','--worker',str(output/'render_manifest.json')],stdout=log,stderr=subprocess.STDOUT,check=True)
    compose(output)
    print(str(output/'01_ubicacion.png'))
    print(str(output/'02_comparacion.png'))


if __name__=='__main__':
    main()
