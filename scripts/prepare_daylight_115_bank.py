"""Freeze115 new RGB captures and unchanged original camera selection."""
from pathlib import Path
import sys,copy
from collections import Counter
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha,awake_seconds
from uchuva_lsystem.daylight_115_bank import VERSION,weather_slots,capture_condition,WEATHER_COUNTS
from uchuva_lsystem.blue_sky_sample_review import sparse_assignments


def prepare(root):
    bank=root/'bank';prior=REPO/'outputs/daylight_cast_correction_20261111'
    if bank.exists():raise ValueError('Preserve existing bank; resume its controller')
    files=dict(read(prior/'source_lock.json')['files'])
    for p,h in files.items():assert sha(p)==h,p
    for p,item in read(prior/'baseline.json')['locks'].items():
        assert sha(p)==item['sha256'],p
        if item.get('files'):
            for f,h in read(p)['files'].items():assert sha(f)==h,f
    source=Path(read(prior/'plan.json')['source']);assert read(source/'pause_requested.json')['active']
    old=REPO/'outputs/reviewed_augmentation_115_20261031/plan.json';records=read(old)['selected_records']
    assert len(records)==len(set(records))==115
    rows=[read(p) for p in records];weather=weather_slots(rows)
    assert all(r['status']=='complete' and r['view_id']!='scene_026_view_001' for r in rows)
    bank.mkdir(parents=True,exist_ok=False)
    plan=dict(version=VERSION,source=str(source),seed=20261111,capture_seed=20261112,target=115,
        original_pilot_plan=str(old),same_camera_slots_as_previous_pilot=True,
        vein_maps_manifest=read(prior/'plan.json')['vein_maps_manifest'],
        weather_counts=WEATHER_COUNTS,overmature_fraction=.03,visible_cap=.05,
        views=[dict(record=str(Path(p).resolve()),view_id=r['view_id'],scene_id=r['scene_id'],
            condition=capture_condition(r,weather[r['view_id']])) for p,r in zip(records,rows)],
        training_authorized_after_seal=True,max_views_per_worker=6,first_worker_views_per_scene=2,
        mask_policy='exact cached native geometry masks; all115 pixel-audited; fresh native check per layout',
        historical_generation_remains_paused=True,expand_beyond115=False)
    for sid in sorted({r['scene_id'] for r in rows}):
        folder=source/'dataset/scenes'/sid;a=read(folder/'accepted.json');group=[r for r in rows if r['scene_id']==sid]
        assert a['physical_admission'] and len({r['bulk_geometry_sha256'] for r in group})==1
        assert (folder/'capture_complete.json').exists()
        assign=sparse_assignments(a['assignments'],group,seed=20261111)
        path=bank/'assignments'/f'{sid}.json';write(path,assign);files[str(path)]=sha(path)
        for name in ('scene.blend','accepted.json','capture_plan.json','capture_complete.json','mesh.json','ground.json','orientation.json'):
            p=folder/name;files[str(p)]=sha(p)
    for p,r in zip(records,rows):
        for f in (Path(p),Path(r['mask']),Path(r['mask']).parent/'annotations.json',Path(r['label'])):
            files[str(f.resolve())]=sha(f)
        assert sha(r['mask'])==r['mask_sha256'] and sha(r['label'])==r['label_sha256']
    write(bank/'plan.json',plan);write(bank/'baseline.json',read(prior/'baseline.json'))
    for name in ('src/uchuva_lsystem/daylight_115_bank.py','scripts/prepare_daylight_115_bank.py',
                 'scripts/render_daylight_115_bank.py','scripts/run_daylight_115_bank.py','tests/test_daylight_115_bank.py'):
        p=REPO/name;files[str(p)]=sha(p)
    for p in (bank/'plan.json',old):files[str(p.resolve())]=sha(p)
    write(bank/'source_lock.json',dict(version=VERSION,files=files))
    write(bank/'budget.json',dict(schema='bounded115-native-active-clock/1',awake_started_seconds=awake_seconds(),
        image_limit=115,max_worker_active_seconds=7200,historical_budgets_unchanged=True))
    write(root/'authorization.json',dict(date='2026-11-12',instruction='Generate115 corrected images with few overmature calyces and varied skies; repeat synthetic+classical vs real+classical with three seeds; show results before expanding',
        capture_limit=115,training_runs=6,updates_each=4000,seeds=[20261022,20261023,20261024],
        old_generation_stays_paused=True,automatic_expansion=False,new_plants=False))
    files[str(root/'authorization.json')]=sha(root/'authorization.json')
    write(bank/'source_lock.json',dict(version=VERSION,files=files))
    write(root/'state.json',dict(stage='prepared_capture',target=115,training_started=False))
    print(root)


if __name__=='__main__':prepare(Path(sys.argv[1]).resolve())
