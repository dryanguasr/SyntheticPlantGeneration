"""Evaluator-only subset with visibility recomputed on selected exposures."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from evaluate_integral_screening import read_selected_truth
from uchuva_lsystem.segmentation_cycles import write,sha

def main():
    root=ROOT/'outputs/integral_diagnosis_20261014'
    old=ROOT/'outputs/continuous_row_20261008'
    selection=root/'public_sequence_1hz/frames.json'
    stamps={f['stamp_ns'] for f in json.loads(selection.read_text())}
    audit=json.loads((old/'evaluator/mapping_audit.json').read_text())
    if not audit['passed']:raise ValueError('Source identity audit failed')
    objects,frames=read_selected_truth(old/'evaluator/truth.json',stamps)
    visible={str(i['code']) for f in frames.values() for i in f['instances']}
    for code,obj in objects.items():obj['ever_visible']=code in visible
    out=root/'sequence_evaluator';out.mkdir(exist_ok=False)
    write(out/'truth.json',dict(objects=objects,frames=[frames[s] for s in sorted(stamps)]))
    write(out/'mapping_audit.json',dict(**audit,subset_only=True,
        selection_sha256=sha(selection),source_audit_sha256=sha(old/'evaluator/mapping_audit.json'),
        note='Inherited source mapping audit; no new mapping inferred. Visibility recomputed on exact subset.'))
    write(out/'scope.json',dict(frames=len(frames),target_visible=sum(o['role']=='target' and o['ever_visible'] for o in objects.values()),
        role_policy='Background excluded from denominator; intrusions remain errors',
        limitation='Development 1Hz subset; unseen here does not mean fully occluded throughout original 30Hz flight'))
    print('EVALUATOR_SUBSET',len(frames),'frames',flush=True)

if __name__=='__main__':main()
