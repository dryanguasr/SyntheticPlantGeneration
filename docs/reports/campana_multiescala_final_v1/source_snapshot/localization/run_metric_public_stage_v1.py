"""Serial CPU controller for the three already captured routes."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=ROOT.parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')

def main():
    protocol=read(HERE/'protocol.json');manifest=read(HERE/'preparation_manifest.json')
    assert sha(HERE/'protocol.json')==manifest['protocol_sha256']
    assert read(HERE/'cpu_check_v1.json')['passed']
    state=dict(stage='public_localization',controller_pid=os.getpid(),localization_complete=False,
               started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),routes={})
    state_path=HERE/'execution_state_v1.json'
    if state_path.exists():raise FileExistsError('Do not duplicate or silently resume controller')
    write(HERE/'launch_readiness_v1.json',dict(passed=True,protocol_sha256=sha(HERE/'protocol.json'),
        cpu_check_sha256=sha(HERE/'cpu_check_v1.json'),controller_sha256=sha(Path(__file__)),
        free_gib=psutil.virtual_memory().available/2**30))
    write(state_path,state)
    try:
        for route in protocol['route_order']:
            flight=ROOT/'flights'/route;output=HERE/'public_estimates'/route
            assert sha(flight/'tracking_new/observations.json')==manifest['tracking_sha256'][route]
            assert psutil.virtual_memory().available/2**30>=6.5
            command=[sys.executable,str(HERE/'localize_public_v1.py'),
                '--public',str(flight/'public'),'--rgb-admission',str(flight/'public_admission_v1.json'),
                '--sensors',str(flight/'sensors_public'),'--sensor-admission',str(flight/'sensors_public_admission_v1.json'),
                '--observations',str(flight/'tracking_new/observations.json'),'--protocol',str(HERE/'protocol.json'),
                '--out',str(output),'--frozen-src',str(REPO/'outputs/frozen_field_pilot_20261019/frozen/src/uchuva_gazebo')]
            with (HERE/(route+'.stdout.log')).open('x') as stdout,(HERE/(route+'.stderr.log')).open('x') as stderr:
                process=subprocess.Popen(command,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                state.update(route=route,child_pid=process.pid,command=command);write(state_path,state)
                minimum=100.
                while process.poll() is None:
                    free=psutil.virtual_memory().available/2**30;minimum=min(minimum,free)
                    if free<3:
                        process.terminate();process.wait(timeout=30)
                        raise RuntimeError('RAM early stop of this localization child')
                    time.sleep(1)
                state['routes'][route]=dict(returncode=process.returncode,minimum_free_gib=minimum)
                write(state_path,state)
                if process.returncode:raise RuntimeError('Preserved failed route '+route)
                assert read(output/'summary.json')['complete']
        state.update(stage='public_localization_complete_private_evaluation_pending',child_pid=None,controller_pid=None,
            finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    except Exception as exc:
        state.update(stage='failed_preserved',error=repr(exc),child_pid=None,controller_pid=None)
        raise
    finally:write(state_path,state)

if __name__=='__main__':main()
