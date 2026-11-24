"""Visual review cards: current GT, clean crop and explicit provisional notes."""
from pathlib import Path
import sys,math,textwrap
from PIL import Image,ImageDraw,ImageFont
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'scripts'),str(REPO/'src')]
from appearance_campaign import read,write,sha
from render_four_model_review_panels import wrapped
from diagnose_sobremadura_pilot import iou
ROOT=REPO/'outputs/suspected_sobremadura_labels_20261113'
GALLERY=REPO/'outputs/sobremadura_four_models_20261113'

CASES=[
 ('r153_gt11','P1','prioritaria','Tejido muy oscuro, venas marcadas y contorno estrecho/plegado. Comparar con los GT Sobre de esta misma foto.'),
 ('r153_gt6','P2','prioritaria','Tonos pardos y grisaceos entre venas, textura irregular de aspecto seco. La clase sigue pendiente de adjudicacion.'),
 ('r364_gt1','P3','prioritaria','Oscurecimiento extenso y aspecto seco, con pliegues visibles. No basta el color para certificar el estado del fruto.'),
 ('r548_gt5','P4','prioritaria','Capacho estrecho, pardo y de aspecto seco. Revisar si el plegado corresponde a deterioro o a la vista parcial.'),
 ('r579_gt5','P5','ambigua','Pigmentacion entre venas y gris/pardo, pero conserva volumen. Puede existir solapamiento visual entre clases.'),
 ('r44_gt1','P6','ambigua','Capacho oscuro pequeno; resolucion limitada. Revisar en la imagen original y no decidir por el color.'),
 ('r153_gt1','M1','prioritaria','Capacho alargado y plegado, pardo/grisaceo, con apariencia desecada. Es una discrepancia visual a revisar.'),
 ('r599_gt2','M2','prioritaria','Tejido pardo con pliegues y apertura aparente. Revisar junto con los GT Sobre de la misma escena.'),
 ('r548_gt2','M3','prioritaria','Aspecto pardo y seco, silueta estrecha. No se infiere reabsorcion fisiologica de esta fotografia.'),
 ('r282_gt1','M4','ambigua','Color pajizo y pliegues bajo una zona proximal oscura. Madura seca y Sobremadura pueden confundirse visualmente.'),
 ('r101_gt0','M5','ambigua','Pajizo/papeloso y mancha proximal, aun inflado. La mancha sola no determina Sobremadura.'),
 ('r579_gt0','M6','ambigua','Venas y zonas intermedias muy pigmentadas; conserva volumen. Revisar definicion de clase y fruto si es visible.'),
 ('r113_u0','U1','posible_omision','Capacho muy oscuro visible fuera de la unica caja de esta foto. Revisar primero la omision de instancia; su clase no se adjudica aqui.'),
 ('r588_u0','U2','descartada_como_evidencia','Al ampliar parece tejido foliar enrollado, con nervadura central. No se presenta como Sobremadura omitida; evidencia de un posible falso positivo del modelo.'),
 ('r8_u0','U3','posible_omision','Estructura parda/papelosa bajo el follaje. Hay que confirmar que es capacho y no hoja antes de anotar una instancia.'),
 ('r384_u0','U4','posible_omision','Estructura parda bajo el follaje, compatible con capacho seco o tejido foliar. Verificar identidad del organo y politica de oclusion.'),
 ('r584_u0','U5','posible_omision','Vista similar a U4, posiblemente del mismo organo/planta. No contarlas como evidencias biologicas independientes.'),
 ('r661_u0','U6','omision_clase_incierta','Capacho a contraluz sin caja sobre el candidato. Puede ser una omision de instancia, pero la clase no se resuelve por oscuridad.'),
]


def main():
    data=read(ROOT/'candidates.json');byid={c['id']:c for c in data['candidates']}
    rows={r['id']:r for r in wrapped(GALLERY/'gallery_data.js','window.GALLERY=')['rows']}
    out=ROOT/'cases';out.mkdir(exist_ok=True)
    fonts={s:ImageFont.truetype('arial.ttf',s) for s in (16,18,20,23,28)}
    proof=[]
    for cid,key,priority,note in CASES:
        c=byid[cid].copy();row=rows[c['row']];src=data['source'][str(c['row'])]
        original=Image.open(src['image']).convert('RGB');assert sha(src['image'])==row['source_image_sha256']
        cls='Pintona' if c['actual_class']==0 else 'Madura' if c['actual_class']==1 else 'SIN CAJA sobre el candidato'
        canvas=Image.new('RGB',(1600,1030),'#f5f2eb');draw=ImageDraw.Draw(canvas)
        draw.text((25,15),f'{key} | Fila {c["row"]} | Etiqueta actual: {cls}',font=fonts[28],fill='#173d37')
        draw.text((25,55),'Sospecha visual de Codex; pendiente de revision humana. Etiquetas originales intactas.',font=fonts[20],fill='#80562b')
        draw.text((25,95),'Contexto: todas las cajas GT; amarillo = region que se propone revisar',font=fonts[18],fill='#173d37')
        draw.text((825,95),'Recorte limpio: sin cajas ni predicciones sobre la textura',font=fonts[18],fill='#173d37')
        context=original.copy();ink=ImageDraw.Draw(context)
        for j,t in enumerate(row['truth']):
            ink.rectangle(t['bbox'],outline=['#00dd73','#ffaa00','#ff33cc'][t['class_id']],width=3)
            ink.text((t['bbox'][0],t['bbox'][1]),f'{j}:{["P","M","S"][t["class_id"]]}',font=fonts[18],fill='white',stroke_width=2,stroke_fill='black')
        ink.rectangle(c['bbox'],outline='#ffff00',width=6)
        region=c['bbox'];pad=.3*max(region[2]-region[0],region[3]-region[1])
        crop=(max(0,math.floor(region[0]-pad)),max(0,math.floor(region[1]-pad)),min(original.width,math.ceil(region[2]+pad)),min(original.height,math.ceil(region[3]+pad)))
        clean=original.crop(crop)
        for image,x in ((context,25),(clean,825)):
            s=min(750/image.width,680/image.height);image=image.resize((round(image.width*s),round(image.height*s)),Image.Resampling.LANCZOS)
            canvas.paste(image,(x+(750-image.width)//2,125+(680-image.height)//2))
        for j,line in enumerate(textwrap.wrap(note,112)):draw.text((25,830+26*j),line,font=fonts[23],fill='#173d37')
        support=' / '.join(f'{f}: '+','.join(str(p['seed'])[-2:] for p in c['support'] if p['family']==f) for f in c['families'])
        draw.text((25,930),f'Prioridad: {priority} | GT indice: {c["truth_index"]} | apoyo modelos: {len(c["families"])} familias (no verdad terreno)',font=fonts[18],fill='#735f45')
        if c['actual_class'] is None:
            metrics=[]
            for t in row['truth']:
                a=c['bbox'];b=t['bbox'];inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                metrics.append(dict(iou=iou(a,b),candidate_fraction=inter/max(1,(a[2]-a[0])*(a[3]-a[1]))))
            c['max_iou_any_gt']=max((m['iou'] for m in metrics),default=0)
            c['max_candidate_fraction_covered_by_gt']=max((m['candidate_fraction'] for m in metrics),default=0)
            draw.text((25,966),f'Verificacion geometrica: IoU max con cualquier GT {c["max_iou_any_gt"]:.3f}; fraccion de candidato cubierta {c["max_candidate_fraction_covered_by_gt"]:.3f}.',font=fonts[18],fill='#735f45')
        else:draw.text((25,966),'No equivale a validar madurez interna del fruto. Oscurecimiento, sombra y color natural pueden solaparse.',font=fonts[18],fill='#735f45')
        path=out/f'{key}_{cid}.png';canvas.save(path)
        c.update(review_id=key,priority=priority,visual_note=note,card=str(path),card_sha256=sha(path),source_image=src['image'],source_label=src['label'],source_image_sha256=sha(src['image']),source_label_sha256=sha(src['label']))
        proof.append(c)
    write(ROOT/'reviewed_cases.json',dict(cases=proof,reviewer='Codex visual inspection, not human adjudication',labels_changed=False,model_predictions_are_not_ground_truth=True,photos_screened=94,model_proposals_screened=144,source_lock=str(ROOT/'input_lock.json')))
    print([(c['review_id'],c['id'],c.get('max_candidate_fraction_covered_by_gt')) for c in proof])


if __name__=='__main__':main()
