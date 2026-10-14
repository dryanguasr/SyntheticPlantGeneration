"""Sequential, bounded scene jobs; failed geometry never becomes training data."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import shutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import group_seeds, write
from uchuva_lsystem.execution_budget import remaining_seconds


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--iteration',type=int,required=True)
    p.add_argument('--seeds',type=int,nargs='+',required=True)
    p.add_argument('--blender',required=True)
    p.add_argument('--max-attempts',type=int,default=3)
    p.add_argument('--audit-group',choices=['development','final'])
    p.add_argument('--capture-folder',default='dataset_captures')
    p.add_argument('--source-capture-folder',default=None)
    a=p.parse_args()
    groups=group_seeds();allowed=set(groups[a.audit_group] if a.audit_group else groups['train']+groups['val'])
    if not set(a.seeds)<=allowed:raise ValueError('Seed is outside the requested frozen group')
    if a.audit_group=='final' and not (a.root/'winner_selection.json').exists():
        raise ValueError('Final scenario stays reserved until winner selection')
    folder=(a.root/'field_audits'/a.audit_group if a.audit_group else a.root/f'cycle_{a.iteration:02d}'/a.capture_folder)
    folder.mkdir(parents=True,exist_ok=True)
    results=[]
    for seed in a.seeds:
        if remaining_seconds(a.root)<(600 if a.audit_group=='final' else 5400):
            raise TimeoutError('Preserve final closure reserve')
        if a.iteration==1:
            source=(a.root/'repair_flower_margins/morphology.json' if seed==420100
                    else a.root/'axis_clear_morphologies'/f'{seed}.json')
            approved=a.root/'approved_morphologies'/f'{seed}.json'
            if approved.exists():source=approved
        else:
            previous=a.root/f'cycle_{a.iteration-1:02d}'/(a.source_capture_folder or a.capture_folder)
            sources=[d/'morphology.json' for d in previous.glob(f'{seed}_attempt*') if (d/'complete.json').exists()]
            if len(sources)!=1:raise ValueError(f'One accepted previous morphology required: {seed}')
            source=sources[0]
        accepted=False
        for attempt in range(1,a.max_attempts+1):
            out=folder/f'{seed}_attempt{attempt}'
            audit_valid=(out/'mesh_audit.json').exists() and json.loads((out/'mesh_audit.json').read_text())['acceptance']=='passed'
            if (out/'complete.json').exists() or (a.audit_group and audit_valid):accepted=True;break
            if out.exists():
                for candidate in ('morphology_after_reproductive.json','morphology_in_progress.json','morphology.json'):
                    if (out/candidate).exists():source=out/candidate
                continue
            stage=a.audit_group or a.capture_folder
            name=f'cycle{a.iteration}_{stage}_scene{seed}_attempt{attempt}'
            command=[sys.executable,str(ROOT/'scripts/run_effective_job.py'),'--root',str(a.root),
                '--name',name,'--timeout','900','--',a.blender,'-b','-t','4','--python-exit-code','1',
                '--python',str(ROOT/'scripts/render_segmentation_cycle.py'),'--','--root',str(a.root),
                '--morphology',str(source),'--iteration',str(a.iteration),'--views','10','--output',str(out)]
            if a.iteration==1 and source.parent.name not in ('approved_morphologies','repair_flower_margins'):
                command.append('--repair')
            if a.audit_group:command.append('--audit-only')
            code=subprocess.call(command)
            audit_valid=(out/'mesh_audit.json').exists() and json.loads((out/'mesh_audit.json').read_text())['acceptance']=='passed'
            if code==0 and ((out/'complete.json').exists() or (a.audit_group and audit_valid)):accepted=True;break
            candidates=[out/name for name in ('morphology_after_reproductive.json','morphology_in_progress.json','morphology.json') if (out/name).exists()]
            if not candidates:break
            source=candidates[-1]
        if accepted:
            approved=a.root/'approved_morphologies';approved.mkdir(exist_ok=True)
            for source_name,target_name in [('morphology.json',f'{seed}.json'),('mesh_audit.json',f'{seed}_audit.json')]:
                if not (approved/target_name).exists():shutil.copy2(out/source_name,approved/target_name)
        results.append({'seed':seed,'accepted':accepted,'folder':str(out)})
        write(folder/f'batch_status_{a.seeds[0]}.json',{'script_version':'segmentation-batch/1.0',
              'seed':a.seeds[0],'parameter_preset':'bouquet_calyx_appearance_cycles_v1','iteration':a.iteration,'scenes':results,
              'remaining_effective_seconds':remaining_seconds(a.root),'all_accepted':all(r['accepted'] for r in results)})
        print('SCENE_RESULT',seed,accepted,flush=True)
    if not all(r['accepted'] for r in results):raise SystemExit(1)


if __name__=='__main__':main()
