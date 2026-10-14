"""Measured-mesh feedback into nodal pedicel parameters, never detached organs."""
import math


def _remove_pose_objects(objects):
    """Release trial geometry immediately; removing objects alone leaks datablocks."""
    import bpy
    for obj in objects:
        data=obj.data
        bpy.data.objects.remove(obj,do_unlink=True)
        if data is not None and data.users==0:
            if isinstance(data,bpy.types.Mesh):bpy.data.meshes.remove(data)
            elif isinstance(data,bpy.types.Curve):bpy.data.curves.remove(data)


def _rendered_node_frames(plant):
    """Replay renderer transforms for pose trials, without changing morphology."""
    from mathutils import Vector
    from .blender_geometry import _axis_direction, _bend_direction, _apply_axis_load_deflection
    frames={}
    def visit(axis,start,parent):
        direction=(Vector(axis.resolved_direction).normalized() if axis.resolved_direction
                   else _axis_direction(parent,axis.azimuth_deg,axis.branch_angle_deg))
        current=start.copy()
        for index,internode in enumerate(axis.internodes):
            direction=_bend_direction(direction,internode.bend_azimuth_deg,internode.bend_angle_deg)
            direction=_apply_axis_load_deflection(direction,axis=axis,segment_index=index,
                                                  segment_count=len(axis.internodes))
            current=current+direction*(internode.length_cm*.08)
            if index<len(axis.nodes):frames[axis.nodes[index].id]=(current.copy(),direction.copy())
        for child in axis.child_axes:
            point,direction=frames[child.parent_node_id]
            visit(child,point,direction)
    for axis in plant.axes:visit(axis,Vector((0,0,0)),Vector((.05,-.03,1)).normalized())
    return frames


def repair_calyx_poses(plant, instance_id='plant'):
    """Search attachment-preserving poses against evaluated organ meshes.

    Updates morphology angles/length, then the caller rebuilds all geometry.
    Bounded length extension is explicitly an engineering heuristic, not a
    botanical measurement. Leaves remain obstacles, not visual occlusion tests.
    """
    import bpy
    from mathutils import Vector, Matrix
    from mathutils.bvhtree import BVHTree
    from .growth import _node_frames
    from .scene import PlantInstance
    from .sparse_pilot import walk_axes
    from .blender_geometry import _mesh_collision_exempt
    from .collisions import CM_TO_SCENE_UNIT

    bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get()
    frames=_rendered_node_frames(plant)
    cache={}

    def box(vertices):
        return tuple(min(v[d] for v in vertices) for d in range(3)),tuple(max(v[d] for v in vertices) for d in range(3))

    def overlaps(a,b):return all(a[0][d]<=b[1][d] and b[0][d]<=a[1][d] for d in range(3))

    for obj in bpy.context.scene.objects:
        if obj.type not in {'MESH','CURVE'} or obj.get('uchuva_semantic_class') not in {'leaf','stem','calyx'}:continue
        ev=obj.evaluated_get(deps);mesh=ev.to_mesh();mesh.calc_loop_triangles()
        vertices=[ev.matrix_world@v.co for v in mesh.vertices]
        faces=[tuple(t.vertices) for t in mesh.loop_triangles];ev.to_mesh_clear()
        if not faces:continue
        cache[obj.name]={'obj':obj,'vertices':vertices,'faces':faces,'box':box(vertices),
                         'bvh':BVHTree.FromPolygons(vertices,faces,all_triangles=True)}

    def direction(azimuth,angle):
        a,b=math.radians(azimuth),math.radians(angle)
        return Vector((math.cos(a)*math.cos(b),math.sin(a)*math.cos(b),-math.sin(b)))

    changes=[];remaining=[]
    for axis in walk_axes(plant.axes):
        for node in axis.nodes:
            unit=node.reproductive_unit
            if not unit or not unit.calyx:continue
            identifier=instance_id+':'+unit.id
            targets=[c for c in cache.values() if c['obj'].get('uchuva_reproductive_instance_id')==identifier
                     and c['obj'].get('uchuva_semantic_class')=='calyx']
            if not targets:continue
            target=targets[0];origin=Vector(frames[node.id][0]);pedicel=unit.pedicel
            original=(pedicel.azimuth_deg,pedicel.angle_deg,pedicel.length_cm)
            original_direction=direction(original[0],min(72,max(5,original[1])))
            obstacles=[c for c in cache.values() if c is not target
                and c['obj'].get('uchuva_reproductive_instance_id')!=identifier
                and not _mesh_collision_exempt(target['obj'],c['obj'])]

            def candidate(pose):
                az,angle,length=pose;new_direction=direction(az,angle)
                # Match the renderer's absolute track orientation, including roll.
                old=(-original_direction).to_track_quat('Z','Y').to_matrix().to_4x4()
                new=(-new_direction).to_track_quat('Z','Y').to_matrix().to_4x4()
                rotation=new@old.inverted()
                transform=Matrix.Translation(origin+new_direction*((length-original[2])*CM_TO_SCENE_UNIT))@rotation@Matrix.Translation(-origin)
                vertices=[transform@v for v in target['vertices']];bounds=box(vertices)
                nearby=[c for c in obstacles if overlaps(bounds,c['box'])]
                tree=BVHTree.FromPolygons(vertices,target['faces'],all_triangles=True)
                hits=[c for c in nearby if tree.overlap(c['bvh'])]
                return len(hits),vertices,bounds,tree,[c['obj'].name for c in hits]

            best_pose=original;best=candidate(original)
            if best[0]:
                azimuths=[(original[0]+offset)%360 for offset in (0,30,-30,60,-60,90,-90,120,-120,150,-150,180)]
                for factor in (1,1.25,1.5):
                    if not best[0]:break
                    for angle in (original[1],20,35,50,65,72):
                        if not best[0]:break
                        for az in azimuths:
                            pose=(az,min(72,max(5,angle)),original[2]*factor)
                            value=candidate(pose)
                            if value[0]<best[0]:best_pose,best=pose,value
                            if not best[0]:break
            if best_pose!=original:
                pedicel.azimuth_deg,pedicel.angle_deg,pedicel.length_cm=best_pose
                pedicel.provenance['mesh_feedback_pose']='engineering_heuristic_bounded_length_1_5x'
                changes.append({'unit':unit.id,'before':original,'after':best_pose,'remaining_mesh_pairs':best[0]})
                target.update(vertices=best[1],box=best[2],bvh=best[3])
            if best[0]:remaining.append({'unit':unit.id,'obstacles':best[4]})
    return {'method':'mesh_feedback_into_morphology_pedicel','adjustments':changes,
            'remaining_target_conflicts':remaining,'mesh_rebuild_and_audit_required':True}


def repair_leaf_poses(plant, materials, instance_id='plant', checkpoint=None):
    return _repair_local_poses(plant,materials,instance_id,'leaf',checkpoint)


def repair_reproductive_poses(plant,materials,instance_id='plant',checkpoint=None):
    return _repair_local_poses(plant,materials,instance_id,'reproductive',checkpoint)


def _repair_local_poses(plant, materials, instance_id, kind, checkpoint=None):
    """Rebuild local organ groups for exact trials; preserve all organs and IDs."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from .growth import _node_frames
    from .scene import PlantInstance
    from .sparse_pilot import walk_axes
    from .blender_geometry import (_create_leaf_at_node, _create_reproductive_unit_at_node,
                                   _new_collision_context, _mesh_collision_exempt,
                                   _mesh_pair_required_clearance)
    frames=_rendered_node_frames(plant)
    cache={}

    def cached(obj):
        deps=bpy.context.evaluated_depsgraph_get();ev=obj.evaluated_get(deps);mesh=ev.to_mesh();mesh.calc_loop_triangles()
        # Match the full audit's polygon tessellation, including non-planar quads.
        # Loop-triangle tessellation can disagree at a leaf/petiole boundary.
        vertices=[ev.matrix_world@v.co for v in mesh.vertices];faces=[tuple(p.vertices) for p in mesh.polygons]
        ev.to_mesh_clear()
        if not faces:return None
        return {'obj':obj,'vertices':vertices,'box':([min(v[d] for v in vertices) for d in range(3)],
                    [max(v[d] for v in vertices) for d in range(3)]),
                'bvh':BVHTree.FromPolygons(vertices,faces,all_triangles=False,epsilon=.0005)}

    bpy.context.view_layer.update()
    for obj in bpy.context.scene.objects:
        if obj.type in {'MESH','CURVE'} and obj.get('uchuva_semantic_class') in {'leaf','stem','calyx'}:
            value=cached(obj)
            if value:cache[obj.name]=value

    def score(group,obstacles):
        total=0
        for item in group:
            for other in obstacles:
                left,right=item['obj'],other['obj']
                a,b=item['box'],other['box']
                if not all(a[0][d]<=b[1][d]+.024 and b[0][d]<=a[1][d]+.024 for d in range(3)):continue
                if left.get('uchuva_semantic_class')==right.get('uchuva_semantic_class')=='leaf':continue
                if _mesh_collision_exempt(left,right):continue
                if item['bvh'].overlap(other['bvh']):
                    total+=100000;continue
                clearance=_mesh_pair_required_clearance(left,right)
                if clearance:
                    too_close=False
                    for vertices,tree in ((item['vertices'],other['bvh']),
                                          (other['vertices'],item['bvh'])):
                        for vertex in vertices:
                            nearest=tree.find_nearest(vertex,clearance)
                            if nearest is not None and nearest[3] is not None and nearest[3]<clearance:
                                too_close=True;break
                        if too_close:break
                    total+=int(too_close)
        return total

    def remove(objects):
        _remove_pose_objects(objects)

    changes=[];remaining=[];fixed_leaf_ids=set()
    leaf_ids={n.leaf.id for ax in walk_axes(plant.axes) for n in ax.nodes if n.leaf}
    moving_leaf_ids=leaf_ids | {x+'_petiole' for x in leaf_ids} | {x+'_midrib' for x in leaf_ids}
    for axis in walk_axes(plant.axes):
        for node in axis.nodes:
            leaf=node.leaf if kind=='leaf' else node.reproductive_unit
            if not leaf:continue
            own=([value for value in cache.values() if str(value['obj'].get('uchuva_organ_id','')) in
                 {leaf.id,leaf.id+'_petiole',leaf.id+'_midrib'}] if kind=='leaf' else
                 [value for value in cache.values() if value['obj'].get('uchuva_reproductive_instance_id')==instance_id+':'+leaf.id])
            obstacles=[v for v in cache.values() if v not in own]
            if kind=='reproductive':
                # Leaves are repositioned against the repaired reproductive units
                # in the next pass. Avoid spending the whole search trying to
                # clear a blade that will move anyway. The final rebuilt mesh
                # audit still includes every leaf, petiole and calyx.
                obstacles=[v for v in obstacles if str(v['obj'].get('uchuva_organ_id','')) not in moving_leaf_ids]
            else:
                # Preserve already resolved leaves. Later leaves will clear these
                # poses in turn; do not optimize against their obsolete poses.
                fixed_leaf_ids.update((leaf.id,leaf.id+'_petiole',leaf.id+'_midrib'))
                pending_leaf_ids=moving_leaf_ids-fixed_leaf_ids
                obstacles=[v for v in obstacles if str(v['obj'].get('uchuva_organ_id','')) not in pending_leaf_ids]
            initial=score(own,obstacles)
            if not initial:continue
            before=((leaf.azimuth_deg,leaf.insertion_angle_deg,leaf.curl,leaf.twist_deg) if kind=='leaf' else
                    (leaf.pedicel.azimuth_deg,leaf.pedicel.angle_deg,leaf.pedicel.length_cm))
            best_pose=before;best=initial

            def build(pose):
                if kind=='leaf':
                    leaf.azimuth_deg,leaf.insertion_angle_deg,leaf.curl,leaf.twist_deg=pose
                    objects=_create_leaf_at_node(Vector(frames[node.id][0]),Vector(frames[node.id][1]),leaf,
                        materials,_new_collision_context(),{'plant_id':instance_id,'plant_role':'target'},
                        .08,'petiole_green',node.id,axis.order)
                else:
                    leaf.pedicel.azimuth_deg,leaf.pedicel.angle_deg,leaf.pedicel.length_cm=pose
                    objects=_create_reproductive_unit_at_node(Vector(frames[node.id][0]),leaf,
                        materials,_new_collision_context(),{'plant_id':instance_id,'plant_role':'target'},
                        .08,'petiole_green',node.id,axis.order)
                bpy.context.view_layer.update()
                group=[cached(o) for o in objects if o.get('uchuva_semantic_class') in {'leaf','stem','calyx'}]
                return objects,[g for g in group if g]

            for factor in ((1,) if kind=='leaf' else (1,1.25,1.5)):
                if not best:break
                for delta in (0,15,-15,30,-30,60,-60,90,-90,120,-120,150,-150,180):
                    if not best:break
                    for angle in ((before[1],75,95,115,135,155,55,35,15,175) if kind=='leaf' else (before[1],5,20,35,50,65,72)):
                        pose=((before[0]+delta)%360,angle,*before[2:]) if kind=='leaf' else ((before[0]+delta)%360,angle,before[2]*factor)
                        objects,group=build(pose);value=score(group,obstacles);remove(objects)
                        if value<best:best_pose,best=pose,value
                        if not best:break
            if kind=='leaf':leaf.azimuth_deg,leaf.insertion_angle_deg,leaf.curl,leaf.twist_deg=best_pose
            else:leaf.pedicel.azimuth_deg,leaf.pedicel.angle_deg,leaf.pedicel.length_cm=best_pose
            if best_pose!=before:
                for item in own:cache.pop(item['obj'].name)
                remove([item['obj'] for item in own])
                objects,group=build(best_pose)
                for item in group:cache[item['obj'].name]=item
                (leaf.provenance if kind=='leaf' else leaf.pedicel.provenance)['mesh_feedback_pose']='engineering_heuristic_preserved_nodal_attachment'
                changes.append({'organ':leaf.id,'before':before,'after':best_pose,'initial_score':initial,'remaining_score':best})
                if checkpoint and len(changes)%10==0:
                    from .segmentation_cycles import write
                    write(checkpoint,plant.to_dict())
            if best:remaining.append({'organ':leaf.id,'remaining_score':best})
            print('ORGAN_POSE',kind,leaf.id,initial,best,flush=True)
    return {'method':'evaluated_local_group_pose_search','organ_kind':kind,'adjustments':changes,
            'bvh_epsilon':.0005,
            'score':'100000 * intersection_pairs + clearance_pairs',
            'remaining_controls':remaining,'requires_full_rebuild_audit':True}
