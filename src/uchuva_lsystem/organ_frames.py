"""Pure local organ-frame calculations shared by geometry interpreters."""
import math


def orthogonal_leaf_direction(axis_direction, azimuth_deg, insertion_angle_deg):
    """Project world azimuth onto the axis-normal plane before applying angle."""
    def unit(v):
        length = math.sqrt(sum(x*x for x in v))
        if length < 1e-12:
            raise ValueError('Zero axis direction')
        return tuple(x/length for x in v)
    axis = unit(axis_direction)
    az = math.radians(azimuth_deg)
    radial = (math.cos(az), math.sin(az), 0.0)
    dot = sum(x*y for x,y in zip(axis,radial))
    projected = tuple(x-dot*y for x,y in zip(radial,axis))
    if sum(x*x for x in projected) < 1e-12:
        # Deterministic perpendicular reference at the azimuth singularity.
        index = min(range(3), key=lambda i: abs(axis[i]))
        ref = tuple(float(i == index) for i in range(3))
        projected = tuple(x-axis[index]*y for x,y in zip(ref,axis))
    radial = unit(projected)
    angle = math.radians(insertion_angle_deg)
    return unit(tuple(x*math.cos(angle)+y*math.sin(angle) for x,y in zip(axis,radial)))


def branch_direction_3d(parent_direction, azimuth_deg, branch_angle_deg):
    """Local cone around a parent tangent, including horizontal parent axes."""
    length = math.sqrt(sum(x*x for x in parent_direction))
    if length < 1e-12:
        raise ValueError('Zero parent direction')
    axis = tuple(x/length for x in parent_direction)
    index = min(range(3), key=lambda i: abs(axis[i]))
    ref = tuple(float(i == index) for i in range(3))
    radial = tuple(ref[i]-axis[index]*axis[i] for i in range(3))
    length = math.sqrt(sum(x*x for x in radial))
    u = tuple(x/length for x in radial)
    v = (axis[1]*u[2]-axis[2]*u[1], axis[2]*u[0]-axis[0]*u[2], axis[0]*u[1]-axis[1]*u[0])
    az, angle = math.radians(azimuth_deg), math.radians(branch_angle_deg)
    return tuple(axis[i]*math.cos(angle)+(u[i]*math.cos(az)+v[i]*math.sin(az))*math.sin(angle) for i in range(3))


def local_cone_leaf_direction(axis_direction, azimuth_deg, insertion_angle_deg):
    """Opt-in leaf azimuth around a complete local 3D cone.

    Unlike the historical world-XY projection, the radial plane retains both
    degrees of freedom on horizontal stems. Insertion remains the angle to the
    stem tangent. Azimuth is relative to the deterministic least-aligned-axis
    basis, not a world compass heading or a camera-facing direction.
    """
    axis = tuple(float(value) for value in axis_direction)
    azimuth, insertion = float(azimuth_deg), float(insertion_angle_deg)
    if (len(axis) != 3 or not all(math.isfinite(value) for value in axis)
            or not math.isfinite(azimuth) or not math.isfinite(insertion)
            or not 0 <= insertion <= 180):
        raise ValueError("Invalid local-cone leaf direction parameters")
    return branch_direction_3d(axis, azimuth, insertion)
