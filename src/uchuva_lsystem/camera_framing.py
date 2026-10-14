"""Pure perspective fit for a complete plant and its marker, without scaling them."""
import math


def fit_level_camera(points, *, side=-1, azimuth=0., margin=.07,
                     horizontal_fov=math.pi/3, aspect=1280/720, clearance=.35):
    if not points or side not in (-1, 1) or not 0 < margin < .5:
        raise ValueError('Invalid framing inputs')
    center = tuple((min(p[i] for p in points)+max(p[i] for p in points))/2 for i in range(3))
    radial = (math.sin(azimuth), side*math.cos(azimuth))
    right = (-radial[1], radial[0])
    horizontal = math.tan(horizontal_fov/2)*(1-2*margin)
    vertical = horizontal/aspect
    left=[];right_bound=[];top=[];bottom=[];radial_bounds=[]
    for point in points:
        x, y, z = (point[i]-center[i] for i in range(3))
        toward_camera = x*radial[0]+y*radial[1]
        across = x*right[0]+y*right[1]
        left.append(toward_camera+across/horizontal);right_bound.append(toward_camera-across/horizontal)
        top.append(toward_camera+z/vertical);bottom.append(toward_camera-z/vertical)
        radial_bounds.append(toward_camera+clearance)
    a,b,c,d=max(left),max(right_bound),max(top),max(bottom)
    distance=max((a+b)/2,(c+d)/2,max(radial_bounds))
    across_shift=(a-b)*horizontal/2;vertical_shift=(c-d)*vertical/2
    target=[center[0]+across_shift*right[0],center[1]+across_shift*right[1],center[2]+vertical_shift]
    return {'position': [target[0]+distance*radial[0], target[1]+distance*radial[1],target[2]],
            'target': target, 'distance': distance, 'margin': margin,
            'method': 'perspective fit of visible target bounds; engineering clearance heuristic'}
