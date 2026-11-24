"""Portable four-model gallery from frozen caches; no inference or data edits."""
from pathlib import Path
import json, hashlib, math, io
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from PIL import Image
from pypdf import PdfReader

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'outputs/sobremadura_four_models_20261113'
OUT=ROOT/'portable_gallery'
W,H=1190,900
INK='#173d37'; BG='#f6f3ec'
COLORS=['#158c5c','#ac6600','#bf157f']
SHORT=['P','M','S']


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def wrapped(path,prefix):
    return json.loads(path.read_text(encoding='utf-8').split(prefix,1)[1].removesuffix(';'))


def text(c,x,y,value,size=10,color=INK):
    c.setFillColor(HexColor(color));c.setFont('Helvetica',size);c.drawString(x,y,value)


def frame(c,title,subtitle,page):
    c.setFillColor(HexColor(BG));c.rect(0,0,W,H,fill=1,stroke=0)
    text(c,22,H-27,title,18)
    text(c,22,H-48,subtitle,10)
    text(c,22,25,'GT: blanco discontinuo + P/M/S. Predicciones: P verde, M ocre, S magenta; confianza >= 0,0761.',10)
    text(c,22,10,'Sin etiqueta no prueba ausencia biologica. Referencias historicas y pareja reciente: no es una ablacion controlada de cuatro brazos.',9)
    text(c,W-68,10,f'Pag. {page}',9)


def panel(c,row,model,data,image,crop,x,y,width,height,threshold):
    text(c,x,y+height-17,model['title']+' | '+model['date'].replace('\u2013','-'),14)
    text(c,x,y+height-34,model['detail'].replace('\u00b7','/'),10)
    count=sum(p[4]==2 and p[5]>=threshold for p in data['predictions'])
    text(c,x,y+height-50,f'Sobre predichas en foto: {count} | TP {data["tp"]} / FP {data["fp"]} / FN {data["fn"]}',9)
    bx,by,bw,bh=x,y+8,width,height-70
    cw,ch=crop[2]-crop[0],crop[3]-crop[1]
    s=min(bw/cw,bh/ch);iw,ih=cw*s,ch*s;ix=bx+(bw-iw)/2;iy=by+(bh-ih)/2
    # Actual crop, not an overlay hiding the original; source RGB stays intact.
    c.drawImage(image,ix,iy,width=iw,height=ih,mask=None)
    c.saveState();clip=c.beginPath();clip.rect(ix,iy,iw,ih);c.clipPath(clip,stroke=0)
    def box(b):return (ix+(b[0]-crop[0])*s,iy+(crop[3]-b[3])*s,(b[2]-b[0])*s,(b[3]-b[1])*s)
    def visible(b):return b[2]>crop[0] and b[0]<crop[2] and b[3]>crop[1] and b[1]<crop[3]
    labels=[]
    for gt in row['truth']:
        if not visible(gt['bbox']):continue
        a,b,d,e=box(gt['bbox']);c.setDash();c.setStrokeColor(HexColor('#163b31'));c.setLineWidth(2.8);c.rect(a,b,d,e)
        c.setDash(3,2);c.setStrokeColor(HexColor('#ffffff'));c.setLineWidth(1.2);c.rect(a,b,d,e);c.setDash()
        label='GT '+SHORT[gt['class_id']];text(c,max(ix,min(a,ix+iw-25)),max(iy+2,min(b+2,iy+ih-9)),label,7,'#ffffff')
    for p in sorted(data['predictions'],key=lambda p:p[5]):
        if p[5]<threshold or not visible(p[:4]):continue
        a,b,d,e=box(p[:4]);color=COLORS[p[4]]
        c.setDash();c.setLineWidth(.9);c.setStrokeColor(HexColor(color));c.rect(a,b,d,e)
        label=f'{SHORT[p[4]]} {p[5]:.2f}';lw=c.stringWidth(label,'Helvetica',7)+4
        tx=max(ix,min(a,ix+iw-lw));ty=max(iy,min(b+e-9-9*p[4],iy+ih-9))
        for _ in range(16):
            if not any(tx<q[2] and tx+lw>q[0] and ty<q[3] and ty+9>q[1] for q in labels):break
            ty=max(iy,ty-9)
        labels.append((tx,ty,tx+lw,ty+9));c.setFillColor(HexColor(color));c.rect(tx,ty,lw,9,fill=1,stroke=0)
        text(c,tx+2,ty+1,label,7,'#ffffff')
    c.restoreState()
    if count==0:text(c,x+width-190,y+height-50,'SIN PREDICCION SOBREMADURA',8,'#9b3b37')


def main():
    pause=json.loads((REPO/'outputs/spatial_dataset_completion_20261030/pause_requested.json').read_text())
    assert pause['active']
    meta=wrapped(ROOT/'gallery_data.js','window.GALLERY=')
    # Recheck frozen source images, labels, cached predictions and model weights.
    lock=json.loads((ROOT/'input_lock.json').read_text())
    for path,expected in lock['files'].items():
        if sha(path)!=expected:raise ValueError(f'Review input changed: {path}')
    source=json.loads((REPO/'outputs/daylight_augmentation_115_20261112/pilot/real_manifest.json').read_text())
    sources={r['source_row']:r for r in source['records'] if r['split']=='test'}
    OUT.mkdir(exist_ok=True)
    ordered=sorted(meta['rows'],key=lambda r:(not bool(r['gt_sobre']),r['id']))
    # Overview of every photo, plus a same-crop four-model page for every GT Sobre.
    jobs=[]
    for row in ordered:
        jobs.append((row,None))
        jobs.extend((row,t['bbox']) for t in row['truth'] if t['class_id']==2)
    assert len(ordered)==94 and len(jobs)==152
    proof=[]
    for seed in meta['seeds']:
        data=wrapped(ROOT/'data'/f'seed_{seed}.js',f'window.MODEL_DATA[{seed}]=')
        path=OUT/f'galeria_94_fotos_semilla_{seed}.pdf'
        c=canvas.Canvas(str(path),pagesize=(W,H),pageCompression=1)
        c.setTitle(f'Sobremadura: 94 fotos, cuatro modelos, semilla {seed}')
        frame(c,'Galeria para inspeccion - cuatro modelos',f'Semilla {seed} | 94 fotos reales + 58 detalles de Sobremaduras anotadas | Generacion pausada',1)
        lines=[
            'Como revisar',
            'Cada foto aparece con los cuatro modelos. Despues se muestran recortes de cada Sobremadura anotada.',
            'Las primeras 28 fotos tienen 58 etiquetas Sobremadura; despues se incluyen las otras 66 fotos.',
            'En las fotos sin etiqueta Sobre tambien se dibujan los candidatos: no se convierten en verdad terreno.',
            '',
            'Modelos y comparabilidad',
            'Sin aumentacion: referencia de octubre, 461 reales, sin clasica.',
            'Clasica: control reciente de noviembre, 461 reales.',
            'Sintetica: referencia de octubre, 461 reales + 389 sinteticas historicas, sin clasica.',
            'Hibrida: noviembre, 461 reales + 115 sinteticas nuevas, con clasica.',
            'Solo Clasica / Hibrida constituye la pareja reciente emparejada. Los otros dos bancos y dosis difieren.',
            '',
            'Lectura de las cajas',
            'GT = etiqueta original. P = Pintona; M = Madura; S = Sobremadura.',
            'Las predicciones de TODAS las clases se muestran al mismo umbral fijo 0,076076, elegido en val.',
            'La ausencia de una caja S indica que no supera ese umbral; no descarta candidatos de menor confianza.',
            'TP / FP / FN son conteos Sobremadura de la foto COMPLETA, tambien en las paginas de detalle.',
            'Acerca el PDF para leer las cajas vectoriales. RGB y etiquetas originales permanecen intactos.',
            '',
            'Indice: fila : pagina de foto completa (los detalles siguen inmediatamente)',
        ]
        cy=H-95
        for line in lines:text(c,30,cy,line,11);cy-=22
        indices=[f'{row["id"]}: {j+2}' for j,(row,focus) in enumerate(jobs) if focus is None]
        for start in range(0,len(indices),9):text(c,30,cy,' | '.join(indices[start:start+9]),10);cy-=19
        c.showPage()
        manifest=[]
        for page,(row,focus) in enumerate(jobs,2):
            imagepath=Path(sources[row['id']]['image']);assert sha(imagepath)==row['source_image_sha256']
            full=Image.open(imagepath).convert('RGB');w,h=full.size
            crop=(0,0,w,h)
            if focus is not None:
                pad=.6*max(focus[2]-focus[0],focus[3]-focus[1])
                crop=(max(0,math.floor(focus[0]-pad)),max(0,math.floor(focus[1]-pad)),min(w,math.ceil(focus[2]+pad)),min(h,math.ceil(focus[3]+pad)))
            if focus is None:
                # Preserve the source JPEG stream in the PDF instead of
                # expanding each repeated photograph to a lossless RGB bitmap.
                image=ImageReader(str(imagepath))
            else:
                preview=io.BytesIO()
                full.crop(crop).save(preview,format='JPEG',quality=95,subsampling=0)
                preview.seek(0);image=ImageReader(preview)
            kind='FOTO COMPLETA' if focus is None else 'DETALLE GT SOBREMADURA'
            frame(c,f'Fila {row["id"]} | {kind} | semilla {seed}',f'{row["file"]} | {row["gt_sobre"]} Sobremaduras anotadas en la foto',page)
            for k,model in enumerate(meta['models']):
                panel(c,row,model,data[model['id']][str(row['id'])],image,crop,22+(k%2)*585,460-(k//2)*405,560,375,meta['threshold'])
            c.showPage();manifest.append(dict(page=page,row=row['id'],type=kind,crop=list(crop)))
            if page%25==0:print(f'Semilla {seed}: pagina {page}/153',flush=True)
        c.save();reader=PdfReader(path)
        assert len(reader.pages)==153
        assert '94 fotos reales' in reader.pages[0].extract_text()
        proof.append(dict(seed=seed,path=str(path),pages=153,real_photos=94,detail_pages=58,sha256=sha(path),page_map=manifest))
    (OUT/'manifest.json').write_text(json.dumps(dict(pdfs=proof,generation_paused=True,new_inference=False,new_training=False,source_labels_unchanged=True),indent=2),encoding='utf-8')
    print(json.dumps([{k:v for k,v in p.items() if k!='page_map'} for p in proof],indent=2))


if __name__=='__main__':main()
