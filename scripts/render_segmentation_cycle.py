"""Blender: render one new morphology at drone framing with lossless masks."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import random
import sys
import time

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import VERSION, GRADE_PRESETS, class_for_grade, check_deadline, write, sha
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.blender_scene import cleanup_scene, create_project_materials, create_material
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology, audit_scene_mesh_collisions
from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations, _set_render_engine
from uchuva_lsystem.sparse_pilot import walk_axes

spec = importlib.util.spec_from_file_location('sparse_renderer', ROOT/'scripts/render_sparse_pilot.py')
helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--morphology', type=Path, required=True)
    p.add_argument('--iteration', dest='cycle', type=int, required=True)
    p.add_argument('--views', type=int, default=10)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--audit-only', action='store_true')
    p.add_argument('--engine',choices=['CYCLES','BLENDER_EEVEE_NEXT'],default='BLENDER_EEVEE_NEXT')
    p.add_argument('--repair',action='store_true')
    p.add_argument('--resume-leaf-repair',action='store_true',help='Input is a checkpoint after reproductive repair; preserve that pass')
    a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    check_deadline(a.root); a.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    payload = json.loads(a.morphology.read_text())
    plant = Plant.from_dict(payload); cleanup_scene()
    common = dict(script_version=VERSION,seed=plant.seed,parameter_preset=plant.parameter_preset,cycle=a.cycle)
    # Fixed first-cycle intervention; later options must come from diagnosed errors.
    policy_path = a.root/f'cycle_{a.cycle:02d}'/'appearance.json'
    policy = json.loads(policy_path.read_text()) if policy_path.exists() else {}
    materials = create_project_materials(seed=plant.seed)
    grades = {}
    for axis in walk_axes(plant.axes):
        for node in axis.nodes:
            unit = node.reproductive_unit
            if unit and unit.calyx and unit.synthetic_reference_grade is not None:
                grade = unit.synthetic_reference_grade
                unit.calyx.material_key = GRADE_PRESETS[grade]
                grades['plant:'+unit.id] = grade
    geometry = build_geometry_from_morphology(plant, materials, instance_id='plant',
        add_ground=False, defer_scene_update=True)
    if a.repair:
        from uchuva_lsystem.blender_pose_repair import repair_reproductive_poses, repair_leaf_poses
        if not a.resume_leaf_repair:
            repair=repair_reproductive_poses(plant,materials,checkpoint=a.output/'morphology_in_progress.json')
            write(a.output/'pose_repair.json',{**common,**repair})
            write(a.output/'morphology_after_reproductive.json',plant.to_dict())
            cleanup_scene();materials=create_project_materials(seed=plant.seed)
            geometry=build_geometry_from_morphology(plant,materials,instance_id='plant',
                add_ground=False,defer_scene_update=True)
        else:
            write(a.output/'recovery.json',dict(checkpoint=str(a.morphology),checkpoint_sha256=sha(a.morphology),
                preserved_reproductive_pass=True,full_audit_still_required=True))
        leaf_repair=repair_leaf_poses(plant,materials,checkpoint=a.output/'morphology_in_progress.json')
        write(a.output/'leaf_pose_repair.json',{**common,**leaf_repair})
        cleanup_scene();materials=create_project_materials(seed=plant.seed)
        geometry=build_geometry_from_morphology(plant,materials,instance_id='plant',
            add_ground=False,defer_scene_update=True)
    bpy.context.view_layer.update()
    # Appearance-only intervention: preserve meshes, IDs and calyx class hues.
    seen=set()
    for key,material in materials.items():
        if not key.startswith('calyx_') or material.as_pointer() in seen:continue
        seen.add(material.as_pointer())
        if material.use_nodes:
            for node in material.node_tree.nodes:
                if node.type=='NORMAL_MAP':
                    node.inputs['Strength'].default_value=material.get('uchuva_normal_strength',.22)*policy.get('calyx_normal_gain',1.0)
    objects = list(bpy.context.scene.objects)
    points = [obj.matrix_world@Vector(v) for obj in objects if obj.type in {'MESH','CURVE'} for v in obj.bound_box]
    bounds = [[min(v[d] for v in points),max(v[d] for v in points)] for d in range(3)]
    audit = audit_scene_mesh_collisions(near_contact_distance=0, limit_clearance_search=True,
        max_bvh_cache_objects=128,tolerate_only_leaf_leaf=True)
    severe = [r for r in audit['physical_collisions'] if 'calyx' in (r['semantic_a'],r['semantic_b'])
              and 'leaf' not in (r['semantic_a'],r['semantic_b'])]
    audit.update(common, capacho_rigid_conflict_examples=len(severe),
                 acceptance='passed' if audit['status']=='valid' else 'pending_conflict_review',
                 audit_seconds=time.perf_counter()-started)
    write(a.output/'mesh_audit.json',audit)
    write(a.output/'morphology.json',plant.to_dict())
    if a.audit_only: return
    if audit['acceptance']!='passed':raise ValueError('Physical mesh and clearance gate not passed')
    if policy.get('tight_framing'):
        # Blender already provides exact evaluated vertices; no added dependency.
        points=[];deps=bpy.context.evaluated_depsgraph_get()
        for obj in objects:
            if obj.type not in {'MESH','CURVE'}:continue
            evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh()
            points.extend(evaluated.matrix_world@v.co for v in mesh.vertices)
            evaluated.to_mesh_clear()
    scene = bpy.context.scene
    scene.unit_settings.system='METRIC'; scene.unit_settings.scale_length=1/8
    # Sparse deterministic low vegetation, independent of the three appearance classes.
    from types import SimpleNamespace
    context_instances = ([SimpleNamespace(position=(x*8,y*8,0),plant_id=f'context_{x}_{y}')
                          for x in (-1,0,1) for y in (-1,0,1)]
                         if policy.get('geometric_seedlings', True) else [])
    helper.environment(plant.seed, context_instances)
    if policy.get('soil_color_variation'):
        soil=bpy.data.materials.get('sparse_soil');nodes=soil.node_tree.nodes;links=soil.node_tree.links
        coordinate=nodes.new('ShaderNodeTexCoord')
        noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=.45
        noise.inputs['Detail'].default_value=4
        ramp=nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color=(.055,.033,.016,1)
        ramp.color_ramp.elements[1].color=(.22,.17,.095,1)
        links.new(coordinate.outputs['Object'],noise.inputs['Vector'])
        links.new(noise.outputs['Fac'],ramp.inputs['Fac'])
        links.new(ramp.outputs['Color'],nodes.get('Principled BSDF').inputs['Base Color'])
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = policy.get('world_strength', .7)
    scene.view_settings.view_transform='AgX'; scene.view_settings.exposure=policy.get('exposure',.35)
    lighting_rng=random.Random(plant.seed+2719)
    if policy.get('vary_lighting_by_scene'):
        scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=lighting_rng.uniform(*policy.get('world_strength_range',[.5,.9]))
        scene.view_settings.exposure=lighting_rng.uniform(*policy.get('exposure_range',[.2,.45]))
        sun=bpy.data.objects.get('sun')
        sun.data.energy=lighting_rng.uniform(*policy.get('sun_energy_range',[1.3,2.5]))
        sun.rotation_euler=(lighting_rng.uniform(.3,.8),lighting_rng.uniform(-.5,.5),lighting_rng.uniform(-math.pi,math.pi))
    camera = bpy.data.objects.new('drone_camera',bpy.data.cameras.new('drone_camera'))
    scene.collection.objects.link(camera); scene.camera=camera
    camera.data.lens=36/(2*math.tan(math.radians(30))); camera.data.sensor_width=36
    camera.data.sensor_fit='HORIZONTAL'
    scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    scene.render.film_transparent=False
    # Use exact cells from the existing dictionary, never a drawn placeholder.
    white=create_material('cycle_marker_white',(.9,.9,.9,1),1)
    black=create_material('cycle_marker_black',(.001,.001,.001,1),1)
    marker_ids = [plant.seed % 36*2, plant.seed % 36*2+1]
    for identifier, sign in zip(marker_ids,(-1,1)):
        marker={'id':identifier,'plant_id':'plant','face':'front' if sign<0 else 'back',
            'center_world_m':[0,sign*.18,.12], 'normal_world':[0,sign,0],
            'side_m':.10,'backing_thickness_m':.003}
        cells=json.loads((ROOT/f'outputs/sparse_overhead_pilot_v7/markers/{identifier}.json').read_text())
        helper.plate(marker,cells,white,black)
    # Two posts/cable provide context without moving botanical organs.
    from uchuva_lsystem.blender_geometry import _create_cylinder_between
    post=create_material('cycle_support',(.13,.10,.07,1),.9)
    tie=create_material('cycle_strings',(.6,.62,.57,1),.9)
    post_x = 12 if policy.get('outward_support_strings') else 7
    for x in (-post_x,post_x):
        _create_cylinder_between(f'post_{x}',(x,0,0),(x,0,20),.18,post)
    _create_cylinder_between('overhead',(-post_x,0,20),(post_x,0,20),.012,tie)
    if policy.get('visible_support_strings'):
        from uchuva_lsystem.blender_pose_repair import _rendered_node_frames
        frames=_rendered_node_frames(plant)
        branches=[axis for axis in walk_axes(plant.axes) if axis.order==1 and axis.nodes]
        for index,axis in enumerate(branches[::max(1,len(branches)//4)][:4]):
            attachment=Vector(frames[axis.nodes[-1].id][0])
            anchor=Vector((max(-6.8,min(6.8,attachment.x)),0,20))
            if policy.get('outward_support_strings'):
                from uchuva_lsystem.support import outward_tie_anchor
                anchor=Vector(outward_tie_anchor(tuple(attachment),(0,0,0),
                              (-post_x,0,20),(post_x,0,20),policy.get('outward_offset_m',.9)*8))
            _create_cylinder_between(f'visible_training_string_{index}',attachment,anchor,.012,tie)
    rng=random.Random(plant.seed)
    center=Vector((0,0,max(bounds[2][1],9)/2))
    distance=max(policy.get('camera_distance_min_m',2.3), (bounds[2][1]/8+.15)/(2*math.tan(math.atan(math.tan(math.pi/6)*720/1280))*.85))
    records=[]
    for view in range(a.views):
        check_deadline(a.root); tick=time.perf_counter()
        sign=-1 if view<5 else 1
        azimuth=math.radians((-12,-6,0,6,12)[view%5])
        d=distance*(1+.04*(view%3))
        camera.location=(math.sin(azimuth)*d*8,sign*math.cos(azimuth)*d*8, center.z+.3*8)
        aim=center
        if 'camera_height_m' in policy:
            camera.location.z=policy['camera_height_m']*8
            aim=Vector((0,0,camera.location.z))
        if policy.get('tight_framing'):
            from uchuva_lsystem.camera_framing import fit_level_camera
            target_points=[tuple(v/8) for v in points]
            target_points += [(x,y,z) for x in (-.05,.05) for y in (-.18,.18) for z in (.07,.17)]
            fit=fit_level_camera(target_points,side=sign,azimuth=azimuth,
                                 margin=policy.get('framing_margin',.07))
            camera.location=Vector(fit['position'])*8;aim=Vector(fit['target'])*8;d=fit['distance']
        camera.rotation_euler=(aim-camera.location).to_track_quat('-Z','Y').to_euler()
        bpy.context.view_layer.update()
        if policy.get('tight_framing'):
            inverse=camera.matrix_world.inverted();horizontal=math.tan(math.pi/6);vertical=horizontal*720/1280
            projected=[]
            for point in points:
                v=inverse@point;depth=-v.z
                projected.append((.5+v.x/(2*depth*horizontal),.5+v.y/(2*depth*vertical),depth))
            complete=bool(projected) and all(.05<=u<=.95 and .05<=v<=.95 and d>0 for u,v,d in projected)
        else:
            projected=[world_to_camera_view(scene,camera,v) for v in points]
            complete=bool(projected) and all(.05<=v.x<=.95 and .05<=v.y<=.95 and v.z>0 for v in projected)
        folder=a.output/f'view_{view:02d}';folder.mkdir()
        _set_render_engine(scene,a.engine);scene.cycles.samples=16;scene.cycles.use_denoising=True
        scene.render.filepath=str((folder/'rgb.png').resolve())
        bpy.ops.render.render(write_still=True)
        mask=render_crisp_calyx_annotations(camera,folder,width=1280,height=720)
        record={**common,'view':view,'grades':grades,'mask':mask,'camera_matrix':[list(r) for r in camera.matrix_world],
            'distance_m':d,'whole_plant_in_frame':complete,'marker_ids':marker_ids,
            'seconds':time.perf_counter()-tick,'rgb_sha256':sha(folder/'rgb.png')}
        record['lighting']={'world_strength':scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value,
            'exposure':scene.view_settings.exposure,'sun_energy':bpy.data.objects['sun'].data.energy,
            'sun_rotation':list(bpy.data.objects['sun'].rotation_euler),'status':'engineering_heuristic'}
        record['framing_policy']='tight_complete_plant_and_marker' if policy.get('tight_framing') else 'original_wide'
        record['projected_plant_bounds']=[min(v[0] for v in projected),min(v[1] for v in projected),
                                          max(v[0] for v in projected),max(v[1] for v in projected)]
        write(folder/'capture.json',record);records.append(record)
        print('CAPTURE',plant.seed,view,round(record['seconds'],1),complete,flush=True)
    write(a.output/'complete.json',{**common,'views':len(records),'seconds':time.perf_counter()-started,
        'source_sha256':sha(a.morphology),'policy':policy,'bounds':bounds,'geometry':geometry})
    if a.views<=2:
        bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str((a.output/'technical.blend').resolve()))


if __name__=='__main__': main()
