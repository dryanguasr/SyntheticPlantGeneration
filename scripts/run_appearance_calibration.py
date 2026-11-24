"""Run one immutable, actively timed calibration attempt; never starts training."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time
from appearance_campaign import charged_job,remaining_budget,write,read,sha

REPO=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--attempt',required=True);p.add_argument('--limit',type=int,default=0)
    p.add_argument('--structure-only',action='store_true')
    a=p.parse_args();root=a.root.resolve();out=root/'calibration'/a.attempt
    if Path(a.attempt).name!=a.attempt:raise ValueError('Attempt must be a single directory name')
    snap=out/'source_snapshot';snap.mkdir(parents=True,exist_ok=True)
    if not (out/'profiles.json').exists():shutil.copy2(root/'profiles.json',out/'profiles.json')
    if not (out/'plants.json').exists():
        # Compatibility for a short diagnostic attempt using already generated trees.
        if not a.limit:raise FileNotFoundError('Prepare this round trees before rendering')
        shutil.copy2(root/'calibration/round_01/plants.json',out/'plants.json')
    manifest=snap/'snapshot_manifest.json'
    if not manifest.exists():
        sources=list((REPO/'src/uchuva_lsystem').glob('*.py'))+list((REPO/'assets/textures/current').glob('*'))+[REPO/'scripts/render_appearance_calibration.py']
        hashes={}
        for path in sources:
            if not path.is_file():continue
            relative=path.relative_to(REPO);dest=snap/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dest);hashes[str(relative)]=sha(dest)
        write(manifest,{'files':hashes,'source_root':str(REPO)})
    for relative,digest in read(manifest)['files'].items():
        if sha(snap/relative)!=digest:raise ValueError('Calibration snapshot changed: '+relative)
    command=['C:/Program Files/Blender Foundation/Blender 5.1/blender.exe','--background','--factory-startup','--python-exit-code','1',
             '--python',str(snap/'scripts/render_appearance_calibration.py'),'--','--root',str(root),'--output',str(out)]
    if a.limit:command+=['--limit',str(a.limit)]
    if a.structure_only:command+=['--structure-only']
    logs=out/'logs';logs.mkdir(exist_ok=True)
    number=len(list(logs.glob('attempt_*.log')));log=logs/f'attempt_{number:03d}.log'
    with charged_job(root,phase='render',job_id='calibration_'+a.attempt),log.open('w',encoding='utf-8') as stream:
        process=subprocess.Popen(command,cwd=REPO,stdout=stream,stderr=subprocess.STDOUT)
        write(out/'process.json',{'pid':process.pid,'command':command,'started_utc':time.time(),'log':str(log)})
        try:
            while process.poll() is None:
                if remaining_budget(root,'render')<=0:
                    process.terminate();process.wait(timeout=30);raise TimeoutError('Active render budget exhausted')
                time.sleep(2)
            if process.returncode:raise RuntimeError(f'Blender exited {process.returncode}; see {log}')
        except BaseException as error:
            if process.poll() is None:process.terminate();process.wait(timeout=30)
            write(out/f'failure_{number:03d}.json',{'error':repr(error),'exit_code':process.returncode,'log':str(log)})
            raise
    print(out,flush=True)


if __name__=='__main__':main()
