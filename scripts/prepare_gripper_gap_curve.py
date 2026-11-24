#!/usr/bin/env python3
"""Prepare original-CAD jaw gaps and a native BRep audit, without changing CAD.

User-reported openings are approximate, not calibrated measurements. Projected
gaps along grasp-frame X and full 3D BRep minimum distances are distinct.
"""
import argparse
import hashlib
import json
import itertools
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import (forward_kinematics,compose_poses,inverse_pose,
    transform_point,rotate_vector)
from analyze_cad_gripper_range import trace_four_bar,_matrix,prepare_brep_motion
from prepare_cad_robot import from_matrix


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('profile','mechanisms-report','import-report','motion-inventory','asset-root','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--reported-flexible-mm',type=float,default=6)
    parser.add_argument('--reported-rigid-mm',type=float,default=8)
    parser.add_argument('--native-intervals',type=int,default=20)
    parser.add_argument('--native-end-refinement-span',type=float,default=0,
                        help='Optional final interval length to sample more densely, radians.')
    parser.add_argument('--native-end-refinement-step',type=float,default=0,
                        help='Maximum spacing in that final interval, radians.')
    args=parser.parse_args()
    if args.native_intervals<20:raise ValueError('Native audit must retain at least 21 range samples')
    if args.output.exists():raise ValueError('Use a fresh output directory')
    robot=resolve_robot_profile(args.profile);data=robot.to_dict();report=read(args.mechanisms_report)
    parts=read(args.import_report)['parts'];inventory=read(args.motion_inventory)
    zero={j['name']:0 for j in data['joints'] if j['type']!='fixed'}
    axis=next(j['axis'] for j in data['joints'] if j['name']=='gripper_left_driver')
    points={side:next(r['points_base_m'] for r in report['topology_evidence'] if r['name']=='gripper_'+side) for side in ('left','right')}
    placements={v['name']:(link['name'],v['pose'],v['geometry']) for link in data['links'] for v in link['visuals']}
    indexes={row['occurrence_name_path'][-1]:'part_'+str(i) for i,row in enumerate(parts)
             if row['occurrence_name_path'][0]=='Gripper ensamble:1'}
    document=next(d for d in inventory['documents'] if d['source_path']=='gripper/Gripper ensamble.iam')
    occurrence=next(o for o in inventory['occurrences'] if o['root_document_id']==document['id'] and
                    o['parent_id']==document['id'] and o['name']=='Gripper y engranaje:1')
    hlink,hpose,_=placements[indexes['Gripper y engranaje:1']]
    root_from_gripper=compose_poses(compose_poses(forward_kinematics(robot,zero)[hlink],hpose),
                                    inverse_pose(from_matrix(occurrence['transform_root_m'])))
    gripper_from_root=inverse_pose(root_from_gripper)
    role_pairs={'flexible_pads':('gomas:1','gomas:2'),
                'rigid_pad_carriers':('Mordaza blanda:1','Mordaza blanda:2'),
                'cutting_blades':('Cuchilla:1','Cuchilla:2')}
    vertices={};asset_hashes={}
    for name in sum((list(pair) for pair in role_pairs.values()),[]):
        geometry=placements[indexes[name]][2];path=args.asset_root/geometry['uri']
        if sha(path)!=geometry['sha256']:raise ValueError('Visual CAD asset hash mismatch')
        vertices[name]=[tuple(float(v) for v in line.split()[1:4]) for line in path.read_text().splitlines() if line.startswith('v ')]
        asset_hashes[str(path)]=sha(path)
    def evaluate(driver):
        q=zero.copy()
        for side,sign in (('left',1),('right',-1)):
            t=trace_four_bar(points[side],axis,sign*(driver or .001),32)['records'][-1 if driver else 0]
            q['gripper_'+side+('_driver' if side=='left' else '_follower')]=sign*driver
            for suffix,field in [('short_pivot','short_rad'),('jaw_pivot','jaw_joint_rad'),('short_closure_pin','closure_pin_rad')]:
                q['gripper_'+side+'_'+suffix]=t[field]
        fk=forward_kinematics(robot,q)
        frame=next(f for f in data['frames'] if f['name']=='grasp_center')
        grasp=compose_poses(fk[frame['parent']],frame['pose']);direction=rotate_vector(grasp['quaternion_xyzw'],[1,0,0])
        gaps={}
        for role,pair in role_pairs.items():
            supports=[]
            for name in pair:
                link,local,_=placements[indexes[name]];pose=compose_poses(fk[link],local)
                values=[sum((p-c)*d for p,c,d in zip(transform_point(pose,v),grasp['xyz_m'],direction)) for v in vertices[name]]
                supports.append((min(values),max(values)))
            supports.sort(key=lambda r:sum(r))
            gaps[role]=(supports[1][0]-supports[0][1])*1000
        return {'driver_rad':driver,'joint_positions':q,'projected_gap_mm':gaps},fk
    solutions={}
    for role,target in (('flexible_pads',args.reported_flexible_mm),('rigid_pad_carriers',args.reported_rigid_mm)):
        low,high=0.,.1
        if not evaluate(low)[0]['projected_gap_mm'][role]<=target<=evaluate(high)[0]['projected_gap_mm'][role]:
            solutions[role]={'status':'TARGET_OUTSIDE_DIAGNOSTIC_INTERVAL','reported_approximate_mm':target};continue
        for _ in range(45):
            middle=(low+high)/2
            if evaluate(middle)[0]['projected_gap_mm'][role]<target:low=middle
            else:high=middle
        item,_=evaluate((low+high)/2)
        solutions[role]={'status':'IDEAL_CAD_INTERPOLATION_NOT_HARDWARE_CALIBRATION',
                         'reported_approximate_mm':target,**item}
    target=solutions['flexible_pads'].get('driver_rad')
    if target is None:raise ValueError('Reported flexible opening outside the studied CAD interval')
    requested=sorted({i*.01 for i in range(11)}|{target}|{r['driver_rad'] for r in solutions.values() if 'driver_rad' in r})
    curve=[evaluate(q)[0] for q in requested]
    # Retain the five original diagnostic pairs, adding the three functional gaps.
    pairs=[['Eslabon L:1','Eslabon L:2'],['Eslabon 1:1','Engranaje recto2:1'],
        ['Eslabon 1:2','Engranaje recto1:1'],['Gripper y engranaje:1','Eslabon L:1'],
        ['Gripper y engranaje:1','Eslabon L:2'],
        ['Gripper 1:1','Eslabon L:1'],['Gripper 1:1','Eslabon L:2'],
        *[list(p) for p in role_pairs.values()]]
    native_coordinates=sorted({target*i/args.native_intervals for i in range(args.native_intervals+1)}|{q for q in requested if q<=target+1e-12})
    span,step=args.native_end_refinement_span,args.native_end_refinement_step
    if any(not math.isfinite(x) or x<0 for x in (span,step)) or bool(span)!=bool(step):
        raise ValueError('Refinement span and step must both be finite positive values, or both zero')
    if span:
        if span>target or step>span:raise ValueError('Refinement must stay within the studied coordinate interval')
        intervals=math.ceil(span/step)
        native_coordinates=sorted(set(native_coordinates)|{target-span+span*i/intervals for i in range(intervals+1)})
    names=set(sum(pairs,[]));samples=[]
    for driver in native_coordinates:
        item,fk=evaluate(driver);transforms={}
        for name in names:
            link,visual,_=placements[indexes[name]]
            transforms[name]=_matrix(compose_poses(gripper_from_root,compose_poses(fk[link],visual)))
        samples.append({'driver_rad':driver,'occurrence_transforms_m':transforms})
    motion=prepare_brep_motion(inventory,target,args.native_intervals)
    # The same global rigid-point speed bound also covers the blades/pads
    # rigidly attached to each jaw; the cover is fixed in this assembly frame.
    documents={d['id']:d for d in inventory['documents']}
    occurrences={o['name']:o for o in inventory['occurrences'] if
                 o['root_document_id']==document['id'] and o['parent_id']==document['id']}
    relations={r['name']:r for r in document['relations']}
    for side,reference,suffix in (('left','Coincidencia:23','1'),('right','Coincidencia:22','2')):
        center=list(relations[reference]['EntityOne']['BasePoint_m']);center[1]=0
        bound=motion['four_bar_global_derivative_bounds'][side]
        for prefix in ('gomas:','Mordaza blanda:','Cuchilla:'):
            name=prefix+suffix;o=occurrences[name];bounds=documents[o['document_id']]['bounds_m']
            transform=from_matrix(o['transform_root_m'])
            radius=max(math.dist(transform_point(transform,p),center)
                       for p in itertools.product(*zip(bounds['min'],bounds['max'])))
            motion['point_speed_bounds_m_per_driver_rad'][name]=bound['crank_length_m']+bound['jaw_absolute_angular_ratio_upper']*radius
    motion['point_speed_bounds_m_per_driver_rad']['Gripper 1:1']=0
    motion['samples']=samples
    motion['sampling_interval_rad']=max(b-a for a,b in zip(native_coordinates,native_coordinates[1:]))
    motion['end_refinement']={'span_rad':span,'maximum_step_rad':step}
    motion['scope']='Original CAD; native BRep gaps on the ideal saved branch up to reported approximate flexible opening. No actuator or as-built calibration.'
    result={'schema_version':'original-cad-gripper-functional-curve/1.0','scope':__doc__,
        'profile_canonical_sha256':robot.sha256,'reported_openings_status':'approximately_reported_by_user_not_measured',
        'reported_flexible_mm':args.reported_flexible_mm,'reported_rigid_mm':args.reported_rigid_mm,
        'definitions':role_pairs,'rows':curve,'target_solutions':solutions,'root_from_gripper':root_from_gripper,
        'source_files_sha256':{str(p):sha(p) for p in (args.profile,args.mechanisms_report,args.import_report,args.motion_inventory,Path(__file__))},
        'mesh_assets_sha256':asset_hashes,'no_CAD_or_control_changes':True}
    args.output.mkdir()
    for name,value in [('ideal_curve.json',result),('motion.json',motion),('pairs.json',{'pairs':pairs})]:
        (args.output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'target_solutions':solutions,'native_samples':len(samples),'native_pairs':len(pairs)},indent=2))


if __name__=='__main__':main()
