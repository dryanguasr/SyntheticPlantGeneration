"""Sequential owner of the five-hour/20-new-plants correction campaign."""
from pathlib import Path
import ctypes,json,os,shutil,subprocess,sys,time,traceback
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.nodal_automation import read,write,sha,remaining,active_elapsed,stop_reason,unique_admissions,candidate_seeds
from uchuva_lsystem.execution_budget import awake_seconds

def identity(pid=None,handle=None):
    result=dict(pid=os.getpid() if pid is None else pid,utc=datetime.now(timezone.utc).isoformat())
    if os.name=='nt':
        from ctypes import wintypes
        creation=ctypes.c_ulonglong();exit_time=ctypes.c_ulonglong();kernel=ctypes.c_ulonglong();user=ctypes.c_ulonglong()
        process=ctypes.windll.kernel32.GetCurrentProcess() if handle is None else handle
        if ctypes.windll.kernel32.GetProcessTimes(wintypes.HANDLE(process),ctypes.byref(creation),ctypes.byref(exit_time),ctypes.byref(kernel),ctypes.byref(user)):
            result['creation_tick']=creation.value
    return result

def verify(lock, root=None):
    for relative,digest in lock['sources'].items():
        if sha(ROOT/relative)!=digest:raise RuntimeError('Frozen source changed: '+relative)
    if root is not None:
        if lock.get('seed_queue_sha256') and sha(root/'seed_queue.json')!=lock['seed_queue_sha256']:
            raise RuntimeError('Frozen seed queue changed')
        if lock.get('continuations_sha256') and sha(root/'continuations.json')!=lock['continuations_sha256']:
            raise RuntimeError('Frozen continuation inputs changed')
        for name in ('config','profiles'):
            if sha(root/(name+'.json'))!=lock[name+'_sha256']:
                raise RuntimeError('Frozen configuration changed: '+name)

def gallery(root,rows):
    import html
    valid=unique_admissions(rows);cards=[]
    for row in valid:
        folder=Path(row['folder']);image=folder/'preview.png';relative=folder.relative_to(root).as_posix()
        counts=row['counts'];preview=f'<a href="{relative}/preview.png"><img src="{relative}/preview.png"></a>' if image.exists() else '<p>Vista no renderizada; auditorías y árbol disponibles.</p>'
        cards.append(f'<article><h2>Semilla {row["seed"]}</h2>{preview}<p>{counts["leaves"]} hojas, {counts["fruits"]} frutos: conservados. 0 cruces auditados. {row["proximity_warnings"]} advertencias de proximidad.</p><a href="{relative}/admission.json">Auditoría</a> · <a href="{relative}/plant.json">Árbol</a></article>')
    page=f'<!doctype html><html lang="es"><meta charset="utf-8"><title>Corrección nodal automatizada</title><style>body{{font:17px system-ui;max-width:1200px;margin:30px auto;padding:20px;background:#f5f4ef}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:20px}}article{{padding:18px;background:white;border-radius:12px}}img{{width:100%}}</style><h1>Corrección nodal automatizada: {len(valid)} arbustos válidos nuevos</h1><p>Sin entrenamiento. Revisión visual pendiente. Suelo diagnóstico plano, excepción hoja–hoja y advertencias de proximidad conservadas. Flores y contexto no tienen certificación exhaustiva.</p><main>'+''.join(cards)+'</main></html>'
    rejected=[]
    for row in rows:
        folder=Path(row['folder']);image=folder/'rejected_preview.png'
        if row['status']!='admitted' and image.exists():
            relative=folder.relative_to(root).as_posix()
            rejected.append(f'<article><h3>RECHAZADO: semilla {row["seed"]}</h3><img src="{relative}/rejected_preview.png"><p>{row.get("physical_crossings","?")} cruces pendientes. No es escena admitida ni dato de entrenamiento.</p></article>')
    if rejected:page+='<h2>Diagnóstico de rechazos físicos</h2><main>'+''.join(rejected)+'</main>'
    (root/'index.html').write_text(page,encoding='utf-8')
    write(root/'results.json',dict(valid_new_plants=len(valid),rows=rows,new_training_started=False))

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    root=args.root.resolve();budget=read(root/'budget.json');config=read(root/'config.json');lock=read(root/'source_lock.json')
    verify(lock,root);write(root/'controller_identity.json',identity())
    if os.name=='nt':ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    rows=read(root/'results.json')['rows'] if (root/'results.json').exists() else []
    finished={row['seed'] for row in rows};reason=None;child=None
    try:
        continuations=read(root/'continuations.json') if (root/'continuations.json').exists() else []
        def tasks():
            for entry in continuations:yield entry['seed'],entry
            preferred=read(root/'seed_queue.json') if (root/'seed_queue.json').exists() else []
            for number in candidate_seeds(preferred):yield number,None
        completed_folders={row['folder'] for row in rows}
        for seed,continuation in tasks():
            if continuation and str(root/continuation['folder']) in completed_folders:continue
            if not continuation and seed in finished:continue
            reason=stop_reason(budget,len(unique_admissions(rows)))
            if reason:break
            verify(lock,root);index=len(rows);folder=root/continuation['folder'] if continuation else root/'plants'/f'seed_{seed}';folder.mkdir(parents=True,exist_ok=False)
            case_limit=config['third_candidate_seconds'] if seed==2026102602 else config['candidate_seconds']
            job=dict(seed=seed,index=index,folder=str(folder),run_root=str(root),
                active_deadline=awake_seconds()+min(case_limit,remaining(budget)))
            if (root/'seed_queue.json').exists() and seed in read(root/'seed_queue.json'):
                job['render_rejected_preview']=True
            if continuation:
                job.update(raw=continuation['raw'],initial=continuation['initial'])
                job.update(raw_sha256=sha(job['raw']),initial_sha256=sha(job['initial']))
                job['continuation_reason']=continuation['reason']
                job['audit_only']=continuation.get('audit_only',False)
                job['render_rejected_preview']=continuation.get('render_rejected_preview',False)
                if 'render_preview' in continuation:job['render_preview']=continuation['render_preview']
            elif seed==2026102602:
                old=ROOT/'outputs/nodal_repulsion_review_20261027'
                job.update(raw=str(old/'specimens_v8/seed_2026102602/raw.json'),initial=str(old/'specimens_v8/seed_2026102602/mesh_feedback/plant.json'))
                job.update(raw_sha256=sha(job['raw']),initial_sha256=sha(job['initial']))
            write(folder/'job.json',job)
            command=[config['blender'],'--background','--factory-startup','--python-exit-code','1','--python',str(ROOT/'scripts/worker_nodal_automation.py'),'--',str(folder/'job.json')]
            with (folder/'stdout.log').open('w',encoding='utf-8') as out,(folder/'stderr.log').open('w',encoding='utf-8') as err:
                child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                write(folder/'process.json',dict(**identity(child.pid,child._handle if os.name=='nt' else None),command=command))
                terminated=None
                while child.poll() is None:
                    valid=len(unique_admissions(rows))
                    pending=read(folder/'admission.json') if (folder/'admission.json').exists() else None
                    projected=len(unique_admissions(rows+[pending])) if pending else valid
                    reason=stop_reason(budget,projected)
                    if reason or awake_seconds()>job['active_deadline']+3:
                        terminated=reason or 'candidate_active_limit_reached';child.terminate()
                        try:child.wait(timeout=10)
                        except subprocess.TimeoutExpired:child.kill();child.wait()
                        break
                    stage=read(folder/'state.json') if (folder/'state.json').exists() else {}
                    write(root/'state.json',dict(status='running',valid_new_plants=valid,attempted=len(rows)+1,
                        current_seed=seed,worker=stage,active_elapsed_seconds=active_elapsed(budget),remaining_seconds=remaining(budget),new_training_started=False))
                    time.sleep(2)
                exit_code=child.returncode;child=None
            # Admission is written only after full independent geometry/ground/orientation checks.
            admission=folder/'admission.json'
            if admission.exists():
                row=read(admission)
                if (folder/'preview.png').exists():row['preview']=str(folder/'preview.png')
            else:
                best=read(folder/'best_state.json') if (folder/'best_state.json').exists() else {}
                row=dict(status='not_admitted',seed=seed,folder=str(folder),reason=terminated or 'worker_failure',
                    best_crossings=best.get('objective',[None])[0],exit_code=exit_code)
            rows.append(row);finished.add(seed);gallery(root,rows)
            write(folder/'parent_completion.json',dict(exit_code=exit_code,termination=terminated,row_status=row['status']))
            print('AUTOMATION_PLANT',seed,row['status'],'valid',len(unique_admissions(rows)),'active_hours',round(active_elapsed(budget)/3600,3),flush=True)
            if (exit_code or (folder/'failure.json').exists()) and terminated is None and not admission.exists():
                raise RuntimeError(f'Worker {seed} failed operationally; evidence preserved in {folder}')
            if reason:break
        reason=reason or stop_reason(budget,len(unique_admissions(rows)))
        gallery(root,rows);verify(lock,root)
        write(root/'state.json',dict(status='complete',stop_reason=reason,valid_new_plants=len(unique_admissions(rows)),attempted=len(rows),
            active_elapsed_seconds=active_elapsed(budget),remaining_seconds=remaining(budget),new_training_started=False,human_visual_review='pending'))
    except Exception:
        if child and child.poll() is None:child.terminate();child.wait()
        write(root/'controller_failure.json',dict(traceback=traceback.format_exc(),identity=identity(),active_elapsed_seconds=active_elapsed(budget)))
        raise
    finally:
        if os.name=='nt':ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

if __name__=='__main__':main()
