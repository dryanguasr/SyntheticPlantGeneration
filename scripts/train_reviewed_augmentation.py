"""Use the frozen exact-step appearance trainer for the authorized115 pilot."""
import argparse,contextlib,time
from pathlib import Path
import torch
from ultralytics import YOLO
from train_appearance_arm import AppearanceTrainer
from appearance_campaign import read,write,sha,require,check_protocol,verify_sources,charged_job,process_identity
from reviewed_augmentation_pilot import generation_paused


def train(root,config):
    generation_paused();verify_sources(root);protocol=check_protocol(root)
    require(config in read(root/'plan.json')['configs'],'Config outside approved six runs')
    require(read(root/'authorization.json')['selection_reviewed'],'Missing execution authorization')
    output=root/'training'/config['name'];require(not output.exists(),'Preserve previous attempt')
    AppearanceTrainer.campaign_root=root;AppearanceTrainer.target_steps=4000
    AppearanceTrainer.control=config['real_only'];torch.set_num_threads(4)
    model=YOLO(protocol['weights']);started=time.time()
    try:
        model.train(trainer=AppearanceTrainer,data=config['dataset'],epochs=8,
            imgsz=960,batch=2,nbs=2,optimizer='AdamW',lr0=.0002,lrf=.01,warmup_epochs=0,
            hsv_h=0,hsv_s=0,hsv_v=.1,fliplr=.5,flipud=0,
            mosaic=0,mixup=0,copy_paste=0,degrees=0,perspective=0,shear=0,translate=0,scale=0,
            erasing=0,bgr=0,multi_scale=0,seed=config['seed'],device=0,workers=0,cache=False,
            amp=True,deterministic=True,patience=0,project=str(root/'training'),name=config['name'],
            exist_ok=False,plots=False,close_mosaic=0,save=True,save_period=1,val=True)
        t=model.trainer;require(t.steps==4000 and sum(t.exposure.values())==8000,'Incomplete updates/exposure')
        require(len(t.augmentation)==8000,'Missing augmentation decisions')
        write(output/'sampling_sequences.json',t.sequences)
        write(output/'augmentation_decisions.json',[t.augmentation[k] for k in sorted(t.augmentation)])
        write(output/'learning_rates.json',t.lr_history)
        write(output/'completion.json',dict(completed=True,steps=t.steps,wall_seconds=time.time()-started,
            exposure=dict(t.exposure),instance_exposure=dict(t.instance_exposure),best_validation_ap=float(t.best_fitness),
            best_sha256=sha(output/'weights/best.pt'),last_sha256=sha(output/'weights/last.pt'),config=config,
            training_source_lock_sha256=sha(root/'training_source_lock.json'),
            sequence_sha256=sha(output/'sampling_sequences.json'),augmentation_sha256=sha(output/'augmentation_decisions.json'),
            learning_rates_sha256=sha(output/'learning_rates.json')))
    except BaseException as error:
        write(output/'failure.json',dict(error=repr(error),steps=getattr(getattr(model,'trainer',None),'steps',None)))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--accounting-job');a=p.parse_args()
    if a.accounting_job:
        record=read(a.root/'execution_jobs'/(a.accounting_job+'.json'))
        require(record['state']=='active' and process_identity(record['identity']['pid'])==record['identity'],'Accounting owner not live')
    manager=contextlib.nullcontext() if a.accounting_job else charged_job(a.root,'train',read(a.config)['name'])
    with manager:train(a.root.resolve(),read(a.config))
