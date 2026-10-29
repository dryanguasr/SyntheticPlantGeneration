"""Evaluated-mesh feedback into length-preserving nodal branch directions.

This is an engineering coordinate search, not a force model. It requires an
untransformed single plant and never changes topology, dimensions or camera.
Every accepted result still needs a complete independent reconstruction audit.
"""
from __future__ import annotations
import math


def repair_nodal_branches(plant, *, instance_id='growth', passes=3, max_seconds=600, checkpoint=None,
                          defer_leaf_contacts=False):
    import bpy
    from mathutils import Vector, Matrix
    from mathutils.bvhtree import BVHTree
    from .nodal_repulsion import (KEY,axes,protected_anatomy,initialize_growth_poses,pitched,dot,unit,
                                 downstream_module,segment_directions,add,sub,mul)
    from .collisions import build_scene_proxies
    from .geometry_contracts import axis_sag_factor
    from .blender_geometry import (_create_sagging_curve_between,_mesh_collision_exempt,
                                  _mesh_intersection_classification,audit_scene_mesh_collisions)
    from .blender_pose_repair_v2 import _MeshIndex,_auditable,_bounds
    from .blender_pose_repair import _remove_pose_objects
    from .execution_budget import awake_seconds
    before=protected_anatomy(plant);started=awake_seconds();changes=[];trials=0
    scene=initialize_growth_poses(plant)
    for obj in bpy.context.scene.objects:
        if obj.get('uchuva_plant_id')==instance_id and obj.parent:
            if any(abs(obj.parent.matrix_world[i][j]-(1 if i==j else 0))>1e-6 for i in range(4) for j in range(4)):
                raise ValueError('Nodal branch feedback currently requires identity plant transform')
    scratch=bpy.data.scenes.new('nodal_branch_trials')
    def cached(obj):
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh()
        try:
            if mesh is None or not mesh.polygons:return None
            vertices=[evaluated.matrix_world@v.co for v in mesh.vertices]
            polygons=[tuple(p.vertices) for p in mesh.polygons]
            return dict(obj=obj,vertices=vertices,polygons=polygons,bounds=_bounds(vertices),bvh=None)
        finally:evaluated.to_mesh_clear()
    def tree(item):
        if item['bvh'] is None:item['bvh']=BVHTree.FromPolygons(item['vertices'],item['polygons'],epsilon=.0005)
        return item['bvh']
    try:
        for iteration in range(passes):
            if awake_seconds()-started>=max_seconds:break
            mesh_report=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
            if mesh_report['physical_collision_count']==0:break
            hot={r[k] for r in mesh_report['physical_collisions'] for k in ('object_a','object_b')}
            hot_objects=[bpy.data.objects[name] for name in hot]
            wanted=set()
            unit_nodes={instance_id+':'+n.reproductive_unit.id:n.id for a in axes(plant.axes) for n in a.nodes if n.reproductive_unit}
            leaf_nodes={n.leaf.id:n.id for a in axes(plant.axes) for n in a.nodes if n.leaf}
            for obj in hot_objects:
                node=(str(obj.get('uchuva_parent_node_id','')) or str(obj.get('uchuva_node_end_id','')) or
                      unit_nodes.get(obj.get('uchuva_reproductive_instance_id'),'') or leaf_nodes.get(obj.get('uchuva_organ_id'),''))
                if node:wanted.add(node)
            frames={};bones={};build_scene_proxies(scene,{'growth':plant},frame_output=frames,bone_output=bones)
            node_frames=frames['growth'];bone_frames=bones['growth']
            candidates=[]
            for axis in axes(plant.axes):
                for i,node in enumerate(axis.nodes):
                    if i>=len(axis.internodes):continue
                    # Preserve the basal anchor. A primary-axis joint directly
                    # involved in a contact is movable too, within the same
                    # unmeasured 35-degree search excursion as other axes.
                    # It must not be pinned
                    # merely because it belongs to the main stem.
                    if axis.order==0 and (i==0 or node.id not in wanted):continue
                    nodes,_=downstream_module(axis,i)
                    if {n.id for n in nodes}&wanted:candidates.append((axis,i,node))
            candidates.sort(key=lambda row:(node_frames[row[2].id][0][2],row[0].order,row[2].position_index,row[2].id))
            index=_MeshIndex();all_objects=list(bpy.context.scene.objects)
            for obj in all_objects:
                if _auditable(obj):
                    item=cached(obj)
                    if item:index.add(item)
            changed_before=len(changes)
            def score(updates,rigid):
                if defer_leaf_contacts:
                    updates=[p for p in updates if p['obj'].get('uchuva_semantic_class')!='leaf' and p['obj'].get('uchuva_organ_kind')!='petiole']
                updates={p['obj'].name:p for p in updates};seen=set();contacts=penetration=0
                unchanged=all(value is index.entries.get(name) for name,value in updates.items())
                temporary=None
                if not unchanged:
                    temporary=_MeshIndex()
                    for item in updates.values():temporary.add(item)
                for name,left in updates.items():
                    invariant_neighbours=rigid if name in rigid else set()
                    neighbours={p['obj'].name for p in index.near(left['bounds'],invariant_neighbours)}
                    if temporary is not None:neighbours.update(p['obj'].name for p in temporary.near(left['bounds'],invariant_neighbours))
                    for identity in neighbours:
                        if identity==name or name in rigid and identity in rigid:continue
                        key=tuple(sorted((name,identity)))
                        if key in seen:continue
                        seen.add(key);right=updates.get(identity,index.entries.get(identity))
                        if right is None:continue
                        a,b=left['bounds'],right['bounds']
                        if any(a[1][d]+.0005<b[0][d] or b[1][d]+.0005<a[0][d] for d in range(3)):continue
                        x,y=left['obj'],right['obj']
                        if defer_leaf_contacts and any(o.get('uchuva_semantic_class')=='leaf' or o.get('uchuva_organ_kind')=='petiole' for o in (x,y)):
                            continue  # Provisional only: a subsequent leaf pass and full audit are mandatory.
                        if _mesh_collision_exempt(x,y) or x.get('uchuva_semantic_class')==y.get('uchuva_semantic_class')=='leaf':continue
                        overlap=tree(left).overlap(tree(right))
                        if overlap and _mesh_intersection_classification(x,y)!='intentional_support':
                            contacts+=1
                            penetration+=math.prod(max(0.,min(a[1][d],b[1][d])-max(a[0][d],b[0][d])) for d in range(3))
                return contacts,penetration
            for phase in ('lower','raise','lateral','combined'):
                for axis,i,node in candidates:
                    if awake_seconds()-started>=max_seconds:break
                    part=axis.internodes[i];record=part.provenance[KEY];current=tuple(record['direction'])
                    descendants,distal_parts=downstream_module(axis,i);ids={n.id for n in descendants};part_ids={p.id for p in distal_parts}
                    organ_ids=set(part_ids);reproductive_ids=set()
                    for child_node in descendants:
                        if child_node.leaf:
                            organ_ids.update(child_node.leaf.id+suffix for suffix in ('','_petiole','_midrib'))
                        if child_node.reproductive_unit:
                            reproductive_ids.add(instance_id+':'+child_node.reproductive_unit.id)
                    reframe=[part]+([axis.internodes[i+1]] if i+1<len(axis.internodes) else [])
                    stems={p.id:next((o for o in all_objects if o.get('uchuva_organ_id')==p.id and o.get('uchuva_plant_id')==instance_id),None) for p in reframe}
                    if not all(stems.values()):raise ValueError('Missing nodal stem mesh')
                    moved=[o for o in all_objects if o.get('uchuva_plant_id')==instance_id and
                           (o.get('uchuva_parent_node_id') in ids or o.get('uchuva_organ_id') in organ_ids or
                            o.get('uchuva_reproductive_instance_id') in reproductive_ids or
                            o.get('uchuva_organ_kind')=='axis_apex' and o.get('uchuva_node_end_id') in ids)]
                    moved=[o for o in moved if o not in stems.values()]
                    rigid={o.name for o in moved if o.name in index.entries}
                    own=[index.entries[name] for name in rigid]+[index.entries[o.name] for o in stems.values() if o.name in index.entries]
                    initial=score(own,rigid)
                    if not initial[0]:continue
                    proposals=([(p,0.) for p in (-1.,-3.,-6.,-12.)] if phase=='lower' else
                               [(p,0.) for p in (1.,3.,6.,12.)] if phase=='raise' else
                               [(0.,y) for y in (-6.,6.,-12.,12.)] if phase=='lateral' else
                               [(p,y) for p in (-24.,-12.,12.,24.) for y in (-24.,-12.,0.,12.,24.)])
                    accepted=None
                    for degrees,yaw in proposals:
                        direction=pitched(current,degrees,yaw)
                        if phase=='lower' and direction[2]>=current[2]-1e-10:continue
                        if phase=='raise' and direction[2]<=current[2]+1e-10:continue
                        if math.degrees(math.acos(max(-1,min(1,dot(direction,record['input_direction'])))))>35:continue
                        record['direction']=list(direction)
                        state=bone_frames[part.id];new_end=add(state['start'],mul(direction,part.length_cm*.08));delta=Vector(sub(new_end,state['end']))
                        trial=[];temporary=[]
                        try:
                            for name in rigid:
                                old=index.entries[name];vertices=[v+delta for v in old['vertices']]
                                trial.append({**old,'vertices':vertices,'bounds':_bounds(vertices),'bvh':None})
                            with bpy.context.temp_override(scene=scratch,view_layer=scratch.view_layers[0],collection=scratch.collection):
                                for segment in reframe:
                                    j=axis.internodes.index(segment);old=bone_frames[segment.id]
                                    start=Vector(old['start'])+(delta if segment is not part else Vector())
                                    end=Vector(new_end) if segment is part else Vector(old['end'])+delta
                                    incoming,segment_direction=segment_directions(segment,axis.internodes[j-1] if j else None)
                                    obj=_create_sagging_curve_between('nodal_trial',start,end,max(segment.radius_cm*.08,.008),None,
                                        endpoint_tangents=(Vector(incoming),Vector(segment_direction)) if axis.provenance.get('continuous_tangent_v140') else None,
                                        sag_factor=axis_sag_factor(axis))
                                    temporary.append(obj)
                                bpy.context.view_layer.update()
                                for segment,obj in zip(reframe,temporary):
                                    value=cached(obj);value['obj']=stems[segment.id];trial.append(value)
                            if any(p['bounds'][0][2]<.010 for p in trial):continue
                            value=score(trial,rigid);trials+=1
                            if value<initial and (accepted is None or value<accepted[0]):
                                accepted=(value,direction,delta.copy(),degrees,yaw)
                        finally:
                            record['direction']=list(current)
                            _remove_pose_objects(temporary)
                    record['direction']=list(current)
                    if accepted:
                        value,direction,delta,degrees,yaw=accepted
                        record['direction']=list(direction);record['last_mesh_branch_phase']=phase
                        for obj in moved:obj.matrix_world=Matrix.Translation(delta)@obj.matrix_world
                        for segment in reframe:
                            j=axis.internodes.index(segment);old=bone_frames[segment.id]
                            start=Vector(old['start'])+(delta if segment is not part else Vector())
                            end=Vector(add(old['start'],mul(direction,segment.length_cm*.08))) if segment is part else Vector(old['end'])+delta
                            incoming,sd=segment_directions(segment,axis.internodes[j-1] if j else None)
                            replacement=_create_sagging_curve_between('nodal_commit',start,end,max(segment.radius_cm*.08,.008),None,
                                endpoint_tangents=(Vector(incoming),Vector(sd)) if axis.provenance.get('continuous_tangent_v140') else None,sag_factor=axis_sag_factor(axis))
                            target=stems[segment.id];materials=list(target.data.materials);target.data=replacement.data;target.matrix_world=Matrix.Identity(4)
                            for material in materials:target.data.materials.append(material)
                            bpy.data.objects.remove(replacement,do_unlink=True)
                        bpy.context.view_layer.update()
                        for old in own:index.remove(old)
                        for obj in moved+list(stems.values()):
                            if _auditable(obj):
                                item=cached(obj)
                                if item:index.add(item)
                        # Replaying pure frames avoids cumulative cached-coordinate drift.
                        fresh_frames={};fresh_bones={};build_scene_proxies(scene,{'growth':plant},frame_output=fresh_frames,bone_output=fresh_bones)
                        node_frames=fresh_frames['growth'];bone_frames=fresh_bones['growth']
                        change=dict(iteration=iteration,node=node.id,part=part.id,phase=phase,degrees=degrees,yaw=yaw,
                            delta_z=float(delta.z),before=list(initial),after=list(value),descendant_nodes=len(descendants))
                        changes.append(change)
                        assert protected_anatomy(plant)==before
                        print('NODAL_BRANCH',change,flush=True)
                        if checkpoint:checkpoint(plant,change)
                if awake_seconds()-started>=max_seconds:break
            if len(changes)==changed_before:break
    finally:
        _remove_pose_objects(list(scratch.objects));bpy.data.scenes.remove(scratch)
    report=dict(version='evaluated-mesh-nodal-branch/1',status='requires_independent_rebuild',adjustments=changes,
        anatomy_before=before,anatomy_after=protected_anatomy(plant),elapsed_active_seconds=awake_seconds()-started,trials=trials,
        main_axis_excursion_limit_deg=35,lateral_excursion_limit_deg=35,basal_anchor='fixed',
        tiebreak='evaluated AABB overlap volume, used only among equal counts of actual mesh intersections',
        leaf_contacts_deferred=defer_leaf_contacts,physical_admission='not established; full independent audit required')
    plant.metadata.setdefault('mesh_nodal_branch_history',[]).append(report)
    return report
