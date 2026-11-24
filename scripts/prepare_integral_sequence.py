"""Public-only development sequence; identical exposures for two perceptions.

One-Hz screening is not the final five-Hz tracking or a reserved evaluation.
"""
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    root=ROOT/'outputs/integral_diagnosis_20261014'
    source=ROOT/'outputs/continuous_row_20261008/public'
    public=root/'public_sequence_1hz';public.mkdir(exist_ok=False)
    (public/'rgb').mkdir()
    frames=json.loads((source/'frames.json').read_text())
    selected=[];last=-10**30
    for frame in frames:
        if frame['stamp_ns']-last<999000000:continue
        selected.append(frame);last=frame['stamp_ns']
        shutil.copy2(source/'rgb'/frame['filename'],public/'rgb'/frame['filename'])
    shutil.copy2(source/'calibration.json',public/'calibration.json')
    write(public/'frames.json',selected)
    write(root/'sequence_1hz_selection.json',dict(version='development-sequence/1.0',
        frames=len(selected),source_frames_sha256=sha(source/'frames.json'),
        rule='First frame, then elapsed timestamp >= 0.999 s; no evaluator data',
        purpose='Matched perception and historical tracking screening; not final 5Hz tracking',
        seed=20261014,parameter_preset='fixed_development_1hz'))
    queue_path=root/'continuation_queue.json';queue=json.loads(queue_path.read_text())
    python=str(ROOT/'.venv-training/Scripts/python.exe')
    model=json.loads((root/'run.json').read_text())['model']
    stages=[]
    for name,layout,size in [('full_1280','full',1280),('tiles_640','tiles',640)]:
        cache=root/'sequence_perception'/name
        stages.append(dict(name='sequence_inference_'+name,timeout=14400,command=[python,
            'scripts/cache_continuous_predictions.py','--root',str(root),'--public',str(public),
            '--model',model,'--output',str(cache),'--layout',layout,'--input-size',str(size)]))
        stages.append(dict(name='sequence_track_'+name,timeout=14400,command=[python,
            'scripts/track_continuous_predictions.py','--root',str(root),'--public',str(public),
            '--cache',str(cache),'--output',str(root/'sequence_estimates'/name),
            '--protocol','historical_1hz']))
    existing={s['name'] for s in queue['stages']}
    if any(s['name'] in existing for s in stages):raise ValueError('Sequence already queued')
    queue['stages'].extend(stages)
    temporary=queue_path.with_suffix('.tmp');write(temporary,queue);temporary.replace(queue_path)
    print('SEQUENCE_QUEUED',len(selected),'frames per variant',flush=True)


if __name__=='__main__':main()
