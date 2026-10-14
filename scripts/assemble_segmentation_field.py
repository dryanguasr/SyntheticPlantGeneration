"""Assemble six approved morphologies into the bounded Gazebo pilot field."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.scene import CultivationScene
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.sparse_pilot import attach_strings
from uchuva_lsystem.segmentation_cycles import group_seeds,write,sha


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--group',choices=['development','final'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--iteration',type=int,default=1)
    p.add_argument('--seed-manifest',type=Path)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    source=ROOT/'outputs/bouquet_crowns_v4/input.json'
    payload=json.loads(source.read_text())
    budget=json.loads((a.root/'field_budget.json').read_text())
    seeds=budget[a.group+'_seeds']
    allowed=group_seeds()[a.group]
    if a.seed_manifest:
        reservation=json.loads(a.seed_manifest.read_text())
        if reservation.get('version')!='localization-pilot/1.0' or a.group!='final':
            raise ValueError('Unsupported independent reservation')
        allowed=reservation['final_seeds']
        if seeds!=allowed:raise ValueError('Independent final reservation must remain complete and ordered')
    if len(seeds)!=6 or len(set(seeds))!=6 or not set(seeds)<=set(allowed):raise ValueError('Invalid frozen field seeds')
    scene=payload['scene'];scene['plant_instances']=scene['plant_instances'][:6]
    scene['seed']=seeds[0];scene['scene_id']=f'segmentation_{a.group}_{seeds[0]}'
    support=scene['support_system']
    for key in ('posts','lines'):support[key]=[v for v in support[key] if v['row_id']=='row_0']
    support['ties']=[];support['contacts']=[]
    plants={};sources={}
    for instance,seed in zip(scene['plant_instances'],seeds):
        path=a.root/'approved_morphologies'/f'{seed}.json'
        audit_path=a.root/'approved_morphologies'/f'{seed}_audit.json'
        if json.loads(audit_path.read_text())['acceptance']!='passed':raise ValueError('Unapproved morphology')
        plant=Plant.from_dict(json.loads(path.read_text()))
        if plant.seed!=seed:raise ValueError('Morphology seed mismatch')
        if plant.metadata['segmentation_contract']['group']!=a.group:raise ValueError('Group leakage')
        instance.update(seed=seed,scale=1.0,role='target')
        plants[instance['plant_id']]=plant
        sources[str(seed)]={'morphology_sha256':sha(path),'audit_sha256':sha(audit_path)}
    scene=CultivationScene.from_dict(scene);attach_strings(scene,plants)
    policy_path=a.root/f'cycle_{a.iteration:02d}'/'appearance.json'
    policy=json.loads(policy_path.read_text()) if policy_path.exists() else {}
    if policy.get('outward_support_strings'):
        from uchuva_lsystem.support import outward_tie_anchor
        # Extend the end posts and cable so edge bushes can also pull outward.
        for line in scene.support_system.lines:
            line.start=(line.start[0]-9.6,*line.start[1:])
            line.end=(line.end[0]+9.6,*line.end[1:])
        for post in scene.support_system.posts:
            post.position=(post.position[0]+(-9.6 if post.position[0]<0 else 9.6),*post.position[1:])
        centers={v.plant_id:v.position for v in scene.plant_instances}
        lines={v.id:v for v in scene.support_system.lines}
        for tie in scene.support_system.ties:
            line=lines[tie.support_line_id]
            tie.end=outward_tie_anchor(tie.start,centers[tie.plant_id],line.start,line.end,
                                      policy.get('outward_offset_m',.9)*8)
        scene.support_system.provenance['outward_anchors']='engineering_heuristic; existing open morphology preserved; no force simulation'
    ids=set(plants)
    payload.update(seed=seeds[0],preset=f'segmentation_{a.group}_six_bushes',
        script_version='segmentation-field/1.0',scene=scene.to_dict(),
        plants={key:plant.to_dict() for key,plant in plants.items()},
        markers=[m for m in payload['markers'] if m['plant_id'] in ids],
        experimental_group=a.group,approved_sources=sources,
        appearance_cycle=a.iteration,appearance_policy=policy,
        limitations=['Single row of six bushes due measured memory limits; not six-row field coverage',
                     'Individual plant mesh audits; trellis contacts and inter-plant contacts are separate checks'])
    write(a.output,payload)
    print(json.dumps({'group':a.group,'plants':len(plants),'seeds':seeds}))


if __name__=='__main__':main()
