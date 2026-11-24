#!/usr/bin/env python3
"""Create an explicitly estimated CAD-derived V8 demo robot, without simulation.

Two internal payload boxes, a white electronics enclosure and an open basket
are rigidly attached to the chassis. The source CAD meshes are preserved; six
fixed gripper links are aggregated, while one jaw receives an ideal prismatic
guide. This is not a calibrated LiFePO4 pack or a repaired CAD four-bar gripper.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_gazebo.robot_spec import resolve_robot_profile, verify_robot_assets
from uchuva_gazebo.robot_kinematics import forward_kinematics, compose_poses, inverse_pose, transform_point, rotate_vector
from uchuva_gazebo.robot_sdf import resolved_robot_model, resolved_robot_contract
from uchuva_gazebo.robot_collision_filters import collision_masks
from prepare_cad_robot import aggregate_inertia


DEFAULTS={
    'batteries':[
        {'name':'battery_left','center_m':[-.10,.08,0.],'size_m':[.15,.08,.08],'mass_kg':1.0},
        {'name':'battery_right','center_m':[-.10,-.08,0.],'size_m':[.15,.08,.08],'mass_kg':1.0}],
    'electronics':{'name':'electronics_white','center_m':[.05,0.,0.],'size_m':[.14,.10,.08],'mass_kg':.35},
    'basket':{'inner_min_m':[.12,-.13,.114],'inner_max_m':[.34,.13,.190],
              'wall_thickness_m':.004,'mass_kg':.35},
    'gripper':{'open_gap_m':.006,'effort_limit_n':2.,'command_velocity_m_s':.005,
               'position_tolerance_m':.0002,'maximum_settled_speed_m_s':.001,'stable_time_s':.2,
               'p_gain_n_m':1000.,'estimated_damping_ratio':1.},
    'wrist_pitch_command_velocity_rad_s':.25,
    'mounts':{'enabled':True,'estimated_steel_density_kg_m3':7850.},
}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def pose(xyz=(0,0,0),q=(0,0,0,1)):return {'xyz_m':list(xyz),'quaternion_xyzw':list(q)}


def raw_inertia(inertia):
    xx,yy,zz,xy,xz,yz=inertia['tensor_kg_m2']
    return {'mass_kg':inertia['mass_kg'],'center_of_mass_m':inertia['com_m'],
            'xyz_moments_kg_m2':[xx,yy,zz,xy,yz,xz]}


def box_inertia(mass,size):
    if not math.isfinite(mass) or mass<=0 or len(size)!=3 or any(not math.isfinite(x) or x<=0 for x in size):
        raise ValueError('Estimated box mass and dimensions must be finite and positive')
    x,y,z=size
    return {'mass_kg':mass,'com_m':[0,0,0],
            'tensor_kg_m2':[mass*(y*y+z*z)/12,mass*(x*x+z*z)/12,mass*(x*x+y*y)/12,0,0,0]}


def basket_parts(config):
    lo,hi,t=config['inner_min_m'],config['inner_max_m'],config['wall_thickness_m']
    if len(lo)!=3 or len(hi)!=3 or any(not math.isfinite(v) for v in (*lo,*hi,t)) or t<=0:
        raise ValueError('Invalid basket bounds/thickness')
    x,y,z=[b-a for a,b in zip(lo,hi)]
    if min(x,y,z)<=0:raise ValueError('Basket interior must be nonempty')
    cx,cy,cz=[(a+b)/2 for a,b in zip(lo,hi)]
    parts=[('basket_floor',[cx,cy,lo[2]-t/2],[x+2*t,y+2*t,t]),
           ('basket_front',[hi[0]+t/2,cy,cz],[t,y+2*t,z]),
           ('basket_rear',[lo[0]-t/2,cy,cz],[t,y+2*t,z]),
           ('basket_left',[cx,hi[1]+t/2,cz],[x,t,z]),
           ('basket_right',[cx,lo[1]-t/2,cz],[x,t,z])]
    volume=sum(math.prod(size) for _,_,size in parts)
    return [{'name':name,'center_m':center,'size_m':size,
             'mass_kg':config['mass_kg']*math.prod(size)/volume} for name,center,size in parts]


def mount_parts(settings):
    """Small welded/bolted stand-in assemblies; no strength certification.

    The native square-tube faces are measured from CAD parts 119 and 117.
    Clamp plates touch only their upper/lower planes. Shanks sit outside
    the tube, so no original CAD holes or solids need to be modified.
    All primitives have disjoint interiors; the mass is their volume sum.
    """
    config=settings.get('mounts',{})
    if not config.get('enabled',False):return []
    density=config['estimated_steel_density_kg_m3']
    if not math.isfinite(density) or density<=0:raise ValueError('Invalid support density')
    if settings['electronics']['center_m']!=[.05,0.,0.] or settings['electronics']['size_m']!=[.14,.10,.08]:
        raise ValueError('The verified electronics bracket requires the declared internal enclosure placement')
    if settings['basket']['inner_min_m']!=[.12,-.13,.114] or settings['basket']['wall_thickness_m']!=.004:
        raise ValueError('The verified basket bracket requires the declared floor placement')
    parts=[]
    def add(name,center,size,*,role,mate=None,cylinder=False):
        geometry={'type':'cylinder','radius_m':size[0]/2,'length_m':size[2]} if cylinder else {'type':'box','size_m':size}
        volume=math.pi*(size[0]/2)**2*size[2] if cylinder else math.prod(size)
        parts.append({'name':name,'center_m':center,'size_m':size,'geometry':geometry,
            'mass_kg':density*volume,'color_rgba':[.55,.58,.61,1.],
            'role':role,'mating_cad_face':mate,'parameter_status':'engineering_heuristic'})
    assemblies=[('electronics_mount',0.,-.095775,-.076725,.035,.05,.134,.006,.002,-.04,'part_119'),
                ('basket_mount',.1625,.076725,.095775,.095,.245,.190,.008,.004,.110,'part_117')]
    for prefix,x,z_bottom,z_top,y_span,rail_x,rail_length,rail_width,rail_thickness,rail_top,cad_part in assemblies:
        for side,y in [('left',y_span),('right',-y_span)]:
            tag=prefix+'_'+side
            add(tag+'_rail',[rail_x,y,rail_top-rail_thickness/2],[rail_length,rail_width,rail_thickness],role='Longitudinal rail touching the payload underside')
            for face,z,normal in [('upper',z_top+.001,-1),('lower',z_bottom-.001,1)]:
                add(tag+'_'+face+'_clamp',[x,y,z],[.040,.010,.002],role='Tube clamp plate',
                    mate={'part':cad_part,'axis':'z','coordinate_m':z_top if face=='upper' else z_bottom,
                          'support_outward_normal_z':normal,'tube_center_x_m':x})
            for end,dx in [('rear',-.016),('front',.016)]:
                add(tag+'_'+end+'_shank',[x+dx,y,(z_bottom+z_top)/2],[.004,.004,z_top-z_bottom],role='Clamp bolt shank',cylinder=True)
                for cap,z in [('head',z_top+.003),('nut',z_bottom-.003)]:
                    add(tag+'_'+end+'_'+cap,[x+dx,y,z],[.007,.007,.002],role='Idealized bolt head/nut',cylinder=True)
            post_bottom=z_top+.002;post_top=rail_top-rail_thickness
            if post_top<=post_bottom:raise ValueError('Support standoff has nonpositive length')
            for end,dx in [('rear',-.005),('front',.005)]:
                add(tag+'_'+end+'_standoff',[x+dx,y,(post_bottom+post_top)/2],[.004,.004,post_top-post_bottom],role='Welded standoff joining top clamp and rail')
    return parts


def component_inertia(component):
    geometry=component.get('geometry',{'type':'box','size_m':component['size_m']})
    if geometry['type']=='box':return box_inertia(component['mass_kg'],geometry['size_m'])
    radius,length,mass=geometry['radius_m'],geometry['length_m'],component['mass_kg']
    if min(radius,length,mass)<=0:raise ValueError('Invalid support cylinder')
    transverse=mass*(3*radius*radius+length*length)/12
    return {'mass_kg':mass,'com_m':[0,0,0],
            'tensor_kg_m2':[transverse,transverse,mass*radius*radius/2,0,0,0]}


def mesh_vertices(geometry,asset_root):
    if geometry['type']!='mesh':raise ValueError('Expected admitted native CAD jaw mesh')
    path=(asset_root/geometry['uri']).resolve()
    if not path.is_relative_to(asset_root.resolve()) or sha(path)!=geometry['sha256']:
        raise ValueError('Jaw mesh identity differs')
    points=[tuple(map(float,line.split()[1:4])) for line in path.read_text().splitlines() if line.startswith('v ')]
    if not points:raise ValueError('Empty CAD mesh')
    return points


def derive(source,asset_root,settings,evidence):
    old=source.to_dict();new=copy.deepcopy(old)
    if any(j['type']!='fixed' for j in old['joints'] if j['child'].startswith('gripper_')):
        raise ValueError('This derivative requires the explicit fixed-q0 source')
    if old.get('gear_couplings'):raise ValueError('Source contains a live gear transmission')
    poses=forward_kinematics(source,{j['name']:0 for j in old['joints'] if j['type']!='fixed'})
    wrist='arm_wrist_roll';moving='gripper_left_jaw';opposing='gripper_right_jaw'
    merged={l['name'] for l in old['links'] if l['name'].startswith('gripper_') and l['name'] not in (moving,opposing)}
    if len(merged)!=6:raise ValueError('Unexpected CAD fixed-gripper topology')
    old_links={l['name']:l for l in old['links']}
    inv_grasp=inverse_pose(poses['grasp_center']);inv_wrist=inverse_pose(poses[wrist])
    supports={}
    for name in (moving,opposing):
        points=[]
        for shape in old_links[name]['collisions']:
            placement=compose_poses(inv_grasp,compose_poses(poses[name],shape['pose']))
            points.extend(transform_point(placement,p) for p in mesh_vertices(shape['geometry'],asset_root))
        supports[name]=[min(p[0] for p in points),max(p[0] for p in points)]
    closed_gap=supports[opposing][0]-supports[moving][1]
    travel=settings['gripper']['open_gap_m']-closed_gap
    if not 0<closed_gap<settings['gripper']['open_gap_m'] or not 0<travel<=.01:
        raise ValueError('Requested short jaw travel is inconsistent with the CAD geometry')
    new_wrist=next(l for l in new['links'] if l['name']==wrist)
    rigid_parts=[(raw_inertia(new_wrist['inertial']),pose())]
    for name in sorted(merged):
        placement=compose_poses(inv_wrist,poses[name]);body=old_links[name]
        rigid_parts.append((raw_inertia(body['inertial']),placement))
        for category in ('visuals','collisions'):
            for shape in body[category]:
                transformed=copy.deepcopy(shape)
                transformed['pose']=compose_poses(placement,shape['pose'])
                new_wrist[category].append(transformed)
    new_wrist['inertial']=aggregate_inertia(rigid_parts)
    link_map={};links=[]
    for index,link in enumerate(new['links']):
        if link['name'] not in merged:link_map[index]=len(links);links.append(link)
    new['links']=links
    joint_map={};joints=[];removed_joint_names=[]
    for index,joint in enumerate(new['joints']):
        if joint['child'] in merged:
            removed_joint_names.append(joint['name']);continue
        if joint['child'] in (moving,opposing):
            joint['parent']=wrist
            joint['origin']=compose_poses(inv_wrist,poses[joint['child']])
            joint['child_pose']=pose()
            if joint['child']==moving:
                joint['type']='prismatic';joint['group']='gripper'
                # Joint origin frame has the original jaw orientation. Express
                # the fixed grasp-frame -X direction in that frame, not world.
                direction=rotate_vector(poses['grasp_center']['quaternion_xyzw'],[-1,0,0])
                joint['axis']=rotate_vector(inverse_pose(poses[moving])['quaternion_xyzw'],direction)
                joint['limits']={'lower':0.,'upper':travel,'effort':settings['gripper']['effort_limit_n'],
                                 'velocity':settings['gripper']['command_velocity_m_s']}
                for key in ('damping','friction','spring_reference','spring_stiffness'):joint.pop(key,None)
                moving_joint=joint['name']
        joint_map[index]=len(joints);joints.append(joint)
    new['joints']=joints
    if any(f['parent'] in merged for f in new['frames']):raise ValueError('Cannot discard a referenced CAD frame')
    if any(c['body'] in merged or c['auxiliary'] in merged for c in new.get('closures',[])):
        raise ValueError('Cannot collapse an active suspension/closure')

    def remap(path):
        parts=path.split('/')
        table=link_map if len(parts)>2 and parts[1]=='links' else joint_map if len(parts)>2 and parts[1]=='joints' else None
        if table is not None and parts[2].isdigit():
            value=table.get(int(parts[2]))
            if value is None:return None
            parts[2]=str(value)
        return '/'.join(parts)
    new['parameter_metadata']={p:meta for key,meta in old['parameter_metadata'].items() if (p:=remap(key)) is not None}
    new['derived_values']=[{**r,'path':p} for r in old['derived_values'] if (p:=remap(r['path'])) is not None]
    # Compile the changed rigid graph explicitly; no global self-collision off.
    exclusions={}
    for row in old['collision_policy']['excluded_pairs']:
        pair=tuple(sorted(wrist if n in merged else n for n in row['links']))
        if pair[0]!=pair[1]:exclusions[pair]=row['reason']+'; fixed CAD members aggregated for the demo'
    for joint in joints:
        pair=tuple(sorted((joint['parent'],joint['child'])))
        if joint['child']==moving:
            exclusions[pair]='Ideal prismatic jaw-to-housing guide replaces the CAD four-bar; native adjacent-body exclusion is a declared demo approximation, not a contact validation.'
        elif joint['child']==opposing:
            exclusions[pair]='Opposing jaw is rigidly fixed to the housing; same-body internal interface after fixed-group reduction.'
        else:exclusions.setdefault(pair,'Preserved physical joint adjacency')
    jaw_pair=tuple(sorted((moving,opposing)))
    exclusions[jaw_pair]='Certified internal mechanical clearance: closed native mesh half-spaces separated by '+format(closed_gap,'.17g')+' m; opening moves only left jaw along negative grasp X, increasing separation for the entire declared stroke. External contacts remain active.'
    new['collision_policy']={'mode':'explicit_pairs','excluded_pairs':[{'links':list(pair),'reason':reason} for pair,reason in sorted(exclusions.items())]}

    brackets=mount_parts(settings)
    components=[*settings['batteries'],settings['electronics'],*basket_parts(settings['basket']),*brackets]
    base=next(l for l in new['links'] if l['name']==new['root_link'])
    mass_parts=[(raw_inertia(base['inertial']),pose())]
    for component in components:
        name,center,size,mass=(component[k] for k in ('name','center_m','size_m','mass_kg'))
        if not name or any(s['name']==name for s in base['visuals']+base['collisions']):raise ValueError('Duplicate component name')
        inertia=component_inertia(component)
        if len(center)!=3 or any(not math.isfinite(v) for v in center):raise ValueError('Invalid component center')
        geometry=copy.deepcopy(component.get('geometry',{'type':'box','size_m':size}))
        color=component.get('color_rgba',([.91,.92,.90,1.] if name.startswith('electronics') else
               [.12,.22,.28,1.] if name.startswith('battery') else [.18,.36,.31,1.]))
        base['visuals'].append({'name':name+'_visual','pose':pose(center),'geometry':copy.deepcopy(geometry),'color_rgba':color})
        base['collisions'].append({'name':name,'pose':pose(center),'geometry':copy.deepcopy(geometry),'surface':{'mu':.6,'mu2':.6}})
        mass_parts.append((raw_inertia(inertia),pose(center)))
    base['inertial']=aggregate_inertia(mass_parts)
    basket=settings['basket'];basket_center=[(a+b)/2 for a,b in zip(basket['inner_min_m'],basket['inner_max_m'])]
    new['frames'].append({'name':'basket','parent':new['root_link'],'pose':pose(basket_center)})
    grip=settings['gripper'];effort=grip['effort_limit_n']
    moving_mass=old_links[moving]['inertial']['mass_kg']
    damping=2*grip['estimated_damping_ratio']*math.sqrt(grip['p_gain_n_m']*moving_mass)
    new['control']['gripper']={moving_joint:{'p_gain':grip['p_gain_n_m'],'i_gain':0.,'d_gain':damping,
        'i_min':0.,'i_max':0.,'cmd_min':-effort,'cmd_max':effort,'command_velocity':grip['command_velocity_m_s'],
        'reference_mode':'ramped_position'}}
    new['actuators'].append({'name':'demo_prismatic_jaw_actuator','joint':moving_joint,'continuous_effort':effort,
        'peak_effort':effort,'transmission_ratio':1.,'efficiency':1.,'effort_reference':'joint_output','status':'estimado'})
    new['profile_id']='cad_v8_demo_payload_prismatic_v1'
    new['provenance']=copy.deepcopy(evidence)
    new['capabilities']=[c for c in new['capabilities'] if c!='native_harvest']
    # The canonical speed is overrideable; gains, joint limit and effort remain
    # byte-identical to source. Payload/layout changes require this preparator.
    speed=settings['wrist_pitch_command_velocity_rad_s']
    if not 0<speed<=old['control']['arm']['wrist_pitch_joint']['command_velocity']:
        raise ValueError('Demo wrist speed may only reduce the existing reference ceiling')
    new['parameters']['demo_wrist_pitch_command_velocity_rad_s']=speed
    new['parameter_metadata']['/parameters/demo_wrist_pitch_command_velocity_rad_s']={**evidence,'update_class':'runtime'}
    target='/control/arm/wrist_pitch_joint/command_velocity'
    new['derived_values']=[r for r in new['derived_values'] if r['path']!=target]
    new['derived_values'].append({'path':target,'expression':{'parameter':'demo_wrist_pitch_command_velocity_rad_s'}})
    new['parameter_metadata'][target]={**evidence,'update_class':'runtime'}
    for name,value in [('demo_jaw_open_position_m',travel),('demo_jaw_closed_gap_m',closed_gap)]:
        new['parameters'][name]=value
        new['parameter_metadata']['/parameters/'+name]={**evidence,'update_class':'cad_reexport'}
    for index,link in enumerate(new['links']):
        if link['name'] in (wrist,new['root_link']):
            new['parameter_metadata'][f'/links/{index}/inertial']={**evidence,'update_class':'model_regeneration'}
    moving_index=next(i for i,j in enumerate(new['joints']) if j['name']==moving_joint)
    for field in ('type','group','origin','axis','limits'):
        new['parameter_metadata'][f'/joints/{moving_index}/{field}']={**evidence,'update_class':'model_regeneration'}
    new['parameter_metadata']['/control/gripper']={**evidence,'update_class':'model_regeneration'}
    robot=resolve_robot_profile(new);actual=robot.to_dict()
    before_mass=sum(l['inertial']['mass_kg'] for l in old['links'])
    expected_mass=before_mass+sum(c['mass_kg'] for c in components)
    after_mass=sum(l['inertial']['mass_kg'] for l in actual['links'])
    if abs(after_mass-expected_mass)>1e-11:raise ValueError('Mass aggregation changed the expected total')
    # Check all original visible/collision surfaces in the common root at q0.
    q0={j['name']:0 for j in actual['joints'] if j['type']!='fixed'};after_poses=forward_kinematics(robot,q0)
    errors=[]
    for category in ('visuals','collisions'):
        original_shapes={s['name']:(l['name'],s) for l in old['links'] for s in l[category]}
        final_shapes={s['name']:(l['name'],s) for l in actual['links'] for s in l[category]}
        if not original_shapes.keys()<=final_shapes.keys():raise ValueError('Original CAD shape discarded')
        for name,(link,shape) in original_shapes.items():
            new_link,new_shape=final_shapes[name]
            if {k:v for k,v in shape.items() if k!='pose'}!={k:v for k,v in new_shape.items() if k!='pose'}:
                raise ValueError('Original CAD surface/material changed: '+name)
            a=compose_poses(poses[link],shape['pose']);b=compose_poses(after_poses[new_link],new_shape['pose'])
            errors.append(math.dist(a['xyz_m'],b['xyz_m']))
            if 1-abs(sum(x*y for x,y in zip(a['quaternion_xyzw'],b['quaternion_xyzw'])))>1e-12:
                raise ValueError('Original CAD surface orientation changed')
    if max(errors)>1e-12:raise ValueError('Original CAD surface position changed')
    if actual['physics']!=old['physics'] or actual['control']['drive']!=old['control']['drive']:
        raise ValueError('Source physics or base control changed')
    masks=collision_masks(actual)
    for link in actual['links']:
        names=[s['name'] for category in ('visuals','collisions') for s in link[category]]
        if len(names)!=len(set(names)):raise ValueError('Gazebo link child names must be unique across visuals and collisions')
    return robot,{'source_mass_kg':before_mass,'added_mass_kg':expected_mass-before_mass,'total_mass_kg':after_mass,
        'original_meshes_and_colliders_preserved':True,'maximum_original_shape_q0_position_error_m':max(errors),
        'aggregated_fixed_gripper_links':sorted(merged),'removed_fixed_joint_names':removed_joint_names,
        'link_count':len(actual['links']),'visual_count':sum(len(l['visuals']) for l in actual['links']),
        'collision_count':sum(len(l['collisions']) for l in actual['links']),
        'added_components':components,'collision_masks':masks,
        'supports':{'count':len(brackets),'mass_kg':sum(c['mass_kg'] for c in brackets),
            'density_status':'Estimated steel density, not measured purchased hardware',
            'method':'Rigid same-link clamp plates, bolts, standoffs and narrow rails. CAD tube faces and payload underside are explicit mating planes; no global collision suppression.',
            'limitations':'Basket rails cantilever from the rear crossmember. Strength, screw preload, welds and fatigue are not FEA- or hardware-validated.'},
        'gripper':{'joint':moving_joint,'open_position_m':travel,'closed_position_m':0.,
            'position_tolerance_m':grip['position_tolerance_m'],'maximum_speed_m_s':grip['maximum_settled_speed_m_s'],
            'stable_time_s':grip['stable_time_s'],'command_velocity_m_s':grip['command_velocity_m_s'],
            'closed_gap_m':closed_gap,'open_gap_m':closed_gap+travel,'effort_limit_n':effort,
            'controller_damping_derivation':{'method':'Isolated slider critical damping D=2*zeta*sqrt(P*m); fixed-parent approximation, not native validation.',
                'moving_mass_kg':moving_mass,'p_gain_n_m':grip['p_gain_n_m'],'estimated_damping_ratio':grip['estimated_damping_ratio'],
                'd_gain_ns_m':damping,'maximum_step_s':actual['physics']['maximum_step_s'],
                'step_times_d_over_m':actual['physics']['maximum_step_s']*damping/moving_mass},
            'axis_in_joint_frame':next(j['axis'] for j in actual['joints'] if j['name']==moving_joint),
            'opening_direction_in_grasp_frame':[-1,0,0],
            'source_jaw_half_spaces_in_grasp_x_m':supports,
            'continuous_jaw_pair_separation_proof':'Every native mesh vertex lies in its declared half-space. With q>=0, the complete left body translates by -q along grasp X; minimum separation is closed_gap+q throughout the interval. The pair exclusion does not remove either jaw from external contact.',
            'guide_approximation':'Ideal prismatic parent-child guide, not the original CAD four-bar or validated tooth/contact mechanics.',
            'grasp_frame_note':'Existing grasp_center is fixed at CAD q0. Unilateral opening shifts the gap midpoint by -q/2; this is not a calibrated physical gripping point.'},
        'bin':{'frame':'chassis','root_link':actual['root_link'],'inner_min_m':basket['inner_min_m'],
            'inner_max_m':basket['inner_max_m'],'collision_names':[c['name'] for c in basket_parts(basket)],
            'open_top':True,'wall_thickness_m':basket['wall_thickness_m']},
        'wrist_revision':{'parameter':'demo_wrist_pitch_command_velocity_rad_s','before_rad_s':old['control']['arm']['wrist_pitch_joint']['command_velocity'],
            'after_rad_s':speed,'gains_effort_and_joint_limit_unchanged':True,
            'reason':'Commissioning hypothesis after .336151rad/s observed with .3rad/s reference and unsaturated effort; no hardware or native PASS claimed.'}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('profile','asset-root','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--expected-source-sha256',required=True)
    parser.add_argument('--parameters',type=Path,help='Complete replacement for the explicitly estimated layout/settings JSON')
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a fresh output directory')
    source=resolve_robot_profile(args.profile)
    if source.sha256!=args.expected_source_sha256:raise ValueError('Unexpected canonical source')
    settings=read(args.parameters) if args.parameters else copy.deepcopy(DEFAULTS)
    inputs=[args.profile,Path(__file__),ROOT/'scripts/prepare_cad_robot.py',ROOT/'src/uchuva_gazebo/robot_spec.py',
        ROOT/'src/uchuva_gazebo/robot_sdf.py',ROOT/'src/uchuva_gazebo/robot_kinematics.py',
        ROOT/'src/uchuva_gazebo/robot_collision_filters.py',ROOT/'configs/robots/robot_spec.schema.json']
    if args.parameters:inputs.append(args.parameters)
    frozen={p:p.read_bytes() for p in inputs};assets=verify_robot_assets(source,args.asset_root)
    evidence={'status':'estimado','source':'User-approved CAD-derived demonstration; original source RobotSpec '+source.sha256,
        'revision':sha(args.profile),'method':'Preserve native CAD surfaces, aggregate fixed rigid masses, use one ideal short prismatic jaw and explicitly estimated payload/basket primitives.',
        'uncertainty':'Battery count/type is requested; box dimensions/masses, electronics enclosure, basket and actuator force are manual_initial_guess, not measured hardware. No electrical capacity or LiFePO4 performance is inferred. Native dynamics, contacts and harvesting must be tested separately.'}
    robot,report=derive(source,args.asset_root.resolve(),settings,evidence)
    args.output.mkdir(parents=True);shutil.copytree(args.asset_root,args.output/'assets')
    if verify_robot_assets(robot,args.output/'assets')!=assets:raise ValueError('Copied CAD assets changed')
    write(args.output/'profile.json',robot.to_dict());write(args.output/'parameters.json',settings)
    sdf=ET.Element('sdf',version='1.10');sdf.append(resolved_robot_model(robot));ET.indent(sdf,space='  ')
    (args.output/'model.sdf').write_text(ET.tostring(sdf,encoding='unicode')+'\n',encoding='utf-8')
    contract=resolved_robot_contract(robot)
    if contract.get('native_harvest_eligible'):raise ValueError('Demo preparator cannot grant harvest admission')
    write(args.output/'robot_contract.json',contract)
    snapshots=args.output/'source_snapshot';snapshots.mkdir()
    for path,content in frozen.items():
        if path.read_bytes()!=content:raise ValueError('Input changed during preparation')
        (snapshots/path.name).write_bytes(content)
    write(args.output/'derivation.json',{'status':'PREPARED_NOT_NATIVE_VALIDATED','native_validation':'NO EJECUTADO',
        'source_robot_spec_sha256':source.sha256,'robot_spec_sha256':robot.sha256,
        'profile_sha256':sha(args.output/'profile.json'),'sdf_sha256':sha(args.output/'model.sdf'),'asset_root':'assets',
        'parameter_status':'manual_initial_guess except CAD-derived jaw geometry and inherited physical properties',
        'source_files_sha256':{str(p):hashlib.sha256(b).hexdigest() for p,b in frozen.items()},**report})
    print(json.dumps({'robot_spec_sha256':robot.sha256,'output':str(args.output),'gripper':report['gripper'],'bin':report['bin'],'mass_kg':report['total_mass_kg']},indent=2))


if __name__=='__main__':main()
