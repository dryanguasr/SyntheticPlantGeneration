"""Finish the authorized V184 comparison and conditional V185 close-patch pilot.

Serial guarded jobs only. Existing outputs are not overwritten or silently retried.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone


def write(path,data):
    path.write_text(json.dumps(data,indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    root=a.root.resolve();out=root/'field_training_v184';status=out/'continuation.json'
    def state(stage,**extra):
        write(status,dict(stage=stage,updated_utc=datetime.now(timezone.utc).isoformat(),**extra))
    def job(name,command,timeout=7200):
        state(name,command=command)
        subprocess.run([sys.executable,'scripts/run_effective_job.py','--root',str(root),'--name',name,
                        '--timeout',str(timeout),'--minimum-start-free-gib','6.5','--',sys.executable,*command],check=True)
    try:
        state('waiting_for_existing_full_pilot_v184')
        while True:
            record=json.loads((root/'execution_jobs/full_pilot_v184.json').read_text())
            if record['state']=='completed':break
            if record['state']=='failed':raise RuntimeError('Full pilot failed; inspect guard log before retry')
            time.sleep(10)
        experiment=json.loads((out/'training/experiment.json').read_text())
        updates=[json.loads(line) for line in (out/'training/parameter_updates.jsonl').read_text().splitlines()]
        assert len(updates)==12 and experiment['epochs_completed']==12
        assert experiment['optimizer_steps_executed']>300
        assert all(u['epoch_optimizer_steps']>0 and u['changed_parameter_tensors']>0 for u in updates)
        write(out/'update_verification.json',dict(experiment=experiment,epochs=updates,in_memory_change_verified=True))
        job('native_comparison_v184',['scripts/evaluate_field_pilot.py','--root',str(root),'--version','184'])
        wide=json.loads((out/'evaluation.json').read_text())
        validation=wide['results']['new_v184']['splits']['val']['total']
        poor=validation['precision']<.5 or validation['recall']<.5
        write(out/'closeup_decision.json',dict(validation=validation,criterion='P < .50 OR R < .50',
              engineering_heuristic=True,triggered=poor,test_used_for_decision=False))
        if poor:
            close=root/'field_closeup_v185';audit=json.loads((close/'input_audit.json').read_text())
            assert audit['pixel_and_mask_roundtrip_exact']
            epochs=max(2,math.ceil(384/audit['images']['train']))
            protocol=dict(version='185',source_dataset='field_pilot_v181/dataset',epochs=epochs,
                requested_batches=epochs*audit['images']['train'],initialization='field_training_v184/training/weights/last.pt',
                nbs=1,batch=1,warmup=0,image_size=960,mask_ratio=2,crop_size=384,stride=256,
                confidence=.25,mask_iou=.5,checkpoint='last',roi='RGB HSV heuristic; not trained shrub detector',
                deduplication='class-agnostic confidence order; mask IoU>.45 or intersection/min_area>.75',
                native_resolution=[1280,720],new_optical_detail=False,geometry_changes=False,
                test_use='report only, no threshold/epoch selection',reserved_seeds_used=False)
            write(close/'protocol.json',protocol)
            job('close_patch_training_v185',['scripts/train_raster_segmentation.py','--root',str(root),
                '--dataset',str(close/'dataset'),'--output',str(close/'training'),'--epochs',str(epochs),
                '--size','960','--batch','1','--technical','--mask-ratio','2','--supervision-policy','any_coverage',
                '--weights',str(out/'training/weights/last.pt'),'--nominal-batch-size','1','--warmup-epochs','0'])
            close_exp=json.loads((close/'training/experiment.json').read_text())
            close_updates=[json.loads(line) for line in (close/'training/parameter_updates.jsonl').read_text().splitlines()]
            assert close_exp['optimizer_steps_executed']>.8*protocol['requested_batches']
            assert all(u['changed_parameter_tensors']>0 for u in close_updates)
            write(close/'update_verification.json',dict(experiment=close_exp,epochs=close_updates,in_memory_change_verified=True))
            job('native_roi_comparison_v185',['scripts/field_roi_patch_pilot.py','--root',str(root),'evaluate'])
        # All source RGB and native masks must remain byte-identical after the jobs.
        data=root/'field_pilot_v181/dataset';checked=[]
        for row in json.loads((data/'raster_manifest.json').read_text())['images']:
            for key,hash_key in [('image','rgb_sha256'),('mask','raster_sha256')]:
                digest=hashlib.sha256((data/row[key]).read_bytes()).hexdigest()
                assert digest==row[hash_key]
                checked.append(dict(path=row[key],sha256=digest))
        write(out/'source_integrity.json',dict(files=checked,unchanged=True))
        summary=dict(wide={k:v['splits'] for k,v in wide['results'].items()},closeup_triggered=poor,
                     source_files_unchanged=len(checked),campaign_complete=False)
        if poor:summary['roi_close']=json.loads((root/'field_closeup_v185/evaluation.json').read_text())['splits']
        write(out/'summary.json',summary)
        continuity=root/'overnight_refinement.json';d=json.loads(continuity.read_text())
        d['state']='v184_comparison_and_conditional_v185_complete'
        d['technical_transition']='field_training_v184/summary.json'
        d['last_verified_trial']=summary
        d['active_next_trial']='Review native-mask full-view comparison and ROI patch results before promoting any model. Full campaign remains pending; no shrub geometry changes.'
        write(continuity,d)
        state('completed',summary=str(out/'summary.json'))
    except BaseException as error:
        state('failed',error=repr(error))
        raise


if __name__=='__main__':main()
