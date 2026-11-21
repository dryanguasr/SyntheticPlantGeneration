"""Opt-in, bounded axis-pose search after evaluated stem intersection evidence.

Only serialized nodal azimuth and branch angle may change. Every trial replays
the entire morphology through the shared proxy interpreter: a cached rigid
subtree rotation would be wrong for the local-frame basis used by this model.
Proxy improvement is never an evaluated-mesh admission certificate.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
import math
from typing import Callable

from .collisions import CollisionProxy, build_scene_proxies, _candidate_pairs, _proxy_clearance
from .execution_budget import awake_seconds
from .grammar import record_reproductive_counts
from .provenance import parameter_snapshot_sha256
from .scene import CultivationScene, PlantInstance


VERSION = "bounded-axis-pose/2"
RECORD = "axis_pose_repair_v1"


def _axes(items):
    for axis in items:
        yield axis
        yield from _axes(axis.child_axes)


def axis_pose_invariant_manifest(plant):
    """Hash everything in the tree except the two permitted axis-pose fields."""
    axes = deepcopy(plant.to_dict()["axes"])

    def strip(items):
        for axis in items:
            axis.pop("azimuth_deg")
            axis.pop("branch_angle_deg")
            axis["provenance"].pop(RECORD, None)
            strip(axis["child_axes"])
    strip(axes)
    counts = Counter()
    for axis in _axes(plant.axes):
        counts["axes"] += 1
        counts["nodes"] += len(axis.nodes)
        for node in axis.nodes:
            counts["leaves"] += bool(node.leaf)
            unit = node.reproductive_unit
            if unit:
                counts["reproductive_units"] += 1
                counts["flowers"] += unit.stage == "flower"
                counts["fruits"] += unit.fruit is not None
                counts["calyces"] += unit.calyx is not None
    protected = {"axes": axes, "effective_parameters_sha256": plant.metadata.get("effective_parameters_sha256")}
    return {"sha256": parameter_snapshot_sha256(protected), "counts": dict(counts)}


def local_pose_distance_deg(left, right):
    """Angular separation on one local cone, independent of camera and parent."""
    az0, an0 = (math.radians(v) for v in left)
    az1, an1 = (math.radians(v) for v in right)
    dot = math.cos(an0)*math.cos(an1) + math.sin(an0)*math.sin(an1)*math.cos(az0-az1)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def axis_angular_candidates(current, original, bounds, max_correction_deg, *, limit=32, step_deg=3.):
    """Nearby deterministic candidates; cumulative angle is bounded to original."""
    values = (*current, *original, *bounds, max_correction_deg)
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError("Finite axis pose and range required")
    if not (0 <= bounds[0] <= bounds[1] <= 180 and 0 < max_correction_deg <= 180 and limit > 0):
        raise ValueError("Invalid bounded axis-pose search")
    if not math.isfinite(step_deg) or not .25 <= step_deg <= 3:
        raise ValueError("Axis search step must be between 0.25 and three degrees")
    offsets = [0.]+[sign*i*step_deg for i in range(1,int(12/step_deg)+1) for sign in (1,-1)]
    candidates = set()
    for daz in offsets:
        for dan in offsets:
            if daz == dan == 0:
                continue
            pose = (round((current[0]+daz)%360, 6), round(current[1]+dan, 6))
            if not bounds[0] <= pose[1] <= bounds[1]:
                continue
            az_delta = abs((pose[0]-original[0]+180)%360-180)
            if (az_delta <= max_correction_deg+1e-9
                    and local_pose_distance_deg(original, pose) <= max_correction_deg+1e-8):
                candidates.add(pose)
    return sorted(candidates, key=lambda p:(round(local_pose_distance_deg(current,p),8),
                                           round(local_pose_distance_deg(original,p),8),p))[:limit]


def confirmed_axis_relations(intersection_pairs, object_inventory, *, plant_id, clearance=False):
    """Accept only axis_segment pairs from evaluated collision rows and metadata."""
    relations = set()
    rows = []
    self_intersections = []
    for row in intersection_pairs:
        if clearance:
            required=float(row.get("required_clearance",0))
            actual=float(row.get("clearance",math.inf))
            if not math.isfinite(required) or not math.isfinite(actual):
                raise ValueError("Evaluated clearance must be finite")
            if required <= 0 or actual >= required:
                continue
        else:
            classification = row.get("strict_classification", row.get("classification", "physical_collision"))
            if classification != "physical_collision":
                continue
        names = row.get("object_a"), row.get("object_b")
        if not all(name in object_inventory for name in names):
            raise ValueError("Evaluated pair references an object absent from the supplied inventory")
        props = [object_inventory[name].get("properties", {}) for name in names]
        if not all(p.get("uchuva_organ_kind") in {"axis_segment","axis_apex"} for p in props):
            continue
        if not all(p.get("uchuva_plant_id") == plant_id for p in props):
            continue
        ids = tuple(sorted(p.get("uchuva_axis_id", "") for p in props))
        if not all(ids):
            raise ValueError("Axis segment is missing its morphological axis identity")
        detail = {"objects": list(names), "axis_ids": [p["uchuva_axis_id"] for p in props],
                  "kinds":[p["uchuva_organ_kind"] for p in props],
                  "internode_indices": [p.get("uchuva_internode_index") for p in props],
                  "evidence_kind":"evaluated_clearance_violation" if clearance else "evaluated_mesh_intersection"}
        if clearance:
            detail.update(clearance=actual,required_clearance=required)
        if ids[0] == ids[1]:
            self_intersections.append(detail)
        else:
            relations.add(ids)
            rows.append(detail)
    return sorted(relations), rows, self_intersections


def _axis_attachment_exempt(a,b):
    """Exact nodal neighbourhood used by evaluated mesh axis attachments."""
    if a.axis_id==b.axis_id:
        return abs(a.internode_index-b.internode_index)<=1
    for child,parent in ((a,b),(b,a)):
        if child.internode_index!=0 or not child.axis_parent_node_id:
            continue
        try:
            axis_id,index=child.axis_parent_node_id.rsplit("_node_",1)
            index=int(index)
        except (ValueError,AttributeError):
            continue
        if parent.axis_id==axis_id and parent.internode_index in {index,index+1}:
            return True
    return False


def confirmed_organ_axis_constraints(plant, pairs, inventory, plant_id):
    """Only measured organ/axis conflicts may trigger this optional search.

    A pedicel rooted inside a neighbouring branch cannot be repaired merely by
    swinging the pedicel. Keep its axil and all dimensions; move a bounded axis
    pose instead, then require full evaluated-mesh reconstruction.
    """
    owners={f"{plant_id}:{n.reproductive_unit.id}":axis.id for axis in _axes(plant.axes)
            for n in axis.nodes if n.reproductive_unit}
    result=[]
    for row in pairs:
        if 'clearance' in row:
            actual=float(row['clearance']);required=float(row.get('required_clearance',0))
            if not math.isfinite(actual) or not math.isfinite(required):
                raise ValueError('Measured separation must be finite')
            if required<=0 or actual>=required:
                continue
        elif row.get('strict_classification',row.get('classification','physical_collision'))!='physical_collision':
            continue
        names=[row.get('object_a'),row.get('object_b')]
        if not all(name in inventory for name in names):
            raise ValueError('Measured organ/axis pair missing from inventory')
        props=[inventory[name].get('properties',{}) for name in names]
        if all(p.get('uchuva_semantic_class')=='calyx' and p.get('uchuva_plant_id')==plant_id for p in props):
            units=[p.get('uchuva_reproductive_instance_id') for p in props]
            if not all(u in owners for u in units):
                raise ValueError('Measured calyx pair lacks a morphological owner')
            result.append(dict(unit=units[0],other_unit=units[1],kind='calyx',owner_axis=owners[units[0]],
                axis=owners[units[1]],required=float(row.get('required_clearance',.022)),objects=names))
            continue
        for source,target in (props,props[::-1]):
            kind='calyx' if source.get('uchuva_semantic_class')=='calyx' else source.get('uchuva_organ_kind')
            if kind not in {'pedicel','calyx'} or target.get('uchuva_organ_kind')!='axis_segment':
                continue
            if source.get('uchuva_plant_id')!=plant_id or target.get('uchuva_plant_id')!=plant_id:
                continue
            unit=source.get('uchuva_reproductive_instance_id')
            axis=target.get('uchuva_axis_id')
            if unit not in owners or not axis:
                raise ValueError('Measured pair lacks a morphological owner')
            if owners[unit]==axis:
                continue
            required=float(row.get('required_clearance',.024 if kind=='pedicel' else .022))
            if not math.isfinite(required) or required<=0:
                raise ValueError('Invalid measured clearance requirement')
            result.append(dict(unit=unit,kind=kind,owner_axis=owners[unit],axis=axis,
                internode_index=target['uchuva_internode_index'],required=required,objects=names))
    return result


def _with_apex_proxies(proxies, plant, instance):
    """Add each rendered apex marker without changing morphology or the tree."""
    ends={}
    for p in proxies:
        if p.kind=="stem" and p.axis_id:
            ends[p.axis_id]=p
    result=list(proxies)
    for axis in _axes(plant.axes):
        last=ends.get(axis.id)
        if last is None:
            continue
        point=last.end
        # Same marker radius as _build_axis_geometry, then instance scaling.
        radius=max(.018*(1-.18*axis.order),.008)*instance.scale
        result.append(CollisionProxy(proxy_id=f"{instance.plant_id}:{axis.id}:apex",
            plant_id=instance.plant_id,kind="stem",shape="capsule",center=point,
            axes=last.axes,half_extents=(0.,0.,0.),start=point,end=point,radius=radius,
            group_id=f"{instance.plant_id}:{axis.id}:apex",axis_id=axis.id,
            axis_parent_node_id=axis.parent_node_id,internode_index=len(axis.internodes)))
    return result


def _axis_conflicts(proxies, required_clearance=0.):
    """Aggregate conservative capsules per internode pair, preserving all axes."""
    stems = [p for p in proxies if p.kind == "stem" and p.axis_id]
    conflicts,clearances = {},{}
    indexed={p.proxy_id:p for p in stems}
    padded=[replace(p,radius=p.radius+required_clearance*.5) for p in stems]
    for padded_a,padded_b in _candidate_pairs(padded):
        a,b=indexed[padded_a.proxy_id],indexed[padded_b.proxy_id]
        if a.group_id == b.group_id or _axis_attachment_exempt(a,b):
            continue
        gap = _proxy_clearance(a,b)
        if gap >= required_clearance:
            continue
        left,right = sorted(((a.axis_id,a.internode_index),(b.axis_id,b.internode_index)))
        key = (left,right)
        if gap < 0:
            conflicts[key] = max(conflicts.get(key,0.),-gap)
        elif required_clearance>0:
            clearances[key] = max(clearances.get(key,0.),required_clearance-gap)
    return conflicts,clearances


def _score(conflicts):
    return (len(conflicts), round(sum(conflicts.values()),10), round(max(conflicts.values(),default=0.),10))


def _relations(conflicts):
    return {tuple(sorted((a[0],b[0]))) for a,b in conflicts}


def _ground_violations(proxies, ground_height):
    """Sample conservative AABB bottoms; the rooted first main segment is allowed."""
    violations = {}
    for p in proxies:
        if p.kind == "stem" and p.axis_parent_node_id is None and p.internode_index == 0:
            continue
        low,high = p.aabb()
        ground = max(float(ground_height(x,y)) for x,y in
                     ((low[0],low[1]),(low[0],high[1]),(high[0],low[1]),(high[0],high[1]),(p.center[0],p.center[1])))
        if not math.isfinite(ground):
            raise ValueError("Ground callback returned a nonfinite elevation")
        depth = ground-low[2]
        if depth > 0:
            key = p.group_id or p.proxy_id
            violations[key] = max(violations.get(key,0.),depth)
    return violations


def repair_axis_poses(plant, *, instance: PlantInstance, intersection_pairs, object_inventory,
                      clearance_pairs=None,
                      include_organ_axis_constraints=False,
                      angular_step_deg=3.,
                      max_passes=2, max_trials_per_axis=32, max_seconds=120,
                      ground_height: Callable[[float,float],float] | None = None):
    """Atomically apply the bounded search; preserve the input tree on failure."""
    from .nodal_repulsion import require_legacy_pose_inputs
    require_legacy_pose_inputs([plant],'repair_axis_poses')
    original=deepcopy(plant)
    try:
        return _repair_axis_poses(plant,instance=instance,intersection_pairs=intersection_pairs,
                                  clearance_pairs=clearance_pairs,
                                  include_organ_axis_constraints=include_organ_axis_constraints,
                                  angular_step_deg=angular_step_deg,
                                  object_inventory=object_inventory,max_passes=max_passes,
                                  max_trials_per_axis=max_trials_per_axis,max_seconds=max_seconds,
                                  ground_height=ground_height)
    except BaseException:
        plant.__dict__.clear()
        plant.__dict__.update(original.__dict__)
        raise


def _repair_axis_poses(plant, *, instance: PlantInstance, intersection_pairs, object_inventory,
                      clearance_pairs=None,
                      include_organ_axis_constraints=False,
                      angular_step_deg=3.,
                      max_passes=2, max_trials_per_axis=32, max_seconds=120,
                      ground_height: Callable[[float,float],float] | None = None):
    """Search confirmed axis crossings, mutate nodal poses and return an audit.

    ``intersection_pairs`` must come from evaluated physical collision reporting;
    no purely proxy-discovered axis becomes a new pose target. The caller must
    rebuild all geometry from this serialized tree before any organ-pose search.
    ``ground_height`` uses scene/world units; without it a flat Z=0 guard is used
    and the actual terrain remains unverified. Only this one plant is modelled.
    """
    if max_passes < 1 or max_trials_per_axis < 1 or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("Positive bounded search limits required")
    params = plant.metadata.get("effective_parameters")
    if not params or parameter_snapshot_sha256(params) != plant.metadata.get("effective_parameters_sha256"):
        raise ValueError("Axis pose repair requires an intact effective parameter snapshot")
    if params.get("branching", {}).get("frame", {}).get("value") != "local_cone_v1":
        raise ValueError("Axis pose repair requires the explicit local_cone_v1 branch frame")
    maximum = float(params.get("growth", {}).get("max_final_axis_correction_deg", {}).get("value",0))
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("An effective positive maximum axis correction is required")
    known, evidence, self_crossings = confirmed_axis_relations(intersection_pairs,object_inventory,plant_id=instance.plant_id)
    clearance_known,clearance_evidence,self_clearances=confirmed_axis_relations(
        clearance_pairs or [],object_inventory,plant_id=instance.plant_id,clearance=True)
    known=sorted(set(known)|set(clearance_known))
    organ_constraints=(confirmed_organ_axis_constraints(plant,list(intersection_pairs)+list(clearance_pairs or []),
        object_inventory,instance.plant_id) if include_organ_axis_constraints else [])
    known=sorted(set(known)|{tuple(sorted((r['owner_axis'],r['axis']))) for r in organ_constraints})
    required_clearance=max((row["required_clearance"] for row in clearance_evidence),default=0.)
    if organ_constraints:
        required_clearance=max(required_clearance,.024)
    lookup = {a.id:a for a in _axes(plant.axes)}
    if any(axis_id not in lookup for pair in known for axis_id in pair):
        raise ValueError("Evaluated intersection refers to a different morphology tree")
    initial_tree = parameter_snapshot_sha256(plant.to_dict())
    invariant = axis_pose_invariant_manifest(plant)
    scene = CultivationScene("axis_pose_repair", "single_plant_study", plant.seed,plant_instances=[instance])
    started = awake_seconds()
    ground = ground_height or (lambda x,y:0.)

    def replay():
        proxies = build_scene_proxies(scene,{instance.plant_id:plant})
        proxies = _with_apex_proxies(proxies,plant,instance)
        conflicts,clearances=_axis_conflicts(proxies,required_clearance)
        for constraint in organ_constraints:
            organs=[p for p in proxies if p.group_id==constraint['unit'] and p.kind==constraint['kind']]
            stems=([p for p in proxies if p.group_id==constraint['other_unit'] and p.kind=='calyx']
                   if constraint.get('other_unit') else [p for p in proxies if p.kind=='stem' and p.axis_id==constraint['axis']
                   and p.internode_index==constraint['internode_index']])
            if not organs or not stems:
                raise ValueError('Measured contact has no matching morphology proxy')
            gap=min(_proxy_clearance(a,b) for a in organs for b in stems)
            key=((constraint['owner_axis'],'organ:'+constraint['unit']),
                 (constraint['axis'],'organ:'+constraint['other_unit'] if constraint.get('other_unit')
                  else 'segment:'+str(constraint['internode_index'])))
            if gap<0:
                conflicts[key]=-gap
            elif gap<constraint['required']:
                clearances[key]=constraint['required']-gap
        return conflicts,clearances,_ground_violations(proxies,ground)

    def objective(physical,clearance):
        return (*_score(physical),*_score(clearance))

    conflicts,clearances,terrain = replay()
    initial_score = _score(conflicts)
    initial_clearance_score = _score(clearances)
    initial_relations = _relations(conflicts)|_relations(clearances)
    confirmed = set(known)
    unresolved_unrepresented = sorted(confirmed-initial_relations)
    eligible = {axis_id for pair in known for axis_id in pair if lookup[axis_id].order > 0}
    # Higher-order/smaller axes first; a parent rotation cannot fix its internal
    # conflict by a cached rigid rotation, and would disturb many more organs.
    ordered = sorted(eligible,key=lambda k:(-lookup[k].order,len(list(_axes([lookup[k]]))),k))
    changes=[]
    trials=0
    exhausted=False
    for pass_index in range(max_passes):
        pass_changed=False
        for axis_id in ordered:
            if awake_seconds()-started >= max_seconds:
                exhausted=True
                break
            if not any(axis_id in pair for pair in confirmed & (_relations(conflicts)|_relations(clearances))):
                continue
            axis=lookup[axis_id]
            if not axis.provenance.get("branch_frame_v140") or axis.resolved_direction is not None:
                continue
            range_spec=params["branching"]["branch_angle_deg_by_order"][str(axis.order)]
            bounds=(float(range_spec["min"]),float(range_spec["max"]))
            current=(axis.azimuth_deg,axis.branch_angle_deg)
            existing=axis.provenance.get(RECORD,{})
            original=tuple(existing.get("generated_pose",current))
            best=None
            for pose in axis_angular_candidates(current,original,bounds,maximum,limit=max_trials_per_axis,step_deg=angular_step_deg):
                if awake_seconds()-started >= max_seconds:
                    exhausted=True
                    break
                trials+=1
                axis.azimuth_deg,axis.branch_angle_deg=pose
                try:
                    trial_conflicts,trial_clearances,trial_terrain=replay()
                finally:
                    axis.azimuth_deg,axis.branch_angle_deg=current
                # No newly conflicting axis relation, no new/worse terrain
                # violation, and strict improvement of the full axis score.
                if not _relations(trial_conflicts) <= _relations(conflicts):
                    continue
                if not (_relations(trial_conflicts)|_relations(trial_clearances)) <= (_relations(conflicts)|_relations(clearances)):
                    continue
                if any(key not in terrain or value>terrain[key]+1e-8 for key,value in trial_terrain.items()):
                    continue
                score=objective(trial_conflicts,trial_clearances)
                if score >= objective(conflicts,clearances):
                    continue
                rank=(score,local_pose_distance_deg(original,pose),pose)
                if best is None or rank<best[0]:
                    best=(rank,pose,trial_conflicts,trial_clearances,trial_terrain)
            if best is not None:
                _,pose,next_conflicts,next_clearances,next_terrain=best
                change={"axis_id":axis_id,"pass":pass_index,"from_pose":list(current),"to_pose":list(pose),
                        "score_before":list(objective(conflicts,clearances)),"score_after":list(objective(next_conflicts,next_clearances)),
                        "cumulative_local_correction_deg":local_pose_distance_deg(original,pose)}
                axis.azimuth_deg,axis.branch_angle_deg=pose
                record=deepcopy(existing)
                record.update(version=VERSION,stage="adapted",generated_pose=list(original),effective_pose=list(pose),
                              angle_range_deg=list(bounds),max_correction_deg=maximum,frame="local_cone_v1")
                record.setdefault("changes",[]).append(change)
                axis.provenance[RECORD]=record
                changes.append(change)
                conflicts,clearances,terrain=next_conflicts,next_clearances,next_terrain
                pass_changed=True
            if exhausted:
                break
        if exhausted or not pass_changed:
            break
    protected_after=axis_pose_invariant_manifest(plant)
    if protected_after!=invariant:
        raise AssertionError("Axis pose repair changed protected morphology")
    report={"version":VERSION,"status":"proxy_improved_requires_mesh_rebuild" if changes else "no_verified_proxy_improvement",
            "source_tree_sha256":initial_tree,"effective_parameters_sha256":plant.metadata["effective_parameters_sha256"],
            "confirmed_axis_relations":[list(p) for p in known],"evaluated_pair_evidence":evidence,
            "evaluated_clearance_evidence":clearance_evidence,
            "evaluated_organ_axis_constraints":organ_constraints,
            "same_axis_self_intersections_not_repaired":self_crossings,
            "same_axis_clearances_not_repaired":self_clearances,
            "confirmed_relations_not_represented_by_proxy":[list(p) for p in unresolved_unrepresented],
            "confirmed_relations_still_conflicting_in_proxy":[list(p) for p in sorted(confirmed & _relations(conflicts))],
            "confirmed_relations_still_clearance_deficient_in_proxy":[list(p) for p in sorted(confirmed & _relations(clearances))],
            "initial_axis_proxy_score":list(initial_score),"final_axis_proxy_score":list(_score(conflicts)),
            "initial_axis_clearance_score":list(initial_clearance_score),"final_axis_clearance_score":list(_score(clearances)),
            "required_clearance_scene_units":required_clearance,
            "clearance_policy":"Exact evaluated requirement; maximum supplied requirement guards all axis pairs conservatively. No clearance-only axis is targeted without evaluated evidence.",
            "trials":trials,"changes":changes,"exhausted":exhausted,"awake_seconds":awake_seconds()-started,
            "max_correction_deg":maximum,"angular_step_deg":angular_step_deg,"protected_before":invariant,"protected_after":protected_after,
            "requires_full_mesh_rebuild":True,"physical_validity":"not_established",
            "ground_guard":"caller_height_sampled_proxy_aabb" if ground_height else "flat_z0_proxy_guard_actual_terrain_unverified",
            "other_plants_and_supports":"not_evaluated_by_this_single_plant_search"}
    if changes:
        record_reproductive_counts(plant,"adapted")
    plant.metadata.setdefault("axis_pose_repair_history",[]).append(deepcopy(report))
    return report
