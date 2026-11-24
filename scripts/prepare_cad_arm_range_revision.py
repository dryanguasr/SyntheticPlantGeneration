#!/usr/bin/env python3
"""Resolve a traceable tentative TOTAL arm-travel revision, never a live update."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile


def arm_range_revision(profile,revision,source,digest):
    base=resolve_robot_profile(profile);before=base.to_dict();staged=copy.deepcopy(before)
    if base.sha256!=revision['base_robot_spec_sha256']:raise ValueError('Arm range revision source identity mismatch')
    names=list(base.joint_names)
    if len(names)!=5 or set(names)!=set(revision['joint_names']):raise ValueError('Exactly the five declared arm joints are required')
    if revision['status']!='user_reported_approximate' or revision['centering_status']!='engineering_heuristic_unconfirmed':
        raise ValueError('Tentative user travel and unconfirmed centering must remain explicit')
    lower,upper=revision['candidate_limits_rad'];total=revision['total_travel_rad']
    values=[lower,upper,total,revision['original_total_travel']]
    if not all(type(v) in (int,float) and math.isfinite(v) for v in values):raise ValueError('Finite range values are required')
    if revision['original_unit']!='degree' or abs(math.radians(revision['original_total_travel'])-total)>1e-12:
        raise ValueError('Original travel and SI conversion disagree')
    if lower>=0 or upper<=0 or abs(upper-lower-total)>1e-12 or abs(lower+upper)>1e-12:
        raise ValueError('Symmetric candidate must span the reported TOTAL travel')
    provenance={'status':'estimado','source':source,'revision':digest,
        'method':revision['interpretation']+' '+revision['centering_assumption'],
        'uncertainty':'user_reported_approximate; centering engineering_heuristic_unconfirmed; no measured hard stops'}
    overrides={};changed=[]
    for index,joint in enumerate(staged['joints']):
        if joint['name'] not in names:continue
        for field,value in (('lower',lower),('upper',upper)):
            pointer=f'/joints/{index}/limits/{field}'
            metadata=staged['parameter_metadata'].get(pointer)
            if metadata and metadata['update_class']!='model_regeneration':
                raise ValueError('Existing range update contract does not allow model regeneration')
            staged['parameter_metadata'][pointer]={**provenance,'update_class':'model_regeneration'}
            overrides[pointer]={'value':value,'provenance':provenance}
            changed.append({'joint':joint['name'],'path':pointer,'previous_value_rad':joint['limits'][field],
                            'candidate_value_rad':value})
    resolved=resolve_robot_profile(staged,overrides);after=resolved.to_dict()
    # Compare every physical/control field after restoring only the 10 bound
    # values. Metadata/history are the only permitted additional differences.
    restored=copy.deepcopy(after)
    for index,joint in enumerate(before['joints']):
        if joint['name'] in names:
            for field in ('lower','upper'):restored['joints'][index]['limits'][field]=joint['limits'][field]
    for key in ('parameter_metadata','override_history'):restored[key]=copy.deepcopy(before[key])
    if restored!=before:raise ValueError('Arm range revision changed an undeclared profile field')
    return base,resolved,changed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('profile','revision','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();revision=json.loads(args.revision.read_text());digest=hashlib.sha256(args.revision.read_bytes()).hexdigest()
    register=revision.get('observation_register')
    if register and hashlib.sha256((ROOT/register['path']).read_bytes()).hexdigest()!=register['sha256']:
        raise ValueError('The source observation register has changed; resolve a new explicit revision')
    base,resolved,changes=arm_range_revision(args.profile,revision,args.revision.as_posix(),digest)
    args.output.mkdir(parents=True,exist_ok=False)
    for name,data in (('profile.json',resolved.to_dict()),('source_profile.json',base.to_dict()),('range_revision.json',revision)):
        (args.output/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    report={'status':'PREPARED_EXPLORATORY_NOT_NATIVE_ADMITTED','source_robot_spec_sha256':base.sha256,
        'candidate_robot_spec_sha256':resolved.sha256,'range_revision_sha256':digest,'changed_physical_fields':changes,
        'only_five_arm_lower_upper_bounds_changed':True,'user_report_status':revision['status'],
        'centering_status':revision['centering_status'],'original_value_degree_total':revision['original_total_travel'],
        'value_si_rad_total':revision['total_travel_rad'],'acceptance_threshold_changes':[],
        'observation_register':register,
        'consumed_source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__),ROOT/'src/uchuva_gazebo/robot_spec.py',ROOT/'configs/robots/robot_spec.schema.json')}}
    (args.output/'derivation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':report['status'],'candidate_sha256':resolved.sha256,'changed_bounds':len(changes)}))


if __name__=='__main__':main()
