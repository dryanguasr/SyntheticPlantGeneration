"""A cycle is complete only when dataset, training and both flight evaluations exist."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--iteration',type=int,required=True);p.add_argument('--flight',type=Path,required=True)
    a=p.parse_args();cycle=a.root/f'cycle_{a.iteration:02d}';out=cycle/'completion.json'
    if out.exists():raise FileExistsError(out)
    def read(path):return json.loads(path.read_text())
    budget=read(a.root/'common_dataset_budget.json')
    dataset=read(cycle/'dataset/dataset_contract.json');manifest=read(cycle/'dataset/raster_manifest.json')
    training=read(cycle/'training/experiment.json')
    flight=read(a.flight/'result.json');validation=read(a.flight/'segmentation_validation.json')
    current=read(cycle/'evaluation_current/metrics.json');reference=read(cycle/'evaluation_reference/metrics.json')
    model=cycle/'training/weights/best.pt';model_hash=sha(model)
    if not dataset['training_eligible'] or len(manifest['images'])!=budget['images_per_cycle']:
        raise ValueError('Dataset gate failed')
    if training['technical_only'] or training['initialization_sha256']!=sha(a.root/'yolo26n-seg.pt'):
        raise ValueError('Fresh general initialization required')
    optimization=read(a.root/'common_optimization_budget.json')
    if training['epochs_completed']!=optimization['epochs'] or training['epochs_requested']!=optimization['epochs']:
        raise ValueError('Common optimization budget was not completed')
    if not flight['completed'] or not validation['passed']:raise ValueError('Flight gate failed')
    if not reference['fixed_reference_verified']:raise ValueError('Common reference gate failed')
    if any(v['model_sha256']!=model_hash for v in (current,reference)):raise ValueError('Wrong evaluated checkpoint')
    if current['capture_manifest_sha256']!=sha(a.flight/'paired/pairs.json'):raise ValueError('Wrong current flight capture')
    if a.iteration>1:
        previous=read(cycle/'evaluation_previous_current/metrics.json')
        previous_model=a.root/f'cycle_{a.iteration-1:02d}'/'training/weights/best.pt'
        if previous['model_sha256']!=sha(previous_model) or previous['capture_manifest_sha256']!=current['capture_manifest_sha256']:
            raise ValueError('Previous-model/current-flight cross evaluation missing')
    if not (cycle/'error_diagnosis.json').exists():raise ValueError('Prioritized diagnosis required')
    write(out,{'script_version':'segmentation-cycle-completion/1.0','seed':20261002,
        'parameter_preset':'four_consecutive_stages','iteration':a.iteration,'complete':True,
        'model_sha256':model_hash,'dataset_sha256':sha(cycle/'dataset/raster_manifest.json'),
        'flight':str(a.flight.resolve()),'fixed_reference_mask_map50_95':reference['mask_map50_95'],
        'fixed_reference_capture_sha256':reference['capture_manifest_sha256'],
        'scope':'synthetic_Gazebo_only; no demonstrated real-crop transfer'})
    print(json.dumps({'complete':True,'iteration':a.iteration}))


if __name__=='__main__':main()
