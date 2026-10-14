"""Small morphology and material fixtures; no reserved morphology or renders."""
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.basal_architecture import basal_scaffolds
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters
from uchuva_lsystem.segmentation_cycles import write,sha
from uchuva_lsystem.validation import validate_morphology_tree


def main():
    root=ROOT/'outputs/integral_diagnosis_20261014';out=root/'fixtures';out.mkdir(exist_ok=False)
    for seed in (814140,814141,814142):
        base=prepare_plant(generate_morphology_tree(seed,sparse_morphology_parameters('individual_dense_crown_v3')))
        write(out/f'baseline_{seed}.json',base.to_dict())
        for count in range(2,6):
            try:plant=basal_scaffolds(base,count)
            except ValueError as e:
                write(out/f'basal_{seed}_{count}_rejected.json',dict(reason=str(e)));continue
            write(out/f'basal_{seed}_{count}.json',plant.to_dict())
            write(out/f'basal_{seed}_{count}_validation.json',validate_morphology_tree(plant))
    old=ROOT/'outputs/continuous_row_20261008/field_batched'
    field=out/'normal_maps_field';field.mkdir()
    tree=ET.parse(old/'field.sdf');count=0;maps={}
    assets=ROOT/'assets/textures/current'
    for element in tree.findall('.//uri'):
        if element.text.startswith('meshes/'):
            element.text=(old/element.text).resolve().as_posix()
    for tag in ('albedo_map','roughness_map'):
        for e in tree.findall('.//'+tag):e.text=(old/e.text).resolve().as_posix()
    for metal in tree.findall('.//material/pbr/metal'):
        albedo=metal.findtext('albedo_map')
        if not albedo:continue
        name=Path(albedo).name.replace('_albedo','_normal');p=assets/name
        if not p.exists():raise FileNotFoundError(p)
        ET.SubElement(metal,'normal_map',{'type':'tangent'}).text=p.resolve().as_posix()
        count+=1;maps[name]=sha(p)
    ET.indent(tree);tree.write(field/'field.sdf',encoding='utf-8',xml_declaration=True)
    write(field/'provenance.json',dict(version='material-normal-assay/1.0',
        source_sha256=sha(old/'field.sdf'),source_geometry='same immutable mesh files',
        normal_maps=count,normal_map_sha256=maps,normal_space='tangent',
        stage='prepared_not_render_validated',impact_on_detection='not_measured'))
    print('FIXTURES',count,'normal maps',flush=True)


if __name__=='__main__':main()
