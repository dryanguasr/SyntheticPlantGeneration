"""Bounded mesh-based pose repair for independently generated bank plants.

The caller owns scene reconstruction, active-time accounting and admission.
No camera, label count or organ dimension is an input to the search.
"""
from __future__ import annotations
from copy import deepcopy
import math


def anatomy_signature(plant):
    from .blender_pose_repair_v2 import pose_invariant_manifest
    protected=deepcopy(plant)
    def visit(axes):
        for axis in axes:
            axis.azimuth_deg=axis.branch_angle_deg=0.
            axis.provenance.pop('axis_pose_repair_v1',None)
            visit(axis.child_axes)
    visit(protected.axes)
    return pose_invariant_manifest(protected)


def repair_bank_plants(plants, records, layout, build, audit, folder, write, *, rounds=3):
    import bpy
    from mathutils import Matrix, Vector
    from mathutils.bvhtree import BVHTree
    from .axis_pose_repair import repair_axis_poses
    from .blender_pose_repair_v2 import repair_size_preserving_poses
    from .validation import validate_morphology_tree
    from .grammar import record_reproductive_counts
    from .morphology import Plant
    before=[anatomy_signature(p) for p in plants]
    sets=build(plants)
    mesh,ground=audit('generated')
    history=[]
    for cycle in range(rounds):
        if mesh['physical_collision_count']==0 and ground['status']=='valid':break
        for index,(plant,instance) in enumerate(zip(plants,layout.plant_instances)):
            inventory={o.name:dict(type=o.type,hide_render=o.hide_render,
                properties={k:v for k,v in o.items() if k.startswith('uchuva_') and isinstance(v,(str,int,float,bool))})
                for o in bpy.context.scene.objects}
            terrain=bpy.data.objects['uchuva_terrain_agricultural']
            terrain_tree=BVHTree.FromObject(terrain,bpy.context.evaluated_depsgraph_get())
            inverse=terrain.matrix_world.inverted()
            def height(x,y):
                hit=terrain_tree.ray_cast(inverse@Vector((x,y,1000.)),Vector((0,0,-1)))
                if hit[0] is None:raise ValueError('Axis candidate outside terrain coverage')
                return (terrain.matrix_world@hit[0]).z
            axis=repair_axis_poses(plant,instance=instance,
                intersection_pairs=mesh['physical_collisions'],object_inventory=inventory,
                include_organ_axis_constraints=True,clearance_pairs=[],
                max_passes=2,max_trials_per_axis=32,max_seconds=100,ground_height=height)
            write(folder/f'repair_c{cycle}_p{index}_axis.json',axis)
            if axis['changes']:
                sets=build(plants)
                mesh,ground=audit(f'c{cycle}_p{index}_axes')
            transform=Matrix.Translation(Vector(instance.position))@Matrix.Rotation(math.radians(instance.rotation_deg),4,'Z')
            # Guarantee a leaf pass. Large reproductive populations previously
            # exhausted every plant deadline before a single leaf was visited.
            # The total search allowance remains 360/180 s, split explicitly.
            reports=[]
            for kind,seconds in (("leaf",120 if cycle==0 else 60),
                                 ("reproductive",240 if cycle==0 else 120)):
                report=repair_size_preserving_poses(plant,sets['previous'],instance_id=instance.plant_id,
                    world_from_local=transform,max_passes=4,
                    max_trials_per_organ=2048 if kind=='reproductive' and cycle>0 else 112,
                    max_seconds=seconds,ground_clearance_m=.001,
                    fine_angular_step_deg=5,dense_reproductive_step_deg=5 if kind=='reproductive' and cycle>0 else None,
                    repair_clearance=False,organ_kinds=(kind,),checkpoint=folder/f'checkpoint_p{index}_{kind}.json')
                write(folder/f'repair_c{cycle}_p{index}_{kind}.json',report)
                reports.append(report)
            write(folder/f'repair_c{cycle}_p{index}_organs.json',dict(
                status='per_kind_search_requires_full_audit',
                elapsed_seconds=sum(r['elapsed_seconds'] for r in reports),
                candidate_count=sum(r['candidate_count'] for r in reports),
                adjustments=[a for r in reports for a in r['adjustments']],
                max_seconds_by_kind=dict(leaf=120 if cycle==0 else 60,reproductive=240 if cycle==0 else 120)))
            assert anatomy_signature(plant)==before[index],'Pose repair changed anatomy'
            # Rebuild after each plant: later plants see exact serialized geometry,
            # including neighbours changed by earlier searches.
            write(folder/f'c{cycle}_p{index}_adapted.json',plant.to_dict())
            plants[index]=Plant.from_dict(plant.to_dict())
            sets=build(plants)
            mesh,ground=audit(f'c{cycle}_p{index}_rebuilt')
        history.append(dict(cycle=cycle,physical=mesh['physical_collision_count'],
            positive_clearance=mesh['clearance_violation_count'],ground=ground['status']))
        print('BANK_REPAIR_CYCLE',history[-1],flush=True)
    validations=[]
    for index,plant in enumerate(plants):
        record_reproductive_counts(plant,'adapted')
        assert anatomy_signature(plant)==before[index]
        validation=validate_morphology_tree(plant,stage='adapted')
        write(folder/f'plant_{index}_adapted_validation.json',validation)
        path=folder/f'plant_{index}_adapted.json'
        write(path,plant.to_dict())
        from hashlib import sha256
        record=records[index]
        record.update(generated_path=record['path'],generated_sha256=record['sha256'],
            path=str(path.resolve()),sha256=sha256(path.read_bytes()).hexdigest(),
            counts_after_adaptation=before[index]['counts'],anatomy_preserved=True,
            validation=validation['status'],validation_stage='adapted')
        validations.append(validation)
    sets=build(plants)
    mesh,ground=audit('adapted_final')
    write(folder/'repair_summary.json',dict(history=history,invariants=before,
        physical_collisions=mesh['physical_collision_count'],positive_clearance=mesh['clearance_violation_count'],
        ground_status=ground['status'],anatomy_preserved=True,validation_errors=[len(v['errors']) for v in validations],
        policy='positive inter-organ gaps descriptive; exact intersections block; terrain margin 1mm required'))
    return sets,mesh,ground,validations
