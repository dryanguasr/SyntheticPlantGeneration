"""Keep individual crop obstacles and open aisles; remove only chase camera."""
import argparse
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def main():
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);a=p.parse_args()
    path=a.package/'flight.sdf';backup=a.package/'flight_before_corridor_physics.sdf'
    if backup.exists():raise FileExistsError(backup)
    preflight=json.loads((a.package/'preflight.json').read_text())
    if preflight['clearance_policy']!='individual_plant_boxes_and_support_capsules' or not preflight['passed']:
        raise ValueError('Individual obstacle preflight required')
    tree=ET.parse(path);world=tree.getroot().find('world')
    link=world.find("model[@name='field']/link")
    # Retain all physical support capsules. Add conservative plant boxes,
    # rather than filling the entire multi-row field (which would close aisles).
    original=len(link.findall('collision'))
    for plant,(low,high) in preflight['plant_mesh_bounds_m'].items():
        collision=ET.SubElement(link,'collision',name=f'plant_envelope_{plant}')
        ET.SubElement(collision,'pose').text=' '.join(map(str,[(low[d]+high[d])/2 for d in range(3)]+[0,0,0]))
        ET.SubElement(ET.SubElement(ET.SubElement(collision,'geometry'),'box'),'size').text=' '.join(str(high[d]-low[d]) for d in range(3))
    base=world.find("model[@name='neo_approx']/link[@name='base_link']")
    chase=base.find("sensor[@name='chase']")
    if chase is not None:base.remove(chase)
    shutil.copy2(path,backup);ET.indent(tree);tree.write(path,encoding='utf-8',xml_declaration=True)
    (a.package/'physics_optimization.json').write_text(json.dumps(dict(
        method='individual_plant_boxes_plus_original_structural_capsules',original_colliders=original,
        added_boxes=len(preflight['plant_mesh_bounds_m']),visuals='unchanged',chase_sensor='removed',
        limitation='Conservative navigation obstacles, not a leaf-contact simulator'),indent=2))


if __name__=='__main__':main()
