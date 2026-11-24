"""Paired color review: same cameras, plants, pigment maps and label bytes."""
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from PIL import Image,ImageDraw,ImageFont
import numpy as np
from uchuva_lsystem.nodal_automation import read,write,sha
from report_blue_sky_samples import report as base_report


def report(out):
    base_report(out)
    plan=read(out/'plan.json');prior=Path(plan['comparison_review'])
    rows=[];paired=[]
    for sid in ('scene_027','scene_028'):
        assert read(out/f'{sid}_result.json')['surface_plans']==read(prior/f'{sid}_result.json')['surface_plans']
    for v in plan['views']:
        name=v['source_view'];new=read(out/name/'view.json');old=read(prior/name/'view.json')
        for k in ('camera_matrix','depth_sampling','instances','mask_sha256','label_sha256'):
            assert new[k]==old[k],(name,k)
        for k in ('lighting','capture_condition','analytic_sky_color_adjustment','color_management','effective_exposure_ev'):
            assert new['lighting'].get(k)==old['lighting'].get(k),(name,k)
        assert new['lighting']['camera_background']['sky_type']==old['lighting']['camera_background']['sky_type']
        paired.append(dict(view=name,camera_geometry_labels_material_plans_exact=True,
            solar_and_capture_conditions_exact=True,ambient_color_balance=new['lighting']['ambient_color_balance']))
        rows.append((old,new))
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    # Full before/after scenes, without repainting or replacing any pixels.
    board=Image.new('RGB',(1440,1180),'#eeeae1');d=ImageDraw.Draw(board)
    for j,index in enumerate((0,1)):
        for k,r in enumerate(rows[index]):
            x=k*720;y=j*590;im=Image.open(r['image']).convert('RGB');im.thumbnail((720,540))
            board.paste(im,(x,y+50));d.text((x+10,y+8),('Antes' if k==0 else 'Ahora')+' · '+r['source_view'],font=font,fill='#111')
    board.save(out/'paired_scene_comparison.png')
    # Exact same source rectangles for earth and two grades of deterioration.
    crops=[('Suelo y sombras','scene_027_view_021',(705,505,945,695)),
           ('Sobremadura avanzada','scene_027_view_010',(744,559,820,634)),
           ('Sobremadura extensa · bruma','scene_028_view_010',(845,367,944,480))]
    board=Image.new('RGB',(1000,1120),'#eeeae1');d=ImageDraw.Draw(board)
    metrics=[]
    for j,(label,name,box) in enumerate(crops):
        d.text((10,j*365+8),label+' · mismo recorte',font=font,fill='#111')
        row=[]
        for k,folder in enumerate((prior,out)):
            im=Image.open(folder/name/'rgb.png').convert('RGB').crop(box)
            rgb=np.asarray(im,dtype=float);mean=rgb.mean(axis=(0,1))
            row.append(dict(mean_sRGB=mean.tolist(),display_B_over_R=float(mean[2]/max(mean[0],1e-9))))
            im.thumbnail((480,300));factor=min(480/im.width,300/im.height)
            im=im.resize((round(im.width*factor),round(im.height*factor)),Image.Resampling.LANCZOS)
            board.paste(im,(k*500+(500-im.width)//2,j*365+52+(300-im.height)//2))
            d.text((k*500+10,j*365+32),'Antes' if k==0 else 'Ahora',font=small,fill='#111')
        metrics.append(dict(label=label,view=name,source_box=box,before=row[0],after=row[1],
            scope='same displayed RGB rectangle, may include occluders; not a lesion-area or whole-floor measurement'))
    board.save(out/'paired_ground_calyx.png')
    write(out/'paired_color_metrics.json',dict(pairs=paired,crop_metrics=metrics,
        raw_pigment_maps_unchanged=True,camera_sky_parameters_unchanged=True,
        no_temperature_or_exposure_correction=True,scope='ambient-radiance chroma change only; visual engineering approximation'))
    qa=read(out/'review.json');qa.update(paired_with_previous_previews=True,
        all_paired_label_bytes_exact=True,pigment_roughness_normal_maps_unchanged=True,
        solar_and_camera_sky_parameters_unchanged=True,color_change_scope='non-camera environment radiance chroma only')
    write(out/'review.json',qa)
    page=out/'review.html';s=page.read_text(encoding='utf-8')
    s=s.replace('<h1>Muestras de cultivo: cielos e iluminación</h1>',
        '<h1>Corrección de dominante azul: cielo conservado, suelo y capachos</h1><p>Comparación emparejada. Sólo cambia el cromatismo de radiancia ambiental de rayos no dirigidos a cámara. Materiales, mapas de pigmento, sol, cámara, máscaras y clases se conservan. Es una corrección visual heurística, no radiometría atmosférica validada.</p><h2>Suelo y Sobremadura: antes / ahora</h2><img src="paired_ground_calyx.png"><h2>Escenas emparejadas</h2><img src="paired_scene_comparison.png">')
    page.write_text(s,encoding='utf-8')
    write(out/'comparison_report_source_lock.json',dict(files={str(Path(__file__).resolve()):sha(__file__)}))
    print(dict(paired_views=len(paired),crop_metrics=metrics,bank_images_added=0,training_started=False))


if __name__=='__main__':report(Path(sys.argv[1]).resolve())
