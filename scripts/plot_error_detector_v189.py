"""User-requested plots: conditional 3D errors and class-agnostic native mask matching."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
r=Path('outputs/integral_diagnosis_20261014');out=r/'error_detector_plots_v189';out.mkdir(exist_ok=True)
ev=json.loads((r/'field_geometry_evaluation_v189/evaluation_private.json').read_text())
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(12,4.8),sharey=True,layout='constrained');bins=np.arange(0,20,2)
for ax,key,title,col in zip(axes,['visual_pose','fused'],['Solo marcador visual','Marcador + sensores relativos'],['#6689bb','#168c83']):
 data=np.array([v['error_m'] for v in ev['variants'][key]['rows']])*100
 n,_,bars=ax.hist(data,bins=bins,color=col,edgecolor='white')
 for count,bar in zip(n,bars):
  if count:ax.text(bar.get_x()+bar.get_width()/2,count+.15,str(int(count)),ha='center')
 med=np.median(data);p90=np.percentile(data,90)
 ax.axvline(med,color='#27384b',ls='--',label=f'Mediana {med:.2f} cm');ax.axvline(p90,color='#b85324',ls=':',lw=2,label=f'P90 {p90:.2f} cm')
 ax.set(title=title,xlabel='Error 3D del centro del capacho (cm)',xticks=np.arange(0,19,2),xlim=(0,18));ax.legend(frameon=False);ax.grid(axis='y',alpha=.2)
axes[0].set_ylabel('Número de trayectorias')
fig.suptitle('V189 · Error 3D condicionado a asociaciones verificadas',fontweight='bold')
fig.supxlabel('35 trayectorias / 34 capachos; 3 con respaldo de una sola coincidencia.\nExcluidas en fusión: 2 identidades mixtas y 8 sin correspondencia. No es error de toda la población.',fontsize=10)
fig.savefig(out/'histograma_error_3d.png',dpi=160);plt.close(fig)
p=r/'field_tracking_v187';mapping=json.loads((p/'evaluator_private/class_mapping_private.json').read_text());obs=json.loads((p/'predictions/observations.json').read_text());cm=np.zeros((4,4),int);frames=[]
for i,frame in enumerate(obs):
 a=json.loads((p/f'evaluator_private/view_{i:03d}/annotations_private.json').read_text());rgb=np.array(Image.open(p/f'evaluator_private/view_{i:03d}/mask_calyx_crisp_v2.png').convert('RGB')).astype(np.uint32);packed=rgb[:,:,0]*65536+rgb[:,:,1]*256+rgb[:,:,2];native=np.zeros(packed.shape,np.uint16);labels=[]
 for itemkey,item in a['items'].items():
  if item['semantic_class']!='calyx' or not item['visible_pixels']:continue
  color=a['palette'][itemkey];mid=len(labels)+1;native[packed==(color[0]*65536+color[1]*256+color[2])]=mid
  labels.append(dict(mask_id=mid,pixels=item['visible_pixels'],class_id=mapping[item['instance_id']]['class_id']))
 masks=np.load(p/'predictions'/(str(frame['stamp_ns'])+'.npz'))['masks'];pred=frame['detections'];remaining=set(range(len(labels)));matches=[]
 # Class-independent geometric matching reveals off-diagonal class mistakes.
 for j in sorted(range(len(pred)),key=lambda j:-pred[j]['confidence']):
  inter=np.bincount(native[masks[j]].astype(np.int64),minlength=len(labels)+1);area=int(masks[j].sum());pairs=[(inter[labels[k]['mask_id']]/max(1,area+labels[k]['pixels']-inter[labels[k]['mask_id']]),k) for k in remaining]
  if pairs and max(pairs)[0]>=.5:
   iou,k=max(pairs);remaining.remove(k);cm[labels[k]['class_id'],pred[j]['class_id']]+=1;matches.append(dict(prediction=j,truth=k,iou=float(iou)))
  else:cm[3,pred[j]['class_id']]+=1
 for k in remaining:cm[labels[k]['class_id'],3]+=1
 frames.append(dict(stamp_ns=frame['stamp_ns'],truth=len(labels),predictions=len(pred),matches=matches))
assert cm[:3,:].sum()==763 and cm[:,:3].sum()==360
names=['Pintona','Madura','Sobremadura','Fondo / ausencia'];fig,ax=plt.subplots(figsize=(8.5,7.5),layout='constrained');im=ax.imshow(cm,cmap='Blues',vmin=0)
for y in range(4):
 for x in range(4):
  value='—' if (x,y)==(3,3) else str(cm[y,x]);ax.text(x,y,value,ha='center',va='center',fontsize=16,fontweight='bold',color='white' if cm[y,x]>cm.max()*.55 else '#162b3b')
ax.set_xticks(range(4),['Pintona','Madura','Sobremadura','No detectada']);ax.set_yticks(range(4),['Pintona','Madura','Sobremadura','Sin objeto real']);ax.set_xlabel('Clase predicha');ax.set_ylabel('Clase real sintética');ax.set_title('V186 + ROI/parches · Matriz de confusión\n8 vistas consecutivas de validación V187',fontweight='bold',pad=18)
fig.colorbar(im,ax=ax,shrink=.7,label='Observaciones de instancia')
fig.supxlabel('Confianza ≥ 0,25 · IoU de máscara ≥ 0,50 · Emparejamiento independiente de clase\n763 observaciones reales y 360 detecciones; un capacho puede aparecer en varias vistas.\nClases de apariencia del capacho, no madurez interna del fruto. Fondo–fondo no se contabiliza.',fontsize=10)
fig.savefig(out/'matriz_confusion_detector.png',dpi=160);plt.close(fig)
(out/'confusion.json').write_text(json.dumps(dict(rows='truth',columns='prediction',classes=names,matrix=cm.tolist(),protocol='confidence-ordered one-to-one class-independent native mask IoU>=0.5; confidence>=0.25',frames=frames),indent=2))
print(cm.tolist())
