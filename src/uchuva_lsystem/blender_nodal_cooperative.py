"""Cooperative axillary endpoints for mutually blocked capachos.

All search states are provisional. Unchanged mesh tolerances, gravity axes and
organ dimensions apply. Only a complete independent rebuild can admit a scene.
"""
from copy import deepcopy


def repair_components(*, plant, index, organ_groups, owners, frames, instance_id,
                      score, bvh, reproductive_trial, build, ground, started,
                      max_seconds, checkpoint):
    import bpy
    from .nodal_repulsion import KEY,joint_angles,cooperative_joint_candidates,protected_anatomy
    from .blender_pose_repair import _remove_pose_objects
    from .blender_geometry import _mesh_collision_exempt
    from .execution_budget import awake_seconds
    before=protected_anatomy(plant);changes=[];trials=0;diagnostics=[]
    adjacency={}
    for identity in sorted(owners):
        group=[index.entries[o.name] for o in organ_groups.get(('reproductive',identity),[]) if o.name in index.entries]
        for left in group:
            if left['obj'].get('uchuva_semantic_class')!='calyx':continue
            for right in index.near(left['bounds'],{p['obj'].name for p in group}):
                if right['obj'].get('uchuva_semantic_class')!='calyx':continue
                other=str(right['obj'].get('uchuva_reproductive_instance_id','')).removeprefix(instance_id+':')
                if other in owners and bvh(left).overlap(bvh(right)):
                    adjacency.setdefault(identity,set()).add(other);adjacency.setdefault(other,set()).add(identity)
    # A clear neighbouring capacho can still block every escape of a colliding
    # pair. Coordinate the existing reproductive insertions on that axis too;
    # never remove the neighbour or pretend a two-unit failure proves that the
    # whole branch is infeasible. All outside axes remain mesh obstacles.
    for identity in list(adjacency):
        axis=owners[identity][0]
        for sibling,(other_axis,_,unit) in owners.items():
            if other_axis.id==axis.id and unit.calyx is not None and sibling!=identity:
                adjacency.setdefault(identity,set()).add(sibling)
                adjacency.setdefault(sibling,set()).add(identity)
    unseen=set(adjacency);components=[]
    while unseen:
        pending=[min(unseen)];component=set()
        while pending:
            identity=pending.pop()
            if identity in component:continue
            component.add(identity);unseen.discard(identity);pending.extend(adjacency[identity]-component)
        components.append(sorted(component,key=lambda identity:(frames[owners[identity][1].id][0].z,identity)))
    for identities in components:
        if awake_seconds()-started>=max_seconds:break
        groups=[[index.entries[o.name] for o in organ_groups.get(('reproductive',identity),[]) if o.name in index.entries] for identity in identities]
        objects=[organ_groups['reproductive',identity] for identity in identities]
        excluded={p['obj'].name for group in groups for p in group}
        original=[joint_angles(owners[identity][2].pedicel.provenance[KEY]['direction']) for identity in identities]
        pools=[]
        for position,identity in enumerate(identities):
            axis,node,organ=owners[identity]
            candidates=cooperative_joint_candidates(original[position],organ.pedicel.provenance[KEY]['input_direction'],lower_first=position==0,
                excursion_limit_deg=organ.pedicel.provenance[KEY].get('excursion_limit_deg',75))
            pool=[]
            for pose in candidates:
                if awake_seconds()-started>=max_seconds:break
                trial=reproductive_trial(organ,node,groups[position],pose);trials+=1
                if score(trial,excluded,ignore_leaf_obstacles=True)[0] or ground and ground.score(trial)!=(0,0,0):continue
                leaf_cost=score(trial,excluded)[0]
                pool.append((pose,trial,leaf_cost))
            # Coordinate descent already exhausted lower-first moves. At this
            # cooperative stage prefer a solution requiring fewer leaf repairs.
            pool.sort(key=lambda item:item[2]);pools.append(pool)
        record=dict(identities=identities,pool_sizes=[len(p) for p in pools],status='unresolved')
        diagnostics.append(record)
        compatibility={}
        def compatible(a,i,b,j):
            key=(a,i,b,j) if a<b else (b,j,a,i)
            if key not in compatibility:
                conflict=False
                for left in pools[a][i][1]:
                    for right in pools[b][j][1]:
                        if _mesh_collision_exempt(left['obj'],right['obj']):continue
                        x,y=left['bounds'],right['bounds']
                        if any(x[1][d]+.0005<y[0][d] or y[1][d]+.0005<x[0][d] for d in range(3)):continue
                        if bvh(left).overlap(bvh(right)):conflict=True;break
                    if conflict:break
                compatibility[key]=not conflict
            return compatibility[key]
        from .nodal_constraint_search import solve_ordered_domains
        solution=solve_ordered_domains([range(len(pool)) for pool in pools],compatible,
            expired=lambda:awake_seconds()-started>=max_seconds)
        selected=solution.selected
        record['constraint_search_status']=solution.status
        record['forward_compatibility_calls']=solution.compatibility_calls
        record['compatibility_tests']=len(compatibility)
        if selected is None:
            if solution.status=='time_budget_exhausted':record['status']='time_budget_exhausted'
            print('NODAL_COMPONENT_UNRESOLVED',record,flush=True);continue
        new_objects=[];new_groups=[]
        try:
            for i,identity in enumerate(identities):
                axis,node,organ=owners[identity];pose=pools[i][selected[i]][0]
                visibility={str(o.get('uchuva_organ_id','')):(o.hide_render,o.hide_viewport,o.hide_get()) for o in objects[i]}
                replacement,group=build(organ,node,axis,'reproductive',pose,str(objects[i][0].get('uchuva_plant_role','foreground')),visibility)
                new_objects.append(replacement);new_groups.append(group)
                if sorted(str(o.get('uchuva_organ_id')) for o in replacement)!=sorted(str(o.get('uchuva_organ_id')) for o in objects[i]):
                    raise RuntimeError('Cooperative endpoint reconstruction changed organ identities')
            flat=[p for group in new_groups for p in group]
            if score(flat,excluded,ignore_leaf_obstacles=True)[0]:raise RuntimeError('Rebuilt component intersects rigid obstacles')
            for a in range(len(identities)):
                for b in range(a+1,len(identities)):
                    for left in new_groups[a]:
                        for right in new_groups[b]:
                            if not _mesh_collision_exempt(left['obj'],right['obj']) and bvh(left).overlap(bvh(right)):
                                raise RuntimeError('Rebuilt component differs from compatibility trial')
        except Exception:
            for group in new_objects:_remove_pose_objects(group)
            from .nodal_repulsion import joint_direction
            for identity,pose in zip(identities,original):owners[identity][2].pedicel.provenance[KEY]['direction']=list(joint_direction(*pose))
            raise
        for i,identity in enumerate(identities):
            for old in groups[i]:index.remove(old)
            collections=list(objects[i][0].users_collection)
            for obj in new_objects[i]:
                for collection in collections:
                    if obj.name not in collection.objects:collection.objects.link(obj)
                for collection in list(obj.users_collection):
                    if collection not in collections:collection.objects.unlink(obj)
            _remove_pose_objects(objects[i]);organ_groups['reproductive',identity]=new_objects[i]
            for item in new_groups[i]:index.add(item)
            pose,trial,leaf_cost=pools[i][selected[i]]
            adjustment=dict(kind='paired_reproductive' if len(identities)==2 else 'cooperative_reproductive',organ_id=identity,
                component=identities,before_deg=list(original[i]),after_deg=list(pose),temporary_leaf_contacts=leaf_cost,
                requires_followup_leaf_pass=leaf_cost>0,status='engineering_heuristic',dimensions_unchanged=True,
                physical_admission='not established; full independent reconstruction required')
            owners[identity][2].pedicel.provenance[KEY].setdefault('cooperative_mesh_feedback',[]).append(deepcopy(adjustment))
            changes.append(adjustment)
        assert protected_anatomy(plant)==before
        record['status']='compatible_rigid_component_requires_leaf_pass_and_full_audit'
        print('NODAL_COMPONENT',record,flush=True)
        if callable(checkpoint):checkpoint(plant,changes[-1])
    return changes,trials,diagnostics
