"""Exact-mesh trials of length-preserving two/four-bone nodal poses.

Only posture records in the morphology tree are committed. Cached trials are
guidance: callers must independently rebuild the entire tree before admission.
"""
from __future__ import annotations
from copy import deepcopy
import math


def repair_local_nodal_contacts(plant, mesh_report, *, instance_id='growth',
                                max_nodes=3, max_trials=40, max_seconds=90,
                                checkpoint=None, candidate_modes=('counterbend_pair','fixed_pair')):
    import bpy
    from mathutils import Matrix, Vector
    from mathutils.bvhtree import BVHTree
    from .nodal_repulsion import (KEY, axes, initialize_growth_poses, protected_anatomy,
                                 counterbend_candidates, local_joint_candidates, sub)
    from .collisions import build_scene_proxies
    from .geometry_contracts import axis_sag_factor
    from .blender_pose_repair import _remove_pose_objects
    from .blender_pose_repair_v2 import _MeshIndex, _auditable, _bounds
    from .blender_geometry import (_create_sagging_curve_between, _mesh_collision_exempt,
                                  _mesh_intersection_classification)
    from .execution_budget import awake_seconds

    started=awake_seconds();invariant=protected_anatomy(plant)
    layout=initialize_growth_poses(plant)
    owners={n.id:(a,n) for a in axes(plant.axes) for n in a.nodes}
    unit_nodes={instance_id+':'+n.reproductive_unit.id:n.id for _,n in owners.values() if n.reproductive_unit}
    organ_nodes={}
    for _,n in owners.values():
        if n.leaf:
            for suffix in ('','_petiole','_midrib'):organ_nodes[n.leaf.id+suffix]=n.id

    objects=[o for o in bpy.context.scene.objects if o.get('uchuva_plant_id')==instance_id
             and o.type in {'MESH','CURVE','SURFACE'}]
    root=bpy.data.objects.get('uchuva_'+instance_id+'_root')
    if root and any(abs(root.matrix_world[i][j]-(1 if i==j else 0))>1e-6 for i in range(4) for j in range(4)):
        raise ValueError('Automatic local nodal repair requires identity instance transform')
    part_owner={p.id:a for a in axes(plant.axes) for p in a.internodes}
    part_lookup={p.id:p for a in axes(plant.axes) for p in a.internodes}
    def node_of(obj):
        return (str(obj.get('uchuva_parent_node_id','')) or str(obj.get('uchuva_node_end_id',''))
                or unit_nodes.get(obj.get('uchuva_reproductive_instance_id'),'')
                or organ_nodes.get(obj.get('uchuva_organ_id'),''))
    lookup={o.name:o for o in objects};hot={}
    for row in mesh_report.get('physical_collisions',[]):
        for key in ('object_a','object_b'):
            obj=lookup.get(row[key])
            if obj is None:continue
            node_id=node_of(obj)
            if node_id in owners:hot.setdefault(node_id,set()).add(obj.name)
    if 'four_nodes' in candidate_modes:
        # A colliding insertion can be an inner joint of a valid upstream
        # window even when starting the window at that insertion is impossible.
        for node_id,target_names in [(k,set(v)) for k,v in hot.items()]:
            axis,node=owners[node_id];position=axis.nodes.index(node)
            for previous in axis.nodes[max(0,position-3):position]:
                hot.setdefault(previous.id,set()).update(target_names)
    frames={};bones={}
    build_scene_proxies(layout,{'growth':plant},frame_output=frames,bone_output=bones)
    ordered=sorted(hot,key=lambda k:(frames['growth'][k][0][2],owners[k][0].order,owners[k][1].position_index,k))
    # Cache actual evaluated geometry, not proxy shapes.
    def cached(obj):
        ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        try:
            if mesh is None or not mesh.polygons:return None
            vertices=[ev.matrix_world@v.co for v in mesh.vertices]
            polygons=[tuple(p.vertices) for p in mesh.polygons]
            return dict(obj=obj,vertices=vertices,polygons=polygons,bounds=_bounds(vertices),bvh=None)
        finally:ev.to_mesh_clear()
    def tree(item):
        if item['bvh'] is None:
            item['bvh']=BVHTree.FromPolygons(item['vertices'],item['polygons'],epsilon=.0005)
        return item['bvh']
    index=_MeshIndex()
    for obj in objects:
        if _auditable(obj):
            item=cached(obj)
            if item:index.add(item)

    def score(items, classes, target_names):
        changed={p['obj'].name:p for p in items};temporary=_MeshIndex()
        groups={}
        for item in items:
            temporary.add(item)
            category=classes.get(item['obj'].name)
            if category is not None:groups.setdefault(category,set()).add(item['obj'].name)
        seen=set();physical=critical=target=0;target_volume=0.
        for name,left in changed.items():
            category=classes.get(name);excluded=groups.get(category,set()) if category is not None else set()
            neighbours={p['obj'].name for p in index.near(left['bounds'],excluded)}
            neighbours.update(p['obj'].name for p in temporary.near(left['bounds'],excluded))
            for identity in sorted(neighbours):
                if identity==name:continue
                pair=tuple(sorted((name,identity)))
                if pair in seen:continue
                seen.add(pair);right=changed.get(identity,index.entries.get(identity))
                if right is None:continue
                a,b=left['bounds'],right['bounds']
                if any(a[1][d]+.0011<b[0][d] or b[1][d]+.0011<a[0][d] for d in range(3)):continue
                x,y=left['obj'],right['obj']
                if _mesh_collision_exempt(x,y) or x.get('uchuva_semantic_class')==y.get('uchuva_semantic_class')=='leaf':continue
                if not tree(left).overlap(tree(right)):continue
                if _mesh_intersection_classification(x,y) in {'intentional_support','visual_occlusion'}:continue
                physical+=1
                rigid=not any(o.get('uchuva_semantic_class')=='leaf' or o.get('uchuva_organ_kind')=='petiole' for o in (x,y))
                critical+=rigid
                if name in target_names or identity in target_names:
                    target+=1
                    target_volume+=math.prod(max(0.,min(a[1][d],b[1][d])-max(a[0][d],b[0][d])) for d in range(3))
        return dict(physical=physical,critical=critical,target=target,target_volume=target_volume)

    scratch=bpy.data.scenes.new('local_nodal_trials');adjustments=[];trial_count=0
    try:
        for node_id in ordered:
            if len(adjustments)>=max_nodes or awake_seconds()-started>=max_seconds:break
            axis,node=owners[node_id];position=axis.nodes.index(node)
            if position>=len(axis.internodes)-1:continue
            frames={};bones={}
            build_scene_proxies(layout,{'growth':plant},frame_output=frames,bone_output=bones)
            old_frames,old_bones=frames['growth'],bones['growth']
            bearing=(node.reproductive_unit.pedicel.provenance[KEY]['direction'] if node.reproductive_unit else
                     node.leaf.provenance[KEY]['direction'] if node.leaf else (0,0,-1))
            families=[]
            if 'counterbend_pair' in candidate_modes:families.append(counterbend_candidates(axis,position,old_bones,bearing=bearing))
            if 'fixed_pair' in candidate_modes:families.append(local_joint_candidates(axis,position,old_bones))
            if 'four_nodes' in candidate_modes:
                from .nodal_chain_candidates import four_node_candidates,balanced_proposals
                families.append(four_node_candidates(axis,position,old_bones,bearing=bearing))
                candidates=balanced_proposals(families,max_trials)
            else:
                candidates=[p for family in families for p in family]
                candidates.sort(key=lambda c:(c['delta_z']>1e-10,abs(c['degrees']),abs(c.get('azimuth',0))))
            available_parts=axis.internodes[position:position+(4 if 'four_nodes' in candidate_modes else 2)]
            original=[deepcopy(p.provenance[KEY]['direction']) for p in available_parts]
            target_names=hot[node_id]
            best=None
            for proposal in candidates[:max_trials]:
                if awake_seconds()-started>=max_seconds:break
                directions=proposal.get('directions') or (proposal['first_direction'],proposal['second_direction'])
                parts=available_parts[:len(directions)]
                for part,direction in zip(parts,directions):
                    part.provenance[KEY]['direction']=list(direction)
                new_frames={};new_bones={}
                build_scene_proxies(layout,{'growth':plant},frame_output=new_frames,bone_output=new_bones)
                new_frames,new_bones=new_frames['growth'],new_bones['growth']
                updates=[];classes={};translations={};rebuilds={};temporary=[]
                try:
                    for obj in objects:
                        organ=str(obj.get('uchuva_organ_id',''));kind=obj.get('uchuva_organ_kind')
                        if kind=='axis_segment' and organ in old_bones:
                            before,after=old_bones[organ],new_bones[organ]
                            delta=Vector(sub(after['start'],before['start']))
                            unchanged=(Vector(sub(after['end'],before['end']))-delta).length<1e-8
                            unchanged=unchanged and all((Vector(after[k])-Vector(before[k])).length<1e-8 for k in ('incoming','direction'))
                            if not unchanged:
                                rebuilds[obj.name]=(obj,organ,after);continue
                        else:
                            attached=node_of(obj)
                            if attached not in old_frames:continue
                            delta=Vector(sub(new_frames[attached][0],old_frames[attached][0]))
                        if delta.length<1e-9:continue
                        translations[obj.name]=(obj,delta)
                        if obj.name in index.entries:
                            old=index.entries[obj.name];vertices=[v+delta for v in old['vertices']]
                            updates.append({**old,'vertices':vertices,'bounds':_bounds(vertices),'bvh':None})
                            classes[obj.name]=tuple(round(v,10) for v in delta)
                    with bpy.context.temp_override(scene=scratch,view_layer=scratch.view_layers[0],collection=scratch.collection):
                        for name,(obj,organ,after) in rebuilds.items():
                            owner=part_owner[organ];part=part_lookup[organ]
                            curve=_create_sagging_curve_between('local_trial',Vector(after['start']),Vector(after['end']),max(part.radius_cm*.08,.008),None,
                                endpoint_tangents=(Vector(after['incoming']),Vector(after['direction'])) if owner.provenance.get('continuous_tangent_v140') else None,
                                sag_factor=axis_sag_factor(owner))
                            temporary.append(curve)
                        bpy.context.view_layer.update()
                        for (name,(obj,_,_)),curve in zip(rebuilds.items(),temporary):
                            item=cached(curve);item['obj']=obj;updates.append(item)
                    if not updates or any(item['bounds'][0][2]<.010 for item in updates):continue
                    prior=[index.entries[item['obj'].name] for item in updates]
                    old_score=score(prior,classes,target_names);new_score=score(updates,classes,target_names)
                    trial_count+=1
                    objective=lambda s:(s['target'],s['target_volume'],s['critical'],s['physical'])
                    if objective(new_score)<objective(old_score) and (best is None or objective(new_score)<objective(best['score'])):
                        best=dict(proposal=deepcopy(proposal),score=new_score,old_score=old_score,
                                  translations=translations,rebuilds=rebuilds)
                    if best and best['score']['target']==0:break
                finally:
                    _remove_pose_objects(temporary)
                    for part,direction in zip(available_parts,original):part.provenance[KEY]['direction']=list(direction)
            if best is None:continue
            proposal=best['proposal']
            directions=proposal.get('directions') or (proposal['first_direction'],proposal['second_direction'])
            parts=available_parts[:len(directions)]
            for part,direction in zip(parts,directions):
                part.provenance[KEY]['direction']=list(direction)
                part.provenance[KEY]['automatic_local_joint']=dict(node=node_id,proposal=proposal,status='engineering_heuristic')
            for obj,delta in best['translations'].values():obj.matrix_world=Matrix.Translation(delta)@obj.matrix_world
            for obj,organ,after in best['rebuilds'].values():
                owner=part_owner[organ];part=part_lookup[organ]
                curve=_create_sagging_curve_between('local_commit',Vector(after['start']),Vector(after['end']),max(part.radius_cm*.08,.008),None,
                    endpoint_tangents=(Vector(after['incoming']),Vector(after['direction'])) if owner.provenance.get('continuous_tangent_v140') else None,
                    sag_factor=axis_sag_factor(owner))
                materials=list(obj.data.materials);obj.data=curve.data;obj.matrix_world=Matrix.Identity(4)
                for material in materials:obj.data.materials.append(material)
                bpy.data.objects.remove(curve,do_unlink=True)
            bpy.context.view_layer.update()
            affected=set(best['translations'])|set(best['rebuilds'])
            for name in affected:
                if name in index.entries:index.remove(index.entries[name])
                if name in lookup and _auditable(lookup[name]):
                    item=cached(lookup[name])
                    if item:index.add(item)
            change=dict(node=node_id,proposal=proposal,before=best['old_score'],after=best['score'],
                        provisional=True,requires_independent_rebuild=True)
            adjustments.append(change)
            assert protected_anatomy(plant)==invariant
            print('AUTO_LOCAL_NODE',node_id,best['old_score'],best['score'],flush=True)
            if checkpoint:checkpoint(plant,change)
    finally:
        _remove_pose_objects(list(scratch.objects));bpy.data.scenes.remove(scratch)
    result=dict(version='automatic-local-nodal/3',upstream_window_span=4 if 'four_nodes' in candidate_modes else 1,candidate_modes=list(candidate_modes),adjustments=adjustments,trials=trial_count,
                elapsed_active_seconds=awake_seconds()-started,anatomy_before=invariant,anatomy_after=protected_anatomy(plant),
                physical_admission='not established; full reconstruction required')
    plant.metadata.setdefault('automatic_local_nodal_history',[]).append(result)
    return result
