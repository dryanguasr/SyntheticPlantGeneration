"""Legible paired target overlays and train-only appearance examples."""
from pathlib import Path
import argparse,shutil
import numpy as np
from PIL import Image
from appearance_campaign import read,write,sha,NAMES
from diagnose_sobremadura_pilot import iou


def run(root,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    diagnosis=read(out/'diagnosis.json');threshold=diagnosis['threshold_fixed_from_original_val'];pairs=[]
    initial=out/'initial_overlays';initial.mkdir(exist_ok=True)
    for number,c in enumerate(diagnosis['cases'],1):
        path=out/f'error_pair_{number}.png'
        if path.exists() and not (initial/path.name).exists():shutil.copy2(path,initial/path.name)
        seed=c['seed'];rows={arm:read(root/'evaluation'/f'final_{arm}_{seed}'/'predictions.json')[c['row_index']]
            for arm in ('real_classical','synthetic115_classical')}
        if c['kind']=='GT_regression':truth=rows['real_classical']['truth'][c['truth_index']]
        else:truth=max(rows['real_classical']['truth'],key=lambda t:iou(t['bbox'],c['bbox']))
        fig,axes=plt.subplots(1,2,figsize=(12,5.8));descriptions=[]
        for axis,(arm,row) in zip(axes,rows.items()):
            with Image.open(row['image']) as im:axis.imshow(im.convert('RGB'));w,h=im.size
            x,y,xx,yy=truth['bbox'];pad=max(65,(xx-x)*.65,(yy-y)*.65)
            left,right=max(0,x-pad),min(w,xx+pad);top,bottom=max(0,y-pad),min(h,yy+pad)
            eligible=[p for p in row['predictions'] if p['confidence']>=threshold and iou(p['bbox'],truth['bbox'])>=.5]
            other=None
            if c['kind']=='GT_regression':
                p=max((p for p in row['predictions'] if p['class_id']==2 and iou(p['bbox'],truth['bbox'])>=.5),key=lambda p:p['confidence'],default=None)
                other=max((p for p in eligible if p['class_id']!=2),key=lambda p:p['confidence'],default=None)
            elif arm=='synthetic115_classical':p=c['fp']['prediction']
            else:p=max(eligible,key=lambda p:iou(p['bbox'],truth['bbox']),default=None)
            axis.add_patch(Rectangle((x,y),xx-x,yy-y,fill=False,edgecolor='lime',linewidth=2))
            if p:
                a,b,cc,dd=p['bbox'];axis.add_patch(Rectangle((a,b),cc-a,dd-b,fill=False,edgecolor='red',linewidth=2,linestyle='-' if p['confidence']>=threshold else '--'))
                state='admitida' if p['confidence']>=threshold else 'bajo umbral'
                label=f"{NAMES[p['class_id']]} {p['confidence']:.3f} ({state}) · IoU {iou(p['bbox'],truth['bbox']):.2f}"
                if other:label+=f"\nTambién emite {NAMES[other['class_id']]} {other['confidence']:.3f}"
            else:
                low=max((p['confidence'] for p in row['predictions'] if p['class_id']==2 and iou(p['bbox'],truth['bbox'])>=.5),default=0)
                label=f'Sin detección localizada al umbral común\nMejor Sobremadura por debajo del umbral: {low:.3f}'
            axis.set_xlim(left,right);axis.set_ylim(bottom,top);axis.axis('off')
            title='Real + clásica' if arm=='real_classical' else 'Sintética + clásica'
            axis.set_title(title+'\n'+label,fontsize=10,pad=12)
            descriptions.append(dict(arm=arm,annotation=truth,prediction=p,description=label))
        fig.suptitle(f"Etiqueta: {NAMES[truth['class_id']]} · fila {c['source_row']} · semilla {seed}\nVerde: caja anotada · rojo: candidato seleccionado (discontinuo si no supera el umbral)",fontsize=12,y=.99)
        fig.tight_layout(rect=(0,0,1,.88));fig.savefig(path,dpi=160);plt.close(fig)
        pairs.append(dict(file=path.name,source_row=c['source_row'],seed=seed,target=truth,models=descriptions,
            selection='GT regression: highest-confidence class2 candidate, including below-threshold dashed candidate; also disclose overlapping competing class. New-FP case: exact selected FP. Other boxes omitted for legibility, not from evaluation.'))
    manifest=read(root/'datasets/paired_slots115/manifest.json');appearance=[]
    fig,axes=plt.subplots(2,6,figsize=(16,6))
    for i,domain in enumerate(('real','synthetic')):
        eligible=[]
        for r in manifest['entries']:
            if r['split']!='train' or r['domain']!=domain:continue
            boxes=[list(map(float,l.split())) for l in Path(r['label']).read_text().splitlines() if int(l.split()[0])==2]
            if boxes:eligible.append((r,max(boxes,key=lambda b:b[3]*b[4])))
        eligible.sort(key=lambda a:a[0]['source_id'])
        for j,index in enumerate(np.linspace(0,len(eligible)-1,6,dtype=int)):
            row,box=eligible[index]
            with Image.open(row['image']) as im:
                w,h=im.size;_,cx,cy,bw,bh=box;x,y,xx,yy=(cx-bw/2)*w,(cy-bh/2)*h,(cx+bw/2)*w,(cy+bh/2)*h
                pad=max(2,.1*max(xx-x,yy-y));crop=im.convert('RGB').crop((max(0,int(x-pad)),max(0,int(y-pad)),min(w,int(xx+pad+1)),min(h,int(yy+pad+1))))
                axes[i,j].imshow(crop,interpolation='nearest')
            axes[i,j].set_title(('Real train' if domain=='real' else 'Sintética train')+'\n'+row['source_id']+f' · {min(bw*w,bh*h)*960/max(w,h):.0f}px',fontsize=9)
            axes[i,j].axis('off');appearance.append(dict(domain=domain,source_id=row['source_id'],source_image=row['image'],source_label=row['label'],box=box))
    fig.suptitle('Sobremadura etiquetada en entrenamiento. Mayor caja por imagen; seis posiciones equiespaciadas por fuente.\nRecortes ampliados a tamaño visual común; no representan la escala relativa original.',fontsize=11)
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(out/'training_appearance.png',dpi=160);plt.close(fig)
    write(out/'plot_manifest.json',dict(script_sha256=sha(__file__),diagnosis_sha256=sha(out/'diagnosis.json'),
        pairs=pairs,training_appearance_cases=appearance,used_test_for_error_examples=True,used_test_for_model_selection=False,
        outputs={p.name:sha(p) for p in out.glob('*.png')}))
    print('Readable paired examples saved; original diagnostic overlays preserved')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('out',type=Path);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
