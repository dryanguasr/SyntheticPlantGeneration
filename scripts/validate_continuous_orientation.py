"""Evaluator/controller audit of executed orientation; never perception input."""
import argparse
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.continuous_row import inward_yaw
from uchuva_gazebo.segmentation_evaluation import whole_plant_in_frame
from uchuva_lsystem.segmentation_cycles import write


def station_samples_after_startup(rows, initial_hold_seconds):
    """Use the mission's existing startup hold, retaining its violations separately."""
    end=rows[0]['t']+initial_hold_seconds
    startup=[r for r in rows if r['t']<end]
    station=[r for r in rows if r['near_station'] and r['t']>=end]
    return startup,station


def main():
    p=argparse.ArgumentParser();p.add_argument('flight',type=Path);a=p.parse_args()
    telemetry=json.loads((a.flight/'telemetry.json').read_text())['samples']
    preflight=json.loads((a.flight.parent/'preflight.json').read_text())
    mission=json.loads((a.flight.parent/'mission.json').read_text());points={w['phase']:w for w in mission['waypoints']}
    validation=json.loads((a.flight/'segmentation_validation.json').read_text());rows=[];yaw=[];times=[]
    for sample in telemetry:
        point=points[sample['phase']];x,y,z,w=sample['quaternion_xyzw'];actual=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
        position=np.asarray(sample['position']);camera=position+[.068*math.cos(actual),.068*math.sin(actual),.005]
        desired=inward_yaw(camera,point['look_at_world_m']);error=abs(math.atan2(math.sin(desired-actual),math.cos(desired-actual)))
        target=point['target_plant_id'];markers=[m for m in preflight['markers'] if m['plant_id']==target]
        complete=whole_plant_in_frame(preflight['plant_mesh_bounds_m'][target],markers,position,sample['quaternion_xyzw'],
            hull_points=preflight['plant_mesh_hulls_m'][target],margin=.05)
        rows.append(dict(t=sample['t'],phase=sample['phase'],error_deg=math.degrees(error),whole_target_with_margin=complete,
            clearance_m=sample['clearance_lower_bound_m'],near_station=bool('station' in point['phase'] and np.linalg.norm(position-point['position'])<.04)))
        yaw.append(actual);times.append(sample['t'])
    turn=[r for r in rows if r['phase'].startswith('inward_turn_')]
    startup,station=station_samples_after_startup(rows,mission.get('initial_hold_seconds',0))
    delta=np.diff(times);rates=np.diff(np.unwrap(yaw))/delta;accelerations=np.diff(rates)/delta[1:]
    checks=dict(turn_executed=bool(turn),turn_looks_inward=bool(turn) and max(r['error_deg'] for r in turn)<=20,
        turn_target_kept_with_margin=bool(turn) and all(r['whole_target_with_margin'] for r in turn),
        station_framing=bool(station) and all(r['whole_target_with_margin'] for r in station),
        clearance_ge_15cm=min(r['clearance_m'] for r in rows)>=.15)
    # Edge-on marker invisibility is reported separately from viewing direction.
    marker_rows=[r for r in validation['frames'] if r.get('phase','').startswith('inward_turn_')]
    write(a.flight/'orientation_validation.json',dict(version='executed-inward-orientation/1.1',passed=all(checks.values()),checks=checks,
        station_scope='After the predeclared initial hold; all turn samples remain evaluated',
        initial_hold_seconds=mission.get('initial_hold_seconds',0),
        startup_framing_violation_samples=[r for r in startup if not r['whole_target_with_margin']],
        startup_samples=len(startup),evaluated_station_samples=len(station),
        maximum_turn_error_deg=max((r['error_deg'] for r in turn),default=None),
        measured_yaw_rate_max_rad_s=float(max(abs(rates),default=0)),measured_yaw_acceleration_max_rad_s2=float(max(abs(accelerations),default=0)),
        turn_aruco_undecodable_frames=sum(not r.get('target_marker_decoded') for r in marker_rows),turn_captured_frames=len(marker_rows),
        frames_without_marker_are_not_automatically_orientation_failures=True,samples=rows))
    if not all(checks.values()):raise SystemExit('Executed inward turn validation failed: '+str(checks))


if __name__=='__main__':main()
