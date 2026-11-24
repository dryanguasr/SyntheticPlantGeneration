"""Freeze four visual samples without reopening either paused campaign."""
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.blue_sky_sample_review import sample_conditions,sparse_assignments,VERSION


def prepare(out):
    prior=REPO/'outputs/calyx_ash_drying_20261111'
    files=dict(read(prior/'source_lock.json')['files'])
    for p,h in files.items():assert sha(p)==h,p
    source=Path(read(prior/'plan.json')['source'])
    baseline=read(prior/'baseline.json')
    for p,item in baseline['locks'].items():
        assert sha(p)==item['sha256'],p
        if item.get('files'):
            for f,h in read(p)['files'].items():assert sha(f)==h,f
    assert read(source/'pause_requested.json')['active']
    out.mkdir(exist_ok=False,parents=True)
    plan=dict(version=VERSION,source=str(source),seed=20261111,
        vein_maps_manifest=read(prior/'plan.json')['vein_maps_manifest'],
        views=sample_conditions(),preview_only=True,training_started=False,
        overmature_target_fraction=.03,visible_overmature_cap=.05,
        fraction_status='engineering_heuristic_for_user_requested_small_minority; not crop prevalence',
        geometry='reuse two admitted scenes unchanged; no plants removed, regenerated, contracted or pruned',
        authorization='four small sky/light approval views with few new-texture overmature calyces; no bank expansion or pilot resume')
    for sid in sorted({v['scene_id'] for v in plan['views']}):
        folder=source/'dataset/scenes'/sid;accepted=read(folder/'accepted.json')
        assert accepted['physical_admission']
        assert read(folder/'ground.json')['status']=='valid'
        assert read(folder/'orientation.json')['status']=='valid'
        assert read(folder/'mesh.json')['physical_collision_count']==0
        views=[read(source/'dataset/views'/v['source_view']/'view.json') for v in plan['views'] if v['scene_id']==sid]
        assignments=sparse_assignments(accepted['assignments'],views,seed=plan['seed'])
        path=out/f'{sid}_assignments.json';write(path,assignments);files[str(path)]=sha(path)
        for name in ('scene.blend','accepted.json','ground.json','orientation.json','mesh.json','capture_plan.json','capture_complete.json'):
            p=folder/name;files[str(p)]=sha(p)
        for view in views:
            p=source/'dataset/views'/view['view_id']/'view.json';files[str(p)]=sha(p)
            for key in ('image','mask','label'):
                p=Path(view[key]);assert sha(p)==view[key+'_sha256'];files[str(p)]=sha(p)
    write(out/'plan.json',plan);write(out/'baseline.json',baseline)
    for p in (out/'plan.json',REPO/'src/uchuva_lsystem/blue_sky_sample_review.py',
              REPO/'scripts/prepare_blue_sky_samples.py',REPO/'scripts/render_blue_sky_samples.py',
              REPO/'tests/test_blue_sky_sample_review.py'):
        files[str(p)]=sha(p)
    write(out/'source_lock.json',dict(version=VERSION,files=files))
    print(out)


if __name__=='__main__':prepare(Path(sys.argv[1]).resolve())
