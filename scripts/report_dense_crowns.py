"""Assemble paired scientific comparisons and metrics, without changing images used for measurement."""
import argparse
import json
from pathlib import Path
import statistics
import shutil
from PIL import Image, ImageDraw, ImageFont

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--field',type=Path,required=True)
    p.add_argument('--reviews',type=Path,nargs='+',required=True);p.add_argument('--reference',type=Path,required=True)
    a=p.parse_args();out=a.field/'review';out.mkdir(exist_ok=True)
    provenance=json.loads((a.field/'comparison.json').read_text())
    rows=[];locations={}
    for directory in a.reviews:
        for pattern in ('*_dense.blend','*_mesh_contacts.json','*.png'):
            for artifact in directory.glob(pattern):shutil.copy2(artifact,out/artifact.name)
        for r in json.loads((directory/'metrics.json').read_text()):
            rows.append(r);locations[(r['plant_id'],r['version'])]=directory
    ids=sorted({r['plant_id'] for r in rows});ratios=[]
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',25)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
    for face in ['front','back']:
        board=Image.new('RGB',(1440,1040),(239,240,232));d=ImageDraw.Draw(board)
        d.text((25,18),f'Frondosidad por arbusto | {"frente" if face=="front" else "reverso"}',font=font,fill='black')
        for col,identifier in enumerate(ids):
            pair={r['version']:r for r in rows if r['plant_id']==identifier}
            ratio=pair['after']['coverage'][face]/pair['before']['coverage'][face];ratios.append(ratio)
            d.text((col*480+15,60),f'{identifier}: cobertura +{(ratio-1)*100:.1f} %',font=small,fill='black')
            for j,version in enumerate(['before','after']):
                im=Image.open(locations[(identifier,version)]/f'{identifier}_{version}_{face}.png').convert('RGBA')
                # Same crop and scale for every synthetic image; alpha compositing is presentation only.
                im=im.crop((110,170,540,795));im.thumbnail((230,570))
                tile=Image.new('RGB',im.size,(226,229,214));tile.paste(im,mask=im.getchannel('A'))
                board.paste(tile,(col*480+j*240+5,110))
                d.text((col*480+j*240+25,87),'Anterior' if j==0 else 'Nueva',font=small,fill='black')
            d.text((col*480+15,462),f'Hojas: área de malla {pair["before"]["leaf_mesh_area_m2"]:.2f} → {pair["after"]["leaf_mesh_area_m2"]:.2f} m²',font=small,fill='black')
        reference=Image.open(a.reference).convert('RGB');reference.thumbnail((960,480));board.paste(reference,((1440-reference.width)//2,520))
        d.text((20,1005),'Referencia real cualitativa; escala y cámara no equivalentes. No es validación botánica.',font=small,fill='black')
        board.save(out/f'comparison_{face}.jpg',quality=94)
    result={'script_version':'dense-crown-review/1.0','parameter_preset':provenance['parameter_preset'],
            'seed':provenance['seed'],'metrics':rows,'median_paired_coverage_ratio':statistics.median(ratios),
            'coverage_target_met':statistics.median(ratios)>=1.3,
            'interpretation':'Leaf alpha silhouette / fixed image area; not occlusion fraction; mesh area includes modeled surfaces',
            'human_validation':'pending'}
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='metrics'}))

if __name__=='__main__':main()
