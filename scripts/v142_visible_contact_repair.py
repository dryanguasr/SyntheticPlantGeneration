"""Small, explicitly targeted nodal pedicel adjustments; never global plant repair."""
import math

def repair_visible_targets(plants, entries, materials, target_names):
 import bpy
 from mathutils import Vector
 from mathutils.bvhtree import BVHTree
 from uchuva_lsystem.blender_pose_repair import _rendered_node_frames, _remove_pose_objects
 from uchuva_lsystem.blender_geometry import _create_reproductive_unit_at_node,_new_collision_context,_mesh_collision_exempt
 def axes(p):
  todo=list(p.axes)
  while todo:
   a=todo.pop();todo.extend(a.child_axes);yield a
 def record(obj):
  ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());m=ev.to_mesh();vs=[ev.matrix_world@v.co for v in m.vertices];fs=[tuple(p.vertices) for p in m.polygons];ev.to_mesh_clear()
  if not fs:return None
  return dict(obj=obj,bounds=([min(v[d] for v in vs) for d in range(3)],[max(v[d] for v in vs) for d in range(3)]),tree=BVHTree.FromPolygons(vs,fs,epsilon=0))
 def overlaps(a,b,margin=0):return all(a[0][d]<=b[1][d]+margin and b[0][d]<=a[1][d]+margin for d in range(3))
 targets=[]
 for name in target_names:
  obj=bpy.data.objects.get(name)
  if obj is None:raise ValueError('Missing selected target '+name)
  targets.append(str(obj.get('uchuva_reproductive_instance_id')))
 changes=[]
 for plant,entry in zip(plants,entries):
  frames=_rendered_node_frames(plant)
  for axis in axes(plant):
   for node in axis.nodes:
    u=node.reproductive_unit
    if not u or entry['instance_id']+':'+u.id not in targets:continue
    identifier=entry['instance_id']+':'+u.id;own=[o for o in list(bpy.context.scene.objects) if o.get('uchuva_reproductive_instance_id')==identifier]
    before=(u.pedicel.azimuth_deg,u.pedicel.angle_deg,u.pedicel.length_cm);original=[record(o) for o in own if o.get('uchuva_semantic_class') in ('calyx','stem')];original=[x for x in original if x]
    bounds=([min(x['bounds'][0][d] for x in original) for d in range(3)],[max(x['bounds'][1][d] for x in original) for d in range(3)])
    obstacles=[];margin=max(.5,2*before[2]*.08)
    for o in list(bpy.context.scene.objects):
     if o in own or o.type not in ('MESH','CURVE') or o.get('uchuva_semantic_class') not in ('calyx','stem'):continue
     pts=[o.matrix_world@Vector(v) for v in o.bound_box];bb=([min(v[d] for v in pts) for d in range(3)],[max(v[d] for v in pts) for d in range(3)])
     if overlaps(bounds,bb,margin):
      value=record(o)
      if value:obstacles.append(value)
    def collisions(group):
     result=set()
     for x in group:
      for other in obstacles:
       if overlaps(x['bounds'],other['bounds']) and not _mesh_collision_exempt(x['obj'],other['obj']) and x['tree'].overlap(other['tree']):result.add((x['obj'].get('uchuva_organ_id'),other['obj'].name))
     return result
    initial=collisions(original);best=initial;pose=before
    def build(values):
     u.pedicel.azimuth_deg,u.pedicel.angle_deg,u.pedicel.length_cm=values
     objects=_create_reproductive_unit_at_node(Vector(frames[node.id][0])+Vector(entry['position']),u,materials,_new_collision_context(),{'plant_id':entry['instance_id'],'plant_role':'foreground'},.08,'petiole_green',node.id,axis.order)
     bpy.context.view_layer.update();group=[record(o) for o in objects if o.get('uchuva_semantic_class') in ('calyx','stem')];return objects,[x for x in group if x]
    candidates=[]
    for factor in (1,1.05,1.1):
     for da in (0,4,-4,8,-8,12,-12):
      for dt in (0,4,-4,8,-8):
       if factor==1 and da==dt==0:continue
       if not 0<=before[1]+dt<=180:continue
       candidates.append((abs(da)/12+abs(dt)/8+(factor-1)*10,((before[0]+da)%360,before[1]+dt,before[2]*factor)))
    for cost,trial in sorted(candidates)[:24]:
     if not best:break
     objects,group=build(trial);found=collisions(group);_remove_pose_objects(objects)
     # No newly introduced rigid pair, even if it would reduce the overall count.
     if found<=initial and len(found)<len(best):best=found;pose=trial
    u.pedicel.azimuth_deg,u.pedicel.angle_deg,u.pedicel.length_cm=pose
    if pose!=before:
     _remove_pose_objects(own);build(pose)
    changes.append(dict(plant=entry['sample'],organ=u.id,before=before,after=pose,rigid_pairs_before=len(initial),rigid_pairs_after=len(best),new_pairs=0,changed=pose!=before))
    print('LOCAL_REPAIR',entry['sample'],u.id,len(initial),len(best),pose!=before,flush=True)
 return changes
