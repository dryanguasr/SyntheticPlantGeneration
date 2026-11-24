"""Seal read-only review artifacts without changing frozen campaign inputs."""
from pathlib import Path
import sys, json, hashlib, shutil
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from appearance_campaign import verify_sources
from daylight_augmentation_pilot import generation_paused


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    root=REPO/'outputs/sobremadura_four_models_20261113'
    current=REPO/'outputs/daylight_augmentation_115_20261112/pilot'
    generation_paused(current)
    training_lock=verify_sources(current)
    checked={}
    for name in ('input_lock.json','diagnosis_inputs.json'):
        lock=json.loads((root/name).read_text(encoding='utf-8'))
        for path,expected in lock['files'].items():
            actual=digest(path)
            if actual!=expected:raise ValueError(f'Frozen review input changed: {path}')
            checked[path]=actual
    before=REPO/'outputs/daylight_augmentation_115_20261112/graph_before_gallery_20261113.txt'
    shutil.copy2(before,root/'graph_before.txt')
    def lines(path):
        raw=path.read_bytes()
        return [line for line in raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-8-sig').splitlines() if line]
    errors_before,errors_after=lines(before),lines(root/'graph_after.txt')
    if len(errors_before)!=10 or errors_before!=errors_after:raise ValueError('Unexpected context graph regression')
    runtime=json.loads((root/'runtime_checks.json').read_text())
    if not runtime['passed'] or len(runtime['behaviors'])!=12:raise ValueError('Runtime contracts failed')
    panels=json.loads((root/'static_panels.json').read_text())
    for panel in panels['panels']:
        if digest(panel['path'])!=panel['sha256']:raise ValueError('Review panel changed')
    state=dict(status='review_complete_awaiting_user_correction_decision',generation_paused=True,
               real_photos=94,photos_labelled_sobremadura=28,labelled_sobremadura_instances=58,
               model_families=4,seeds=3,controlled_four_arm_ablation=False,
               historical_model_families=['none','synthetic'],current_paired_families=['classical','hybrid'],
               new_training=False,new_inference=False,new_plant_renders=False,source_labels_edited=False,
               browser_visual_verified=False,static_panels_reviewed=3,
               training_files_verified=len(training_lock['files']),review_inputs_verified=len(checked),
               python_unit_checks=4,node_contract_checks=12,graph_preexisting_errors=10,graph_new_errors=0)
    (root/'state.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    artifacts={str(p):digest(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json'}
    for p in [REPO/'scripts/render_four_model_review_panels.py',REPO/'scripts/verify_four_model_review_delivery.py',
              REPO/'tests/test_four_model_gallery.py',REPO/'scripts/test_sobremadura_gallery_runtime.cjs',
              REPO/'docs/reports/diagnostico_sobremadura_y_galeria_2026-11-13.md',
              REPO/'docs/repository_context_graph.json',REPO/'docs/plan_auditoria_cientifica_blender_2026-09-08.md']:
        artifacts[str(p)]=digest(p)
    manifest=dict(state=state,verified_input_hashes=checked,artifacts=artifacts)
    (root/'delivery_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(state,indent=2))


if __name__=='__main__':main()
