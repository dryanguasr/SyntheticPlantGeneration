"""Run authorized dependent stages sequentially, without concurrent GPU jobs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

from prepare_union_pilot import ROOT, write


def run(script,arguments,log):
    write(ROOT/'pipeline_status.json',{'stage':script,'arguments':arguments,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    with (ROOT/log).open('w',encoding='utf-8') as stream:
        subprocess.run([sys.executable,'scripts/'+script,*arguments],stdout=stream,stderr=subprocess.STDOUT,check=True)


def main():
    protocol=json.loads((ROOT/'protocol.json').read_text())
    cutoff=datetime.fromisoformat(protocol['synthetic_admission_deadline_utc']).timestamp()
    completion=ROOT/'training/real/completion.json'
    while not completion.exists():
        if (ROOT/'training/real/failure.json').exists():raise RuntimeError('Real training failed')
        if time.time()>datetime.fromisoformat(protocol['training_stop_utc']).timestamp():raise TimeoutError('Real training did not complete')
        time.sleep(5)
    real=json.loads(completion.read_text());arms=['real']
    # Admission includes a conservative 90-minute second run and final delivery reserve.
    remaining=datetime.fromisoformat(protocol['deadline_utc']).timestamp()-time.time()
    if time.time()<cutoff and remaining>3*3600 and (ROOT/'mixed_dataset/manifest.json').exists():
        run('train_union_pilot.py',['--arm','mixed','--dataset',str(ROOT/'mixed_dataset/data.yaml'),
                                  '--target-steps',str(real['optimizer_steps'])],'training_mixed.log')
        mixed=json.loads((ROOT/'training/mixed/completion.json').read_text())
        if mixed['optimizer_steps']!=real['optimizer_steps']:
            write(ROOT/'mixed_budget_warning.json',{'real_steps':real['optimizer_steps'],'mixed_steps':mixed['optimizer_steps'],
                  'claim':'Exploratory only; matched-budget comparison failed'})
        arms.append('mixed')
    else:
        write(ROOT/'synthetic_not_run.json',{'reason':'admission time, remaining budget or preparation gate','time_utc':datetime.now(timezone.utc).isoformat()})
    run('evaluate_union_detector.py',['--arms',*arms],'detector_evaluation.log')
    for arm in arms:
        run('evaluate_union_videos.py',['--arm',arm],f'videos_{arm}.log')
    write(ROOT/'pipeline_status.json',{'stage':'completed','arms':arms,'completed_at_utc':datetime.now(timezone.utc).isoformat()})


if __name__=='__main__':
    try:main()
    except Exception as exc:
        write(ROOT/'pipeline_failure.json',{'type':type(exc).__name__,'message':str(exc),'time_utc':datetime.now(timezone.utc).isoformat()})
        raise
