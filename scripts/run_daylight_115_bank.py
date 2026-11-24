"""Own one Blender at a time; stop exactly at115 audited new captures."""
from pathlib import Path
import sys,subprocess,time,shutil,ctypes,traceback
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha,awake_seconds
from uchuva_lsystem.dataset_completion import owner_alive
from appearance_campaign import GPUJobLock,process_identity
from report_dataset_completion import audit_pixels


def checked_rows(bank):
    plan=read(bank/'plan.json');allowed={r['view_id']:r for r in plan['views']};result=[]
    for p in sorted((bank/'views').glob('*/view.json')):
        r=read(p);assert r['view_id'] in allowed and r['status']=='complete'
        assert r['source_lock_sha256']==sha(bank/'source_lock.json')
        for k in ('image','mask','label'):assert sha(r[k])==r[k+'_sha256'],r[k]
        check=read(Path(r['mask_cache']['native_validation']));assert check['passed'] and check['source_lock_sha256']==sha(bank/'source_lock.json')
        audit=p.parent/'pixel_audit.json'
        if not audit.exists():write(audit,audit_pixels(r,read(bank/'assignments'/f'{r["scene_id"]}.json')))
        assert read(audit)['status']=='pass';result.append(r)
    assert len(result)<=115
    return result


def run(root,stop_after=None):
    bank=root/'bank';plan=read(bank/'plan.json')
    with GPUJobLock(bank/'controller.lock'),GPUJobLock():
        write(bank/'controller_identity.json',process_identity());ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        for job in sorted((bank/'jobs').glob('job_*')):
            if (job/'exit.json').exists() or not (job/'process.json').exists():continue
            ident=read(job/'process.json')
            while owner_alive(ident):
                write(root/'state.json',dict(stage='adopting_capture_worker',job=str(job),identity=ident));time.sleep(3)
            write(job/'exit.json',dict(recovered=True,result_exists=(job/'result.json').exists()))
        while True:
            for p,h in read(bank/'source_lock.json')['files'].items():assert sha(p)==h,p
            assert read(Path(plan['source'])/'pause_requested.json')['active']
            rows=checked_rows(bank);done={r['view_id'] for r in rows}
            write(root/'state.json',dict(stage='capturing',complete_images=len(rows),target=115,training_started=False))
            if stop_after is not None and len(rows)>=stop_after and len(rows)<115:
                write(root/'state.json',dict(stage='capture_benchmark_complete',complete_images=len(rows),target=115,training_started=False))
                return
            if len(rows)==115:
                assert len({r['image_sha256'] for r in rows})==115,'Duplicate RGB content'
                from PIL import Image
                import numpy as np
                for r in rows:
                    im=Image.open(r['image']).convert('RGB');assert im.size==(960,720)
                    a=np.asarray(im);assert float(a.mean())>4 and float(np.percentile(a,99))>20,'Technical black frame'
                from collections import Counter
                sky=Counter(r['lighting']['camera_background']['sky_type'] for r in rows)
                assert dict(sky)==plan['weather_counts']
                write(bank/'manifest.json',dict(views=rows,complete_images=115,sky_counts=dict(sky),pixel_audited=True,expanded_historical_bank=False))
                write(bank/'sealed.json',dict(complete_images=115,manifest_sha256=sha(bank/'manifest.json'),source_lock_sha256=sha(bank/'source_lock.json'),rendering_stopped=True,training_started=False))
                write(root/'state.json',dict(stage='bank_complete_pending_technical_review',complete_images=115,training_started=False,automatic_expansion=False));return
            todo=[r for r in plan['views'] if r['view_id'] not in done];sid=todo[0]['scene_id']
            native=(bank/'prepared'/sid/'native_mask_validation.json').exists()
            count=plan['max_views_per_worker'] if native else plan['first_worker_views_per_scene']
            if stop_after is not None:count=min(count,stop_after-len(rows))
            selected=[r['view_id'] for r in todo if r['scene_id']==sid][:count]
            n=max([int(p.name.split('_')[-1]) for p in (bank/'jobs').glob('job_*')],default=-1)+1
            job=bank/'jobs'/f'job_{n:03d}';job.mkdir(parents=True,exist_ok=False)
            for name in selected:
                p=bank/'views'/name
                if p.exists():
                    target=job/'incomplete_preserved'/name;target.parent.mkdir(parents=True,exist_ok=True)
                    assert p.resolve().is_relative_to(bank.resolve()) and target.resolve().is_relative_to(bank.resolve())
                    shutil.move(str(p),str(target))
            write(job/'task.json',dict(scene_id=sid,view_ids=selected))
            command=[r'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe','--background','--python-exit-code','1','--python',str(REPO/'scripts/render_daylight_115_bank.py'),'--',str(bank),str(job)]
            started=awake_seconds()
            with (job/'stdout.log').open('w',encoding='utf-8') as stdout,(job/'stderr.log').open('w',encoding='utf-8') as stderr:
                child=subprocess.Popen(command,cwd=REPO,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
                ident=process_identity(child.pid);assert ident
                owner=dict(pid=ident['pid'],creation_tick=ident['created'],command=command);write(job/'process.json',owner)
                try:
                    while child.poll() is None:
                        elapsed=max(0,awake_seconds()-started)
                        write(bank/'heartbeat.json',dict(job=str(job),identity=owner,active_seconds=elapsed,complete_images=len(rows)))
                        if elapsed>7200:
                            child.terminate();child.wait(timeout=20);raise TimeoutError('Owned capture worker timeout')
                        time.sleep(3)
                    write(job/'exit.json',dict(returncode=child.returncode,active_seconds=awake_seconds()-started))
                    if child.returncode:raise RuntimeError('Capture failed; preserve '+str(job))
                    assert read(job/'result.json')['completed']
                finally:
                    if child.poll() is None:child.terminate();child.wait(timeout=20)


if __name__=='__main__':
    root=Path(sys.argv[1]).resolve()
    try:run(root,int(sys.argv[2]) if len(sys.argv)>2 else None)
    except BaseException:
        write(root/'capture_failure.json',dict(traceback=traceback.format_exc()));raise
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
