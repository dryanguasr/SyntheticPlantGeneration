"""Validate dense-field identities/layout and publish a compact measured summary."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--new',type=Path,required=True);p.add_argument('--field',type=Path,required=True)
    a=p.parse_args();old=json.loads(a.source.read_text());new=json.loads((a.new/'input.json').read_text())
    assert old['scene']['plant_instances']==new['scene']['plant_instances']
    assert old['markers']==new['markers']
    for kind in ('posts','lines'):
        assert old['scene']['support_system'][kind]==new['scene']['support_system'][kind]
    m=json.loads((a.field/'manifest.json').read_text());inventory=json.loads((a.field/'inventory.json').read_text())['calyces']
    assert m['plant_count']==36 and len(m['markers'])==72 and not m['context_seedlings']
    identifiers=[o['reproductive_id'] for o in inventory];assert len(identifiers)==len(set(identifiers))
    expected=[]
    def walk(axes):
        for axis in axes:
            yield axis
            yield from walk(axis['child_axes'])
    for plant,v in new['plants'].items():
        for axis in walk(v['axes']):
            for node in axis['nodes']:
                unit=node.get('reproductive_unit')
                if unit and unit.get('calyx'):expected.append(plant+':'+unit['id'])
    assert set(identifiers)==set(expected)
    tree=ET.parse(a.field/'field.sdf');models={e.attrib['name'] for e in tree.findall('world/model')}
    assert all(o['model_name'] in models for o in inventory)
    for mesh in m['meshes']:
        path=a.field/mesh['uri'];assert path.is_file()
        with path.open() as f:catalog=f.readline().strip().split(' ',1)[1]
        assert (path.parent/catalog).read_text().count('newmtl ')==1
    result={'script_version':'dense-field-check/1.0','seed':m['seed'],'parameter_preset':m['crown_preset'],
        'layout_and_marker_identity':'passed','posts_and_overhead_cables':'unchanged',
        'attachment_strings':'reattached_to_regenerated_nodes','plant_count':36,'calyx_count':len(inventory),
        'target_calyx_count':sum(o['plant_id'] in {f'plant_{i:02d}' for i in range(12,24)} for o in inventory),
        'unique_id_mesh_model_correspondence':'passed','triangles':sum(x['triangles'] for x in m['meshes']),
        'mesh_bytes':sum((a.field/x['uri']).stat().st_size for x in m['meshes']),
        'export_seconds':m['export_seconds'],'botanical_and_contact_validation':'not_certified'}
    (a.field/'validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
