"""Pure smooth leaf surface, with no texture-scale geometric corrugation."""
import math


def broad_leaf_surface(edges, length, width, sag, ratio, cross_segments=8):
    """Expand paired boundary rows around the unchanged longitudinal midrib.

    ratio is an engineering control, not a measured botanical constant.
    The caller supplies root + paired edge rows, including the collapsed tip.
    """
    if not math.isfinite(ratio) or not 0 <= ratio <= .2:
        raise ValueError('transverse_arch_ratio must be finite in 0..0.2')
    if length <= 0 or width <= 0 or cross_segments < 2 or cross_segments % 2:
        raise ValueError('Positive dimensions and even cross_segments required')
    if len(edges) < 5 or len(edges) % 2 != 1:
        raise ValueError('Expected root followed by paired boundary rows')
    row_count = (len(edges)-1)//2-1
    stride = cross_segments+1
    vertices = [tuple(edges[0])]
    faces = []
    for row in range(row_count):
        left, right = edges[1+2*row:3+2*row]
        t = left[1]/length
        center = (0., left[1], -sag*t*t)
        for j in range(stride):
            q = j/cross_segments
            start, end, weight = (left, center, 2*q) if q <= .5 else (center, right, 2*q-1)
            point = tuple(start[k]*(1-weight)+end[k]*weight for k in range(3))
            z = point[2]-ratio*width*(2*q-1)**2*math.sin(math.pi*t)
            vertices.append((point[0], point[1], z))
    for j in range(cross_segments):
        # Root fan must face the same way as the longitudinal strips.
        faces.append((0, 2+j, 1+j))
    for row in range(row_count-1):
        for j in range(cross_segments):
            a = 1+row*stride+j
            faces.append((a, a+1, a+stride+1, a+stride))
    tip = len(vertices)
    vertices.append(tuple(edges[-1]))
    last = 1+(row_count-1)*stride
    for j in range(cross_segments):
        faces.append((last+j, last+j+1, tip))
    return vertices, faces
