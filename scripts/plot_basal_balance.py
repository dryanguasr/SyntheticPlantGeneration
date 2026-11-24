"""Scientific diagnostic figures from actual interpreted stem geometry."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'outputs/integral_diagnosis_20261014/basal_balance_diagnostic'
curves=json.loads((out/'stems.json').read_text());data=json.loads((out/'metrics.json').read_text())
colors=['#cc503e','#2476b9','#2e9157'];names=['Eje principal restante','Rama basal 2','Rama basal 3']
fig,axs=plt.subplots(1,3,figsize=(15,6),layout='constrained')
for ax,(i,j,title) in zip(axs,[(0,2,'Frontal'),(1,2,'Lateral'),(0,1,'Desde arriba')]):
    for c in curves:
        p=np.asarray(c['points']);g=c['group']
        ax.plot(p[:,i],p[:,j],color='#222222' if c['base'] else colors[g],lw=1.1,alpha=.9)
    ax.set_aspect('equal');ax.set_title(title);ax.grid(alpha=.15)
    ax.set_xlabel('XYZ'[i]+' (unidades del intérprete)');ax.set_ylabel('XYZ'[j]+' (unidades del intérprete)')
fig.suptitle('Piloto actual de tres ramas — semilla 814140\nGeometría de tallos; colores por rama y toda su descendencia',fontsize=15)
fig.legend(handles=[Line2D([0],[0],color=c,lw=3,label=n) for c,n in zip(colors,names)],loc='outside lower center',ncol=3)
fig.savefig(out/'ramas_tres_vistas.png',dpi=160);plt.close(fig)
fig,axs=plt.subplots(2,3,figsize=(14,8),layout='constrained')
for col,r in enumerate(data['reports']):
    groups=r['groups'];length=np.array([g['axis_path_length'] for g in groups]);nodes=np.array([g['nodes'] for g in groups])
    for ax,values,title in [(axs[0,col],length/length.max()*100,'Longitud del eje estructural'),(axs[1,col],nodes/nodes.sum()*100,'Reparto de nodos con su descendencia')]:
        ax.bar(range(3),values,color=colors)
        for k,v in enumerate(values):ax.text(k,v+2,f'{v:.1f} %',ha='center')
        ax.set_ylim(0,115);ax.set_xticks(range(3),['Principal','Basal 2','Basal 3']);ax.set_title(f"Semilla {r['seed']}\n{title}");ax.grid(axis='y',alpha=.15)
    axs[0,col].set_ylabel('Mayor eje = 100 %')
    axs[1,col].set_ylabel('Total de nodos = 100 %')
fig.suptitle('¿Son comparables las tres ramas? No en el piloto actual.\nNo se ha modificado la arquitectura para estas imágenes.',fontsize=16)
fig.savefig(out/'balance_tres_semillas.png',dpi=150);plt.close(fig)
print(out)
