#!/usr/bin/env python3
"""Bound the two original Cuchilla CAD edges in the resolved cut-point frame.

Inputs are explicit and read-only. The STEP topology checks deliberately bind
this repository's original blade, rather than inferring a functional cutting
location from arbitrary solids. Output is geometric evidence, not calibration.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import (
    forward_kinematics, compose_poses, inverse_pose, transform_point)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(matrix, p):
    return [sum(matrix[4*i+j]*p[j] for j in range(3))+matrix[4*i+3]
            for i in range(3)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('profile', 'inventory', 'step', 'motion', 'admission', 'import-report', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    profile, inventory, step = args.profile.resolve(), args.inventory.resolve(), args.step.resolve()
    motion_path, admission_path, import_path = args.motion.resolve(), args.admission.resolve(), args.import_report.resolve()
    if args.output.exists():
        raise ValueError('Use a fresh output directory; previous evidence is preserved')
    def source_key(path):
        try: return str(path.relative_to(ROOT)).replace(chr(92), '/')
        except ValueError: return str(path)
    inputs = [profile, inventory, step, motion_path, admission_path, import_path, Path(__file__),
              ROOT/'src/uchuva_gazebo/robot_spec.py', ROOT/'src/uchuva_gazebo/robot_kinematics.py']
    before = {source_key(p): sha(p) for p in inputs}
    inv, motion, admission, imported = map(read, (inventory, motion_path, admission_path, import_path))
    robot = resolve_robot_profile(profile)
    data = robot.to_dict()
    fk = forward_kinematics(robot, {j['name']: 0 for j in data['joints'] if j['type'] != 'fixed'})
    shapes = {s['name']: (l['name'], s) for l in data['links'] for s in l['visuals']}
    ids = {p['occurrence_name_path'][-1]: 'part_'+str(i) for i,p in enumerate(imported['parts'])
           if p['occurrence_name_path'][0] == 'Gripper ensamble:1'}
    document = next(d for d in inv['documents'] if d['source_path'] == 'gripper/Cuchilla.ipt')
    if sha(step) != document['exports']['step']['sha256']:
        raise ValueError('STEP source changed')
    # STEP product coordinates use millimetres. These actual entity references
    # bind the straight bevel/underside intersection, not an AABB extremum alone.
    entities = {int(k): v for k,v in re.findall(r'#(\d+)\s*=\s*(.*?);', step.read_text(), re.S)}
    if entities[146] != "EDGE_CURVE('',#119,#120,#76,.T.)":
        raise ValueError('Unexpected STEP edge identity')
    def vertex(vertex_id):
        cart_id = int(re.findall(r'#(\d+)', entities[vertex_id])[0])
        values = entities[cart_id].split('(',2)[-1].rstrip(')')
        return [float(x)*.001 for x in values.split(',')]
    endpoints = [vertex(119), vertex(120)]
    if max(abs(a-b) for p,q in zip(endpoints, ([.012,0,-.0035],[-.012,0,-.0035])) for a,b in zip(p,q)) > 1e-14:
        raise ValueError('Unexpected CAD edge coordinates')
    references = lambda identifier: [int(x) for x in re.findall(r'#(\d+)', entities[identifier])]
    def descends(identifier, target, visited=None):
        if identifier == target: return True
        visited = set() if visited is None else visited
        if identifier in visited: return False
        visited.add(identifier)
        return any(descends(child,target,visited) for child in references(identifier))
    adjacent_faces = [k for k,v in entities.items() if v.startswith('ADVANCED_FACE(') and descends(k,146)]
    if adjacent_faces != [234,240]:
        raise ValueError('Unexpected bevel edge face adjacency')
    # Assembly-to-cut frame derived independently from the fixed housing visual.
    assembly = next(d for d in inv['documents'] if d['source_path'] == 'gripper/Gripper ensamble.iam')
    housing_occ = next(o for o in inv['occurrences'] if o['root_document_id'] == assembly['id']
                       and o['parent_id'] == assembly['id'] and o['name'] == 'Gripper y engranaje:1')
    link, housing = shapes[ids['Gripper y engranaje:1']]
    # Exact rigid inverse from the native 4x4; no external geometry dependency.
    native = housing_occ['transform_root_m']
    housing_robot = compose_poses(fk[link], housing['pose'])
    cut_from_robot = inverse_pose(fk['cut_point'])
    def gripper_to_cut(p):
        relative = [sum(native[4*j+i]*(p[j]-native[4*j+3]) for j in range(3)) for i in range(3)]
        return transform_point(cut_from_robot, transform_point(housing_robot, relative))
    samples = motion['samples']
    names = ('Cuchilla:1','Cuchilla:2')
    q0_errors = []
    for name in names:
        link, visual = shapes[ids[name]]
        if visual['geometry']['sha256'] != document['exports']['obj']['sha256']:
            raise ValueError('Blade asset changed')
        native_matrix = samples[0]['occurrence_transforms_m'][name]
        current_pose = compose_poses(fk[link], visual['pose'])
        for p in endpoints:
            a = gripper_to_cut(point(native_matrix,p))
            b = transform_point(cut_from_robot, transform_point(current_pose,p))
            q0_errors.append(math.dist(a,b))
    if max(q0_errors) > 1e-10:
        raise ValueError('Motion/FK frame mismatch')
    rows = []
    for sample in samples:
        rows.append({'driver_rad': sample['driver_rad'], 'segments_cut_m': {
            name:[gripper_to_cut(point(sample['occurrence_transforms_m'][name],p)) for p in endpoints]
            for name in names}})
    speed = {name: motion['point_speed_bounds_m_per_driver_rad'][name] for name in names}
    step_max = max(b['driver_rad']-a['driver_rad'] for a,b in zip(rows,rows[1:]))
    if admission['status'] != 'PASS' or [rows[0]['driver_rad'],rows[-1]['driver_rad']] != admission['interval_rad']:
        raise ValueError('Motion interval/admission mismatch')
    sampled_min = [min(p[k] for row in rows for seg in row['segments_cut_m'].values() for p in seg) for k in range(3)]
    sampled_max = [max(p[k] for row in rows for seg in row['segments_cut_m'].values() for p in seg) for k in range(3)]
    padding = max(speed.values())*step_max/2
    per_blade_bounds = {}
    for name in names:
        pad = speed[name]*step_max/2
        per_blade_bounds[name] = {
            'min_m': [min(p[k] for row in rows for p in row['segments_cut_m'][name])-pad for k in range(3)],
            'max_m': [max(p[k] for row in rows for p in row['segments_cut_m'][name])+pad for k in range(3)],
            'between_sample_padding_m': pad}
    after = {source_key(p): sha(p) for p in inputs}
    if before != after: raise ValueError('Inputs changed during read-only analysis')
    result = {'schema_version':'cad-blade-edge-envelope/1.0', 'status':'NOMINAL_GEOMETRIC_ENVELOPE_ONLY',
        'robot_spec_sha256':robot.sha256, 'source_files_sha256':before,
        'native_document':{'path':document['source_path'],'sha256':document['sha256'],
            'STEP_edge_id':146,'STEP_vertex_ids':[119,120],'STEP_line_id':76,
            'adjacent_STEP_face_ids':adjacent_faces,'adjacent_STEP_plane_ids':[18,22],
            'edge_endpoints_document_m':endpoints,'edge_length_m':math.dist(*endpoints),
            'evidence':'Straight intersection of bevel plane #18 and underside plane #22; not a labelled or calibrated hardware cutting edge.'},
        'frame':'ResolvedRobot cut_point, at nominal arm q0, fixed to wrist; invariant under a common arm/base rigid transform.',
        'current_cut_frame_geometry': 'Historical midpoint of transformed blade AABB centres; functional calibration pending.',
        'q0_FK_vs_native_motion_max_error_m':max(q0_errors),
        'q0':rows[0], 'maximum_opening':rows[-1], 'driver_interval_rad':admission['interval_rad'],
        'sample_count':len(rows),'maximum_sample_spacing_rad':step_max,
        'point_speed_bounds_m_per_driver_rad':speed,
        'source_global_four_bar_derivative_bounds':motion['four_bar_global_derivative_bounds'],
        'sampled_all_edges_aabb_cut_m':{'min_m':sampled_min,'max_m':sampled_max},
        'per_blade_continuous_aabb_cut_m':per_blade_bounds,
        'continuous_convex_bridge_aabb_cut_m':{'min_m':[x-padding for x in sampled_min],
            'max_m':[x+padding for x in sampled_max], 'between_sample_padding_m':padding},
        'continuous_proof':'Every edge point is a convex combination of its two endpoints. At any coordinate in a sampled interval, the nearest sampled coordinate is at most half that interval away; the validated global rigid-point speed bound limits endpoint displacement in Euclidean norm by L*delta/2. Padding each coordinate by this amount encloses every edge and the entire convex hull between both edges for the complete interval.',
        'limitations':['Enclosure is intentionally broader than an actual cutting locus. It does not establish that every enclosed point can cut or grip a pedicel.',
            'No longitudinal contact location, blade sharpness, force/friction, stem cutting law or hardware calibration is established.',
            'No CAD, profile, collision masks, plant poses, controller values or acceptance tolerances were changed.',
            'STEP topology is exact export geometry; motion is the nominal validated four-bar branch. No native dynamics acceptance follows.']}
    args.output.mkdir(parents=True)
    with (args.output/'result.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({k:result[k] for k in ('q0_FK_vs_native_motion_max_error_m','q0','maximum_opening','continuous_convex_bridge_aabb_cut_m')},indent=2))


if __name__ == '__main__': main()
