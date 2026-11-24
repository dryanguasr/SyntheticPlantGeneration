#!/usr/bin/env python3
"""Bounded physical commissioning of one frozen CAD diagnostic robot profile.

No harvest, state teleportation, geometry substitution or nominal-model claim.
The protocol is written before native launch; insufficient effort/contact
response remains a failed diagnostic, not a reason to change its thresholds.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
from uchuva_gazebo.robot_spec import load_robot_json, resolve_robot_profile, verify_robot_assets
from uchuva_gazebo.robot_sdf import resolved_robot_model, resolved_robot_contract
from uchuva_gazebo.robot_kinematics import forward_kinematics, collision_shapes, rotate_vector, compose_poses
from uchuva_gazebo.robot_validation import evaluate_robot_telemetry
from uchuva_gazebo.robot_control_validation import evaluate_position_force_control, evaluate_base_drive_control
from uchuva_gazebo.robot_drive_control import DriveReferenceController
from uchuva_gazebo.robot_mesh_geometry import MeshRepository
from uchuva_gazebo.robot_mechanism_validation import audit_mechanism_sample, audit_passive_gear_commands
from uchuva_gazebo.harvest_validation import yaw_of, angle_error


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def node(parent, tag, value=None, **attributes):
    child=ET.SubElement(parent,tag,attributes)
    if value is not None:
        child.text=str(value)
    return child


def protocol(start_height, max_step_size=.001, experiment='full'):
    config={'schema_version':'cad-mobility-protocol/1.0', 'scope':'Reduced diagnostic CAD only; suspension/gripper frozen and mounting provisional',
        'native_harvest_eligible':False,'pose_commands_used':False,'dt_s':max_step_size,'duration_s':15,
        'observation_tail_s':max_step_size,
        'observation_tail_reason':'One additional physics step supplies the exact-time native response for the final PoseV sample; phase duration and acceptance remain unchanged.',
        'start_xyzyaw':[0,0,start_height,0],
        'ground_contact':{'mu':.6,'mu2':.6,'status':'engineering_heuristic_diagnostic_environment'},
        'phases':[{'name':'settle','start_s':0,'end_s':2,'linear_m_s':0,'angular_rad_s':0},
                  {'name':'static','start_s':2,'end_s':4,'linear_m_s':0,'angular_rad_s':0},
                  {'name':'straight','start_s':4,'end_s':8,'linear_m_s':.05,'angular_rad_s':0},
                  {'name':'stop_after_straight','start_s':8,'end_s':10,'linear_m_s':0,'angular_rad_s':0},
                  {'name':'turn','start_s':10,'end_s':13,'linear_m_s':0,'angular_rad_s':.2},
                  {'name':'stop_after_turn','start_s':13,'end_s':15,'linear_m_s':0,'angular_rad_s':0}],
        'acceptance':{'max_telemetry_gap_s':.05,'joint_position_tolerance_rad':.01,
            'joint_velocity_tolerance_rad_s':.03,'effort_tolerance_nm':1e-6,'orientation_state_max_age_s':.025},
        'criteria':{'minimum_observed_span_s':14.8,'maximum_tilt_rad':.25,'maximum_static_xy_drift_m':.015,
            'maximum_static_arm_error_rad':.035,'minimum_straight_forward_m':.10,
            'maximum_straight_lateral_m':.05,'maximum_straight_yaw_rad':.15,'minimum_turn_angle_rad':.25,
            'maximum_stopped_linear_speed_m_s':.01,'maximum_stopped_angular_speed_rad_s':.03,
            'maximum_ground_penetration_m':.004,'stop_tail_s':.5},
        'criteria_status':'engineering_heuristic_preregistered_before_native_run_not_measured_hardware_accuracy'}
    if experiment=='turn_only':
        config['experiment']='turn_only'
        config['scope']='Isolated turn hypothesis on the complete unchanged CAD; never substitutes the full15s mobility admission'
        config['duration_s']=6
        config['phases']=[{'name':'settle','start_s':0,'end_s':.5,'linear_m_s':0,'angular_rad_s':0},
            {'name':'static','start_s':.5,'end_s':1.5,'linear_m_s':0,'angular_rad_s':0},
            {'name':'turn','start_s':1.5,'end_s':4.5,'linear_m_s':0,'angular_rad_s':.2},
            {'name':'stop_after_turn','start_s':4.5,'end_s':6,'linear_m_s':0,'angular_rad_s':0}]
        config['criteria']['minimum_observed_span_s']=5.8
        config['schedule_revision']='Only schedule/coverage duration changed for isolation; the turn lasts3s and all physical thresholds stay identical. Full15s test still required.'
    elif experiment!='full':raise ValueError('Unknown commissioning experiment')
    return config


def phase_at(config, stamp):
    return next((p for p in config['phases'] if p['start_s']<=stamp<p['end_s']),config['phases'][-1])


def world(robot, config):
    sdf=ET.Element('sdf',version='1.10')
    world_=node(sdf,'world',name='cad_mobility_probe')
    node(world_,'gravity','0 0 -9.81')
    physics=node(world_,'physics',name='step',type='ignored')
    node(physics,'max_step_size',config['dt_s'])
    node(physics,'real_time_factor',1)
    solver=config.get('physics',{}).get('solver_type')
    if solver is not None or config.get('physics'):
        dart=node(physics,'dart')
        if solver is not None:node(node(dart,'solver'),'solver_type',solver)
        node(dart,'collision_detector',config.get('physics',{}).get('collision_detector','ode'))
    node(world_,'plugin',filename='gz-sim-physics-system',name='gz::sim::systems::Physics')
    ground=node(world_,'model',name='ground')
    node(ground,'static','true')
    link=node(ground,'link',name='ground')
    collider=node(link,'collision',name='floor')
    node(collider,'pose','0 0 -.05 0 0 0')
    node(node(node(collider,'geometry'),'box'),'size','10 10 .1')
    surface=node(collider,'surface')
    ode=node(node(surface,'friction'),'ode')
    for key in ('mu','mu2'):
        node(ode,key,config['ground_contact'][key])
    contact=node(surface,'contact')
    node(contact,'collide_bitmask',65535)
    model=resolved_robot_model(robot,config['start_xyzyaw'])
    publisher=node(model,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
    for key,value in (('publish_link_pose','false'),('publish_model_pose','true'),('publish_nested_model_pose','false'),
        ('publish_visual_pose','false'),('publish_collision_pose','false'),('use_pose_vector_msg','true'),
        ('update_frequency',100),('topic','/probe/cad_model_pose')):
        node(publisher,key,value)
    world_.append(model)
    ET.indent(sdf,space='  ')
    return ET.tostring(sdf,encoding='unicode')+'\n'


def evaluate(robot, config, poses, joints, errors, native_code, *, link_poses=(), mesh_repository=None, force_control=(), commands=()):
    limits=config['criteria']
    checks=[{'name':'native_exit_and_callbacks','passed':native_code==0 and not errors,'errors':errors}]
    if len(poses)<2 or len(joints)<2:
        return {'status':'FAIL','checks':checks+[{'name':'observation_available','passed':False}]}
    observations=[{'sim_time':p['sim_time'],'ready':True} for p in poses]
    manifest={'robot_config':robot.to_dict(),'robot_spec_sha256':robot.sha256,
              'robot_task':{'acceptance':config['acceptance']},'mission':{'targets':[]}}
    try:
        checks+=evaluate_robot_telemetry(manifest,joints,observations,[])
        checks+=evaluate_position_force_control(manifest,force_control,joints,observations)
        checks+=evaluate_base_drive_control(manifest,commands,poses)
    except (KeyError,TypeError,ValueError) as error:
        checks.append({'name':'robot_observation_audit','passed':False,'error':str(error)})
    def check(name,passed,**metrics):
        checks.append({'name':name,'passed':bool(passed),**metrics})
    check('complete_protocol_observed',poses[-1]['sim_time']-poses[0]['sim_time']>=limits['minimum_observed_span_s'])
    if robot.data.get('closures') or robot.data.get('gear_couplings'):
        # Both v7+ RobotTelemetry response and PosePublisher use PostUpdate
        # simTime. A pre-step stamp joins a different physical iteration.
        # Historical 100 Hz publication phases can be offset: reject missing
        # exact response times, never substitute a nearby sample.
        by_time={round(row['measured_after_step_time'],9):row for row in joints}
        mechanism_errors=[];mechanism_count=0;closure_maxima={};gear_maxima={}
        for row in link_poses:
            joint=by_time.get(round(row['sim_time'],9))
            if joint is None:
                mechanism_errors.append({'sim_time':row['sim_time'],'error':'Missing exact-time native joint observation'})
                continue
            actual={j['name']:j['position'] for j in joint['joints'] if j['position_available']}
            try:
                audited=audit_mechanism_sample(robot,actual,row['links'])
                mechanism_count+=1
                for closure in audited['closures']:
                    maxima=closure_maxima.setdefault(closure['name'],{'position_error_m':0.,'orientation_error_rad':0.})
                    for key in maxima:maxima[key]=max(maxima[key],closure[key])
                for gear in audited['gears']:
                    gear_maxima[gear['name']]=max(gear_maxima.get(gear['name'],0.),abs(gear['coordinate_error_rad']))
                if not audited['passed']:
                    mechanism_errors.append({'sim_time':row['sim_time'],'errors':audited['failures']})
            except (KeyError,ValueError) as error:
                mechanism_errors.append({'sim_time':row['sim_time'],'error':str(error)})
        passive_errors=[]
        for row in joints:
            audited=audit_passive_gear_commands(robot,row)
            if not audited['passed']:passive_errors.append({'sim_time':row['sim_time'],'errors':audited['failures']})
        mechanism_gap=max((b['sim_time']-a['sim_time'] for a,b in zip(link_poses,link_poses[1:])),default=math.inf)
        mechanism_span=link_poses[-1]['sim_time']-link_poses[0]['sim_time'] if link_poses else 0.
        check('native_mechanism_constraints_observed',mechanism_count>=2 and not mechanism_errors and
              mechanism_gap<=config['acceptance']['max_telemetry_gap_s'] and mechanism_span>=limits['minimum_observed_span_s'],
              synchronized_samples=mechanism_count,observation_status='OBSERVED' if not mechanism_errors else 'NO_OBSERVADO',
              timestamp_contract='PoseV stamp == measured_after_step_time',maximum_sample_gap_s=mechanism_gap if math.isfinite(mechanism_gap) else None,
              observed_span_s=mechanism_span,closure_maxima=closure_maxima,maximum_gear_error_rad=gear_maxima,errors=mechanism_errors)
        check('gear_follower_has_no_motor_command',not passive_errors,errors=passive_errors)
    tilts=[math.acos(max(-1,min(1,rotate_vector(p['pose'][3:],[0,0,1])[2]))) for p in poses]
    check('base_not_tipped',max(tilts)<=limits['maximum_tilt_rad'],maximum_tilt_rad=max(tilts))
    static_phase=next(p for p in config['phases'] if p['name']=='static')
    static=[p for p in poses if static_phase['start_s']<=p['sim_time']<=static_phase['end_s']]
    drift=max((math.hypot(p['pose'][0],p['pose'][1]) for p in static),default=math.inf)
    check('static_base_stays_in_place',drift<=limits['maximum_static_xy_drift_m'],maximum_xy_drift_m=drift if math.isfinite(drift) else None)
    home=robot.data['arm_home_positions']
    arm_error=max((abs(j['position']-home[j['name']]) for row in joints if static_phase['start_s']<=row['sim_time']<=static_phase['end_s'] for j in row['joints'] if j['name'] in home and j['position_available']),default=math.inf)
    check('static_arm_holds_declared_posture',arm_error<=limits['maximum_static_arm_error_rad'],maximum_error_rad=arm_error if math.isfinite(arm_error) else None)
    for phase in ('straight','turn'):
        if not any(p['name']==phase for p in config['phases']):continue
        rows=[p for p in poses if p['phase']==phase]
        if len(rows)<2:
            check(phase+'_response',False)
            continue
        start,end=rows[0]['pose'],rows[-1]['pose']
        dyaw=angle_error(yaw_of(end),yaw_of(start))
        if phase=='straight':
            yaw=yaw_of(start)
            dx,dy=end[0]-start[0],end[1]-start[1]
            forward=math.cos(yaw)*dx+math.sin(yaw)*dy
            lateral=-math.sin(yaw)*dx+math.cos(yaw)*dy
            check('straight_response',forward>=limits['minimum_straight_forward_m'] and abs(lateral)<=limits['maximum_straight_lateral_m'] and abs(dyaw)<=limits['maximum_straight_yaw_rad'],
                  forward_m=forward,lateral_m=lateral,yaw_change_rad=dyaw)
        else:
            check('turn_response',dyaw>=limits['minimum_turn_angle_rad'],yaw_change_rad=dyaw)
    for phase in ('stop_after_straight','stop_after_turn'):
        if not any(p['name']==phase for p in config['phases']):continue
        entry=next(p for p in config['phases'] if p['name']==phase)
        rows=[p for p in poses if entry['end_s']-limits['stop_tail_s']<=p['sim_time']<=entry['end_s']]
        speeds=[]
        for a,b in zip(rows,rows[1:]):
            dt=b['sim_time']-a['sim_time']
            if dt<=0:
                errors.append('non-increasing pose timestamp')
                continue
            speeds.append((math.dist(a['pose'][:3],b['pose'][:3])/dt,abs(angle_error(yaw_of(b['pose']),yaw_of(a['pose'])))/dt))
        linear=max((s[0] for s in speeds),default=math.inf)
        angular=max((s[1] for s in speeds),default=math.inf)
        check(phase+'_settled',linear<=limits['maximum_stopped_linear_speed_m_s'] and angular<=limits['maximum_stopped_angular_speed_rad_s'],
              maximum_speed_m_s=linear if math.isfinite(linear) else None,maximum_yaw_rate_rad_s=angular if math.isfinite(angular) else None)
    # Ground gap uses the actual per-part geometry and every observed joint,
    # with full base tilt, never the historical proxy dimensions.
    minimum_gap, limiting=math.inf,None
    native_links_by_time={round(row['sim_time'],9):row['links'] for row in link_poses}
    ji=0
    for pose in poses:
        while ji+1<len(joints) and joints[ji+1]['sim_time']<=pose['sim_time']:
            ji+=1
        row=joints[ji]
        if abs(row['sim_time']-pose['sim_time'])>config['acceptance']['max_telemetry_gap_s']:
            continue
        actual={j['name']:j['position'] for j in row['joints'] if j['position_available']}
        if not set(robot.joint_names)<=set(actual):
            continue
        try:
            frames=forward_kinematics(robot,actual,pose['pose'],check_limits=False)
            if link_poses:
                native_links=native_links_by_time.get(round(pose['sim_time'],9))
                if native_links is None:
                    raise ValueError('Ground audit lacks exact-time native link poses')
                base_pose={'xyz_m':pose['pose'][:3],'quaternion_xyzw':pose['pose'][3:]}
                frames={name:compose_poses(base_pose,value) for name,value in native_links.items()}
            # Primitive support establishes a finite exact bound first. A mesh
            # can be skipped only if its enclosing box cannot lower the global
            # minimum; limiting meshes still use exact tessellation vertices.
            for shape in sorted(collision_shapes(robot,frames),key=lambda s:s['geometry']['type']=='mesh'):
                g=shape['geometry']; q=shape['pose']['quaternion_xyzw']
                if g['type']=='mesh':
                    if mesh_repository is None:raise ValueError('Mesh ground audit requires verified shared collision assets')
                    if mesh_repository.conservative_world_bounds(shape)[0][2]>=minimum_gap:continue
                    gap=mesh_repository.world_bounds(shape)[0][2]
                    if gap<minimum_gap:minimum_gap,limiting=gap,shape['link']+'/'+shape['name']
                    continue
                if g['type']=='sphere':
                    height=g['radius_m']
                elif g['type']=='cylinder':
                    axial=abs(rotate_vector(q,[0,0,1])[2])
                    height=g['radius_m']*math.sqrt(max(0,1-axial*axial))+g['length_m']*axial/2
                else:
                    height=sum(abs(rotate_vector(q,[int(i==j) for i in range(3)])[2])*g['size_m'][j]/2 for j in range(3))
                gap=shape['pose']['xyz_m'][2]-height
                if gap<minimum_gap:
                    minimum_gap,limiting=gap,shape['link']+'/'+shape['name']
        except (KeyError,ValueError) as error:
            errors.append(str(error))
            break
    check('ground_penetration_bounded',math.isfinite(minimum_gap) and minimum_gap>=-limits['maximum_ground_penetration_m'],
          minimum_gap_m=minimum_gap if math.isfinite(minimum_gap) else None,limiting_collision=limiting)
    return {'status':'PASS' if all(c['passed'] for c in checks) and not errors else 'FAIL',
            'checks':checks,'native_harvest_eligible':False,'scope':config['scope'],
            'robot_spec_sha256':robot.sha256,'pose_samples':len(poses),'joint_samples':len(joints)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True,type=Path)
    parser.add_argument('--asset-root',required=True,type=Path)
    parser.add_argument('--plugin-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--start-height',required=True,type=float)
    parser.add_argument('--max-step-size',type=float,default=.001,
                        help='Explicit physics integration step; acceptance thresholds and phase durations stay unchanged')
    parser.add_argument('--wall-timeout',type=float,default=180,
                        help='Computational wall-clock budget, independent of simulated duration and acceptance tolerances')
    parser.add_argument('--experiment',choices=('full','turn_only'),default='full',
                        help='The short causal turn experiment never substitutes full15s mobility admission')
    args=parser.parse_args()
    if not math.isfinite(args.start_height) or args.start_height<=0:
        parser.error('Positive finite diagnostic start height required')
    if not math.isfinite(args.max_step_size) or not 0<args.max_step_size<=.001:
        parser.error('Physics step must be positive, finite and at most .001 seconds')
    if not math.isfinite(args.wall_timeout) or args.wall_timeout<=0:
        parser.error('Positive finite wall-clock budget required')
    robot=resolve_robot_profile(load_robot_json(args.profile))
    robot.require_capability('native_force_drive')
    if 'native_harvest' in robot.data['capabilities']:
        raise ValueError('This protocol expects an explicitly non-harvest diagnostic profile')
    assets=verify_robot_assets(robot,args.asset_root)
    mesh_geometries=[s['geometry'] for link in robot.links for s in link['collisions'] if s['geometry']['type']=='mesh']
    mesh_repository=MeshRepository(args.asset_root,mesh_geometries) if mesh_geometries else None
    build=load_robot_json(args.plugin_dir/'build_provenance.json')
    observer_digest=sha(args.plugin_dir/'libUchuvaRobotTelemetrySystem.so')
    if (build.get('robot_telemetry_library_sha256')!=observer_digest or
        build.get('libraries_sha256',{}).get('libUchuvaRobotTelemetrySystem.so')!=observer_digest or
        build.get('source_sha256',{}).get('RobotTelemetrySystem.cc')!=sha(REPO/'gazebo/harvest_system/RobotTelemetrySystem.cc')):
        raise ValueError('Observer binary/source does not match its build provenance; rebuild before diagnostic')
    data=robot.to_dict(); drive=data['control']['drive']; contract=resolved_robot_contract(robot)
    if contract['topics'].get('position_force_states'):
        for name in ('JointPositionForceSystem.cc','PositionForceController.hh','ObservationSchedule.hh'):
            if build.get('source_sha256',{}).get(name)!=sha(REPO/'gazebo/harvest_system'/name):
                raise ValueError('Ramped controller source does not match its build provenance: '+name)
        if 'libUchuvaJointPositionForceSystem.so' not in build.get('libraries_sha256',{}):
            raise ValueError('Ramped controller library is missing from the frozen build')
    config=protocol(args.start_height,args.max_step_size,args.experiment)
    config['wall_timeout_s']=args.wall_timeout
    if data.get('physics'):
        config['physics']=data['physics']
        if args.max_step_size>data['physics']['maximum_step_s']:
            raise ValueError('Requested integration step exceeds the profile physics maximum')
    if data.get('closed_loops') or data.get('closures'):
        if args.experiment=='full':config['scope']='CAD diagnostic with declared native closed loops; mounting and actuator/contact parameters remain estimated'
        config['mechanism_acceptance']={'suspension_closure_position_m':.001,'gripper_closure_position_m':.0005,
            'closure_rotation_rad':.001,'gear_coordinate_rad':.001,
            'native_pose_joint_join':'PoseV header exactly equals observer measured_after_step_time; no nearest/interpolated substitute',
            'passive_gear_motor_command_tolerance':1e-12}
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    dump(output/'protocol.json',config)
    dump(output/'robot_resolved.json',data)
    (output/'profile_source.json').write_bytes(args.profile.read_bytes())
    (output/'runner_source.py').write_bytes(Path(__file__).read_bytes())
    plugins=output/'plugins'; plugins.mkdir()
    libraries=build['libraries_sha256']
    for name,digest in libraries.items():
        if Path(name).name!=name or not name.startswith('libUchuva') or not name.endswith('.so'):
            raise ValueError('Unexpected native library path in build provenance')
        if sha(args.plugin_dir/name)!=digest:
            raise ValueError('Native library does not match build provenance: '+name)
        shutil.copyfile(args.plugin_dir/name,plugins/name)
        if sha(plugins/name)!=digest:
            raise ValueError('Native library changed during snapshot: '+name)
    shutil.copyfile(args.plugin_dir/'build_provenance.json',plugins/'build_provenance.json')
    if sha(plugins/'libUchuvaRobotTelemetrySystem.so')!=observer_digest:
        raise ValueError('Observer binary changed during snapshot')
    for uri,digest in assets.items():
        target=output/uri; target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            raise ValueError('CAD asset would overwrite a frozen diagnostic artifact')
        shutil.copyfile(args.asset_root/uri,target)
        if sha(target)!=digest:
            raise ValueError('CAD asset changed during snapshot')
    sdf=output/'world.sdf'; sdf.write_text(world(robot,config))
    dump(output/'provenance.json',{'robot_spec_sha256':robot.sha256,'profile_source_sha256':sha(args.profile),
        'runner_sha256':sha(__file__),'assets_sha256':assets,'observer_sha256':sha(plugins/'libUchuvaRobotTelemetrySystem.so'),
        'build_provenance_sha256':sha(plugins/'build_provenance.json'),'sdf_sha256':sha(sdf),
        'libraries_sha256':libraries,
        'implementation_files_sha256':{name:sha(REPO/'src/uchuva_gazebo'/name) for name in ('robot_spec.py','robot_sdf.py','robot_kinematics.py','robot_validation.py','robot_control_validation.py','robot_drive_control.py','robot_collision_filters.py','closed_loops.py','robot_mesh_geometry.py','robot_mechanism_validation.py') if (REPO/'src/uchuva_gazebo'/name).exists()},
        'gazebo_versions':subprocess.check_output(['gz','sim','--versions'],text=True).strip()})
    validation=subprocess.run(['gz','sdf','-k',str(sdf)],capture_output=True,text=True)
    (output/'sdf_check.log').write_text(validation.stdout+validation.stderr)
    if validation.returncode:
        dump(output/'result.json',{'status':'FAIL','error':'native SDF validation failed','native_harvest_eligible':False})
        return 1
    os.environ['GZ_PARTITION']='uchuva-cad-mobility-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(plugins)+os.pathsep+os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH','')
    os.environ['GZ_SIM_RESOURCE_PATH']=str(output)+os.pathsep+os.environ.get('GZ_SIM_RESOURCE_PATH','')
    from gz.transport13 import Node
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.double_pb2 import Double
    node_=Node(); poses=[]; joints=[]; commands=[]; link_poses=[]; force_control=[]; errors=[]; lock=threading.Lock()
    wheel_publishers={name:node_.advertise(data['namespace']+'/drive/'+name+'/cmd_vel',Double) for name in drive['joints']}
    arm_publishers={name:node_.advertise(topic,Double) for name,topic in contract['topics']['joint_commands'].items()}
    drive_controller=DriveReferenceController(drive)
    arm_references={name:0. for name in arm_publishers}
    def link_pose_callback(message):
        try:
            stamps=set();links={}
            for observed in message.pose:
                stamp=observed.header.stamp.sec+observed.header.stamp.nsec*1e-9
                values=[observed.position.x,observed.position.y,observed.position.z,observed.orientation.x,observed.orientation.y,observed.orientation.z,observed.orientation.w]
                header={entry.key:list(entry.value) for entry in observed.header.data}
                if header.get('frame_id')!=[data['model_name']] or not observed.name.startswith(data['model_name']+'::'):
                    raise ValueError('Native link pose has unexpected parent frame/model')
                if not math.isfinite(stamp) or not all(math.isfinite(v) for v in values) or abs(sum(v*v for v in values[3:])-1)>1e-6:
                    raise ValueError('Native link pose must be finite with unit quaternion')
                name=observed.name[len(data['model_name'])+2:]
                if name in links:raise ValueError('Duplicate native link pose')
                links[name]={'xyz_m':values[:3],'quaternion_xyzw':values[3:]};stamps.add(stamp)
            if len(stamps)!=1:raise ValueError('Mixed or missing native link timestamps')
            stamp=stamps.pop()
            if set(links)!={link['name'] for link in robot.links}:raise ValueError('Missing or unexpected native links')
            with lock:
                if link_poses and stamp<=link_poses[-1]['sim_time']:raise ValueError('Non-increasing native link timestamp')
                link_poses.append({'sim_time':stamp,'parent_frame':data['model_name'],'links':links})
        except Exception as error:errors.append('link_pose_callback: '+str(error))
    def pose_callback(message):
        try:
            for pose in message.pose:
                if pose.name.rsplit('::',1)[-1]!=data['model_name']:
                    continue
                stamp=pose.header.stamp.sec+pose.header.stamp.nsec*1e-9
                values=[pose.position.x,pose.position.y,pose.position.z,pose.orientation.x,pose.orientation.y,pose.orientation.z,pose.orientation.w]
                if not math.isfinite(stamp) or not all(math.isfinite(v) for v in values) or abs(sum(v*v for v in values[3:])-1)>1e-6:
                    raise ValueError('Nonfinite observed pose or invalid unit quaternion')
                with lock:
                    if poses and stamp<=poses[-1]['sim_time']:
                        raise ValueError('Non-increasing observed pose timestamp')
                    drive_controller.observe_pose(stamp,values)
                    poses.append({'sim_time':stamp,'phase':phase_at(config,stamp)['name'],'pose':values})
        except Exception as error:
            errors.append('pose_callback: '+str(error))
    def joint_callback(message):
        try:
            row=json.loads(message.data)
            if row['robot_spec_sha256']!=robot.sha256:
                raise ValueError('Wrong robot identity')
            stamp=row['sim_time']; phase=phase_at(config,stamp)
            if type(stamp) not in (int,float) or not math.isfinite(stamp) or (joints and stamp<=joints[-1]['sim_time']):
                raise ValueError('Invalid or non-increasing robot observation timestamp')
            row['phase']=phase['name']
            with lock:
                dt=max(0,stamp-drive_controller.previous[0])
                try:
                    drive_record=drive_controller.step(phase['linear_m_s'],phase['angular_rad_s'],stamp)
                except ValueError as error:
                    errors.append('drive_feedback: '+str(error))
                    drive_record=drive_controller.step(0,0,stamp)
                    drive_record['rejected_request_error']=str(error)
            wheel_refs=drive_record['wheel_velocity_references_rad_s']
            for name,value in wheel_refs.items():
                msg=Double(); msg.data=value; wheel_publishers[name].publish(msg)
            for name,publisher in arm_publishers.items():
                rate=data['control']['arm'][name]['command_velocity']
                arm_references[name]+=max(-rate*dt,min(rate*dt,data['arm_home_positions'][name]-arm_references[name]))
                msg=Double(); msg.data=arm_references[name]; publisher.publish(msg)
            with lock:
                joints.append(row)
                commands.append({'sim_time':stamp,'phase':phase['name'],'linear_m_s':drive_record['linear_m_s'],'angular_rad_s':drive_record['angular_rad_s'],
                                 'wheel_velocity_references_rad_s':wheel_refs,'arm_positions_rad':dict(arm_references),
                                 'drive_reference':drive_record})
        except Exception as error:
            errors.append(str(error))
    if not node_.subscribe(Pose_V,'/probe/cad_model_pose',pose_callback) or not node_.subscribe(StringMsg,contract['topics_robot_telemetry'],joint_callback):
        raise RuntimeError('Native subscription failed')
    def force_callback(expected_joint):
        def receive(message):
            try:
                row=json.loads(message.data)
                if row.get('joint_name')!=expected_joint or row.get('robot_spec_sha256')!=robot.sha256:
                    raise ValueError('Unexpected force-controller identity')
                with lock:force_control.append(row)
            except Exception as error:errors.append('force_callback: '+str(error))
        return receive
    force_callbacks=[]
    for name,topic in contract['topics'].get('position_force_states',{}).items():
        callback=force_callback(name);force_callbacks.append(callback)
        if not node_.subscribe(StringMsg,topic,callback):raise RuntimeError('Native force-controller subscription failed')
    link_topic=contract['topics'].get('link_poses')
    if link_topic and not node_.subscribe(Pose_V,link_topic,link_pose_callback):raise RuntimeError('Native link pose subscription failed')
    native_started=time.monotonic()
    with (output/'native.log').open('w') as log:
        process=subprocess.Popen(['gz','sim','--force-version','8','-s','-r','--iterations',str(round((config['duration_s']+config['observation_tail_s'])/config['dt_s'])),str(sdf)],
            stdout=log,stderr=subprocess.STDOUT,cwd=output,start_new_session=True)
        try:
            while True:
                elapsed=time.monotonic()-native_started
                remaining=args.wall_timeout-elapsed
                if remaining<=0:raise subprocess.TimeoutExpired(process.args,args.wall_timeout)
                try:
                    code=process.wait(timeout=min(30.,remaining));break
                except subprocess.TimeoutExpired:
                    with lock:
                        progress={'wall_seconds':time.monotonic()-native_started,
                            'last_observed_sim_time':joints[-1]['sim_time'] if joints else None,
                            'joint_samples':len(joints),'model_pose_samples':len(poses),
                            'link_pose_samples':len(link_poses),'callback_errors':list(errors)}
                    dump(output/'progress.json',progress)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try: code=process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL); code=process.wait(timeout=5)
            errors.append('native_timeout')
    native_wall_seconds=time.monotonic()-native_started
    dump(output/'native_completion.json',{'native_exit_code':code,'native_wall_seconds':native_wall_seconds,
        'native_process_pid':process.pid,'native_wait_returned':True,'errors':list(errors),
        'robot_spec_sha256':robot.sha256,'protocol_sha256':sha(output/'protocol.json')})
    time.sleep(.15)
    node_.unsubscribe('/probe/cad_model_pose'); node_.unsubscribe(contract['topics_robot_telemetry'])
    if link_topic:node_.unsubscribe(link_topic)
    for topic in contract['topics'].get('position_force_states',{}).values():node_.unsubscribe(topic)
    for name,records in (('poses',poses),('joints',joints),('commands',commands),('link_poses',link_poses),('force_control',force_control)):
        (output/(name+'.jsonl')).write_text(''.join(json.dumps(row,allow_nan=False)+'\n' for row in records))
    result=evaluate(robot,config,poses,joints,errors,code,link_poses=link_poses,mesh_repository=mesh_repository,force_control=force_control,commands=commands)
    result.setdefault('robot_spec_sha256',robot.sha256)
    result.setdefault('native_harvest_eligible',False)
    result.setdefault('scope',config['scope'])
    result['native_exit_code']=code
    result['native_wall_seconds']=native_wall_seconds
    result['evidence_files_sha256']={p.relative_to(output).as_posix():sha(p) for p in output.iterdir() if p.is_file()}
    dump(output/'result.json',result)
    print(json.dumps(result,indent=2,allow_nan=False))
    return int(result['status']!='PASS')


if __name__=='__main__':
    raise SystemExit(main())
