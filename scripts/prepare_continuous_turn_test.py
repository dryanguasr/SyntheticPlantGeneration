"""Create a recoverable end-turn technical mission, preserving the full route."""
import argparse
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    mission=json.loads((a.source/'mission.json').read_text());waypoints=mission['waypoints']
    turn=[i for i,w in enumerate(waypoints) if w['phase'].startswith('inward_turn_')]
    if not turn:raise ValueError('No inward turn in mission')
    mission['waypoints']=waypoints[min(turn)-1:max(turn)+2];mission['technical_scope']='terminal turn only; not complete experimental route'
    tree=ET.parse(a.source/'flight.sdf')
    first=mission['waypoints'][0];tree.find("world/model[@name='neo_approx']/pose").text=' '.join(map(str,[*first['position'],0,0,first['yaw']]))
    for tag in ('uri','albedo_map','roughness_map','normal_map'):
        for node in tree.findall('.//'+tag):
            if node.text and '://' not in node.text and not node.text.startswith('/mnt/'):
                path=(a.source/node.text).resolve().as_posix()
                if path[1:3]==':/':path='/mnt/'+path[0].lower()+path[2:]
                node.text=path
    for name in ('preflight.json','inventory.json','provenance.json'):shutil.copy2(a.source/name,a.output/name)
    (a.output/'mission.json').write_text(json.dumps(mission,indent=2));ET.indent(tree);tree.write(a.output/'flight.sdf',encoding='utf-8',xml_declaration=True)


if __name__=='__main__':main()
