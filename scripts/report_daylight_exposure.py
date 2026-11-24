"""Reconstruct full and selected-checkpoint exposure from six closed runs.

Read-only post-hoc audit: no rendering, training, inference or selection.
"""
from pathlib import Path
import argparse
import audit_cached_synthetic_bias as audit
from appearance_campaign import read, write, sha, verify_sources
from daylight_augmentation_pilot import generation_paused, completed


def report(root):
    root=root.resolve();generation_paused(root);verify_sources(root)
    plan=read(root/'plan.json')
    assert len(plan['configs'])==6 and all(completed(root,c) for c in plan['configs'])
    inputs=audit.Inputs();inputs.digest(__file__);inputs.digest(audit.__file__)
    inputs.read(root/'plan.json');inputs.digest(root/'training_source_lock.json')
    manifest=inputs.read(root/'datasets/paired_slots115/manifest.json')
    result=audit.exposure_audit(inputs,manifest,plan,root)
    inputs.verify()
    out=root/'diagnostics/exposure';out.mkdir(parents=True,exist_ok=False)
    write(out/'exposure.json',result)
    write(out/'audit_inputs.json',dict(files=inputs.hashes,exposure_sha256=sha(out/'exposure.json'),
        no_training_or_inference=True,source_lock_sha256=sha(root/'training_source_lock.json')))
    print(out/'exposure.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    report(parser.parse_args().root)
