#!/usr/bin/env python3
"""Native support probe for the CAD gripper's positive-X four-bar loop.

The four axes are extracted from named CAD constraints. Body masses/inertias,
drive gains/effort and angle stops are estimated fixture values. Gear contact,
mirrored synchronization, rubber gripping and cutting forces are out of scope.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from probe_cad_suspension_loop import run_case, node, numbers, dump, sha

REPO=Path(__file__).resolve().parents[1]


def world(config, closed):
    sdf=ET.Element('sdf',version='1.10')
    world_=node(sdf,'world',name='gripper_loop_probe')
    node(world_,'gravity','0 0 -9.81')
    physics=node(world_,'physics',name='step',type='ignored')
    node(physics,'max_step_size',.001);node(physics,'real_time_factor',1)
    node(world_,'plugin',filename='gz-sim-physics-system',name='gz::sim::systems::Physics')
    model=node(world_,'model',name='gripper_probe')
    node(model,'pose','0 0 1 0 0 0')
    a,b,c,d=[config['axis_points_cad_m'][key] for key in 'ABCD']
    positions={'housing':[0,0,0],'short_rocker':a,'drive_crank':b,'coupler':d}
    centers={'housing':[0,0,0],'short_rocker':[(y-x)/2 for x,y in zip(a,d)],
             'drive_crank':[(y-x)/2 for x,y in zip(b,c)],'coupler':[(y-x)/2 for x,y in zip(d,c)]}
    for name,position in positions.items():
        link=node(model,'link',name=name);node(link,'pose',numbers([*position,0,0,0]))
        inertial=node(link,'inertial');node(inertial,'mass',.1 if name=='housing' else .01)
        node(inertial,'pose',numbers([*centers[name],0,0,0]))
        tensor=node(inertial,'inertia')
        for key in ('ixx','iyy','izz'):node(tensor,key,.00001)
    rows=[('anchor','fixed','world','housing',[0,0,0]),('rocker_pivot','revolute','housing','short_rocker',a),
          ('drive_pivot','revolute','housing','drive_crank',b),('crank_coupler','revolute','drive_crank','coupler',c)]
    if closed:rows.append(('gripper_closure','revolute','coupler','short_rocker',d))
    for name,kind,parent,child,point in rows:
        joint=node(model,'joint',name=name,type=kind);node(joint,'parent',parent);node(joint,'child',child)
        node(joint,'pose',numbers([*point,0,0,0]),relative_to='__model__')
        if kind=='fixed':continue
        axis=node(joint,'axis');node(axis,'xyz','0 1 0')
        limits=node(axis,'limit')
        for key,value in (('lower',-.4),('upper',.4),('effort',.02),('velocity',1)):node(limits,key,value)
        node(node(axis,'dynamics'),'damping',.002)
    controller=node(model,'plugin',filename='gz-sim-joint-position-controller-system',name='gz::sim::systems::JointPositionController')
    for key,value in (('joint_name','drive_pivot'),('initial_position',0),('topic',config['position_reference_schedule']['topic']),('use_velocity_commands','false'),
        ('p_gain',.2),('i_gain',0),('d_gain',.01),('cmd_min',-.02),('cmd_max',.02)):
        node(controller,key,value)
    publisher=node(model,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
    for key,value in (('publish_link_pose','true'),('publish_model_pose','false'),('use_pose_vector_msg','true'),
        ('static_publisher','false'),('update_frequency',100),('topic','/probe/suspension_poses')):node(publisher,key,value)
    observer=node(model,'plugin',filename='libUchuvaRobotTelemetrySystem.so',name='uchuva::RobotTelemetrySystem')
    node(observer,'robot_spec_sha256',config['fixture_sha256']);node(observer,'topic','/probe/suspension_joints')
    for name,kind,*_ in rows:
        if kind!='fixed':node(node(observer,'joint',name=name),'effort_limit',.02 if name=='drive_pivot' else 0)
    ET.indent(sdf,space='  ')
    return ET.tostring(sdf,encoding='unicode')+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plugin-dir',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,default=REPO/'outputs/real_harvester_cad/inventory_full_01/cad_inventory.json')
    parser.add_argument('--case',choices=['closed_loop','open_control'])
    args=parser.parse_args();output=args.output.resolve();plugins=args.plugin_dir.resolve()
    if args.case:return run_case(output,plugins,args.case,world)
    build=json.loads((plugins/'build_provenance.json').read_text())
    observer_digest=sha(plugins/'libUchuvaRobotTelemetrySystem.so')
    if (build.get('robot_telemetry_library_sha256') != observer_digest or
        build.get('libraries_sha256',{}).get('libUchuvaRobotTelemetrySystem.so') != observer_digest or
        build.get('source_sha256',{}).get('RobotTelemetrySystem.cc') != sha(REPO/'gazebo/harvest_system/RobotTelemetrySystem.cc')):
        raise ValueError('Observer binary/source differs from build provenance')
    inventory=json.loads(args.inventory.read_text(encoding='utf-8-sig'))
    document=next(row for row in inventory['documents'] if row['source_path']=='gripper/Gripper ensamble.iam')
    relations={row['name']:row for row in document['relations']}
    references={'A':('Coincidencia:10','EntityOne'),'B':('Coincidencia:1','EntityTwo'),
                'C':('Coincidencia:22','EntityOne'),'D':('Coincidencia:15','EntityOne')}
    points={};evidence={}
    for label,(name,entity) in references.items():
        row=relations[name][entity]
        axis=row['AxisVector'];point=row['BasePoint_m']
        if abs(abs(axis[1])-1)>1e-8 or abs(axis[0])+abs(axis[2])>1e-8:
            raise ValueError('CAD axes are not a verified parallel-Y four-bar')
        # The Y coordinates select arbitrary points on the same infinite axis;
        # choose y=0 consistently, preserving its XZ location exactly.
        points[label]=[point[0],0,point[2]]
        evidence[label]={'constraint':name,'entity':entity,'raw_point_m':point,'raw_axis':axis}
    config={'scope':'Positive-X CAD gripper four-bar topology only; mirrored gear synchronization and contact not validated',
        'inventory_sha256':sha(args.inventory),'document_id':document['id'],'document_sha256':document['sha256'],
        'axis_points_cad_m':points,'axis_evidence':evidence,'open_joint_names':['rocker_pivot','drive_pivot','crank_coupler'],
        'closure_joint_name':'gripper_closure','closure_parent_link':'short_rocker','closure_child_link':'coupler',
        'closure_parent_offset_m':[d-a for a,d in zip(points['A'],points['D'])], 'closure_child_offset_m':[0,0,0],
        'estimated_fixture':{'moving_body_mass_kg':.01,'body_diagonal_inertia_kg_m2':.00001,
            'drive_effort_nm':.02,'pid':[.2,0,.01],'angle_limits_rad':[-.4,.4],'damping_nms_rad':.002},
        'position_reference_schedule':{'joint_name':'drive_pivot','topic':'/probe/gripper_drive_reference',
            'steps':[{'start_s':0,'position_rad':0},{'start_s':.5,'position_rad':.1},{'start_s':1.2,'position_rad':-.1}]},
        'parameter_status':'engineering_heuristic_for_topology_probe_not_hardware_measurement'}
    config['fixture_sha256']=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    output.mkdir(parents=True,exist_ok=False)
    frozen_plugins=output/'plugins';frozen_plugins.mkdir()
    for name in ('libUchuvaRobotTelemetrySystem.so','build_provenance.json'):
        shutil.copyfile(plugins/name,frozen_plugins/name)
    if sha(frozen_plugins/'libUchuvaRobotTelemetrySystem.so') != observer_digest:
        raise ValueError('Observer changed during snapshot')
    plugins=frozen_plugins
    dump(output/'fixture.json',config)
    dump(output/'protocol.json',{'observe_from_s':.2,'minimum_samples':100,'maximum_closure_residual_m':.0005,
        'minimum_joint_excursion_rad':{'drive_pivot':.02},
        'criteria_status':'Engineering fixture criteria declared before execution, not hardware accuracy',
        'decision':'All four physical revolutes must be observed, drive excursion at least .02 rad, and closing pin residual at most .5 mm; native exit zero alone is insufficient.'})
    (output/'probe_source.py').write_bytes(Path(__file__).read_bytes())
    shared=Path(__file__).with_name('probe_cad_suspension_loop.py');(output/'shared_runner_source.py').write_bytes(shared.read_bytes())
    dump(output/'provenance.json',{'script_sha256':sha(__file__),'shared_runner_sha256':sha(shared),
        'observer_sha256':sha(plugins/'libUchuvaRobotTelemetrySystem.so'),
        'build_provenance_sha256':sha(plugins/'build_provenance.json'),
        'primary_source':'https://raw.githubusercontent.com/gazebosim/gz-physics/gz-physics7_7.8.0/dartsim/src/SDFFeatures.cc'})
    for case in ('closed_loop','open_control'):
        subprocess.run([sys.executable,__file__,'--output',str(output),'--plugin-dir',str(plugins),'--case',case],check=True)
    cases={case:json.loads((output/case/'result.json').read_text()) for case in ('closed_loop','open_control')}
    dump(output/'summary.json',{'native_closed_loop_supported':cases['closed_loop']['native_topology_supported_and_observed'],
        'scope':config['scope'],'cases':cases})
    return 0


if __name__=='__main__':raise SystemExit(main())
