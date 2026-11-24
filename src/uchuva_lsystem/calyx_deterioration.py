"""Pure, opt-in visible calyx deterioration hypotheses; not physiological age.

User field observation motivates the traits. Numerical ranges are engineering
heuristics for visual review. No inferred internal fruit resorption is modeled.
Historical plant dimensions, labels and interpreters remain unchanged.
"""
from dataclasses import dataclass,asdict
import math,random

VERSION='visible-calyx-deterioration/2'


@dataclass(frozen=True)
class CalyxDeterioration:
    seed:int
    severity:float
    radius_scale:float
    length_scale:float
    transverse_compression:float
    wrinkle_depth:float
    brown_coverage:float
    proximal_darkening:float
    bleaching:float
    phase:float
    phenotype:str='dark_proximal'
    parameter_status:str='engineering_heuristic_pending_visual_review'
    provenance:str='user_field_observation_2026-10-31; visual calyx traits only'
    physiological_resorption:str='unverified_not_simulated'

    def to_dict(self):return dict(version=VERSION,**asdict(self))


def deterioration_state(seed,severity,phenotype='dark_proximal'):
    if not math.isfinite(severity) or not 0<=severity<=1:raise ValueError('Severity must be in[0,1]')
    if phenotype not in ('dark_proximal','bleached_dry'):raise ValueError('Unknown visible phenotype')
    rng=random.Random(seed);d=float(severity);v=rng.uniform(.88,1.12)
    dark=min(.97,1.12*d) if phenotype=='dark_proximal' else .52*d
    bleach=max(0,(d-.45)/.55)*(.6 if phenotype=='dark_proximal' else .92)
    return CalyxDeterioration(seed,d,1-.22*d,1-.23*d,1-.43*d,
        .18*d*v,min(.90,.95*d),dark,bleach,rng.uniform(0,math.tau),phenotype)


def deform_calyx_point(point,*,length,radius,state):
    """Map local calyx geometry, +Z proximal; keep its attachment pole fixed.

    This opt-in shell hypothesis does not establish compatibility with a berry
    inside the compressed envelope. Full-plant admission must check that later.
    """
    if length<=0 or radius<=0:raise ValueError('Positive reference dimensions required')
    x,y,z=map(float,point)
    if state.severity==0:return x,y,z
    anchor=.5*length;t=max(0,min(1,(anchor-z)/length));w=math.sin(math.pi*t)**.8
    angle=math.atan2(y,x);phase=state.phase
    folds=1-state.wrinkle_depth*w*(.5+.5*math.sin(7*math.pi*t+2*angle+phase))
    folds*=1-.07*state.severity*w*(.5+.5*math.cos(5*angle+phase+3*t))
    crease=math.atan2(math.sin(angle-phase-.7*t),math.cos(angle-phase-.7*t))
    folds*=1-.40*state.severity*w*math.exp(-.5*(crease/.32)**2)
    sy=1-w*(1-state.radius_scale);sx=sy*(1-w*(1-state.transverse_compression))
    twist=.22*state.severity*w*math.sin(3*t+phase)
    xx=x*math.cos(twist)-y*math.sin(twist);yy=x*math.sin(twist)+y*math.cos(twist)
    dx=radius*.10*state.severity*w*math.sin(5*t+phase)
    dy=radius*.04*state.severity*w*math.cos(7*t+phase)
    return xx*sx*folds+dx,yy*sy*folds+dy,anchor+(z-anchor)*state.length_scale
