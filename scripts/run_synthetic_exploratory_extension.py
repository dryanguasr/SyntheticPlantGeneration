"""Authorized size-gate waiver, isolated from the frozen real-only campaign."""
import os
from pathlib import Path
import shutil
import sys
import time

REPO=Path(__file__).resolve().parents[1]
PARENT=REPO/'outputs/augmentation_pilot_20261022'
EXT=PARENT/'synthetic_exploratory_extension'
os.environ['UCHUVA_AUGMENTATION_ROOT']=str(EXT)

from augmentation_pilot import read,write,sha,link,make_dataset,gate
import run_augmentation_campaign as campaign


def prepare():
    EXT.mkdir(exist_ok=False)
    for name in ['protocol.json','budget.json','real_manifest.json','subsets.json','training_source_lock.json']:
        shutil.copy2(PARENT/name,EXT/name)
    (EXT/'geometry').mkdir()
    shutil.copy2(PARENT/'geometry/real_train.json',EXT/'geometry/real_train.json')
    write(EXT/'authorization.json',dict(version='synthetic-exploratory/1',created=time.time(),
        user_instruction='Prueba también la aumentación sintética con las imágenes disponibles, aunque no cumplan todos los criterios de tamaño. Compara distintas proporciones, con y sin aumentación clásica, y reporta esas limitaciones.',
        size_gate_waived=True,density_gate_waived=True,technical_integrity_still_required=True,
        parent=str(PARENT),original_budget_preserved=True,selection_uses_validation_only=True,
        protocol_note='protocol.json preserves identical optimizer and seed settings for reuse of frozen real controls; this authorization overrides geometric admission only'))
    source=read(PARENT/'synthetic/manifest.json')['rows'];by_id={r['synthetic_id']:r for r in source}
    ordered=read(PARENT/'synthetic/bank_order.json')['ids']
    ordered += sorted(set(by_id)-set(ordered))
    synthetic=[by_id[k] for k in ordered]
    assert len(synthetic)==389
    for r in synthetic:
        assert sha(r['image'])==r['image_sha256'] and sha(r['label'])==r['label_sha256']
    write(EXT/'synthetic/bank_order.json',dict(ids=ordered,source_sha256=sha(PARENT/'synthetic/manifest.json'),
        selection='Existing train-only geometry ordering followed by 12 calibration captures; all valid available images, no test-based selection'))
    real=read(EXT/'real_manifest.json')['rows'];subsets=read(EXT/'subsets.json');matrix=[]
    original={a['arm']:a for a in read(PARENT/'matrix.json')}
    for fraction in [100,50,25]:
        selected=[r for r in real if r['source_row'] in subsets[str(fraction)]]
        for ratio in [0,.25,.5,1]:
            wanted=round(len(selected)*ratio);bank=synthetic[:wanted];actual=len(bank)/len(selected)
            base=f'r{fraction}_s{int(ratio*100)}'
            diagnostic=gate(selected,bank) if ratio else dict(passed=True)
            write(EXT/'admissions'/f'{base}.json',dict(geometric_diagnostic=diagnostic,admitted=True,
                admission_reason='user_authorized_exploratory_size_mismatch' if ratio else 'real_control',
                requested=wanted,actual=len(bank),requested_ratio=ratio,actual_ratio=actual,
                capped_by_available_images=len(bank)<wanted))
            dataset=make_dataset(base,selected,bank) if ratio else Path(original[base+'_c0']['dataset'])
            for classical in [False,True]:
                matrix.append(dict(arm=base+f'_c{int(classical)}',real_fraction=fraction,synthetic_ratio=actual,
                    requested_synthetic_ratio=ratio,real_images=len(selected),synthetic_images=len(bank),
                    classical=classical,dataset=str(dataset),status='ready',geometric_admission_passed=diagnostic['passed'],
                    exploratory_waiver=bool(ratio)))
    write(EXT/'matrix.json',matrix)
    write(EXT/'state.json',dict(stage='waiting_for_parent_gpu',complete=False,pid=os.getpid(),updated=time.time()))


def main():
    if not EXT.exists():prepare()
    assert read(EXT/'authorization.json')['size_gate_waived']
    # Existing controller owns the GPU until its whole job has finished.
    while not read(PARENT/'state.json').get('complete'):
        if (PARENT/'controller_failure.json').exists():raise RuntimeError('Parent needs attention before extension')
        if time.time()>=read(EXT/'budget.json')['training_deadline']:raise TimeoutError('Original budget expired')
        time.sleep(30)
    # Completed controls are immutable evidence; copy metadata, hardlink only weights.
    inherited=[]
    for complete in sorted((PARENT/'training').glob('*/completion.json')):
        name=complete.parent.name
        if not name.startswith(('screen_','final_')):continue
        payload=read(complete)
        assert payload['steps']==(2000 if name.startswith('screen_') else 4000)
        assert sha(complete.parent/'weights/best.pt')==payload['best_sha256']
        target=EXT/'training'/name
        for source in complete.parent.rglob('*'):
            if not source.is_file():continue
            destination=target/source.relative_to(complete.parent);destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists():assert sha(source)==sha(destination)
            elif source.suffix=='.pt':link(source,destination)
            else:shutil.copy2(source,destination)
        inherited.append(dict(name=name,source=str(complete),sha256=sha(complete)))
    write(EXT/'inherited_controls.json',dict(runs=inherited,parent_test_metrics_not_read_for_selection=True))
    original_job=campaign.job
    def job(script,args,name,deadline):
        if script=='evaluate_augmentation_campaign.py':script='evaluate_synthetic_extension.py'
        return original_job(script,args,name,deadline)
    campaign.job=job
    campaign.train()


if __name__=='__main__':
    try:main()
    except Exception as error:
        write(EXT/'controller_failure.json',dict(error=repr(error),when=time.time()))
        write(EXT/'state.json',dict(stage='needs_attention',complete=False,error=repr(error),updated=time.time()))
        raise
