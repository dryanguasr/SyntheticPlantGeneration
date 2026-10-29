"""Prepare a new reproducible spatial-admission run; never launch implicitly."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.nodal_automation import write,sha
from uchuva_lsystem.execution_budget import awake_seconds
from uchuva_lsystem.appearance_profiles import initial_profiles


def prepare(root,seed,blender,hours=1,candidate_seconds=1200):
    root=Path(root).resolve()
    if hours<=0 or candidate_seconds<=0:raise ValueError('Positive active-time budgets required')
    root.mkdir(parents=True,exist_ok=False)
    config=dict(version='portable-spatial-admission/1',blender=str(blender),proxy_seconds=60,
        leaf_seconds=240,reproductive_seconds=180,branch_seconds=45,local_seconds=90,
        rounds=20,minimum_round_seconds=60,qualification_reserve_seconds=300,
        candidate_seconds=candidate_seconds,pedicel_excursion_deg=180,local_trigger_crossings=32,
        branch_trigger_crossings=64,previews=False,diagnostic_rejected_previews=False,
        local_candidate_modes=['counterbend_pair','fixed_pair','four_nodes'],
        automatic_spatial_admission=True,fresh_seed_fallback_start=seed+1,
        seed_policy='Sequential independent fresh seeds; no historical output dependencies')
    write(root/'config.json',config);write(root/'profiles.json',initial_profiles())
    write(root/'queue.json',[dict(seed=seed,origin='fresh_seed_portable_queue')])
    write(root/'budget.json',dict(version='portable-spatial-admission/1',started_utc=datetime.now(timezone.utc).isoformat(),
        awake_started_seconds=awake_seconds(),limit_active_seconds=hours*3600,
        excluded_intervals=[],target_new_valid_plants=1000000000,suspension_excluded=True))
    write(root/'authorization.json',dict(source='Explicit invocation of prepare_spatial_plant_pool.py',hours=hours,
        training_authorized=False,dataset_authorized=False,parameter_status='engineering_heuristic'))
    scripts=['prepare_spatial_plant_pool.py','run_spatial_plant_pool.py','worker_spatial_pool.py','run_nodal_automation.py']
    sources=list((ROOT/'src/uchuva_lsystem').glob('*.py'))+[ROOT/'scripts'/n for n in scripts]
    inputs=[root/n for n in ['config.json','profiles.json','queue.json','budget.json','authorization.json']]
    lock=dict(sources={p.relative_to(ROOT).as_posix():sha(p) for p in sources},
        inputs={str(p):sha(p) for p in inputs},config_sha256=sha(root/'config.json'),profiles_sha256=sha(root/'profiles.json'))
    write(root/'source_lock.json',lock)
    for p in sources:
        target=root/'frozen_source'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    return root


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--blender',type=Path,required=True);p.add_argument('--hours',type=float,default=1)
    p.add_argument('--candidate-seconds',type=float,default=1200)
    a=p.parse_args();root=prepare(a.root,a.seed,a.blender,a.hours,a.candidate_seconds)
    print(f'Prepared {root}; active budget begins now. Launch explicitly: python scripts/run_spatial_plant_pool.py "{root}"')


if __name__=='__main__':main()
