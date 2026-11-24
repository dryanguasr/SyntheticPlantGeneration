"""Vein-registered visible pigmentation, based on the user's field observation.

Arrival times are engineering heuristics in UV space, not physiological time.
Only the existing vein network seeds the process. The UV convention is v=0
proximal (pedicel), v=1 distal; PNG rows run in the opposite direction.
"""
from array import array
from dataclasses import asdict,dataclass
import heapq,math
from .calyx_mottling import surface_plan as previous_plan

VERSION='vein-origin-calyx-pigmentation/1'


@dataclass(frozen=True)
class VeinSpreadPlan:
    name:str
    class_id:int
    seed:int
    phase:float
    contraction:float
    phenotype:str
    progress:float
    halo_strength:float
    vein_strength:float
    transmitted_diffuse_mix:float=.12
    parameter_status:str='engineering_heuristic_from_user_observation_pending_visual_review'
    origin:str='existing UV vein mask; proximal veins start earlier; spread into adjacent tissue and distally'
    physiological_resorption:str='unverified; visible drying/contraction only'

    def to_dict(self):return dict(version=VERSION,**asdict(self))


def surface_plan(class_id,index,seed):
    old=previous_plan(class_id,index,seed)
    if class_id==2:
        progress=(0,.15,.32,.52,.70,.42)[index%6]
        halo=(0,.48,.63,.76,.80,.50)[index%6]
        vein=(0,.74,.84,.90,.92,.78)[index%6]
    else:
        progress=(0,.085,.12)[index%3]
        halo=.30 if progress else 0;vein=.52 if progress else 0
    name='advanced_venous' if old.name=='advanced_mottled' else old.name
    return VeinSpreadPlan(name,class_id,seed,old.phase,old.contraction,old.phenotype,progress,halo,vein)


def smoothstep(low,high,x):
    t=max(0.,min(1.,(x-low)/(high-low)))
    return t*t*(3-2*t)


def arrival_field(veins,width,height,*,seed=20261111,threshold=.20):
    """Multi-source shortest arrival on a periodic-U, bounded-V image grid.

    Input is PNG row order. Each vein seed receives an earlier proximal time.
    Growth away from veins has a positive cost; upward spread is slower than
    downward spread. Noise modulates rates only; it never creates new seeds.
    """
    if width<2 or height<2 or len(veins)!=width*height:raise ValueError('Invalid field size')
    times=array('d',[math.inf])*(width*height);heap=[];phase=(seed%997)*.013
    for y in range(height):
        v=1-(y+.5)/height
        for x in range(width):
            i=y*width+x;signal=veins[i]
            if signal<threshold:continue
            u=(x+.5)/width
            variation=.065*(.5+.5*math.sin(math.tau*(3*u+1.7*v)+phase))*math.sin(math.pi*v)**.7
            value=.018+.43*v**1.15+.07*(1-signal)+variation
            times[i]=value;heap.append((value,i))
    if not heap:raise ValueError('No registered vein seeds')
    heapq.heapify(heap)
    directions=[(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]
    while heap:
        value,i=heapq.heappop(heap)
        if value!=times[i]:continue
        y,x=divmod(i,width);v=1-(y+.5)/height
        for dx,dy in directions:
            yy=y+dy
            if not 0<=yy<height:continue
            xx=(x+dx)%width;j=yy*width+xx
            # PNG dy<0 goes towards larger v (the distal tip).
            direction=1. if dy<0 else (1.5 if dy>0 else 1.12)
            distance=math.hypot(dx/width,dy/height)
            rate=7.5*(1+.45*v)*direction
            rate*=1+.20*math.sin(math.tau*(5*xx/width+2.4*v)+phase)
            candidate=value+distance*rate
            if candidate<times[j]:times[j]=candidate;heapq.heappush(heap,(candidate,j))
    return times


def pigment_weights(arrival,vein_signal,uv_v,plan,window=.7):
    if plan.progress==0:return 0.,0.
    reached=1-smoothstep(plan.progress-.045,plan.progress+.045,arrival)
    proximal=1-.28*uv_v
    halo=reached*plan.halo_strength*proximal*(.65+.35*window)
    core_reached=1-smoothstep(plan.progress-.035,plan.progress+.035,arrival*.62)
    core=core_reached*vein_signal**.5*plan.vein_strength*(1-.12*uv_v)
    return core,halo
