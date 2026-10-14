"""Immediately chain prepared stages after the initial morphology/export queue.

The extension queue is read between jobs so verified stages can be appended.
It never launches a second heavy job or silently retries failed experiments.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root=a.root.resolve()
    lock=a.root/'continuation.lock'
    with lock.open('x') as f:f.write(str(os.getpid()))
    try:
        # A restarted watcher must not leave the previous failure as its live
        # status while waiting for the initial queue or its resource admission.
        write(a.root/'continuation_status.json',dict(state='waiting_for_initial_queue',
            pid=os.getpid(),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        while True:
            completion=a.root/'study_complete.json'
            if completion.exists() and json.loads(completion.read_text()).get('verified_complete'):
                write(a.root/'continuation_status.json',dict(state='completed',updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
                break
            if (a.root/'queue.lock').exists() or (a.root/'execution_job.lock').exists():
                # Other supervisor owns an actual job; heartbeat diagnoses stale
                # locks using process evidence. Never delete locks speculatively.
                time.sleep(2);continue
            initial=json.loads((a.root/'queue_status.json').read_text())
            recovery_stages=[]
            if initial['state']=='needs_diagnosis':
                # Only an explicitly diagnosed, persisted recovery may cross a
                # failed initial queue. Never reinterpret the failed job as passed.
                recovery_path=a.root/'initial_queue_recovery.json'
                if not recovery_path.exists():raise RuntimeError('Initial queue failed; inspect its logs')
                recovery=json.loads(recovery_path.read_text())
                failed=a.root/'execution_jobs'/f"{recovery['failed_stage']}.json"
                if not failed.exists() or json.loads(failed.read_text())['state']!='failed':
                    raise RuntimeError('Recovery does not match the diagnosed failed job')
                recovery_stages=recovery['stages']
            queue=json.loads((a.root/'continuation_queue.json').read_text())
            pending=[]
            for stage in recovery_stages+queue['stages']:
                record=a.root/'execution_jobs'/f"{stage['name']}.json"
                if record.exists():
                    if json.loads(record.read_text())['state']!='completed':raise RuntimeError(f'Failed stage requires diagnosis: {record}')
                else:pending.append(stage)
            if not pending:
                write(a.root/'continuation_status.json',dict(state='awaiting_verified_next_stages',pid=os.getpid(),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
                time.sleep(10);continue
            stage=pending[0]
            write(a.root/'continuation_status.json',dict(state='running',stage=stage['name'],pid=os.getpid(),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
            subprocess.run([sys.executable,str(ROOT/'scripts/run_effective_job.py'),'--root',str(a.root),
                '--name',stage['name'],'--timeout',str(stage['timeout']),
                *(['--minimum-start-free-gib',str(stage['minimum_start_free_gib'])]
                  if 'minimum_start_free_gib' in stage else []),
                '--',*stage['command']],cwd=ROOT,check=True)
    except BaseException as exc:
        write(a.root/'continuation_status.json',dict(state='needs_diagnosis',error=repr(exc),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        raise
    finally:lock.unlink()


if __name__=='__main__':main()
