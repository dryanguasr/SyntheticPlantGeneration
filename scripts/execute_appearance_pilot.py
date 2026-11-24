"""Run the authorized bank, pretraining diagnostics and serial factorial.

This orchestration never changes frozen scientific inputs and never promotes a
model. Each component preserves attempts and owns its existing active-time job.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys
import time
import traceback
from appearance_campaign import (GPUJobLock,verify_review,read,write,sha,
    process_identity,charged_job,require,budget_usage)

REPO=Path(__file__).resolve().parents[1]


def run(root,blender):
    verify_review(root)
    with GPUJobLock(root/'pipeline.lock'):
        for path in (root/'execution_jobs').glob('*.json'):
            job=read(path);owner=job.get('identity')
            require(not (job.get('state')=='active' and owner and process_identity(owner['pid'])==owner),
                    'Prior active-time owner is still alive; do not duplicate workloads')
        for path in (root/'children').glob('*.json'):
            child=read(path).get('identity')
            require(not child or process_identity(child['pid'])!=child,'Prior training child is still alive')
        identity=process_identity()
        previous=root/'pipeline_controller.json'
        if previous.exists():
            row=read(previous)
            old=row.get('identity')
            require(not old or process_identity(old['pid'])!=old,'Prior pipeline controller still alive')
            archive=root/'pipeline_history'/f'{time.time_ns()}.json'
            write(archive,row)
        write(previous,dict(identity=identity,source_sha256=sha(__file__),started_utc=time.time(),state='running'))
        def invoke(script,*args):
            positional=[str(args[0])] if script=='run_appearance_campaign.py' else []
            remaining=args[1:] if positional else args
            command=[sys.executable,str(REPO/'scripts'/script),*positional,'--root',str(root),*map(str,remaining)]
            print('PIPELINE',command,flush=True)
            subprocess.run(command,cwd=REPO,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            manifest=root/'banks/manifest.json'
            if not manifest.exists():
                write(root/'state.json',dict(stage='generating_heterogeneous_bank',complete=False,
                    human_review='approved',training_enabled=True,identity=identity))
                invoke('render_appearance_bank.py','--blender',blender)
            require(read(manifest)['available_doses'],'No complete synthetic dose; preserve bank evidence and diagnose')
            with charged_job(root,'render','bank_domain_diagnostics'):
                invoke('report_appearance_bank.py')
            invoke('run_appearance_campaign.py','prepare')
            invoke('run_appearance_campaign.py','run')
            record=read(previous);record.update(state='evaluation_complete_pending_review',ended_utc=time.time(),budget_usage=budget_usage(root));write(previous,record)
        except BaseException as error:
            failure=dict(error=repr(error),traceback=traceback.format_exc(),identity=identity,when_utc=time.time())
            write(root/'pipeline_failures'/f'{time.time_ns()}.json',failure)
            record=read(previous);record.update(state='needs_attention',error=repr(error),ended_utc=time.time());write(previous,record)
            write(root/'state.json',dict(stage='needs_attention',complete=False,**failure))
            raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--blender',type=Path,required=True)
    args=parser.parse_args();run(args.root.resolve(),args.blender.resolve())
