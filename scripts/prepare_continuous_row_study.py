"""Versioned 30 Hz retrospective study: six targets and twelve context plants."""
import argparse
import copy
import datetime
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha,CLASSES
from uchuva_lsystem.execution_budget import awake_seconds
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters,walk_axes,attach_strings
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.bouquet import train_bouquet
from uchuva_lsystem.clearance_bouquet import clear_branch_axes
from uchuva_lsystem.support import outward_tie_anchor


def initialize(root):
    root.mkdir(parents=True,exist_ok=False)
    prior=ROOT/'outputs/localization_pilot_20261005'
    source=prior/'reserved_field_input.json'
    payload=json.loads(source.read_text());old=json.loads((prior/'run.json').read_text())
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    seeds=list(range(620800,620812))
    write(root/'run.json',dict(version='continuous-row-study/1.0',seed=620800,
        parameter_preset='three_rows_retrospective_30hz',started_utc=now,classes=CLASSES,
        model=old['model'],model_sha256=sha(old['model']),background_seeds=seeds,
        historical_campaign=str(prior),source_morphologies_sha256=sha(source),
        scope='retrospective simulation; previously inspected target morphologies, not untouched holdout',
        target_marker_ids=list(range(12)),frame_rate_hz=30,resolution=[1280,720],
        row_spacing_m=6.,row_spacing_status='initial engineering clearance choice; exact geometry and corridor must pass before flight'))
    write(root/'effective_budget.json',dict(version='effective-execution-budget/1.0',limit_seconds=None,
        historical_execution_seconds=0,authorization='User removed time cap on 2026-10-08; continue until deliverables verified',historical_ledger=str(prior/'effective_budget.json')))
    write(root/'controller_sessions/setup.json',dict(state='active',started_utc=now,
        awake_started_seconds=awake_seconds(),awake_elapsed_seconds=0,purpose='Continuous row study implementation and preparation'))
    write(root/'target_source.json',payload)
    for seed in seeds:
        plant=train_bouquet(prepare_plant(generate_morphology_tree(seed,sparse_morphology_parameters('individual_dense_crown_v3'))))
        rng=random.Random(seed+719)
        for axis in walk_axes(plant.axes):
            for node in axis.nodes:
                if node.leaf:
                    node.leaf.curl=rng.uniform(.12,.32);node.leaf.twist_deg=rng.uniform(-22,22)
                    node.leaf.insertion_angle_deg=rng.uniform(95,155)
        plant.metadata['segmentation_contract']=dict(version='continuous-row-study/1.0',classes=CLASSES,green_in_pintona=True,group='background',agronomic_maturity='unknown')
        clear_branch_axes(plant,fine_search=True)
        write(root/'background_morphologies'/f'{seed}.json',plant.to_dict())
    write(root/'status.json',dict(state='implementation_and_background_audits',completed=False))


def assemble(root):
    run=json.loads((root/'run.json').read_text());base=json.loads((root/'target_source.json').read_text())
    payload=copy.deepcopy(base);scene=payload['scene'];scene['plant_instances']=[]
    scene['seed']=run['seed'];scene['preset_name']='target_row_with_two_background_rows'
    scene['metadata']['config'].update(rows=3,columns=6,row_spacing_m=run['row_spacing_m'],
        parameter_status='engineering_choice_pending_full_geometry_flight_validation')
    scene['metadata']['reference_split']='retrospective'
    support=scene['support_system'];support.update(posts=[],lines=[],ties=[],contacts=[])
    plants={};markers=[];roles={};source_audits={}
    for row,y_m in enumerate((0.,-run['row_spacing_m'],run['row_spacing_m'])):
        offset=y_m*8+36;role='target' if row==0 else 'background'
        for key,coords in [('posts',['position']),('lines',['start','end'])]:
            for original in base['scene']['support_system'][key]:
                item=copy.deepcopy(original);item['id']=item['id'].replace('row_0',f'row_{row}')
                item['row_id']=f'row_{row}'
                for coordinate in coords:item[coordinate][1]+=offset
                support[key].append(item)
        for column,original in enumerate(base['scene']['plant_instances']):
            index=row*6+column;identifier=f'plant_{index:02d}';instance=copy.deepcopy(original)
            instance.update(plant_id=identifier,role=role);instance['position'][1]+=offset
            if row==0:plant=Plant.from_dict(base['plants'][original['plant_id']])
            else:
                seed=run['background_seeds'][(row-1)*6+column]
                folder=root/'background_audits'/run.get('background_audit_directories',{}).get(str(seed),str(seed))
                audit=json.loads((folder/'mesh_audit.json').read_text())
                if audit['acceptance']!='passed':raise ValueError(f'Background audit not passed: {seed}')
                plant=Plant.from_dict(json.loads((folder/'morphology.json').read_text()))
                source_audits[str(seed)]=sha(folder/'mesh_audit.json')
            instance['seed']=plant.seed;scene['plant_instances'].append(instance);plants[identifier]=plant
            roles[identifier]=dict(role=role,row_id=f'row_{row}')
            for original_marker in base['markers']:
                if original_marker['plant_id']!=original['plant_id']:continue
                marker=copy.deepcopy(original_marker);marker['plant_id']=identifier;marker['id']+=row*12
                marker['center_world_m'][1]+=offset/8;markers.append(marker)
    scene=CultivationScene.from_dict(scene);attach_strings(scene,plants)
    centers={i.plant_id:i.position for i in scene.plant_instances};lines={line.id:line for line in scene.support_system.lines}
    for tie in scene.support_system.ties:
        line=lines[tie.support_line_id]
        tie.end=outward_tie_anchor(tie.start,centers[tie.plant_id],line.start,line.end,.9*8)
    payload.update(script_version='continuous-row-field/1.0',preset='target_row_with_two_background_rows',
        experimental_group='retrospective',scene=scene.to_dict(),plants={k:p.to_dict() for k,p in plants.items()},markers=markers,
        instance_roles=roles,background_audit_sha256=source_audits,
        rows=[dict(row_id=f'row_{row}',role='target' if row==0 else 'background',center_y_m=y)
              for row,y in enumerate((0.,-run['row_spacing_m'],run['row_spacing_m']))],
        limitations=['Background is context, not an independently evaluated crop','Spacing is an engineering choice; flight requires exact clearance validation'])
    write(root/'field_input.json',payload)
    print('THREE_ROW_FIELD',len(plants),len(markers),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--assemble',action='store_true');args=parser.parse_args()
    (assemble if args.assemble else initialize)(args.root.resolve())


if __name__=='__main__':main()
