"""Pure navigation helpers for inward-facing row inspection; metres/radians."""
import math


def inward_yaw(position, target):
    return math.atan2(target[1]-position[1],target[0]-position[0])


def orientation_speed_scale(error):
    angle=abs(error)
    if angle>=math.radians(20):return 0.
    if angle<=math.radians(10):return 1.
    return (math.radians(20)-angle)/math.radians(10)


def terminal_arc(center,radius,z,plant_id,step_deg=5):
    """Right-hand exterior semicircle; camera always faces the terminal plant."""
    count=math.ceil(180/step_deg)
    result=[]
    for i in range(count+1):
        angle=-math.pi/2+i*math.pi/count
        position=[center[0]+radius*math.cos(angle),center[1]+radius*math.sin(angle),z]
        result.append(dict(position=position,yaw=inward_yaw(position,center),
            look_at_world_m=list(center),target_plant_id=plant_id,phase=f'inward_turn_{i:03d}'))
    return result


def obstacle_distance(point, boxes, capsules):
    distances=[point[2]]
    for low,high in boxes:
        distances.append(math.sqrt(sum(max(low[d]-point[d],0,point[d]-high[d])**2 for d in range(3))))
    for capsule in capsules:
        a,b=capsule['start_m'],capsule['end_m'];v=[b[d]-a[d] for d in range(3)]
        norm=sum(x*x for x in v)
        t=max(0,min(1,sum((point[d]-a[d])*v[d] for d in range(3))/norm)) if norm else 0
        distances.append(max(0,math.dist(point,[a[d]+t*v[d] for d in range(3)])-capsule['radius_m']))
    return min(distances)
