"""Independent visible darkening plans for a small approval-only preview.

Extent is a proximal-to-distal coordinate parameter, not measured stain area.
RGB dark area is measured separately. No physiological resorption is inferred.
"""
from dataclasses import dataclass,asdict
import random,math

VERSION='calyx-darkening-approval/1'


@dataclass(frozen=True)
class DarkeningPlan:
    name:str
    class_id:int
    proximal_extent:float
    intensity:float
    browning:float
    contraction:float
    seed:int
    phase:float
    phenotype:str='dark_proximal'
    parameter_status:str='engineering_heuristic_for_visual_approval'
    physiological_resorption:str='unverified; visible contraction hypothesis only'

    def to_dict(self):return dict(version=VERSION,**asdict(self))


def surface_plan(class_id,index,seed):
    if class_id not in (0,1,2):raise ValueError('Unknown class')
    if class_id!=2:
        extent=(0,.05,.10)[index%3];intensity=0 if extent==0 else .68
        values=('control_with_optional_proximal_patch',extent,intensity,0.,0.,'dark_proximal')
    else:
        presets=[('historical',0.,0.,0.,0.,'dark_proximal'),('light',.15,.68,.18,.18,'dark_proximal'),
            ('intermediate',.40,.85,.45,.42,'dark_proximal'),('extensive',.72,.94,.62,.68,'dark_proximal'),
            ('nearly_total',.96,.98,.70,.88,'dark_proximal'),('dry_bleached',.28,.70,.40,.90,'bleached_dry')]
        values=presets[index%len(presets)]
    name,extent,intensity,brown,contract,phenotype=values
    return DarkeningPlan(name,class_id,extent,intensity,brown,contract,seed,random.Random(seed).uniform(0,math.tau),phenotype)


def dark_weight(local_z_fraction,noise,plan):
    if plan.intensity==0:return 0.
    rank=1-local_z_fraction+.18*(noise-.5)
    return plan.intensity*max(0,min(1,(plan.proximal_extent+.04-rank)/.08))
