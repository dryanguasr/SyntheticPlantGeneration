"""Inspect four complete, isolated sample pairs; never append a dataset."""
from pathlib import Path
from collections import Counter
import sys, subprocess
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
from PIL import Image,ImageDraw,ImageFont
from uchuva_lsystem.nodal_automation import read,write,sha


def report(out):
    plan=read(out/'plan.json');source=Path(plan['source'])
    for p,h in read(out/'source_lock.json')['files'].items():assert sha(p)==h,p
    for p,item in read(out/'baseline.json')['locks'].items():
        assert sha(p)==item['sha256'],p
        if item.get('files'):
            for f,h in read(p)['files'].items():assert sha(f)==h,f
    assert read(source/'pause_requested.json')['active']
    for plant in read(source/'dataset/pool_lock.json')['plants']:
        for k in ('plant','admission'):assert sha(plant[k])==plant[k+'_sha256']
    rows=[];stages={};scene_stats=[]
    for sid in sorted({r['scene_id'] for r in plan['views']}):
        result=read(out/f'{sid}_result.json')
        assert result['all_geometry_unchanged']
        stages.update({(sid,iid):p for iid,p in result['surface_plans'].items()})
        a=read(out/f'{sid}_assignments.json');c=Counter(v['class_id'] for v in a.values())
        scene_stats.append(dict(scene_id=sid,assigned_classes=dict(c),overmature_fraction=c[2]/len(a)))
    expected=[v['source_view'] for v in plan['views']]
    for name in expected:
        r=read(out/name/'view.json');original=read(source/'dataset/views'/name/'view.json')
        assert r['status']=='complete_preview' and r['mask_exactly_identical'] and r['geometry_unchanged']
        for k in ('image','mask','label'):assert sha(r[k])==r[k+'_sha256'],r[k]
        assert r['mask_sha256']==original['mask_sha256']
        assert r['camera_matrix']==original['camera_matrix']
        lines=Path(r['label']).read_text(encoding='utf-8').splitlines()
        assert len(lines)==len(r['instances'])
        for line,i in zip(lines,r['instances']):assert int(line.split()[0])==i['class_id']
        c=Counter(i['class_id'] for i in r['instances'])
        assert c[2]/len(r['instances'])<=plan['visible_overmature_cap']
        r['visible_class_counts']=dict(c);r['visible_overmature_fraction']=c[2]/len(r['instances']);rows.append(r)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    board=Image.new('RGB',(1440,1180),'#eeeae1');d=ImageDraw.Draw(board)
    cards=[]
    for j,r in enumerate(rows):
        x=j%2*720;y=j//2*590
        im=Image.open(r['image']).convert('RGB');im.thumbnail((720,540));board.paste(im,(x,y+50))
        c=r['lighting']['capture_condition'];light=r['lighting']['lighting']
        title=('Azul despejado' if c['sky_type']=='clear_blue' else 'Despejado con bruma')
        text=f"{r['source_view']} · {title} · sol {light['sun_elevation_deg']:.0f}°"
        d.text((x+8,y+5),text,font=small,fill='#111')
        d.text((x+8,y+27),f"{r['visible_class_counts'].get(2,0)} sobremaduras / {len(r['instances'])} capachos visibles",font=small,fill='#111')
        cards.append(f'<article><h2>{text}</h2><img src="{r["source_view"]}/rgb.png"><p>Distancia al foco: {r["depth_sampling"]["distance_m"]:.2f} m. Máscara/objetos/cajas originales; clases locales nuevas.</p></article>')
    board.save(out/'sample_overview.png')
    options=sorted([(i['visible_pixels'],r,i) for r in rows for i in r['instances'] if i['class_id']==2],key=lambda t:-t[0])
    chosen=[];seen=set()
    for desired in ('intermediate','extensive','advanced_diffused','dry_bleached'):
        candidates=[(r,i) for _,r,i in options
                    if i['instance_id'] not in seen and stages[(r['scene_id'],i['instance_id'])]['name']==desired]
        if candidates:
            r,i=candidates[0];seen.add(i['instance_id']);chosen.append((r,i))
    for _,r,i in options:
        if len(chosen)==4:break
        if i['instance_id'] in seen:continue
        seen.add(i['instance_id']);chosen.append((r,i))
    crop_board=Image.new('RGB',(1280,420),'#eeeae1');d=ImageDraw.Draw(crop_board);examples=[]
    for j,(r,i) in enumerate(chosen):
        x,y,w,h=i['bbox_xywh'];pad=max(w,h)*.22
        box=(max(0,int(x-pad)),max(0,int(y-pad)),min(960,int(x+w+pad)),min(720,int(y+h+pad)))
        im=Image.open(r['image']).convert('RGB').crop(box);im.thumbnail((310,320))
        # Enlarge source crops only for inspection; never synthesize pixels.
        factor=min(310/im.width,320/im.height)
        im=im.resize((round(im.width*factor),round(im.height*factor)),Image.Resampling.LANCZOS)
        crop_board.paste(im,(j*320+(320-im.width)//2,45+(320-im.height)//2))
        stage=stages[(r['scene_id'],i['instance_id'])]['name'];d.text((j*320+8,10),stage,font=small,fill='#111')
        d.text((j*320+8,375),r['source_view'],font=small,fill='#111')
        examples.append(dict(source_view=r['source_view'],instance_id=i['instance_id'],stage=stage,source_box=box))
    crop_board.save(out/'overmature_crops.png')
    qa=dict(status='awaiting_user_sample_review',human_approval=False,preview_only=True,
        scene_layouts=2,rendered_rgb_images=4,sky_counts=dict(Counter(r['lighting']['camera_background']['sky_type'] for r in rows)),
        scene_assignment_counts=scene_stats,views=[{k:r[k] for k in ('source_view','visible_class_counts','visible_overmature_fraction','depth_sampling')} for r in rows],
        crops=examples,bank_images_added=0,bank_generation_paused=True,training_started=False,
        protected_artifacts_and_twenty_plants_verified=True,all_masks_geometry_boxes_exact=True,
        class_labels_updated_for_local_appearance=True,shape_contraction_applied=False,
        scientific_scope='appearance hypotheses, not biological fruit maturity or independent new plants')
    write(out/'review.json',qa)
    page='<meta charset="utf-8"><title>Muestras cielo azul y sobremaduras</title><style>body{font-family:Arial;background:#eee;max-width:1500px;margin:auto;padding:20px}img{max-width:100%}article{margin-bottom:30px}</style><h1>Muestras de cultivo: cielos e iluminación</h1><p>Cuatro vistas de dos escenas admitidas intactas. Sólo revisión; banco y piloto pausados. Pocas Sobremaduras, aspecto gris/venoso, sin poda o contracción nueva.</p><h2>Detalles de Sobremadura</h2><img src="overmature_crops.png"><p>Recortes ampliados del RGB nativo; no se retocaron. Las fotos completas permiten valorar su tamaño real.</p>'+''.join(cards)
    (out/'review.html').write_text(page,encoding='utf-8')
    result=subprocess.run([sys.executable,str(REPO/'scripts/validate_repository_context_graph.py')],capture_output=True,text=True)
    after=(result.stdout+result.stderr).strip();(out/'graph_after.txt').write_text(after+'\n',encoding='utf-8')
    assert after==(out/'graph_before.txt').read_text(encoding='utf-8').strip()
    write(out/'report_source_lock.json',dict(files={str(Path(__file__).resolve()):sha(__file__)}))
    print(qa)


if __name__=='__main__':report(Path(sys.argv[1]).resolve())
