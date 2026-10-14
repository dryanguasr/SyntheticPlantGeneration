"""Execute a persisted sequential queue; fail closed and never wait for heartbeat."""
import argparse,datetime,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write
from uchuva_lsystem.execution_budget import remaining_seconds,session_elapsed


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root=a.root.resolve()
    lock=a.root/'queue.lock'
    with lock.open('x') as f:f.write(str(os.getpid()))
    try:
        queue=json.loads((a.root/'queue.json').read_text())
        for stage in queue['stages']:
            record=a.root/'execution_jobs'/f"{stage['name']}.json"
            if record.exists():
                if json.loads(record.read_text())['state']=='completed':continue
                raise RuntimeError(f'Failed previous job requires diagnosis: {record}')
            available=remaining_seconds(a.root)-stage.get('reserve_seconds',5400)
            if available<=0:raise TimeoutError('Preserve final reserve')
            write(a.root/'queue_status.json',dict(state='running',stage=stage['name'],pid=os.getpid(),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
            subprocess.run([sys.executable,str(ROOT/'scripts/run_effective_job.py'),'--root',str(a.root),'--name',stage['name'],'--timeout',str(min(stage['timeout'],available)),'--',*stage['command']],cwd=ROOT,check=True)
        write(a.root/'queue_status.json',dict(state='awaiting_diagnosis_and_next_revision',updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    except BaseException as exc:
        write(a.root/'queue_status.json',dict(state='needs_diagnosis',error=repr(exc),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        raise
    finally:
        for path in (a.root/'controller_sessions').glob('*.json'):
            session=json.loads(path.read_text())
            if session['state']=='active':
                elapsed=session_elapsed(session)
                session.update(state='complete',awake_elapsed_seconds=elapsed,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
                write(path,session)
        lock.unlink()


if __name__=='__main__':main()
