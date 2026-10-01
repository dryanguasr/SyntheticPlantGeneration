"""Add an approximate dynamic Neo and mission to the existing metric field."""
import argparse
import json
from pathlib import Path
import sys
import shutil
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.neo import neo_model,mission_waypoints,VERSION,SOURCE,LENGTH,WIDTH,HEIGHT,MASS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--field',type=Path,required=True)
    parser.add_argument('--no-crop',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--visual-package',type=Path,help='Local output of adapt_neo_visual.py')
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    tree=ET.parse(args.field/'field.sdf'); world=tree.getroot().find('world')
    for model in list(world.findall('model')):
        if model.attrib['name']!='field': world.remove(model)
    if args.no_crop:
        link=world.find("model[@name='field']/link")
        for node in list(link):
            if node.tag in ('visual','collision') and not node.attrib['name'].startswith('soil'):link.remove(node)
    else:
        for uri in world.findall('.//mesh/uri'):
            # sibling package remains portable when both directories are moved together
            import os
            uri.text=Path(os.path.relpath(args.field/uri.text,args.output)).as_posix()
    world.find('physics/max_step_size').text='.002'
    world.find('physics/real_time_factor').text='.5'
    assets=None; visual_metadata=None
    if args.visual_package:
        visual_metadata=json.loads((args.visual_package/'visual_manifest.json').read_text(encoding='utf-8'))
        if not visual_metadata.get('meshes'):
            raise ValueError('Visual package has no meshes')
        shutil.copytree(args.visual_package,args.output/'neo_visual')
        assets=[{**asset,'uri':f"neo_visual/{asset['uri']}"} for asset in visual_metadata['meshes']]
    world.append(neo_model(visual_assets=assets))
    ET.indent(tree); tree.write(args.output/'flight.sdf',encoding='utf-8',xml_declaration=True)
    source=json.loads((args.field/'manifest.json').read_text(encoding='utf-8'))
    metadata={'script_version':VERSION,'seed':source['seed'],'parameter_preset':'neo_approx_above_trellis_v2',
        'airframe':{'name':'DJI Neo approximate','dimensions_m':[LENGTH,WIDTH,HEIGHT],'mass_kg':MASS,
            'source':SOURCE,'envelope_status':'manufacturer_reported','shape_status':'engineering_heuristic'},
        'physics_status':'engineering_heuristic_not_DJI_calibrated','controller':'Gazebo MulticopterVelocityControl',
        'state_estimation':'simulation_ground_truth','propulsion':'four_MulticopterMotorModel_systems',
        'camera_status':'ideal_90deg_horizontal_FOV_not_calibrated_DJI_camera','waypoints':mission_waypoints(),
        'field_source':str(args.field.resolve()),'field_seed':source['seed'],'visual_lod':source.get('visual_lod'),
        'aerial_batch':source.get('aerial_batch'),
        'external_visual':visual_metadata,
        'controller_tuning':{'velocity_time_constants_s':[.5,.5,.25],
            'command_acceleration_limit_m_s2':.5,'status':'engineering_heuristic'},
        'limitations':['No wind, calibrated rotor data or DJI firmware','Canopy collision remains incomplete',
            'Above-trellis survey, not close-range fruit inspection','No real-world flight safety claim']}
    if visual_metadata:
        metadata['airframe']['shape_status']=visual_metadata['source'].get('kind','external_mesh')+'_engineering_heuristic'
    (args.output/'mission.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
    sdf=ET.Element('sdf',version='1.9'); sdf.append(neo_model(start=(0,0,.08),visual_assets=assets))
    ET.indent(sdf); ET.ElementTree(sdf).write(args.output/'neo_approx.sdf',encoding='utf-8',xml_declaration=True)
    print(args.output/'flight.sdf')


if __name__=='__main__':main()
