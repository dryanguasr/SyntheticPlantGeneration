"""Recover individual original calyces and freeze the low-flight pilot package."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.field import element as e, material
from uchuva_gazebo.neo import neo_model


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--field', type=Path, required=True)
    p.add_argument('--capture-plan', type=Path, required=True)
    p.add_argument('--visual-package', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output; out.mkdir(parents=True, exist_ok=True)
    (out/'meshes').mkdir(exist_ok=False); (out/'evaluator').mkdir()
    source = json.loads((args.field/'manifest.json').read_text())
    centers = json.loads(args.capture_plan.read_text())['centers']
    organs = sorted((o for o in source['organs'] if o['semantic_class']=='calyx'),
                    key=lambda o:o['reproductive_id'])
    target = {f'plant_{i:02d}' for i in range(12,24)}
    assert len(organs)==2280 and sum(o['plant_id'] in target for o in organs)==747
    mapping = {}; inventory = []
    for i,o in enumerate(organs):
        name = f'calyx_{i:05d}'
        row = {**o, 'model_name':name,'uri':f'meshes/{name}.obj',
               'panoptic_label':1,'panoptic_instance':len(organs)-i,
               'target':o['plant_id'] in target, **centers[o['reproductive_id']]}
        inventory.append(row)
        for mesh in o['meshes']: mapping[(mesh,o['object'])] = row
    colors = {m['uri']:m['color'] for m in source['meshes']}
    calyx_files = sorted({m for o in organs for m in o['meshes']})
    for uri in calyx_files:
        vertices=normals=0; start_v=start_n=0; dest=None
        with (args.field/uri).open() as stream:
            for line in stream:
                if line.startswith('# source '):
                    if dest: dest.close()
                    row=mapping[(uri,line.strip()[9:])]
                    row['color']=colors[uri]
                    dest=(out/row['uri']).open('w')
                    dest.write(f'mtllib surface.mtl\nusemtl {row["model_name"]}\no {row["model_name"]}\n')
                    start_v,start_n=vertices,normals
                elif line.startswith('v '): vertices+=1; dest.write(line)
                elif line.startswith('vn '): normals+=1; dest.write(line)
                elif line.startswith('f '):
                    indices=[v.split('//') for v in line.split()[1:]]
                    dest.write('f '+' '.join(f'{int(v)-start_v}//{int(n)-start_n}' for v,n in indices)+'\n')
        if dest: dest.close()
    (out/'meshes/surface.mtl').write_text(''.join(
        f'newmtl {o["model_name"]}\nKa {" ".join(map(str,o["color"][:3]))}\nKd {" ".join(map(str,o["color"][:3]))}\n'
        for o in inventory))
    tree=ET.parse(args.field/'field.sdf'); world=tree.getroot().find('world')
    for model in list(world.findall('model')):
        if model.attrib['name']!='field': world.remove(model)
    link=world.find('model/link')
    for visual in list(link.findall('visual')):
        uri=visual.find('geometry/mesh/uri')
        if uri is None: continue
        if uri.text in calyx_files: link.remove(visual)
        else: uri.text=Path(os.path.relpath(args.field/uri.text,out)).as_posix()
    for row in inventory:
        model=e(world,'model',name=row['model_name']); e(model,'static','true')
        visual=e(e(model,'link',name='link'),'visual',name='surface')
        e(e(e(visual,'geometry'),'mesh'),'uri',row['uri']); material(visual,row['color'])
        label=e(model,'plugin',filename='gz-sim-label-system',name='gz::sim::systems::Label')
        e(label,'label',1)
    visual=json.loads((args.visual_package/'visual_manifest.json').read_text())
    shutil.copytree(args.visual_package,out/'neo_visual')
    assets=[{**a,'uri':'neo_visual/'+a['uri']} for a in visual['meshes']]
    neo=neo_model(start=(-4.6,0,.65),visual_assets=assets)
    neo.find('pose').text='-4.6 0 .65 0 0 -1.5707963267948966'
    base=neo.find("link[@name='base_link']")
    camera=base.find("sensor[@name='onboard']")
    camera.find('pose').text=f'.068 0 .005 0 {math.radians(20)} 0'
    import copy
    segmentation=copy.deepcopy(camera); segmentation.set('name','instances'); segmentation.set('type','segmentation')
    segmentation.find('topic').text='/neo/instances'; segmentation.find('update_rate').text='15'
    e(segmentation.find('camera'),'segmentation_type','panoptic')
    base.append(segmentation); world.append(neo)
    world.find('physics/real_time_factor').text='.5'
    ET.indent(tree); tree.write(out/'flight.sdf',encoding='utf-8',xml_declaration=True)
    model=ROOT/'mobile/android/app/src/main/assets/detector.onnx'
    sha=digest(model)
    assert sha=='19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca'
    waypoints=[]
    for i,(height,yaw,start,end) in enumerate(((.65,-math.pi/2,-4.6,4.6),(.95,-math.pi/2,4.6,-4.6),
                                              (.65,math.pi/2,-4.6,4.6),(.95,math.pi/2,4.6,-4.6))):
        waypoints.extend([{'position':[start,0,height],'yaw':yaw,'phase':f'transition_{i}'},
                          {'position':[end,0,height],'yaw':yaw,'phase':f'pass_{i}'}])
    config={'script_version':'low-flight-pilot/0.1','seed':source['seed'],'parameter_preset':'central_aisle_low_v1',
        'waypoints':waypoints,'max_speed_m_s':.20,'margin_m':.15,'target_plants':sorted(target),
        'model_sha256':sha,'model_version':'natural_hybrid_alpha_045','confidence':.25,'additional_nms':False,
        'camera':{'width':1280,'height':720,'fps':15,'evaluation_hz':5,'horizontal_fov_rad':math.pi/2,
                  'pitch_rad':math.radians(20),'K':[[640,0,640],[0,640,360],[0,0,1]],'distortion':[0]*5},
        'marker':{'dictionary':'DICT_4X4_100','side_m':.10},
        'triangulation':{'min_observations':3,'min_parallax_deg':3,'max_reprojection_px':3},
        'association':{'flow_forward_backward_px':1.5,'min_box_iou':.2,'ambiguity_gap':.15},
        'evaluation':{'min_visible_pixels':16,'min_iou':.5},
        'parameter_status':'engineering_heuristic_frozen_before_evaluation',
        'source_manifest_sha256':digest(args.field/'manifest.json'),
        'source_capture_plan_sha256':digest(args.capture_plan),
        'inventory_count':len(inventory),'target_inventory_count':747}
    (out/'mission.json').write_text(json.dumps(config,indent=2))
    (out/'evaluator/inventory.json').write_text(json.dumps({'script_version':config['script_version'],
        'seed':source['seed'],'parameter_preset':config['parameter_preset'],'calyces':inventory,'markers':source['markers']},indent=2))
    (out/'configuration.sha256').write_text(digest(out/'mission.json')+'\n')
    print(json.dumps({'inventory':len(inventory),'target':747,'config_sha256':digest(out/'mission.json')}))


if __name__=='__main__': main()
