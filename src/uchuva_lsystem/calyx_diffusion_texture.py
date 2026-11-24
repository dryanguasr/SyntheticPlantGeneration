"""Offline, vein-guided reaction/diffusion texture experiment.

The graph is pure Python; the optional offline solver uses the already present
NumPy runtime. Neither component needs Blender or changes morphology. All rates
and colors are visual engineering hypotheses, not measured calyx physiology.
"""
from array import array
from dataclasses import dataclass,asdict
import math,random
from .calyx_mottling import surface_plan as previous_plan
from .texture_assets import _draw_stroke,_sinuous_connector

VERSION='calyx-texture-reaction-diffusion/2'
SNAPSHOTS=(0,600,1400,2600,4200)


@dataclass(frozen=True)
class DiffusionPlan:
    name:str
    class_id:int
    seed:int
    phase:float
    contraction:float
    phenotype:str
    snapshot_step:int
    transmitted_diffuse_mix:float=.10
    parameter_status:str='engineering_heuristic_pending_real_image_comparison'
    physiological_resorption:str='unverified; visible drying/compression only'

    def to_dict(self):return dict(version=VERSION,**asdict(self))


def surface_plan(class_id,index,seed):
    old=previous_plan(class_id,index,seed)
    names=('historical','light','intermediate','extensive','advanced_diffused','dry_bleached')
    steps=(0,600,1400,2600,4200,2600)
    return DiffusionPlan(names[index%6] if class_id==2 else old.name,class_id,seed,old.phase,
        old.contraction,old.phenotype,steps[index%6] if class_id==2 else 600)


def vein_graph(resolution,seed):
    """Five structural ribs plus irregular, bounded intercostal reticulation.

    All row positions are constructed inside the domain. No repeated clipping
    of out-of-range rows onto one coordinate, which formed artificial bands in
    the previous texture graph.
    """
    rng=random.Random(seed);height=array('f',[0.])*resolution**2;orders=bytearray(resolution**2)
    for j in range(5):
        for shift,width,strength,order in ((0,.0062,1.,1),(.1,.0028,.60,2)):
            line=[(j/5+shift+.004*math.sin(t*math.tau*1.2+j),.012+.976*t) for t in [k/90 for k in range(91)]]
            _draw_stroke(height,orders,resolution,line,width,strength,order,wrap_x=True)
    rows,columns=14,20;grid=[]
    for y in range(rows):
        v=.055+.89*y/(rows-1)
        grid.append([((x/columns+rng.uniform(-.018,.018))%1,
            v+rng.uniform(-.021,.021)*math.sin(math.pi*y/(rows-1))) for x in range(columns)])
    for y,row in enumerate(grid):
        for x,p in enumerate(row):
            targets=[]
            if rng.random()>.18:targets.append(row[(x+1)%columns])
            if y+1<rows:targets.append(grid[y+1][(x+rng.choice((-1,0,0,1)))%columns])
            for q in targets:
                qu=q[0]
                if qu-p[0]>.5:qu-=1
                elif p[0]-qu>.5:qu+=1
                curve=_sinuous_connector(p,(qu,q[1]),1,rng,12)
                _draw_stroke(height,orders,resolution,curve,rng.uniform(.0015,.0023),rng.uniform(.33,.54),3,wrap_x=True)
    return height,orders,dict(rows=rows,columns=columns,row_domain=(.055,.945),clipped_rows=0,primary_ribs=5)


def simulate(veins,steps=SNAPSHOTS,*,dt=.12,source_enabled=True):
    """Conservative spatial flux, vein-enhanced activation, irreversible pigment.

    U is periodic, V has no-flux boundaries. Only the proximal collar injects
    activator. No source elsewhere means no spontaneous remote pigment islands.
    """
    import numpy as np
    v=np.asarray(veins,dtype=np.float64)
    if v.ndim!=2 or min(v.shape)<4:raise ValueError('2D field required')
    if not np.all(np.isfinite(v)) or np.min(v)<0 or np.max(v)>1:raise ValueError('Veins must lie in [0,1]')
    network=v.copy()
    for _ in range(2):
        north=np.vstack((network[:1],network[:-1]));south=np.vstack((network[1:],network[-1:]))
        network=(4*network+np.roll(network,1,1)+np.roll(network,-1,1)+north+south)/8
    network=np.clip(network*3.,0,1)
    dx=.02+.55*network;dy=.03+1.25*network
    if dt*2*(float(np.max(dx))+float(np.max(dy)))>.95:raise ValueError('Unstable explicit diffusion step')
    def harmonic(a,b):return 2*a*b/(a+b)
    east=harmonic(dx,np.roll(dx,-1,axis=1));west=np.roll(east,1,axis=1)
    south=harmonic(dy[:-1],dy[1:]);rows=v.shape[0]
    source=np.zeros_like(v);source[int(rows*.965):]=network[int(rows*.965):]
    if not source_enabled:source[:]=0
    activation=np.zeros_like(v);pigment=np.zeros_like(v);result={0:pigment.copy()}
    rate=.005+.32*network;accumulation=.005+.032*network
    for step in range(1,max(steps)+1):
        flux=east*(np.roll(activation,-1,axis=1)-activation)+west*(np.roll(activation,1,axis=1)-activation)
        vertical=south*(activation[1:]-activation[:-1]);flux[:-1]+=vertical;flux[1:]-=vertical
        activation=np.clip(activation+dt*(flux+rate*activation*(1-activation)+.7*source*(1-activation)),0,1)
        pigment+=dt*accumulation*activation*(1-pigment)
        if step in steps:result[step]=pigment.copy()
    return result
