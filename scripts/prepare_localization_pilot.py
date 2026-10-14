"""Freeze a new independent localization pilot and export a public RGB bundle."""
import argparse,datetime,json,math,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha,group_seeds
from uchuva_lsystem.execution_budget import awake_seconds


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    a.root.mkdir(parents=True,exist_ok=False)
    previous=ROOT/'outputs/segmentation_cycles_20261002'
    flight=previous/'development_flight_cycle4_close_batched/full'
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    reserved=list(range(520300,520306));assert not set(reserved)&{v for g in group_seeds().values() for v in g}
    write(a.root/'run.json',dict(version='localization-pilot/1.0',seed=520300,parameter_preset='marker_relative_calyx_3d',started_utc=now,classes=['pintona','madura','sobremadura'],final_seeds=reserved,final_selection='frozen before generation; no performance-based replacement',target_recall=.5,target_precision=.9,error_tolerance_m=.05,ground_truth_in_estimator=False,model=str(previous/'cycle_04/training/weights/best.pt'),model_sha256=sha(previous/'cycle_04/training/weights/best.pt'),previous_campaign=str(previous),development_flight=str(flight),git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()))
    write(a.root/'effective_budget.json',dict(version='effective-execution-budget/1.0',limit_seconds=43200,historical_execution_seconds=0,authorization='Independent twelve effective hours authorized 2026-10-05; no inherited wall deadline',created_utc=now))
    write(a.root/'controller_sessions/preparation.json',dict(state='active',started_utc=now,awake_started_seconds=awake_seconds(),awake_elapsed_seconds=0,pid=os.getpid(),purpose='Agent implementation and initial validation'))
    pairs=json.loads((flight/'paired/pairs.json').read_text())['pairs'];public=a.root/'public/development';(public/'rgb').mkdir(parents=True)
    frames=[]
    for pair in pairs:
        source=flight/'paired'/pair['rgb'];name=source.name
        os.link(source,public/'rgb'/name)
        frames.append(dict(stamp_ns=pair['stamp_ns'],filename=name))
    write(public/'frames.json',frames)
    focal=1280/(2*math.tan(math.pi/6))
    # Public fixture dimensions: two opposing printed squares separated by .36 m.
    # No world positions, plant morphology, masks or simulator camera poses exported.
    rig=[]
    for plant in range(6):
        rig.extend([dict(id=2*plant,canonical_id=2*plant,R_marker_from_canonical=[[1,0,0],[0,1,0],[0,0,1]],t_marker_from_canonical_m=[0,0,0]),dict(id=2*plant+1,canonical_id=2*plant,R_marker_from_canonical=[[-1,0,0],[0,1,0],[0,0,-1]],t_marker_from_canonical_m=[0,0,-.36])])
    write(public/'calibration.json',dict(version='public-marker-calibration/1.0',K=[[focal,0,640],[0,focal,360],[0,0,1]],distortion=[0,0,0,0,0],resolution=[1280,720],marker_side_m=.1,marker_dictionary='DICT_4X4_100',rig=rig,fixture_status='engineering-designed rigid pair; ideal calibration for synthetic pilot, not field measurement'))
    write(a.root/'status.json',dict(state='implementation',heartbeat_id='continuidad-del-piloto-3d-de-uchuvas',final_images_examined=False,completed_stages=['contracts_and_reserved_seeds','public_rgb_bundle'],pending=['native_anatomical_mapping_audit','baseline','tracking_revisions','new_flights','reserved_evaluation','report']))
    print(a.root)


if __name__=='__main__':main()
