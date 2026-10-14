"""Run one exclusive experiment job with a sleep-excluding runtime budget."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.execution_budget import awake_seconds, remaining_seconds, free_host_memory_gib, refresh_controller
from uchuva_lsystem.segmentation_cycles import write


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--name',required=True)
    parser.add_argument('--timeout',type=float,required=True)
    parser.add_argument('--minimum-start-free-gib',type=float,default=None)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    if not command:parser.error('Command required')
    folder=args.root/'execution_jobs';folder.mkdir(exist_ok=True)
    record_path=folder/f'{args.name}.json'
    if record_path.exists():raise FileExistsError(record_path)
    allowance=min(args.timeout,remaining_seconds(args.root))
    if allowance<=0:raise TimeoutError('Effective twelve-hour budget exhausted')
    lock=args.root/'execution_job.lock'
    # Exclusive jobs avoid double-charging concurrent intervals and GPU contention.
    with lock.open('x') as stream:stream.write(str(os.getpid()))
    stop_request=args.root/'execution_stop.request'
    if stop_request.exists():stop_request.unlink()
    started=None;process=None;failure=None
    experiment=json.loads((args.root/'run.json').read_text())
    minimum_free_gib=float(experiment.get('minimum_runtime_free_memory_gib',4))
    record={'script_version':'effective-execution-budget/1.0','name':args.name,
            'seed':experiment['seed'],'parameter_preset':experiment['parameter_preset'],
            'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'command':command,'allowance_seconds':allowance,'awake_elapsed_seconds':0,
            'state':'running','pid':None,'minimum_runtime_free_memory_gib':minimum_free_gib}
    try:
        admission=float(experiment.get('minimum_start_free_memory_gib',4))
        if args.minimum_start_free_gib is not None:
            admission=max(admission,args.minimum_start_free_gib)
        waited=awake_seconds()
        while True:
            free=free_host_memory_gib()
            if free is None or free>=admission:break
            record.update(state='waiting_for_memory',free_host_gib=free,
                admission_minimum_gib=admission,inactive_wait_seconds=awake_seconds()-waited)
            write(record_path,record)
            if remaining_seconds(args.root)<=0:raise TimeoutError('Budget exhausted during inactive resource wait')
            time.sleep(2)
        started=awake_seconds()
        record.update(state='running',started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            inactive_wait_seconds=started-waited)
        with zipfile.ZipFile(folder/f'{args.name}_sources.zip','x',zipfile.ZIP_DEFLATED) as archive:
            for parent in ('src','scripts','configs'):
                for source in (ROOT/parent).rglob('*'):
                    if source.is_file() and source.suffix in ('.py','.json') and '__pycache__' not in source.parts:
                        archive.write(source,source.relative_to(ROOT))
        with (folder/f'{args.name}.log').open('w') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            record['pid']=process.pid
            while True:
                refresh_controller(args.root)
                record['awake_elapsed_seconds']=awake_seconds()-started
                free=free_host_memory_gib()
                if free is not None:
                    record['minimum_host_free_gib']=min(record.get('minimum_host_free_gib',free),free)
                    if free<minimum_free_gib and not stop_request.exists():
                        write(stop_request,{'reason':f'host_free_memory_below_{minimum_free_gib:g}_gib','free_gib':free,'minimum_free_gib':minimum_free_gib,'job':args.name})
                        record['resource_stop_awake_seconds']=record['awake_elapsed_seconds']
                write(record_path,record)
                if process.poll() is not None:break
                resource_timeout=record.get('resource_stop_awake_seconds') is not None and record['awake_elapsed_seconds']-record['resource_stop_awake_seconds']>20
                if record['awake_elapsed_seconds']>=allowance or resource_timeout:
                    failure='host_memory_limit' if resource_timeout else 'effective_job_timeout'
                    if os.name=='nt':
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],check=False,
                                       stdout=log,stderr=subprocess.STDOUT)
                    else:process.terminate()
                    process.wait(timeout=30)
                    break
                time.sleep(2)
        record['exit_code']=process.returncode
        record['state']='completed' if process.returncode==0 and failure is None else 'failed'
    except BaseException as exc:
        failure=repr(exc);record['state']='failed'
        if process and process.poll() is None:process.terminate()
        raise
    finally:
        record.update(awake_elapsed_seconds=awake_seconds()-started if started is not None else 0,failure=failure,
                      ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        write(record_path,record);lock.unlink()
    print(json.dumps(record),flush=True)
    if record['state']!='completed':raise SystemExit(1)


if __name__=='__main__':main()
