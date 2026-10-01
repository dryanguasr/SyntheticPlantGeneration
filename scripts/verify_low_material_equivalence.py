"""Verify that catalog splitting changed no geometry, normals, identity or material value."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('old',type=Path);p.add_argument('new',type=Path)
    args=p.parse_args();config=json.loads((args.new/'mission.json').read_text())
    catalog={};name=None
    for line in (args.old/'meshes/surface.mtl').read_text().splitlines():
        if line.startswith('newmtl '):name=line.split()[1];catalog[name]=[]
        if name is not None:catalog[name].append(line)
    count=0;hashes={}
    for old in sorted((args.old/'meshes').glob('calyx_*.obj')):
        new=args.new/'meshes'/old.name
        a=old.read_bytes().split(b'\n',1)[1];b=new.read_bytes().split(b'\n',1)[1]
        if a!=b:raise ValueError(f'Geometry/normal/material assignment changed: {old.name}')
        if (args.new/'meshes'/f'{old.stem}.mtl').read_text().splitlines()!=catalog[old.stem]:
            raise ValueError(f'Material values changed: {old.stem}')
        hashes[old.stem]=hashlib.sha256(a).hexdigest();count+=1
    for filename in ('flight.sdf','mission.json','evaluator/inventory.json'):
        if (args.old/filename).read_bytes()!=(args.new/filename).read_bytes():raise ValueError(f'Changed {filename}')
    result={k:config[k] for k in ('script_version','seed','parameter_preset')}
    result.update({'passed':count==2280,'identical_meshes':count,'identical_materials':count,
                   'identical_sdf_inventory_mission':True,'geometry_sha256':hashes})
    (args.new/'material_equivalence.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='geometry_sha256'}))


if __name__=='__main__':main()
