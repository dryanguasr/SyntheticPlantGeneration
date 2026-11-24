"""Freeze an automatic proposal batch for blind HUMAN segmentation review.

This is a technical input check, not visual or human approval of the masks.
No original labels, model weights, or historical budgets are modified.
"""
from pathlib import Path
from collections import Counter
import sys
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_annotation_audit.store import read,sha,atomic_json,validate_objects,AuditStore
from daylight_augmentation_pilot import generation_paused
from appearance_campaign import verify_sources


def main():
    root=REPO/'outputs/blind_segmentation_50_20261113'
    generation_paused(REPO/'outputs/daylight_augmentation_115_20261112/pilot')
    verify_sources(REPO/'outputs/daylight_augmentation_115_20261112/pilot')
    if (root/'sealed.json').exists():
        store=AuditStore(root);print('Already sealed; verified',store.progress());return
    selected=read(root/'private/selection.json')['samples'];public=read(root/'samples.json')['samples']
    assert len(selected)==len(public)==50
    assert Counter(s['stratum'] for s in selected)=={'random':30,'difficult':20}
    assert all(s['split']=='train' for s in selected)
    assert len({s['image_sha256'] for s in selected})==50
    previous=read(REPO/'outputs/blind_annotation_50_20261113/private/selection.json')['samples']
    assert not {s['source_row'] for s in selected}&{s['source_row'] for s in previous}
    for path,expected in read(root/'private/input_lock.json')['files'].items():
        assert sha(path)==expected,path
    source={s['id']:s for s in selected};counts=Counter()
    for sample in public:
        ident=sample['id'];original=source[ident]
        assert sha(root/sample['image'])==original['image_sha256']
        for kind in ('proposals','originals'):
            payload=read(root/'private'/kind/f'{ident}.json')
            clean=validate_objects(payload['objects'],sample['width'],sample['height'])
            assert all(a['bbox']==b['bbox'] for a,b in zip(clean,payload['objects']))
            counts[kind]+=len(clean)
    app_paths=[REPO/'scripts/annotation_audit_app.py',REPO/'src/uchuva_annotation_audit/store.py',
               REPO/'src/uchuva_annotation_audit/masks.py',REPO/'src/uchuva_annotation_audit/__init__.py']
    files=[root/'samples.json',root/'authorization.json',root/'segmentation_preparation.json',
           *(root/'images').glob('*.jpg'),*(root/'private').rglob('*.json')]
    atomic_json(root/'sealed.json',dict(version='blind-instance-segmentation-audit/1',
        annotation_contract='native_binary_instance_masks; boxes derived from occupied pixels',
        files={p.relative_to(root).as_posix():sha(p) for p in files},
        application_files={str(p):sha(p) for p in app_paths},images=50,
        original_instances=counts['originals'],proposed_masks=counts['proposals'],
        proposal_quality='automatic RGB GrabCut masks prompted by existing detectors; NOT visually or human validated',
        human_review_pending=True,visual_interface_check='partial demonstration inspection; stopped by user',
        original_labels_unchanged=True,no_new_training=True,no_new_plant_renders=True))
    store=AuditStore(root)
    assert store.progress()=={'total':50,'manual':0,'adjudicated':0}
    try:store.comparison(public[0]['id'])
    except PermissionError:pass
    else:raise AssertionError('Blind gate failed')
    atomic_json(root/'state.json',dict(stage='ready_for_blind_human_segmentation_audit',
        progress=store.progress(),random_images=30,difficult_images=20,
        proposed_masks=counts['proposals'],original_instances=counts['originals'],
        generation_paused=True,pilot_training_paused=True,
        human_audit_complete=False,mask_quality_validated=False,labels_changed=False,
        full_visual_interface_validation_complete=False))
    print('Ready:',store.progress(),dict(counts))


if __name__=='__main__':main()
