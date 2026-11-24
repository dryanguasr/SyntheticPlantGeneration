"""Bounded serial render/audit/train controller, with persistent failure evidence."""
import os
import subprocess
import sys
import time
from augmentation_pilot import ROOT, REPO, read, write, sha
from run_augmentation_campaign import job, train


def main():
    budget=read(ROOT/'budget.json');render=ROOT/'renders'
    lock=ROOT/'controller.lock'
    with lock.open('x',encoding='utf-8') as stream:
        import json
        json.dump(dict(pid=os.getpid(),started=time.time()),stream)
    try:
        for path,digest in read(ROOT/'execution_source_lock.json')['files'].items():assert sha(path)==digest,path
        if not (ROOT/'renders_complete.json').exists():
            failures=[]
            for scene in read(render/'protocol.json')['scenes']:
                folder=render/'captures'/scene['name']
                while time.time()+120<budget['render_deadline']:
                    processed=len(list(folder.glob('view_*/capture.json')))+len(list(folder.glob('view_*/rejected_pose.json')))
                    if processed>=scene['views']:break
                    name=f"render_{scene['name']}_{processed}"
                    write(ROOT/'state.json',dict(stage=name,pid=os.getpid(),complete=False,updated=time.time()))
                    log=ROOT/'logs'/f'{name}.log';log.parent.mkdir(exist_ok=True)
                    try:
                        with log.open('w',encoding='utf-8') as output:
                            subprocess.run(['C:/Program Files/Blender Foundation/Blender 5.1/blender.exe','-b','--python-exit-code','1',
                                '--python',str(render/'render.py'),'--','--root',str(render),'--scene',scene['name'],'--limit','24'],
                                cwd=REPO,stdout=output,stderr=subprocess.STDOUT,check=True,timeout=budget['render_deadline']-time.time())
                    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
                        failures.append(dict(scene=scene['name'],error=repr(error)));break
                    after=len(list(folder.glob('view_*/capture.json')))+len(list(folder.glob('view_*/rejected_pose.json')))
                    if after<=processed:raise RuntimeError('Renderer made no progress')
            write(ROOT/'renders_complete.json',dict(finished=time.time(),captures=len(list((render/'captures').glob('*/view_*/capture.json'))),
                rejected_poses=len(list((render/'captures').glob('*/view_*/rejected_pose.json'))),failures=failures))
        job('audit_augmentation_renders.py',[],'render_audit',budget['training_deadline'])
        train()
    except Exception as error:
        write(ROOT/'controller_failure.json',dict(error=repr(error),when=time.time(),pid=os.getpid()))
        write(ROOT/'state.json',dict(stage='needs_attention',error=repr(error),complete=False,updated=time.time()))
        raise
    finally:
        # This exact file was created by this controller; keep its contents as evidence.
        if lock.exists():lock.rename(ROOT/f'controller_finished_{os.getpid()}.json')


if __name__=='__main__':main()
