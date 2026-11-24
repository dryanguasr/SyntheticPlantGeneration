"""Prepare an independent revision while keeping prior samples immutable."""
from pathlib import Path
import sys,copy
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src')]
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.calyx_mottling import VERSION


def prepare(out):
    previous=REPO/'outputs/calyx_approval_samples_20261031'
    for path,h in read(previous/'source_lock.json')['files'].items():
        if sha(path)!=h:raise ValueError('Prior frozen source changed: '+path)
    plan=copy.deepcopy(read(previous/'plan.json'))
    source=Path(plan['source']);assert read(source/'pause_requested.json')['active']
    plan.update(version='irregular-mottling-review/1',previous_review=str(previous),
        material_revision=VERSION,
        authorization='user requests progressive irregular stains, preserved drying/compression and no uniformly opaque black examples without dataset evidence',
        opacity_evidence='train photos show visible veins/light tissue; darkest frames confounded by shade, no reliable intrinsic total-opacity evidence',
        same_organ_progression='same surface seed across fixture stages; original geometry contraction stages unchanged',
        sources_preserved=True,training_started=False)
    out.mkdir(parents=True,exist_ok=False);write(out/'plan.json',plan)
    baseline=read(previous/'baseline.json')
    for p,record in baseline['locks'].items():
        assert sha(p)==record['sha256'],p
        if record.get('files'):
            for path,h in read(p)['files'].items():assert sha(path)==h,path
    write(out/'baseline.json',baseline)
    files=dict(read(previous/'source_lock.json')['files'])
    for f in ('src/uchuva_lsystem/calyx_mottling.py','src/uchuva_lsystem/blender_calyx_mottling.py',
        'scripts/render_calyx_mottling_review.py','scripts/report_calyx_mottling_review.py',
        'scripts/prepare_calyx_mottling_review.py','tests/test_calyx_mottling.py',
        'outputs/calyx_dark_regions_train_20261031/examples_quantified.png',
        'outputs/calyx_dark_regions_train_20261031/review_page_4.png',
        'outputs/calyx_dark_regions_train_20261031/reviewed_summary.json'):
        p=REPO/f;files[str(p)]=sha(p)
    files[str(out/'plan.json')]=sha(out/'plan.json')
    write(out/'source_lock.json',dict(files=files,previous_lock_sha256=sha(previous/'source_lock.json')))
    print(out)


if __name__=='__main__':prepare(Path(sys.argv[1]).resolve())
