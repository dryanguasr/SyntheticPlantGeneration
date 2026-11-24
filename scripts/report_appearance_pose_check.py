"""Verify and display four structural checks separately from the 50-view factorial."""
from pathlib import Path
import argparse
import json
import hashlib

import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,data):Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    root=args.root.resolve();base=root/'calibration/round_02';check=root/'calibration/round_02_leaf_pose_check'
    assert read(check/'completion.json')['captures']==4
    out=check/'review';out.mkdir(exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
    bold=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',28)
    panel=Image.new('RGB',(1440,1520),'#f2f1ec');draw=ImageDraw.Draw(panel)
    draw.text((20,15),'Pose foliar: mismas plantas, tamaños y cámara; cambio de inclinación local',font=bold,fill='#18372f')
    draw.text((20,56),'Izquierda: hojas mayormente de canto. Derecha: hipótesis de orientación; todavía no aprobada.',font=font,fill='#555555')
    records=[]
    for i in range(4):
        name=f'plant_{i:02d}_view0_LT';a,b=base/name,check/name
        left,right=read(a/'capture.json'),read(b/'capture.json')
        assert left['assignments']==right['assignments'],'Pose changed class assignment'
        for folder,capture in [(a,left),(b,right)]:
            assert sha(folder/'rgb.png')==capture['rgb_sha256']
            assert sha(folder/'mask_calyx_crisp_v2.png')==capture['mask_sha256']
        ca,cb=read(a/'camera.json'),read(b/'camera.json')
        error=float(np.max(np.abs(np.asarray(ca['matrix_world'])-np.asarray(cb['matrix_world']))))
        assert error<1e-6 and ca['intrinsic_matrix']==cb['intrinsic_matrix']
        audit=read(check/f'plant_{i:02d}_mesh_audit.json')
        records.append(dict(plant=i,camera_max_abs_difference=error,appearance_assignments_equal=True,
            physical_collisions=audit['physical_collision_count'],clearance_violations=audit['clearance_violation_count'],
            training_allowed=False,old_rgb_sha256=left['rgb_sha256'],new_rgb_sha256=right['rgb_sha256']))
        for j,(folder,label) in enumerate([(a,'Antes de corregir pose'),(b,'Después: misma cámara')]):
            x=15+j*715;y=100+i*350
            draw.text((x,y),f'Planta {i+1} · {label}',font=font,fill='#18372f')
            im=ImageOps.contain(Image.open(folder/'rgb.png').convert('RGB'),(690,310))
            panel.paste(im,(x+(690-im.width)//2,y+35))
    panel.save(out/'comparacion_pose_foliar.jpg',quality=95)
    write(out/'verification.json',dict(purpose='four technical checks, not a new factorial bank',checks=records,human_review='pending'))
    gallery=base/'review/index.html';document=gallery.read_text(encoding='utf-8')
    marker='<h2>Comprobación técnica de pose foliar</h2>'
    if marker not in document:
        document=document.replace('</main>',marker+'<p>Cuatro imágenes adicionales, separadas de las 50 comparaciones anteriores. Mismos órganos y dimensiones; nueva pose foliar y cámara preservada. No se permite entrenamiento: persisten intersecciones.</p><img src="../../round_02_leaf_pose_check/review/comparacion_pose_foliar.jpg"></main>')
        gallery.write_text(document,encoding='utf-8')
    manifest=read(base/'review/report_manifest.json');manifest['files']['index.html']=sha(gallery)
    manifest['structural_diagnostic']=dict(images=4,profile_sha256=sha(check/'profiles.json'),verification=str(out/'verification.json'),verification_sha256=sha(out/'verification.json'))
    write(base/'review/report_manifest.json',manifest)
    print(json.dumps(records,indent=2))


if __name__=='__main__':main()
