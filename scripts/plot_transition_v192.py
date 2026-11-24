"""All-object and size-eligible confusion matrices, with explicit ignored small truth."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
r=Path('outputs/integral_diagnosis_20261014');o=r/'transition_training_v192/evaluation';p=r/'field_tracking_v187';results=json.loads((o/'results.json').read_text());frames=json.loads((p/'predictions/observations.json').read_text());matrices={};stats={}
for variant in ('baseline','fine_tuned'):
 cm=np.zeros((4,4),int);ignored=0
 for i,truth in enumerate(results[variant]['items']):
  a=json.loads((p/f'evaluator_private/view_{i:03d}/annotations_private.json').read_text());rgb=np.array(Image.open(p/f'evaluator_private/view_{i:03d}/mask_calyx_crisp_v2.png').convert('RGB')).astype(np.uint32);packed=rgb[:,:,0]*65536+rgb[:,:,1]*256+rgb[:,:,2];native=np.zeros(packed.shape,np.uint16);byid={v['instance_id']:k for k,v in a['items'].items() if k!='0'}
  for t in truth:
   col=a['palette'][byid[t['instance_id']]];native[packed==col[0]*65536+col[1]*256+col[2]]=t['mask_id']
  if variant=='baseline':masks=np.load(p/'predictions'/(str(frames[i]['stamp_ns'])+'.npz'))['masks'];labels=frames[i]['detections']
  else:masks=np.load(o/f'fine_tuned_{i}.npz')['masks'];labels=json.loads((o/f'fine_tuned_{i}.json').read_text())
  eligible={k for k,t in enumerate(truth) if t['pixels']>=100 and min(t['bbox'][2:])>=8};small=set(range(len(truth)))-eligible;remaining=set(eligible)
  for j in sorted(range(len(labels)),key=lambda j:-labels[j]['confidence']):
   hist=np.bincount(native[masks[j]].astype(np.int64),minlength=len(truth)+1);area=masks[j].sum();iou=lambda k:hist[truth[k]['mask_id']]/max(1,area+truth[k]['pixels']-hist[truth[k]['mask_id']]);pairs=[(iou(k),k) for k in remaining]
   if pairs and max(pairs)[0]>=.5:
    _,k=max(pairs);remaining.remove(k);cm[truth[k]['class_id'],labels[j]['class_id']]+=1
   elif any(iou(k)>=.5 for k in small):ignored+=1
   else:cm[3,labels[j]['class_id']]+=1
  for k in remaining:cm[truth[k]['class_id'],3]+=1
 matrices[variant]={'all':np.array(results[variant]['confusion']),'eligible':cm};stats[variant]={}
 for scope,m in matrices[variant].items():
  tp=int(np.trace(m[:3,:3]));n=int(m[:3,:].sum());pred=int(m[:,:3].sum());stats[variant][scope]=dict(truth=n,predictions=pred,tp=tp,precision=tp/max(1,pred),recall=tp/max(1,n),f1=2*tp/max(1,n+pred),pintona_to_madura=int(m[0,1]),matrix=m.tolist(),ignored_small_predictions=ignored if scope=='eligible' else 0)
for scope,title in [('all','Todos los objetos visibles'),('eligible','Objetos con ≥100 px visibles y lado mínimo ≥8 px')]:
 fig,axs=plt.subplots(1,2,figsize=(13,6.5),layout='constrained');vmax=max(matrices[v][scope].max() for v in matrices)
 for ax,variant,name in zip(axs,matrices,['V186 — anterior','V192 — ajuste corto']):
  m=matrices[variant][scope];ax.imshow(m,cmap='Blues',vmin=0,vmax=vmax)
  for y in range(4):
   for x in range(4):ax.text(x,y,'—' if x==y==3 else str(m[y,x]),ha='center',va='center',fontsize=14,color='white' if m[y,x]>vmax*.55 else 'black')
  ax.set_xticks(range(4),['Pintona','Madura','Sobremadura','No detectada'],rotation=15);ax.set_yticks(range(4),['Pintona','Madura','Sobremadura','Sin coincidencia']);ax.set_xlabel('Predicción');ax.set_ylabel('Verdad sintética');ax.set_title(name)
 fig.suptitle(title+'\nMismas 8 vistas V187 · confianza 0,25 · IoU de máscara 0,50',fontweight='bold')
 fig.supxlabel('Emparejamiento independiente de clase. Clases de apariencia del capacho, no madurez interna.\n'+('Los objetos pequeños siguen visibles; se ignoran predicciones emparejadas a ellos (IoU ≥0,50).\nCriterio de tamaño diagnóstico, no garantía de detectabilidad ni mínimo universal de YOLO.' if scope=='eligible' else 'Observaciones por fotograma, no frutos únicos; incluye omisiones y falsas detecciones.'),fontsize=10)
 fig.savefig(o/f'confusion_{scope}.png',dpi=150);plt.close(fig)
(o/'comparison_metrics.json').write_text(json.dumps(stats,indent=2));print(json.dumps(stats))
# Deterministic examples of corrections, regressions and persistent errors (unique identity).
base=results['baseline']['items'];new=results['fine_tuned']['items'];categories=[('Transición corregida',lambda a,b:a['class_id']==0 and a['predicted_class']==1 and b['predicted_class']==0),('Confusión persistente',lambda a,b:a['class_id']==0 and a['predicted_class']==1 and b['predicted_class']==1),('Regresión',lambda a,b:a['predicted_class']==a['class_id'] and b['predicted_class']!=b['class_id'])]
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17);sheet=Image.new('RGB',(960,870),'white');draw=ImageDraw.Draw(sheet);names={None:'omitida',0:'pintona',1:'madura',2:'sobremadura'};chosen=[]
for row,(name,condition) in enumerate(categories):
 pool={}
 for aa,bb in zip(base,new):
  for a,b in zip(aa,bb):
   assert a['instance_id']==b['instance_id']
   if condition(a,b):pool.setdefault(a['instance_id'],(a,b))
 vals=sorted(pool.values(),key=lambda pair:pair[0]['pixels'])
 for col,q in enumerate([.2,.5,.8]):
  if not vals:draw.text((col*320+5,row*290+30),'Sin casos en esta secuencia',font=font,fill='black');continue
  a,b=vals[round(q*(len(vals)-1))];chosen.append(dict(category=name,before=a,after=b));im=Image.open(p/'public/rgb'/frames[a['frame']]['filename']).convert('RGB');x,y,w,h=a['bbox'];side=max(90,w+40,h+40);left=max(0,min(im.width-side,x+w/2-side/2));top=max(0,min(im.height-side,y+h/2-side/2));crop=im.crop((int(left),int(top),int(left+side),int(top+side))).resize((310,225));ImageDraw.Draw(crop).rectangle(((x-left)*310/side,(y-top)*225/side,(x+w-left)*310/side,(y+h-top)*225/side),outline='red',width=2);sheet.paste(crop,(col*320,row*290+60));draw.text((col*320+4,row*290+3),name,font=font,fill='black');draw.text((col*320+4,row*290+23),names[a['predicted_class']]+' → '+names[b['predicted_class']],font=font,fill='black');draw.text((col*320+4,row*290+42),f"Vista {a['frame']+1}, {a['pixels']} px",font=font,fill='black')
sheet.save(o/'ejemplos_antes_despues.jpg');(o/'example_selection.json').write_text(json.dumps(chosen,indent=2))
