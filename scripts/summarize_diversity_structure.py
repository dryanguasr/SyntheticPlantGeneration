"""Structural reuse and camera coverage supplement for the locked500 review."""
from pathlib import Path
from collections import Counter
import math,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha
from assess_dataset_diversity import describe


def run(revision,real_manifest):
    from PIL import Image
    lock=read(revision/'review_500_lock.json');organs=Counter();yaw=[];pitch=[];rotations=set();foliage=Counter();scene_seen=set();curve=[]
    for n,entry in enumerate(lock['selected'],1):
        p=Path(entry['view_record']);v=read(p)
        organs.update(i['instance_id'] for i in v['instances'])
        m=v['camera_matrix'];direction=[-m[i][2] for i in range(3)];norm=math.sqrt(sum(x*x for x in direction))
        yaw.append(math.degrees(math.atan2(direction[1],direction[0]))%360)
        pitch.append(math.degrees(math.asin(direction[2]/norm)))
        folder=p.parents[2]/'scenes'/v['scene_id']
        if str(folder) not in scene_seen:
            scene_seen.add(str(folder));layout=read(folder/'layout.json');a=read(folder/'accepted.json')
            rotations.update(x['rotation_deg'] for x in layout['plant_instances'])
            foliage.update(x['foliage'] for x in a['foliage'].values())
        if n%100==0:curve.append(dict(images=n,unique_visible_reproductive_ids=len(organs)))
    orientation=Counter()
    for row in read(real_manifest)['records']:
        if row['split']!='train':continue
        with Image.open(row['image']) as image:w,h=image.size
        orientation['portrait' if h>w else 'landscape' if w>h else 'square']+=1
    result=dict(unique_visible_reproductive_ids=len(organs),annotated_reproductive_appearances=sum(organs.values()),
        appearances_per_id=describe(organs.values()),organ_coverage_curve=curve,
        optical_axis_world_yaw_deg=describe(yaw),optical_axis_pitch_deg=describe(pitch),
        placed_plant_rotations_deg=sorted(rotations),scene_foliage_profile_assignments=dict(foliage),
        real_train_orientations=dict(orientation),synthetic_orientation='all landscape4:3',
        limits='identities are reused synthetic organs, not biological independent observations; optical axis angles are world axes, not real camera estimates',
        used_validation=False,used_test=False,training_started=False)
    out=revision/'assessment';write(out/'structure.json',result)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    a=read(out/'review_addendum.json');raw=read(out/'results.json')
    fig,axes=plt.subplots(1,2,figsize=(10,4.5))
    labels=['Todas las cajas','Lado mínimo≥10px','Mayor caja/imagen'];s=[a['reviewed_corrected_summary']['min_side_960']['median'],a['shared_min_side_sensitivities']['10']['synthetic']['sizes']['median'],a['largest_box_size_proxies']['1']['synthetic']['median']]
    r=[raw['real_train']['min_side_960']['median'],a['shared_min_side_sensitivities']['10']['real_train']['sizes']['median'],a['largest_box_size_proxies']['1']['real_train']['median']]
    x=range(3);axes[0].bar([v-.18 for v in x],s,.36,label='Sintéticas corregidas151');axes[0].bar([v+.18 for v in x],r,.36,label='Real train461')
    axes[0].set(xticks=list(x),xticklabels=labels,ylabel='Mediana de lado mínimo a960px',title='El filtro reduce, pero no elimina, la brecha de escala');axes[0].tick_params(axis='x',rotation=15);axes[0].legend()
    axes[1].plot([x['images'] for x in curve],[x['unique_visible_reproductive_ids'] for x in curve],'o-');axes[1].set(xlabel='Imágenes',ylabel='Identidades sintéticas visibles acumuladas',title='Reutilización de órganos de20plantas')
    axes[1].set_ylim(0,len(organs)*1.05)
    fig.tight_layout();fig.savefig(out/'policy_and_reuse.png',dpi=160);plt.close(fig)
    write(out/'structure_manifest.json',dict(script=str(Path(__file__).resolve()),script_sha256=sha(__file__),
        outputs={p.name:sha(p) for p in [out/'structure.json',out/'policy_and_reuse.png']}))
    print(result)


if __name__=='__main__':run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
