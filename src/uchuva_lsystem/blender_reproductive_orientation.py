"""Check interpreted calyx axes and pedicel attachments after final rebuild."""
import math


def gravity_axis_rotation(direction):
    """Stable transverse frame even at exactly +/-Z (no track-quat pole).

    The new posture contract fixes a longitudinal axis, not a measured axial
    roll. Project plant X to choose that otherwise free roll deterministically.
    Used only by gravity_pendulous_v1; legacy track frames remain unchanged.
    """
    from mathutils import Matrix, Vector
    z = Vector(direction).normalized()
    x = Vector((1., 0., 0.)) - z*z.x
    if x.length < 1e-6:
        raise ValueError("Gravity organ axis must not approach horizontal plant X")
    x.normalize()
    y = z.cross(x).normalized()
    return Matrix((x, y, z)).transposed()


def audit_calyx_orientation(plants, layout, objects):
    from mathutils import Matrix, Vector
    from .reproductive_orientation import KEY, organ_direction
    groups = {}
    for obj in objects:
        groups.setdefault((str(obj.get("uchuva_plant_id")), str(obj.get("uchuva_reproductive_id"))), []).append(obj)
    rows, errors = [], []
    for plant, instance in zip(plants, layout.plant_instances):
        rotation = Matrix.Rotation(math.radians(instance.rotation_deg), 3, "Z")
        def visit(axes):
            for axis in axes:
                for node in axis.nodes:
                    unit = node.reproductive_unit
                    if unit is None or unit.calyx is None or KEY not in unit.provenance:
                        continue
                    matches = groups.get((instance.plant_id, unit.id), [])
                    husks = [o for o in matches if o.get("uchuva_semantic_class") == "calyx"]
                    stalks = [o for o in matches if o.get("uchuva_organ_kind") == "pedicel"]
                    if len(husks) != 1 or len(stalks) != 1:
                        errors.append(dict(plant_id=instance.plant_id, unit_id=unit.id, reason="missing_or_duplicate_geometry"))
                        continue
                    husk, stalk = husks[0], stalks[0]
                    distal = -(husk.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
                    expected = rotation @ Vector(organ_direction(unit))
                    inclination = math.degrees(math.acos(max(-1., min(1., -distal.z))))
                    mismatch = (distal-expected).length
                    # Local +Z is the proximal pole; a cylinder's distal end
                    # is +Z too. Mesh coordinates include dimensions already.
                    from .blender_geometry import CM_TO_BLENDER_UNIT
                    length = unit.calyx.length_cm * CM_TO_BLENDER_UNIT * instance.scale
                    proximal = husk.matrix_world.translation - distal * length*.5
                    # Blender cylinder depth lives in the mesh, not its scale.
                    zmax = max(v.co.z for v in stalk.data.vertices)
                    stalk_end = stalk.matrix_world @ Vector((0, 0, zmax))
                    attachment_error = (proximal-stalk_end).length
                    row = dict(plant_id=instance.plant_id, unit_id=unit.id,
                        inclination_from_down_deg=inclination, direction_error=mismatch,
                        attachment_error_bu=attachment_error)
                    rows.append(row)
                    if mismatch > 1e-5 or attachment_error > 1e-4 or inclination > unit.provenance[KEY]["inclination_bounds_deg"][1]+1e-4:
                        errors.append(row)
                visit(axis.child_axes)
        visit(plant.axes)
    return dict(version="calyx-gravity-and-attachment/1", status="invalid" if errors else "valid",
                checked_count=len(rows), errors=errors, rows=rows,
                interpretation="geometric posture check; angular prior is an unmeasured engineering heuristic")
