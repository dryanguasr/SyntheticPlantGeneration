"""Single owned Blender workload for the authorized eight-hour plant-only run."""
from pathlib import Path
from datetime import datetime,timezone
import ctypes
import json
import os
import subprocess
import sys
import time
import traceback
import itertools
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from uchuva_lsystem.nodal_automation import read,write,sha,remaining,active_elapsed,unique_admissions
from uchuva_lsystem.execution_budget import awake_seconds
from run_nodal_automation import identity


def verify(root):
    lock=read(root/'source_lock.json')
    for p,h in lock['sources'].items():
        if sha(ROOT/p)!=h:raise ValueError('Frozen source changed: '+p)
    for p,h in lock['inputs'].items():
        if sha(Path(p))!=h:raise ValueError('Frozen pool input changed: '+p)


def publish(root,rows,state):
    import html
    valid=unique_admissions(rows)
    write(root/'results.json',dict(rows=rows,valid_new_plants=len(valid),training_started=False,dataset_generated=False))
    cards=[]
    for r in valid:
        folder=Path(r['folder']);rel=folder.relative_to(root).as_posix();a=r.get('spatial_admission',{})
        original=r.get('original_counts',r['counts']);after=r['counts']
        fl=(original['fruits']-after['fruits'])/max(1,original['fruits']);ll=(original['leaves']-after['leaves'])/max(1,original['leaves'])
        assert fl<.05 and ll<.05
        picture=f'<img src="{rel}/preview.png">' if (folder/'preview.png').exists() else '<p>Auditorías disponibles; vista no terminada.</p>'
        cards.append(f'<article><h2>Semilla {r["seed"]}</h2>{picture}<p>{after["leaves"]}/{original["leaves"]} hojas; {after["fruits"]}/{original["fruits"]} frutos. Pérdidas: {100*ll:.2f}% / {100*fl:.2f}%.</p><p>0 cruces duros; {r["proximity_warnings"]} proximidades. <a href="{rel}/admission.json">Auditoría</a> · <a href="{rel}/plant.json">Árbol</a></p></article>')
    title='Terminada' if state.get('status')=='complete' else 'En ejecución'
    page=f'<!doctype html><html lang="es"><meta charset="utf-8"><title>Plantas válidas: ocho horas</title><style>body{{font:17px system-ui;max-width:1300px;margin:30px auto;padding:20px;background:#f5f4ef}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:20px}}article{{background:white;padding:16px;border-radius:12px}}img{{width:100%}}</style><h1>{title}: {len(valid)} plantas admitidas</h1><p>Ocho horas efectivas, sin parada en20. Menos del5% de frutos y hojas, contados por separado respecto al original. Sin dataset ni entrenamiento. Revisión visual humana pendiente.</p><p>Auditoría estática: cero cruces duros, suelo plano1mm, orientación y morfología. Hoja–hoja tolerado y proximidad como advertencia; flores/contexto no certificados exhaustivamente.</p><main>'+''.join(cards)+'</main><p><a href="results.json">Todos los intentos, incluidos rechazos</a> · <a href="budget.json">Presupuesto</a></p></html>'
    (root/'review.html').write_text(page,encoding='utf-8')


def main(root):
    budget=read(root/'budget.json');config=read(root/'config.json');verify(root)
    lock_handle=(root/'controller.lock').open('x',encoding='utf-8')
    owner=identity();write(root/'controller_identity.json',owner)
    lock_handle.write(json.dumps(owner));lock_handle.flush()
    rows=read(root/'results.json')['rows'] if (root/'results.json').exists() else []
    done={r['seed'] for r in rows};child=None
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        def tasks():
            yield from read(root/'queue.json')
            for seed in itertools.count(config['fresh_seed_fallback_start']):
                yield dict(seed=seed,origin='fresh_seed_after_ranked_queue')
        for item in tasks():
            if item['seed'] in done:continue
            if remaining(budget)<=0:break
            verify(root);seed=item['seed'];folder=root/'plants'/f'seed_{seed}'
            folder.mkdir(parents=True,exist_ok=False)
            job=dict(seed=seed,index=len(rows),folder=str(folder),run_root=str(root),
                active_deadline=awake_seconds()+min(config['candidate_seconds'],remaining(budget)))
            for key in ('raw','initial'):
                if item.get(key):job[key]=item[key];job[key+'_sha256']=sha(item[key])
            write(folder/'job.json',job)
            command=[config['blender'],'--background','--factory-startup','--python-exit-code','1',
                     '--python',str(ROOT/'scripts/worker_spatial_pool.py'),'--',str(folder/'job.json')]
            with (folder/'stdout.log').open('w',encoding='utf-8') as out,(folder/'stderr.log').open('w',encoding='utf-8') as err:
                child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                write(folder/'process.json',dict(**identity(child.pid,child._handle),command=command))
                terminated=None
                while child.poll() is None:
                    stage=read(folder/'state.json') if (folder/'state.json').exists() else {}
                    state=dict(status='running',stage='plant_generation_and_admission',current_seed=seed,
                        valid_new_plants=len(unique_admissions(rows)),attempted=len(rows)+1,worker=stage,
                        active_seconds=active_elapsed(budget),remaining_seconds=remaining(budget),
                        training_started=False,dataset_generated=False)
                    write(root/'state.json',state)
                    if remaining(budget)<=0 or awake_seconds()>job['active_deadline']+3:
                        terminated='global_active_limit' if remaining(budget)<=0 else 'candidate_active_limit'
                        child.terminate()
                        try:child.wait(timeout=10)
                        except subprocess.TimeoutExpired:child.kill();child.wait()
                        break
                    time.sleep(2)
                code=child.returncode;child=None
            if (folder/'admission.json').exists():
                row=read(folder/'admission.json')
                if row['status']=='admitted':
                    counts=row['counts'];original=row['original_counts']
                    assert row['physical_crossings']==0 and row['ground_status']=='valid' and row['orientation_status']=='valid' and not row['morphology_errors']
                    assert 20*(original['fruits']-counts['fruits'])<original['fruits']
                    assert 20*(original['leaves']-counts['leaves'])<original['leaves']
                    assert row['spatial_admission'].get('leaf_nominal_area_loss_fraction',0)<.05
            else:row=dict(seed=seed,status='not_admitted',folder=str(folder),reason=terminated or 'worker_failed',exit_code=code)
            row['origin']=item['origin'];rows.append(row);done.add(seed)
            write(folder/'parent_completion.json',dict(exit_code=code,termination=terminated))
            publish(root,rows,dict(status='running'))
            print('SPATIAL_POOL',seed,row['status'],'valid',len(unique_admissions(rows)),'active_hours',round(active_elapsed(budget)/3600,3),flush=True)
            if code and terminated is None:raise RuntimeError('Operational worker failure; inspect and preserve '+str(folder))
        verify(root)
        state=dict(status='complete',stop_reason='eight_effective_hours_elapsed' if remaining(budget)<=0 else 'finite_seed_queue_exhausted',
            valid_new_plants=len(unique_admissions(rows)),attempted=len(rows),active_seconds=active_elapsed(budget),
            remaining_seconds=remaining(budget),training_started=False,dataset_generated=False,human_visual_review='pending')
        write(root/'state.json',state);publish(root,rows,state);write(root/'closure.json',state)
    except Exception:
        if child and child.poll() is None:child.terminate();child.wait()
        failure=dict(status='needs_attention',traceback=traceback.format_exc(),identity=owner,
                     active_seconds=active_elapsed(budget),training_started=False,dataset_generated=False)
        write(root/'controller_failure.json',failure);write(root/'state.json',failure)
        raise
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        lock_handle.close();(root/'controller.lock').unlink(missing_ok=True)


if __name__=='__main__':main(Path(sys.argv[1]).resolve())
