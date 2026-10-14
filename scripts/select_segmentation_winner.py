"""Select only on the unchanged development reference, then lock final access."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--evaluations',type=Path,nargs='+',required=True)
    a=p.parse_args();target=a.root/'winner_selection.json'
    if target.exists():raise FileExistsError(target)
    if len(a.evaluations)<3:raise ValueError('Three completed cycle evaluations required')
    rows=[]
    for index,folder in enumerate(a.evaluations,1):
        completion=json.loads((a.root/f'cycle_{index:02d}'/'completion.json').read_text())
        if not completion['complete']:raise ValueError('Incomplete cycle')
        value=json.loads((folder/'metrics.json').read_text())
        if value['scope']!='synthetic_development_not_real_transfer':raise ValueError('Only development selection allowed')
        if not value.get('fixed_reference_verified'):raise ValueError('Fixed reference required')
        if completion['model_sha256']!=value['model_sha256']:raise ValueError('Evaluation is not from the completed cycle')
        rows.append({'evaluation':str(folder),'mask_map50_95':value['mask_map50_95'],
                     'model_sha256':value['model_sha256'],'capture_sha256':value['capture_manifest_sha256'],
                     'metrics_sha256':sha(folder/'metrics.json')})
    if len({row['capture_sha256'] for row in rows})!=1:raise ValueError('Models evaluated on different captures')
    winner=max(range(len(rows)),key=lambda i:rows[i]['mask_map50_95'])
    write(target,{'script_version':'segmentation-model-selection/1.0','seed':20261002,
        'parameter_preset':'fixed_development_mask_map50_95','winner_index':winner,
        'winner':rows[winner],'candidates':rows,'tie_rule':'earliest candidate',
        'final_evaluation_used':False,'post_final_tuning_allowed':False})
    print(json.dumps({'winner_index':winner,'mask_map50_95':rows[winner]['mask_map50_95']}))


if __name__=='__main__':main()
