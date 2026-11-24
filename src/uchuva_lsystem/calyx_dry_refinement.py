"""Opt-in refinement of vein contrast, intervenal pigment and dry paper relief.

Offline NumPy solver; no Blender or morphology changes. All numerical settings
are visual engineering hypotheses, not measured age or chemical concentrations.
"""
from dataclasses import dataclass,asdict
from array import array
import math,random
from .calyx_diffusion_texture import DiffusionPlan,surface_plan as prior_plan,vein_graph,SNAPSHOTS
from .texture_assets import _draw_stroke,_sinuous_connector

VERSION='calyx-vein-tissue-dry-refinement/1'


@dataclass(frozen=True)
class DryPlan(DiffusionPlan):
    texture_revision:str=VERSION
    def to_dict(self):return dict(version=VERSION,**asdict(self))


def surface_plan(class_id,index,seed):
    return DryPlan(**asdict(prior_plan(class_id,index,seed)))


def simulate(veins,steps=SNAPSHOTS,*,dt=.12,source_enabled=True):
    """Retain proximal origin, increase lateral transport and tissue fixation."""
    import numpy as np
    v=np.asarray(veins,dtype=np.float64)
    if v.ndim!=2 or min(v.shape)<4:raise ValueError('2D field required')
    if not np.all(np.isfinite(v)) or np.min(v)<0 or np.max(v)>1:raise ValueError('Veins in [0,1] required')
    network=v.copy()
    for _ in range(2):
        north=np.vstack((network[:1],network[:-1]));south=np.vstack((network[1:],network[-1:]))
        network=(4*network+np.roll(network,1,1)+np.roll(network,-1,1)+north+south)/8
    network=np.clip(network*3.,0,1)
    dx=.055+.52*network;dy=.06+1.20*network
    if dt*2*(float(np.max(dx))+float(np.max(dy)))>.95:raise ValueError('Unstable diffusion step')
    def harmonic(a,b):return 2*a*b/(a+b)
    east=harmonic(dx,np.roll(dx,-1,axis=1));west=np.roll(east,1,axis=1)
    south=harmonic(dy[:-1],dy[1:]);source=np.zeros_like(v)
    source[int(v.shape[0]*.965):]=network[int(v.shape[0]*.965):]
    if not source_enabled:source[:]=0
    a=np.zeros_like(v);p=np.zeros_like(v);result={0:p.copy()}
    rate=.007+.30*network;accumulation=.012+.025*network
    for step in range(1,max(steps)+1):
        flux=east*(np.roll(a,-1,axis=1)-a)+west*(np.roll(a,1,axis=1)-a)
        vertical=south*(a[1:]-a[:-1]);flux[:-1]+=vertical;flux[1:]-=vertical
        a=np.clip(a+dt*(flux+rate*a*(1-a)+.7*source*(1-a)),0,1)
        p+=dt*accumulation*a*(1-p)
        if step in steps:result[step]=p.copy()
    return result


def dry_fibres(resolution,seed):
    """Shallow nonperiodic paper creases/fibres for normal/color maps only."""
    rng=random.Random(seed);height=array('f',[0.])*resolution**2;orders=bytearray(resolution**2)
    for _ in range(330):
        u,v=rng.uniform(0,1),rng.uniform(.025,.975)
        length=rng.uniform(.025,.14);angle=rng.uniform(0,math.tau)
        end=(u+length*math.cos(angle),max(.015,min(.985,v+length*math.sin(angle))))
        points=_sinuous_connector((u,v),end,1,rng,14)
        _draw_stroke(height,orders,resolution,points,rng.uniform(.0007,.0017),rng.uniform(.2,.8),1,wrap_x=True)
    return height


def color_surface(veins,orders,pigment,coherent,grain,class_id,*,severity=0.,bleached=False):
    """Bake contrast hierarchy: strong mature ribs, low reticular late contrast."""
    import numpy as np
    v=np.asarray(veins);order=np.asarray(orders);p=np.asarray(pigment)
    base=np.array(((176,185,108),(193,190,117),(211,188,131))[class_id],dtype=float)
    if class_id in (0,1):
        weights=np.where(order==1,.96,np.where(order==2,.78,.49))
        vein_color=np.array((40,25,57),dtype=float)
    else:
        weights=np.where(order==1,.76*(1-.20*p),np.where(order==2,.49*(1-.40*p),.29*(1-.86*p)))
        vein_color=np.array((64,39,54),dtype=float)
    structure=np.clip(v**.55*weights,0,.96)
    carrier=base[None,None,:]*(1-structure[:,:,None])+vein_color[None,None,:]*structure[:,:,None]
    carrier*=(1+.10*(coherent-.5)+grain)[:,:,None]
    strength=p*(.71+.18*coherent)
    target=np.stack((77+16*coherent,52+17*coherent,59+13*coherent),axis=2)
    rgb=carrier*(1-strength[:,:,None])+target*strength[:,:,None]
    # Small desaturation from drying; not a uniform brown/black fill.
    neutral=rgb@np.array((.2126,.7152,.0722))
    desaturation=.10*severity
    rgb=rgb*(1-desaturation)+neutral[:,:,None]*desaturation
    if bleached:rgb=rgb*.67+np.array((193,179,147))*.33
    return np.clip(rgb,0,255)
