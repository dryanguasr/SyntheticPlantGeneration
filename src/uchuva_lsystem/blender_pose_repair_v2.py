"""Bounded mesh feedback into serialized nodal poses, with anatomy protected.

This opt-in path never extends pedicels or changes organs to satisfy a view.
It is a local search, not a guarantee that a crowded architecture is feasible.
The caller must rebuild the complete tree and run the strict scene audit.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math

ADAPTED_ANGLE_LIMITS = {"leaf": (15.,165.), "reproductive": (5.,72.)}


def _axes(items):
    for axis in items:
        yield axis
        yield from _axes(axis.child_axes)


def pose_invariant_manifest(plant):
    """Protect topology, all dimensions, shapes, phenology and parameter hash."""
    axes = deepcopy(plant.to_dict()["axes"])

    def strip(items):
        for axis in items:
            for node in axis["nodes"]:
                leaf = node.get("leaf")
                if leaf:
                    for key in ("azimuth_deg", "insertion_angle_deg", "orientation_adjustment_deg"):
                        leaf.pop(key, None)
                    leaf.get("provenance", {}).pop("mesh_feedback_pose_v2", None)
                    leaf.get("provenance", {}).pop("mesh_feedback_pose", None)
                    leaf.get("provenance", {}).pop("mesh_feedback_pose_history_v2", None)
                    leaf.get("provenance", {}).pop("mesh_feedback_pose_history_prefix_v2", None)
                unit = node.get("reproductive_unit")
                if unit:
                    for key in ("azimuth_deg", "angle_deg", "orientation_adjustment_deg"):
                        unit["pedicel"].pop(key, None)
                    unit["pedicel"].get("provenance", {}).pop("mesh_feedback_pose_v2", None)
                    unit["pedicel"].get("provenance", {}).pop("mesh_feedback_pose", None)
                    unit["pedicel"].get("provenance", {}).pop("mesh_feedback_pose_history_v2", None)
                    unit["pedicel"].get("provenance", {}).pop("mesh_feedback_pose_history_prefix_v2", None)
            strip(axis["child_axes"])
    strip(axes)
    protected = {"axes": axes, "effective_parameters_sha256": plant.metadata.get("effective_parameters_sha256")}
    payload = json.dumps(protected, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    counts = {"axes": 0, "nodes": 0, "leaves": 0, "reproductive_units": 0, "flowers": 0, "fruits": 0, "calyces": 0}
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
    return {"sha256": hashlib.sha256(payload.encode()).hexdigest(), "counts": counts}


def angular_candidates(azimuth, angle, *, kind, limit=56):
    """Deterministic local rotations, then wider rotations; no size coordinate."""
    if kind not in {"leaf", "reproductive"} or limit < 1:
        raise ValueError("Unknown pose kind or invalid candidate limit")
    if not all(math.isfinite(float(x)) for x in (azimuth, angle)):
        raise ValueError("Nonfinite pose")
    bounds = ADAPTED_ANGLE_LIMITS[kind]
    original = (float(azimuth) % 360, float(angle))
    # Round-robin across inclinations avoids exhausting the budget at one azimuth.
    seen = {original}
    result = []
    for delta in (0, 15, -15, 30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180):
        for shift in (0, 15, -15, 30, -30, 60, -60, 90, -90):
            value = ((original[0] + delta) % 360, min(bounds[1], max(bounds[0], original[1] + shift)))
            if value not in seen:
                result.append(value)
                seen.add(value)
                if len(result) == limit:
                    return result
    return result


def fine_angular_candidates(azimuth, angle, *, kind, step_deg=5, limit=8):
    """One deterministic eight-neighbour angular ring within existing bounds."""
    if kind not in {"leaf", "reproductive"} or not math.isfinite(step_deg) or not 0 < step_deg < 15 or limit < 0:
        raise ValueError("Fine angular step must be finite, positive and less than 15 degrees")
    if not all(math.isfinite(float(x)) for x in (azimuth,angle)):
        raise ValueError("Nonfinite pose")
    if limit == 0:
        return []
    low,high = ADAPTED_ANGLE_LIMITS[kind]
    original = (float(azimuth)%360,float(angle))
    seen, result = {original}, []
    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
        pose = ((original[0]+dx*step_deg)%360,min(high,max(low,original[1]+dy*step_deg)))
        if pose not in seen:
            seen.add(pose)
            result.append(pose)
            if len(result) == limit:
                break
    return result


def _auditable(obj):
    semantic = obj.get("uchuva_semantic_class", "")
    return (not obj.hide_render and obj.type in {"MESH", "CURVE", "SURFACE"}
            and not (semantic == "leaf" and str(obj.get("uchuva_organ_id", "")).endswith("_midrib"))
            and (semantic in {"leaf", "stem", "calyx"} or obj.get("uchuva_plant_role") == "support"))


def dense_reproductive_candidates(step_deg=5):
    """Absolute angular lattice for a residual local minimum; dimensions fixed."""
    if not math.isfinite(step_deg) or step_deg < 2 or step_deg > 15:
        raise ValueError("Dense angular step must be finite and between 2 and 15 degrees")
    low, high = ADAPTED_ANGLE_LIMITS["reproductive"]
    angles = sorted({low, high} | {min(high, low+i*step_deg) for i in range(int((high-low)/step_deg)+1)})
    return [(i*step_deg, angle) for i in range(math.ceil(360/step_deg)) for angle in angles]


def _bounds(vertices):
    return (tuple(min(v[d] for v in vertices) for d in range(3)),
            tuple(max(v[d] for v in vertices) for d in range(3)))


def _world_vertices(item):
    if item["vertices"] is None:
        item["vertices"] = [item["matrix"] @ v for v in item["local"]]
    return item["vertices"]


def _rectangular_height_field(vertices, triangles):
    """Prove complete Cartesian terrain coverage before skipping vertical rays.

    A rectangular bound alone is not sufficient: every grid cell must contain
    exactly two triangles sharing its diagonal. Holes, stacked/folded surfaces
    and general rotated terrain take the conservative ray path instead.
    """
    xs = sorted({float(v[0]) for v in vertices})
    ys = sorted({float(v[1]) for v in vertices})
    if len(xs) < 2 or len(ys) < 2 or len(vertices) != len(xs)*len(ys):
        return False
    xi, yi = ({x:i for i,x in enumerate(xs)}, {y:i for i,y in enumerate(ys)})
    points = [(xi[float(v[0])],yi[float(v[1])]) for v in vertices]
    if len(set(points)) != len(points):
        return False
    cells = {}
    for triangle in triangles:
        coords = frozenset(points[i] for i in triangle)
        if len(coords) != 3:
            return False
        xx,yy = zip(*coords)
        if max(xx)-min(xx) != 1 or max(yy)-min(yy) != 1:
            return False
        cells.setdefault((min(xx),min(yy)),[]).append(coords)
    if len(cells) != (len(xs)-1)*(len(ys)-1):
        return False
    for pair in cells.values():
        if len(pair) != 2 or len(pair[0] | pair[1]) != 4:
            return False
        shared = list(pair[0] & pair[1])
        if len(shared) != 2 or shared[0][0] == shared[1][0] or shared[0][1] == shared[1][1]:
            return False
    return True


class _GroundPenalty:
    """Cached evaluated terrain for the movable organs (no basal exemptions)."""
    def __init__(self, terrain, required_clearance_m):
        import bpy
        from mathutils.bvhtree import BVHTree
        scale = float(bpy.context.scene.unit_settings.scale_length)
        if not math.isfinite(scale) or scale <= 0 or not math.isfinite(required_clearance_m) or required_clearance_m < 0:
            raise ValueError("Ground clearance and metres per Blender unit must be valid")
        if terrain is None:
            raise ValueError("Ground-aware pose repair requires evaluated terrain")
        evaluated = terrain.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            if mesh is None or not mesh.polygons:
                raise ValueError("Ground-aware pose repair requires terrain triangles")
            mesh.calc_loop_triangles()
            points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
            triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
            self.tree = BVHTree.FromPolygons(points,triangles,all_triangles=True)
            self.bounds = _bounds(points)
            self.rectangular_coverage = _rectangular_height_field(points,triangles)
        finally:
            evaluated.to_mesh_clear()
        self.required_bu = required_clearance_m/scale
        self.metres_per_bu = scale
        self.required_m = required_clearance_m
        self.ray_top = self.bounds[1][2]+1
        self.fast_above_count = self.ray_count = 0

    def score(self, group):
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        collisions = clearances = coverage = 0
        for item in group:
            obj = item["obj"]
            if obj.hide_render or obj.get("uchuva_semantic_class") not in {"leaf","calyx","flower","stem"}:
                continue
            bounds = item["bounds"]
            inside = all(self.bounds[0][d] <= bounds[0][d] and bounds[1][d] <= self.bounds[1][d] for d in (0,1))
            if self.rectangular_coverage and inside and bounds[0][2] > self.bounds[1][2]+self.required_bu:
                self.fast_above_count += 1
                continue
            vertices = _world_vertices(item)
            missed = below = deficient = False
            for point in vertices:
                self.ray_count += 1
                hit = self.tree.ray_cast(Vector((point[0],point[1],self.ray_top)),Vector((0,0,-1)))
                if hit[0] is None:
                    missed = True
                    continue
                distance = point[2]-hit[0].z
                below = below or distance < 0
                deficient = deficient or distance < self.required_bu
            # Entirely buried organs need not intersect the terrain surface.
            tree = BVHTree.FromPolygons(vertices,item["triangles"],all_triangles=True)
            intersects = bool(tree.overlap(self.tree))
            collisions += int(below or intersects)
            clearances += int(deficient and not (below or intersects))
            coverage += int(missed)
        return collisions, clearances, coverage


def _ground_not_worse(candidate, previous):
    return all(new <= old for new,old in zip(candidate,previous))


def _cells(bounds, padding=.0245, cell_size=.45):
    low = [math.floor((v-padding)/cell_size) for v in bounds[0]]
    high = [math.floor((v+padding)/cell_size) for v in bounds[1]]
    for x in range(low[0], high[0]+1):
        for y in range(low[1], high[1]+1):
            for z in range(low[2], high[2]+1):
                yield x, y, z


class _MeshIndex:
    def __init__(self):
        self.entries = {}
        self.grid = {}

    def add(self, item):
        key = item["obj"].name
        self.entries[key] = item
        for cell in _cells(item["bounds"]):
            self.grid.setdefault(cell, set()).add(key)

    def remove(self, item):
        key = item["obj"].name
        self.entries.pop(key)
        for cell in _cells(item["bounds"]):
            self.grid[cell].discard(key)

    def near(self, bounds, excluded):
        keys = set()
        for cell in _cells(bounds):
            keys.update(self.grid.get(cell, ()))
        return [self.entries[k] for k in sorted(keys - excluded)]


def repair_size_preserving_poses(plant, materials, *, instance_id="plant", world_from_local=None,
                                max_passes=2, max_trials_per_organ=56, max_seconds=600,
                                checkpoint=None, ground_clearance_m=None, terrain_object=None,
                                fine_angular_step_deg=None, dense_reproductive_step_deg=None, clearance_tiebreak=False,
                                repair_clearance=True, organ_kinds=("reproductive","leaf"), growth_joint_policy=False):
    """Run exact trials in an isolated depsgraph and clean it even on failure."""
    import bpy
    from .blender_pose_repair import _remove_pose_objects
    if not growth_joint_policy:
        from .nodal_repulsion import require_legacy_pose_inputs
        require_legacy_pose_inputs([plant],'repair_size_preserving_poses without growth_joint_policy')
    scratch = bpy.data.scenes.new("uchuva_pose_trials_temporary")
    try:
        return _repair_size_preserving_poses(plant,materials,instance_id=instance_id,
            world_from_local=world_from_local,max_passes=max_passes,
            max_trials_per_organ=max_trials_per_organ,max_seconds=max_seconds,
            checkpoint=checkpoint,ground_clearance_m=ground_clearance_m,
            terrain_object=terrain_object,fine_angular_step_deg=fine_angular_step_deg,
            dense_reproductive_step_deg=dense_reproductive_step_deg,clearance_tiebreak=clearance_tiebreak,
            repair_clearance=repair_clearance,organ_kinds=organ_kinds,_trial_scene=scratch,
            growth_joint_policy=growth_joint_policy)
    finally:
        _remove_pose_objects(list(scratch.objects))
        bpy.data.scenes.remove(scratch)


def _repair_size_preserving_poses(plant, materials, *, instance_id="plant", world_from_local=None,
                                 max_passes=2, max_trials_per_organ=56, max_seconds=600,
                                 checkpoint=None, ground_clearance_m=None, terrain_object=None,
                                 fine_angular_step_deg=None, dense_reproductive_step_deg=None, clearance_tiebreak=False,
                                 repair_clearance=True, organ_kinds=("reproductive","leaf"), _trial_scene=None,
                                 growth_joint_policy=False):
    """Update nodal angles and their scene geometry without changing anatomy.

    Reproductive trials transform evaluated local polygons separately for each
    pedicel and calyx, matching their distinct Blender track axes. Leaf trials
    rebuild exactly: azimuth changes edge detail and direction changes sag.
    All other audited organs remain obstacles. Accepted replacements preserve
    collection membership and visibility. No broad collision exemption is added.
    ``world_from_local`` must match the instance transform used to build the scene.
    """
    import bpy
    from mathutils import Matrix, Vector
    from mathutils.bvhtree import BVHTree
    from .blender_pose_repair import _rendered_node_frames, _remove_pose_objects
    from .blender_geometry import (
        _create_leaf_at_node, _create_reproductive_unit_at_node, _new_collision_context,
        _mesh_collision_exempt, _mesh_pair_required_clearance, _mesh_intersection_classification,
        CM_TO_BLENDER_UNIT, CALYX_CENTER_FROM_PEDICEL_FRACTION,
    )
    from .grammar import record_reproductive_counts
    from .execution_budget import awake_seconds

    if max_passes < 1 or max_trials_per_organ < 1 or max_seconds <= 0:
        raise ValueError("Positive bounded search limits are required")
    if (not organ_kinds or len(set(organ_kinds))!=len(organ_kinds)
            or any(k not in {"reproductive","leaf"} for k in organ_kinds)):
        raise ValueError("Choose unique supported organ kinds")
    if fine_angular_step_deg is not None and (not math.isfinite(fine_angular_step_deg) or not 0 < fine_angular_step_deg < 15):
        raise ValueError("Fine angular step must be finite, positive and less than 15 degrees")
    fine_reserve = min(16,max_trials_per_organ-1) if fine_angular_step_deg is not None else 0
    coarse_limit = max_trials_per_organ-fine_reserve
    started = awake_seconds()
    transform = Matrix.Identity(4) if world_from_local is None else Matrix(world_from_local)
    frames = _rendered_node_frames(plant)
    from .nodal_repulsion import KEY, protected_anatomy, joint_angles, joint_direction, joint_candidates, cooperative_joint_candidates
    invariant_function = protected_anatomy if growth_joint_policy else pose_invariant_manifest
    invariant = invariant_function(plant)
    index = _MeshIndex()
    changes = []
    exhausted = False
    trials = 0
    phase_trials = {"coarse":0,"fine":0}
    bpy.context.view_layer.update()
    ground = (_GroundPenalty(terrain_object or bpy.data.objects.get("uchuva_terrain_agricultural"),
                             ground_clearance_m) if ground_clearance_m is not None else None)

    def relevant(obj):
        return _auditable(obj) or (ground is not None and not obj.hide_render
            and obj.get("uchuva_plant_id") == instance_id and obj.get("uchuva_semantic_class") == "flower")

    def cached(obj):
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ev.to_mesh()
        try:
            if mesh is None or not mesh.polygons:
                return None
            local = [v.co.copy() for v in mesh.vertices]
            polygons = [tuple(p.vertices) for p in mesh.polygons]
            mesh.calc_loop_triangles()
            triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
            matrix = ev.matrix_world.copy()
            vertices = [matrix @ v for v in local]
            return {"obj": obj, "local": local, "local_bounds": _bounds(local), "polygons": polygons,
                    "triangles": triangles, "matrix": matrix,
                    "vertices": vertices, "bounds": _bounds(vertices), "bvh": None}
        finally:
            ev.to_mesh_clear()

    def bvh(item):
        if item["bvh"] is None:
            item["bvh"] = BVHTree.FromPolygons(_world_vertices(item), item["polygons"], all_triangles=False, epsilon=.0005)
        return item["bvh"]

    for obj in bpy.context.scene.objects:
        if relevant(obj):
            item = cached(obj)
            if item:
                index.add(item)

    def score(group, excluded, *, ignore_leaf_obstacles=False):
        intersections = clearance_pairs = 0
        for item in group:
            left = item["obj"]
            if not _auditable(left):
                continue
            for other in index.near(item["bounds"], excluded):
                right = other["obj"]
                if ignore_leaf_obstacles and (right.get('uchuva_semantic_class')=='leaf' or right.get('uchuva_organ_kind')=='petiole'):
                    continue
                if not _auditable(right) or _mesh_collision_exempt(left, right):
                    continue
                a, b = item["bounds"], other["bounds"]
                if any(a[1][d]+.0245 < b[0][d] or b[1][d]+.0245 < a[0][d] for d in range(3)):
                    continue
                if bvh(item).overlap(bvh(other)):
                    classification = _mesh_intersection_classification(left, right)
                    if classification == "intentional_support":
                        continue
                    if left.get("uchuva_semantic_class") == right.get("uchuva_semantic_class") == "leaf":
                        continue
                    intersections += 1
                    continue
                required = _mesh_pair_required_clearance(left, right) if repair_clearance else 0.
                if required:
                    close = False
                    for vertices, tree in ((_world_vertices(item), bvh(other)), (_world_vertices(other), bvh(item))):
                        for vertex in vertices:
                            nearest = tree.find_nearest(vertex, required)
                            if nearest is not None and nearest[3] is not None and nearest[3] < required:
                                close = True
                                break
                        if close:
                            break
                    clearance_pairs += int(close)
        return intersections, clearance_pairs

    def clearance_deficit(group, excluded):
        """Continuous tie-break only; identical required distances and BVHs.

        Never excuses a failing pair. It permits progress on a count plateau by
        reducing the sum of positive vertex-to-surface separation deficits.
        """
        deficit = 0.
        for item in group:
            left=item["obj"]
            if not _auditable(left):
                continue
            for other in index.near(item["bounds"],excluded):
                right=other["obj"]
                if not _auditable(right) or _mesh_collision_exempt(left,right):
                    continue
                required=_mesh_pair_required_clearance(left,right)
                if not required or bvh(item).overlap(bvh(other)):
                    continue
                minimum=required
                for vertices,tree in ((_world_vertices(item),bvh(other)),(_world_vertices(other),bvh(item))):
                    for vertex in vertices:
                        nearest=tree.find_nearest(vertex,minimum)
                        if nearest is not None and nearest[3] is not None:
                            minimum=min(minimum,nearest[3])
                deficit+=max(0.,required-minimum)
        return deficit

    # Avoid rescanning thousands of Blender objects at every nodal candidate.
    organ_groups = {}
    for obj in bpy.context.scene.objects:
        if obj.get("uchuva_plant_id") != instance_id:
            continue
        reproductive = str(obj.get("uchuva_reproductive_instance_id", ""))
        if reproductive:
            organ_groups.setdefault(("reproductive", reproductive.removeprefix(instance_id+":")), []).append(obj)
        else:
            organ_id = str(obj.get("uchuva_organ_id", "")).removeprefix("uchuva_")
            for ending in ("_petiole", "_midrib"):
                organ_id = organ_id.removesuffix(ending)
            organ_groups.setdefault(("leaf",organ_id), []).append(obj)

    def assign(organ, kind, pose):
        target = organ if kind == "leaf" else organ.pedicel
        if growth_joint_policy:
            target.provenance[KEY]['direction'] = list(joint_direction(*pose))
            return
        target.azimuth_deg = pose[0]
        if kind == "leaf":
            target.insertion_angle_deg = pose[1]
        else:
            target.angle_deg = pose[1]

    def build(organ, node, axis, kind, pose, role, visibility):
        assign(organ, kind, pose)
        context = {"plant_id": instance_id, "plant_role": role}
        point, direction = frames[node.id]
        material_key = "petiole_drying" if plant.condition == "drying" else "petiole_green"
        if kind == "leaf":
            objects = _create_leaf_at_node(point, direction, organ, materials, _new_collision_context(),
                                          context, CM_TO_BLENDER_UNIT, material_key, node.id, axis.order)
        else:
            objects = _create_reproductive_unit_at_node(point, organ, materials, _new_collision_context(),
                                                       context, CM_TO_BLENDER_UNIT, material_key, node.id, axis.order)
        for obj in objects:
            # Newly linked, unparented objects have not entered the depsgraph.
            # matrix_basis reads their transform channels immediately.
            obj.matrix_basis = transform @ obj.matrix_basis
            key = str(obj.get("uchuva_organ_id", ""))
            if key in visibility:
                hide_render, hide_viewport, local_hide = visibility[key]
                obj.hide_render, obj.hide_viewport = hide_render, hide_viewport
                obj.hide_set(local_hide)
        bpy.context.view_layer.update()
        return objects, [value for obj in objects if relevant(obj) for value in [cached(obj)] if value]

    def reproductive_trial(unit, node, group, pose):
        from .reproductive_orientation import pedicel_direction, organ_direction
        direction = (Vector(joint_direction(*pose)) if growth_joint_policy else
                     Vector(pedicel_direction(unit, pose[0]-unit.pedicel.azimuth_deg,
                                             pose[1]-unit.pedicel.angle_deg)))
        distal_direction = Vector(organ_direction(unit, tuple(direction)))
        from .blender_reproductive_orientation import gravity_axis_rotation
        def organ_rotation(axis):
            return (gravity_axis_rotation(axis).to_4x4() if "reproductive_orientation" in unit.provenance
                    else axis.to_track_quat("Z", "Y").to_matrix().to_4x4())
        point = frames[node.id][0]
        length = unit.pedicel.length_cm * CM_TO_BLENDER_UNIT
        result = []
        for template in group:
            if template["obj"].get("uchuva_organ_kind") == "pedicel":
                matrix = Matrix.Translation(point + direction * (length*.5)) @ direction.to_track_quat("Z", "Y").to_matrix().to_4x4()
            elif template["obj"].get("uchuva_semantic_class") == "calyx":
                center = point + direction * length + distal_direction * (unit.calyx.length_cm * CM_TO_BLENDER_UNIT * CALYX_CENTER_FROM_PEDICEL_FRACTION)
                matrix = Matrix.Translation(center) @ organ_rotation(-distal_direction)
            elif template["obj"].get("uchuva_semantic_class") == "flower":
                matrix = Matrix.Translation(point + direction * length) @ organ_rotation(distal_direction)
            else:
                raise ValueError("Unsupported reproductive collision template")
            matrix = transform @ matrix
            lo,hi = template["local_bounds"]
            corners = [matrix @ Vector((x,y,z)) for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
            result.append({**template, "matrix": matrix, "vertices": None, "bounds": _bounds(corners), "bvh": None})
        return result

    for pass_index in range(max_passes):
        changed_before = len(changes)
        for kind in organ_kinds:
            # Singleton node groups give a global bottom-up traversal without
            # changing the historical axis-order path.
            groups = ([(a,[n]) for a,n in sorted(((a,n) for a in _axes(plant.axes) for n in a.nodes),
                       key=lambda pair:(frames[pair[1].id][0].z,pair[0].order,pair[1].position_index,pair[1].id))]
                      if growth_joint_policy else [(a,a.nodes) for a in _axes(plant.axes)])
            for axis, nodes in groups:
                for node in nodes:
                    if awake_seconds() - started >= max_seconds:
                        exhausted = True
                        break
                    organ = node.leaf if kind == "leaf" else node.reproductive_unit
                    if organ is None:
                        continue
                    objects = organ_groups.get((kind,organ.id), [])
                    own = [index.entries[o.name] for o in objects if o.name in index.entries]
                    if not own:
                        continue
                    excluded = {item["obj"].name for item in own}
                    initial = score(own, excluded)
                    initial_ground = ground.score(own) if ground else (0,0,0)
                    if initial == (0, 0) and initial_ground == (0,0,0):
                        continue
                    target = organ if kind == "leaf" else organ.pedicel
                    before = (joint_angles(target.provenance[KEY]['direction']) if growth_joint_policy else
                              (target.azimuth_deg, target.insertion_angle_deg if kind == "leaf" else target.angle_deg))
                    role = str(objects[0].get("uchuva_plant_role", "target"))
                    visibility = {str(o.get("uchuva_organ_id", "")): (o.hide_render, o.hide_viewport, o.hide_get()) for o in objects}
                    collections = list(objects[0].users_collection)
                    best_pose, best = before, initial
                    best_ground = initial_ground
                    best_phase = "unchanged"
                    initial_deficit = clearance_deficit(own,excluded) if clearance_tiebreak and initial[0]==0 else None
                    best_deficit = initial_deficit

                    def objective(mesh_score, ground_score):
                        return (mesh_score[0]+ground_score[0]+ground_score[2], mesh_score[1]+ground_score[1])
                    if kind == "reproductive":
                        replay = reproductive_trial(organ, node, own, before)
                        if any(max((a-b).length for a,b in zip(_world_vertices(x), _world_vertices(y))) > 2e-5 for x,y in zip(own,replay)):
                            raise ValueError("Reproductive templates disagree with rendered pose; pass the exact instance transform")
                    try:
                        phases = [("coarse",None)]
                        if fine_angular_step_deg is not None:
                            phases.extend((("fine",fine_angular_step_deg),("fine",min(2.,fine_angular_step_deg*.4))))
                        if dense_reproductive_step_deg is not None and kind == "reproductive":
                            phases.append(("dense",dense_reproductive_step_deg))
                        allow_fine = False
                        organ_trials = 0
                        tested_poses = {before}
                        for phase,step in phases:
                            if phase == "fine" and not allow_fine:
                                break
                            if phase == "dense" and (best_pose != before or best == (0,0)):
                                break
                            remaining = max_trials_per_organ-organ_trials
                            if remaining <= 0:
                                break
                            candidates = (joint_candidates(before,target.provenance[KEY]['input_direction'],kind=kind,limit=remaining,
                                excursion_limit_deg=target.provenance[KEY].get('excursion_limit_deg'))
                                if growth_joint_policy else angular_candidates(*before,kind=kind,limit=coarse_limit) if phase == "coarse"
                                else dense_reproductive_candidates(step)[:remaining] if phase == "dense"
                                else fine_angular_candidates(*best_pose,kind=kind,step_deg=step,limit=min(8,remaining)))
                            for pose in candidates:
                                if pose in tested_poses:
                                    continue
                                tested_poses.add(pose)
                                if awake_seconds()-started >= max_seconds:
                                    exhausted = True
                                    break
                                trial_objects = []
                                try:
                                    if kind == "reproductive":
                                        group = reproductive_trial(organ, node, own, pose)
                                    else:
                                        # Exact renderer and modifiers, without the
                                        # thousands of unchanged crop objects.
                                        with bpy.context.temp_override(scene=_trial_scene,
                                                view_layer=_trial_scene.view_layers[0],
                                                collection=_trial_scene.collection):
                                            trial_objects, group = build(organ,node,axis,kind,pose,role,visibility)
                                    value = score(group, excluded)
                                    ground_value = ground.score(group) if ground else (0,0,0)
                                    deficit_value = (clearance_deficit(group,excluded)
                                        if clearance_tiebreak and phase == "dense" and value[0]==0 else None)
                                    trials += 1
                                    organ_trials += 1
                                    phase_trials[phase] = phase_trials.get(phase,0)+1
                                finally:
                                    _remove_pose_objects(trial_objects)
                                strictly_better = objective(value,ground_value) < objective(best,best_ground)
                                tied_better = (deficit_value is not None and objective(value,ground_value)==objective(best,best_ground)
                                    and best_deficit is not None and deficit_value < best_deficit-1e-4)
                                if _ground_not_worse(ground_value,best_ground) and (strictly_better or tied_better):
                                    best_pose, best = pose, value
                                    best_ground = ground_value
                                    best_phase = phase
                                    best_deficit = deficit_value
                                if best == (0,0) and best_ground == (0,0,0):
                                    break
                            if phase == "coarse":
                                # Refinement is reserved for a genuine coarse plateau.
                                allow_fine = best_pose == before and (best != (0,0) or best_ground != (0,0,0))
                            if exhausted or (best == (0,0) and best_ground == (0,0,0)):
                                break
                    finally:
                        assign(organ,kind,before)
                    if best_pose != before:
                        replacements = []
                        try:
                            replacements, group = build(organ,node,axis,kind,best_pose,role,visibility)
                            exact = score(group, excluded)
                            exact_ground = ground.score(group) if ground else (0,0,0)
                            if exact != best or exact_ground != best_ground:
                                raise RuntimeError("Rebuilt geometry disagrees with trial score; no replacement committed")
                            if sorted(str(o.get("uchuva_organ_id", "")) for o in replacements) != sorted(str(o.get("uchuva_organ_id", "")) for o in objects):
                                raise RuntimeError("Organ identity changed in pose reconstruction")
                            for replacement in replacements:
                                for collection in collections:
                                    if replacement.name not in collection.objects:
                                        collection.objects.link(replacement)
                                for collection in list(replacement.users_collection):
                                    if collection not in collections:
                                        collection.objects.unlink(replacement)
                        except Exception:
                            _remove_pose_objects(replacements)
                            assign(organ,kind,before)
                            raise
                        for old in own:
                            index.remove(old)
                        _remove_pose_objects(objects)
                        organ_groups[kind,organ.id] = replacements
                        for item in group:
                            index.add(item)
                        record = {"organ_id": organ.id, "kind": kind, "node_id": node.id, "pass": pass_index,
                                  "before_deg": list(before), "after_deg": list(best_pose),
                                  "initial_pairs": list(initial), "remaining_pairs": list(best),
                                  "initial_ground": list(initial_ground), "remaining_ground": list(best_ground),
                                  "angular_limits_deg": ({"frame":"plant","azimuth":[0,360],"search_elevation":[-85,85],
                                      "excursion_from_input":120 if kind=='leaf' else target.provenance[KEY].get('excursion_limit_deg',75)} if growth_joint_policy else
                                      {"azimuth":[0,360],"inclination":list(ADAPTED_ANGLE_LIMITS[kind])}),
                                  "search_phase":best_phase,
                                  "clearance_deficit_before_bu":initial_deficit,"clearance_deficit_after_bu":best_deficit,
                                  "status": "engineering_heuristic", "dimensions_unchanged": True}
                        store = target.provenance[KEY] if growth_joint_policy else target.provenance
                        history = store.setdefault("mesh_feedback_pose_history_v2",[])
                        if not history:
                            previous = store.get("mesh_feedback_pose_v2")
                            if previous:
                                history.append(deepcopy(previous))
                                store["mesh_feedback_pose_history_prefix_v2"] = "only_last_legacy_record_available"
                            else:
                                store["mesh_feedback_pose_history_prefix_v2"] = "complete_since_first_mesh_repair"
                        history.append(deepcopy(record))
                        store["mesh_feedback_pose_v2"] = record
                        store["mesh_feedback_pose"] = "bounded_angular_search_dimensions_preserved"
                        changes.append(record)
                        if invariant_function(plant) != invariant:
                            raise RuntimeError("Protected morphology changed during pose repair")
                        if callable(checkpoint):
                            checkpoint(plant, record)
                        elif checkpoint and len(changes) % 10 == 0:
                            from .segmentation_cycles import write
                            write(checkpoint, plant.to_dict())
                        print("POSE_V2", kind, organ.id, initial, best, flush=True)
                if exhausted:
                    break
            if exhausted:
                break
        if exhausted or len(changes) == changed_before:
            break
    component_diagnostics=[]
    if growth_joint_policy and not exhausted and 'reproductive' in organ_kinds:
        from .blender_nodal_cooperative import repair_components
        owners={n.reproductive_unit.id:(a,n,n.reproductive_unit)
                for a in _axes(plant.axes) for n in a.nodes if n.reproductive_unit}
        cooperative,additional_trials,component_diagnostics=repair_components(
            plant=plant,index=index,organ_groups=organ_groups,owners=owners,frames=frames,instance_id=instance_id,
            score=score,bvh=bvh,reproductive_trial=reproductive_trial,build=build,ground=ground,
            started=started,max_seconds=max_seconds,checkpoint=checkpoint)
        changes.extend(cooperative);trials+=additional_trials
    plant.metadata["model_stage"] = "adapted"
    record_reproductive_counts(plant, "adapted")
    report = {"version": "size-preserving-mesh-pose/1", "method": "bounded_angular_nodal_coordinate_search",
              "status": "time_budget_exhausted" if exhausted else "search_finished_requires_full_audit",
              "invariants_before": invariant, "invariants_after": invariant_function(plant),
              "growth_joint_policy":growth_joint_policy,
              "cooperative_components":component_diagnostics,
              "adjustments": changes, "candidate_count": trials, "elapsed_seconds": awake_seconds()-started,
              "candidate_count_by_phase":phase_trials,
              "dense_reproductive_step_deg":dense_reproductive_step_deg,
              "clearance_tiebreak":bool(clearance_tiebreak),
              "repair_positive_interorgan_clearance":bool(repair_clearance),
              "searched_organ_kinds":list(organ_kinds),
              "clock": "Windows QueryUnbiasedInterruptTime; non-Windows monotonic fallback",
              "limits": {"passes": max_passes, "candidates_per_organ": max_trials_per_organ, "seconds": max_seconds,
                         "pedicel_angle_deg": list(ADAPTED_ANGLE_LIMITS["reproductive"]),
                         "leaf_angle_deg": list(ADAPTED_ANGLE_LIMITS["leaf"])},
              "refinement": {"enabled":fine_angular_step_deg is not None,
                             "step_deg":fine_angular_step_deg,
                             "coarse_candidate_limit":coarse_limit,
                             "reserved_fine_candidates":fine_reserve,
                             "trigger":"Residual with no improvement during coarse search",
                             "second_step_deg":None if fine_angular_step_deg is None else min(2.,fine_angular_step_deg*.4),
                             "within_existing_total_per_organ_and_time_limits":True},
              "collision_policy": "existing_exemptions; all_obstacles; only_leaf_leaf_soft; epsilon_0.0005",
              "leaf_trial_evaluation": "unchanged renderer in temporary isolated scene depsgraph; main scene only for accepted commit",
              "ground_policy": None if ground is None else {
                  "required_clearance_m": ground.required_m, "metres_per_blender_unit": ground.metres_per_bu,
                  "source": "evaluated_terrain_mesh", "score_order": ["physical","clearance","coverage"],
                  "monotonic": "No ground score component may increase in an accepted pose",
                  "rectangular_coverage_proven": ground.rectangular_coverage,
                  "above_terrain_fast_skips": ground.fast_above_count, "vertical_rays": ground.ray_count,
                  "scope": "Movable leaves, pedicels, calyces and flowers; independent full ground audit required"},
              "requires_full_rebuild_audit": True,
              "limitations": ["No axis pose changes; unresolved branch crossings remain blocking.",
                              "Local search cannot establish feasibility or eliminate every intersection.",
                              "Camera, materials and class assignments do not enter the objective."]}
    plant.metadata.setdefault("mesh_pose_repair_history", []).append(report)
    if checkpoint and not callable(checkpoint):
        from .segmentation_cycles import write
        write(checkpoint, plant.to_dict())
    return report
