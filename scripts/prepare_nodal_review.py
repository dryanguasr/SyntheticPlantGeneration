"""Prepare a small, declared nodal growth review, without cameras or training."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.nodal_repulsion import resolve_nodal_repulsion,protected_anatomy
from uchuva_lsystem.validation import validate_morphology_tree

def write(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--seeds',type=int,nargs='+',default=[2026102600,2026102601,2026102602])
    parser.add_argument('--seconds',type=float,default=360)
    args=parser.parse_args()
    args.root.mkdir(parents=True,exist_ok=True)
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/'src/uchuva_lsystem').glob('*.py'))}
    write(args.root/'source_lock.json',dict(sources=sources,seeds=args.seeds,training_authorized=False,
        scope='small physical review; no organ count or camera objective'))
    for seed in args.seeds:
        folder=args.root/f'seed_{seed}';folder.mkdir(exist_ok=False)
        plant=generate_morphology_tree(seed,preset_name='trained_trellis_nodal_repulsion_v8',
            phenology_model='literature_cohort_v1',resolve_growth=False)
        write(folder/'raw.json',plant.to_dict());before=protected_anatomy(plant)
        def checkpoint(p,row):
            write(folder/'checkpoint.json',p.to_dict())
            write(folder/'progress.json',row)
            print(seed,json.dumps(row),flush=True)
        result=resolve_nodal_repulsion(plant,sweeps=12,max_seconds=args.seconds,checkpoint=checkpoint)
        assert before==protected_anatomy(plant)
        write(folder/'proxy_search.json',result)
        write(folder/'validation.json',validate_morphology_tree(plant,stage='adapted'))
        write(folder/'plant.json',plant.to_dict())
        print('PREPARED_NOT_ADMITTED',seed,flush=True)

if __name__=='__main__':main()
