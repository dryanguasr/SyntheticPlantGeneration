"""Conservative whole-field collider for a route strictly outside its envelope."""
import argparse
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def main():
    parser=argparse.ArgumentParser();parser.add_argument('package',type=Path)
    args=parser.parse_args();path=args.package/'flight.sdf'
    backup=args.package/'flight_before_physics_optimization.sdf'
    if backup.exists():raise FileExistsError(backup)
    audit=json.loads((args.package/'preflight.json').read_text())
    if not audit['passed'] or audit['minimum_margin_m']<.15:raise ValueError('Exterior route not certified')
    lo,hi=audit['full_mesh_bounds_m'];tree=ET.parse(path);world=tree.getroot().find('world')
    field=world.find("model[@name='field']/link")
    removed=0
    for collision in list(field.findall('collision')):field.remove(collision);removed+=1
    collision=ET.SubElement(field,'collision',name='conservative_whole_crop_envelope')
    ET.SubElement(collision,'pose').text=' '.join(map(str,[(lo[d]+hi[d])/2 for d in range(3)]+[0,0,0]))
    ET.SubElement(ET.SubElement(ET.SubElement(collision,'geometry'),'box'),'size').text=' '.join(str(hi[d]-lo[d]+.000002) for d in range(3))
    base=world.find("model[@name='neo_approx']/link[@name='base_link']")
    chase=base.find("sensor[@name='chase']")
    if chase is not None:base.remove(chase)
    shutil.copy2(path,backup);ET.indent(tree);tree.write(path,encoding='utf-8',xml_declaration=True)
    (args.package/'physics_optimization.json').write_text(json.dumps({'method':'conservative_whole_crop_AABB',
        'removed_field_colliders':removed,'replacement_colliders':1,'bounds_m':[lo,hi],
        'scope':'Exterior flight only; interior free spaces intentionally blocked; not a plant-contact simulator',
        'visuals':'unchanged','chase_sensor':'removed; RGB onboard and panoptic remain'},indent=2))


if __name__=='__main__':main()
