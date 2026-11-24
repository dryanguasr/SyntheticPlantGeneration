"""Pure irregular surface hypotheses; drying geometry is inherited unchanged.

No axial threshold: growing anisotropic patches overlap around the proximal
zone and elsewhere. Extents/mixes are engineering choices for visual approval,
not estimated lesion prevalence or measured optical properties.
"""
from dataclasses import dataclass,asdict
import math,random

VERSION='irregular-calyx-mottling/2'


@dataclass(frozen=True)
class Patch:
    center:tuple
    radii:tuple
    strength:float


@dataclass(frozen=True)
class MottlingPlan:
    name:str
    class_id:int
    seed:int
    phase:float
    contraction:float
    phenotype:str
    max_dark_mix:float
    browning:float
    patches:tuple
    transmitted_diffuse_mix:float=.12
    parameter_status:str='engineering_heuristic_pending_visual_approval'
    opacity_policy:str='no uniform black replacement; preserve substrate veins and light windows; no transparency holes'
    physiological_resorption:str='unverified; visible drying/contraction hypothesis only'

    def to_dict(self):return dict(version=VERSION,**asdict(self))


def surface_plan(class_id,index,seed):
    if class_id not in (0,1,2):raise ValueError('Unknown class')
    rng=random.Random(seed);phase=rng.uniform(0,math.tau)
    if class_id!=2:
        stage=(0,.12,.20)[index%3]
        values=('control_with_optional_proximal_patch',stage,.40 if stage else 0,0,0,'dark_proximal')
    else:
        values=[('historical',0,0,0,0,'dark_proximal'),
            ('light',.24,.52,.08,.18,'dark_proximal'),
            ('intermediate',.48,.72,.20,.42,'dark_proximal'),
            ('extensive',.72,.84,.28,.68,'dark_proximal'),
            ('advanced_mottled',.86,.88,.34,.88,'dark_proximal'),
            ('dry_bleached',.58,.60,.12,.90,'bleached_dry')][index%6]
    name,stage,mix,brown,contraction,phenotype=values
    patches=[]
    if stage:
        for j in range(10 if class_id==2 else 3):
            angle=phase+j*2.399963+rng.uniform(-.35,.35)
            proximal=j<3;z=rng.uniform(.74,.96) if proximal else rng.uniform(.18,.84)
            radial=.46*math.sin(math.pi*z)**.65
            center=(.5+radial*math.cos(angle),.5+radial*math.sin(angle),z)
            growth=.40+stage*1.15
            radii=tuple(v*growth for v in (rng.uniform(.18,.30),rng.uniform(.18,.30),rng.uniform(.20,.37)))
            strength=1 if proximal else min(1,.20+stage*.85)
            patches.append(Patch(center,radii,strength))
    return MottlingPlan(name,class_id,seed,phase,contraction,phenotype,mix,brown,tuple(patches))


def smoothstep(low,high,value):
    t=max(0,min(1,(value-low)/(high-low)))
    return t*t*(3-2*t)


def dark_weight(point,plan,*,macro_noise=.5,micro_noise=.5,warp=(0,0,0)):
    """Continuous 3-D field; noise values supplied by the interpreter/sampler."""
    field=0.
    for patch in plan.patches:
        q=math.sqrt(sum(((point[i]+warp[i]-patch.center[i])/patch.radii[i])**2 for i in range(3)))
        field=max(field,(1-smoothstep(.25,1.3,q))*patch.strength)
    windows=.24+.76*smoothstep(.18,.54,macro_noise)
    texture=.72+.28*micro_noise
    return field*windows*texture*plan.max_dark_mix
