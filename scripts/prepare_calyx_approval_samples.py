"""Freeze a small, separate visual review; preserve every paused bank artifact."""
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src')]
from uchuva_lsystem.nodal_automation import read,write,sha


def prepare(out):
    source=REPO/'outputs/spatial_dataset_completion_20261030'
    fixture=REPO/'outputs/calyx_deterioration_pilot_20261031/revisions/phenotype_variation_02/plan.json'
    assert read(source/'pause_requested.json')['active']
    out.mkdir(parents=True,exist_ok=False)
    write(out/'plan.json',dict(version='calyx-approval-samples/1',seed=20261031,source=str(source),
        context_views=['scene_027_view_010','scene_027_view_007'],specimens=read(fixture)['specimens'],
        scope='small visual approval only; no bank extension or training',
        sampling='deliberately enriched severity examples, not fitted phenotype frequencies',
        context='surface-only; original plants, camera and masks preserved',
        shape='isolated hollow shells; berry containment and whole-plant admission not assessed',
        resorption='unverified physiological mechanism; visible contraction hypothesis only'))
    baseline={}
    for lock in (source/'source_lock.json',REPO/'outputs/reviewed_augmentation_115_20261031/training_source_lock.json'):
        files=read(lock)['files'];bad=[p for p,h in files.items() if sha(p)!=h]
        if bad:raise ValueError('Historical lock differs: '+str(bad[:3]))
        baseline[str(lock)]=dict(sha256=sha(lock),files=len(files),verified=True)
    for f in ('budget.json','pause_requested.json','dataset/pool_lock.json'):
        baseline[str(source/f)]=dict(sha256=sha(source/f))
    pool=read(source/'dataset/pool_lock.json')['plants']
    for plant in pool:
        assert sha(plant['plant'])==plant['plant_sha256']
        assert sha(plant['admission'])==plant['admission_sha256']
    write(out/'baseline.json',dict(locks=baseline,plants_verified=len(pool),bank_complete_images=503))
    files=dict(read(source/'source_lock.json')['files'])
    for name in ('src/uchuva_lsystem/calyx_darkening_review.py','src/uchuva_lsystem/blender_calyx_darkening_review.py',
        'src/uchuva_lsystem/calyx_deterioration.py','scripts/render_calyx_approval_samples.py',
        'scripts/prepare_calyx_approval_samples.py','tests/test_calyx_darkening_review.py'):
        path=REPO/name;files[str(path)]=sha(path)
    for path in (out/'plan.json',fixture,source/'dataset/scenes/scene_027/scene.blend',
        source/'dataset/scenes/scene_027/capture_plan.json',source/'dataset/scenes/scene_027/accepted.json'):
        files[str(path)]=sha(path)
    for vid in read(out/'plan.json')['context_views']:
        row=read(source/'dataset/views'/vid/'view.json')
        for path in [source/'dataset/views'/vid/'view.json']+[Path(row[k]) for k in ('image','mask','label')]:files[str(path)]=sha(path)
    write(out/'source_lock.json',dict(files=files,scope='approval render sources and immutable input artifacts'))
    print(out)


if __name__=='__main__':prepare(Path(sys.argv[1]).resolve())
