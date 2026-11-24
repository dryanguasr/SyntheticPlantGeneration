"""Freeze color-balanced re-captures of the four previous approval views."""
from pathlib import Path
import sys,shutil,copy
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.daylight_balance import VERSION,balance_for_condition


def prepare(out):
    prior=REPO/'outputs/blue_sky_sparse_samples_20261111'
    files=dict(read(prior/'source_lock.json')['files'])
    for p,h in files.items():assert sha(p)==h,p
    baseline=read(prior/'baseline.json')
    for p,item in baseline['locks'].items():
        assert sha(p)==item['sha256'],p
        if item.get('files'):
            for f,h in read(p)['files'].items():assert sha(f)==h,f
    assert not (out/'plan.json').exists()
    assert read(Path(read(prior/'plan.json')['source'])/'pause_requested.json')['active']
    plan=copy.deepcopy(read(prior/'plan.json'))
    plan.update(version=VERSION,comparison_review=str(prior),
        authorization='correct blue cast of overmature calyces and ground; preserve plants/skies/lighting variation; comparable previews only; bank and pilot paused',
        balance_plans={v['source_view']:balance_for_condition(v['condition']).to_dict() for v in plan['views']})
    for sid in sorted({v['scene_id'] for v in plan['views']}):
        src=prior/f'{sid}_assignments.json';dst=out/src.name;shutil.copy2(src,dst);files[str(dst)]=sha(dst)
    for v in plan['views']:
        folder=prior/v['source_view'];r=read(folder/'view.json')
        for p in (folder/'view.json',Path(r['image']),Path(r['mask']),Path(r['label'])):
            files[str(p)]=sha(p)
    write(out/'plan.json',plan);write(out/'baseline.json',baseline)
    for name in ('src/uchuva_lsystem/daylight_balance.py','src/uchuva_lsystem/blender_daylight_balance.py',
                 'scripts/prepare_daylight_balanced_samples.py','scripts/render_daylight_balanced_samples.py',
                 'tests/test_daylight_balance.py'):
        p=REPO/name;files[str(p)]=sha(p)
    files[str(out/'plan.json')]=sha(out/'plan.json')
    write(out/'source_lock.json',dict(version=VERSION,files=files))
    print(out)


if __name__=='__main__':prepare(Path(sys.argv[1]).resolve())
