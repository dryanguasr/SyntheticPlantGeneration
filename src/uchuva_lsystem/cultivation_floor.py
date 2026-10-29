"""Seeded ground context plans; crop morphology is never an input to edit."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import random


@dataclass(frozen=True)
class CultivationFloorConfig:
    version: str = 'earthen_litter_floor/1'
    litter_count: int = 2200
    twig_count: int = 700
    vegetation_clusters: int = 24
    root_clearance_bu: float = .45
    parameter_status: str = 'engineering_heuristic'

    def to_dict(self):
        return asdict(self)


def plan_cultivation_floor(seed, plant_centres, bounds, config=None):
    """Return reproducible positions, never organs or label exclusions.

    Bounds and dimensions are scene units. Litter stays below the 0.01 BU
    crop-ground clearance. Context contact remains outside exhaustive audit.
    """
    cfg=config or CultivationFloorConfig()
    if any(v<0 for v in (cfg.litter_count,cfg.twig_count,cfg.vegetation_clusters)):
        raise ValueError('Ground counts must be nonnegative')
    x0,x1,y0,y1=map(float,bounds)
    if not (x0<x1 and y0<y1):raise ValueError('Nonempty floor bounds required')
    rng=random.Random(seed);centres=[tuple(map(float,p[:2])) for p in plant_centres]
    def point():
        for _ in range(500):
            if centres and rng.random()<.76:
                cx,cy=rng.choice(centres);x=rng.gauss(cx,2.5);y=rng.gauss(cy,1.8)
            else:x=rng.uniform(x0,x1);y=rng.uniform(y0,y1)
            if x0<=x<=x1 and y0<=y<=y1 and all(math.hypot(x-cx,y-cy)>cfg.root_clearance_bu for cx,cy in centres):
                return (x,y)
        raise ValueError('Ground bounds cannot accommodate root exclusion')
    clusters=[point() for _ in range(cfg.vegetation_clusters)]
    def debris(kind,count):
        result=[]
        for _ in range(count):
            x,y=point();length=rng.uniform(.12,.65) if kind=='leaf' else rng.uniform(.16,1.1)
            result.append(dict(kind=kind,x=x,y=y,z=.002,length=length,
                               width=length*rng.uniform(.22,.5) if kind=='leaf' else rng.uniform(.006,.022),
                               angle=rng.uniform(0,math.tau),tone=rng.randrange(4)))
        return result
    return dict(version=cfg.version,seed=seed,config=cfg.to_dict(),bounds=[x0,x1,y0,y1],
                vegetation_centres=clusters,litter=debris('leaf',cfg.litter_count),
                twigs=debris('twig',cfg.twig_count),
                scope='Context only; crop organs, dimensions and poses unchanged; no exhaustive context-contact certification')
