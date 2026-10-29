"""Export an admitted morphology and its evidence as a portable Gazebo bundle."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_automation import read,sha
from uchuva_gazebo.admitted_plants import build_admitted_plant_bundle


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plant',type=Path,required=True)
    p.add_argument('--audits',type=Path,required=True,help='Folder containing admission.json and final static audits')
    p.add_argument('--metres-per-scene-unit',type=float,required=True)
    p.add_argument('--lod',type=int,choices=(0,1,2),default=1)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output already exists; preserve previous bundles')
    names=dict(admission='admission.json',mesh='final_independent_mesh.json',ground='ground.json',orientation='orientation.json')
    payload={k:read(a.audits/n) for k,n in names.items()}
    bundle=build_admitted_plant_bundle(Plant.from_dict(read(a.plant)),payload.pop('admission'),payload,
        metres_per_scene_unit=a.metres_per_scene_unit,lod=a.lod)
    bundle['source_hashes']=dict(plant=sha(a.plant),**{k:sha(a.audits/n) for k,n in names.items()})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(bundle,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(output=str(a.output.resolve()),seed=bundle['source_seed'],sha256=sha(a.output))))


if __name__=='__main__':main()
