"""Read-only diversity review of a locked image subset; never renders/trains.

Perceptual hashes describe projection similarity, not botanical independence
or downstream utility. Real references are restricted to training images.
"""
from pathlib import Path
from collections import Counter,defaultdict
import sys,json,math,statistics,html
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.nodal_automation import read,write,sha


def describe(values):
    import numpy as np
    a=np.asarray(list(values),dtype=float)
    if not len(a):return dict(n=0)
    return dict(n=len(a),min=float(a.min()),p05=float(np.quantile(a,.05)),q25=float(np.quantile(a,.25)),
        median=float(np.median(a)),q75=float(np.quantile(a,.75)),p95=float(np.quantile(a,.95)),max=float(a.max()),mean=float(a.mean()))


def image_features(path,mask=None):
    import numpy as np
    from PIL import Image
    with Image.open(path) as image:
        width,height=image.size;small=image.convert('RGB').resize((160,120),Image.Resampling.LANCZOS)
    rgb=np.asarray(small,dtype=float)/255;lum=rgb@np.array([.2126,.7152,.0722])
    sat=(rgb.max(2)-rgb.min(2))/np.maximum(rgb.max(2),1e-6)
    def phash(image):
        gray=np.asarray(image.convert('L').resize((32,32),Image.Resampling.LANCZOS),dtype=float)
        c=np.cos(np.pi*np.outer(np.arange(32),np.arange(32)+.5)/32)
        low=(c@gray@c.T)[:8,:8].reshape(-1)[1:]
        return sum(int(v>np.median(low))<<i for i,v in enumerate(low))
    feature=dict(width=width,height=height,aspect=width/height,luminance_mean=float(lum.mean()),
        saturation_mean=float(sat.mean()),phash=phash(small),crop_phash=phash(small.crop((16,12,144,108))))
    if mask:
        with Image.open(mask) as image:m=np.asarray(image.convert('RGB').resize((160,120),Image.Resampling.NEAREST))
        target=np.any(m!=0,axis=2)
        feature.update(calyx_pixel_fraction=float(target.mean()),
            calyx_luminance_mean=float(lum[target].mean()) if target.any() else None)
    return feature


def distances(features,key='phash'):
    import numpy as np
    n=len(features);matrix=np.full((n,n),255,dtype=np.uint8)
    for i in range(n):
        for j in range(i):matrix[i,j]=matrix[j,i]=(features[i][key]^features[j][key]).bit_count()
    return matrix


def hash_review(features,matrix):
    import numpy as np
    n=len(features)
    if n<2:return dict(images=n)
    nearest=matrix.min(1);indices=matrix.argmin(1)
    pairs=sorted({(min(i,int(j)),max(i,int(j))) for i,j in enumerate(indices)},key=lambda p:(int(matrix[p]),p))
    coverage={}
    for radius in (2,4,8):
        representatives=[]
        for i in range(n):
            if not representatives or int(matrix[i,representatives].min())>radius:representatives.append(i)
        coverage[str(radius)]=len(representatives)
    return dict(images=n,bits=63,nearest_hamming=describe(nearest),
        fraction_nearest_at_most={str(t):float((nearest<=t).mean()) for t in (2,4,8)},
        greedy_chronological_representatives_by_radius=coverage,
        nearest_pairs=[dict(a=features[i]['view_id'],b=features[j]['view_id'],hamming=int(matrix[i,j])) for i,j in pairs[:12]],
        limits='engineering radii; global structure/lighting can dominate; not semantic duplicates, independence, or efficacy')


def chronological_curve(features,matrix,steps):
    result=[]
    for n in steps:
        if n>len(features):continue
        subset=features[:n];past=max(0,n-steps[0]);novel=[]
        for i in range(past,n):
            if i:novel.append(int(matrix[i,:i].min()))
        result.append(dict(images=n,visible_plants=len(set(p for f in subset for p in f['visible_plants'])),
            scenes=len(set(f['scene'] for f in subset)),
            source_combinations=len(set(tuple(f['present_plants']) for f in subset)),
            nearest_earlier_hamming_last_batch=describe(novel),
            fraction_last_batch_more_than4_from_earlier=sum(v>4 for v in novel)/len(novel) if novel else None))
    return result


def summarize_subset(rows):
    sizes=[];by_class=defaultdict(list);classes=Counter();density=[];weather=Counter();supports=Counter()
    for f in rows:
        density.append(f['instances']);weather[f['sky']]+=1;supports[f['support']]+=1
        classes.update({int(k):v for k,v in f['class_counts'].items()})
        for c,values in f['sizes_by_class'].items():sizes.extend(values);by_class[int(c)].extend(values)
    return dict(images=len(rows),scenes=len(set(f['scene'] for f in rows)),
        visible_plants=len(set(p for f in rows for p in f['visible_plants'])),
        distinct_present_plant_combinations=len(set(tuple(f['present_plants']) for f in rows)),
        classes=dict(classes),class_fractions={str(c):n/sum(classes.values()) for c,n in classes.items()},
        all_three_classes_images=sum(len(f['class_counts'])==3 for f in rows),
        density=describe(density),min_side_960=describe(sizes),min_side_by_class={str(c):describe(v) for c,v in by_class.items()},
        instance_fraction_below_side={str(t):sum(v<t for v in sizes)/len(sizes) for t in (6,8,16,32)},
        weather_configuration=dict(weather),support_modes=dict(supports),
        image_luminance_mean=describe(f['luminance_mean'] for f in rows),
        image_saturation_mean=describe(f['saturation_mean'] for f in rows),
        distance_m=describe(f['distance_m'] for f in rows),
        visible_plants_per_image=describe(len(f['visible_plants']) for f in rows),
        continuous_segments=dict(Counter(f['segment'] for f in rows if f['segment'])))


def candidate_order(features,eligible,matrix,maximum=115):
    groups=defaultdict(list)
    for i in eligible:groups[(features[i]['sky'],features[i]['segment'])].append(i)
    total=len(eligible);chosen=[];used=Counter()
    for step in range(min(maximum,total)):
        available=[g for g,indices in groups.items() if any(i not in chosen for i in indices)]
        group=max(available,key=lambda g:((step+1)*len(groups[g])/total-used[g],g))
        options=[i for i in groups[group] if i not in chosen]
        i=max(options,key=lambda i:(int(matrix[i,chosen].min()) if chosen else 63,-i))
        chosen.append(i);used[group]+=1
    return chosen


def plot_review(out,features,eligible,result,matrix):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(15,8.2));all_=result['all500'];latest=result['corrected_continuous'];real=result['real_train']
    curve=result['chronological_curve'];axes[0,0].plot([v['images'] for v in curve],[v['visible_plants'] for v in curve],'o-',label='Plantas visibles')
    axes[0,0].plot([v['images'] for v in curve],[v['scenes'] for v in curve],'s-',label='Escenas');axes[0,0].set(title='Vistas adicionales reutilizan las mismas 20 plantas',xlabel='Imágenes',ylabel='Cantidad');axes[0,0].legend()
    def cdf(ax,values,label):
        a=np.sort(np.asarray(values));ax.plot(a,np.arange(1,len(a)+1)/len(a),label=label)
    cdf(axes[0,1],[f['instances'] for f in features],'Sintéticas500')
    cdf(axes[0,1],[features[i]['instances'] for i in eligible],f'Corregidas{len(eligible)}')
    cdf(axes[0,1],real['density_values'],'Reales train461');axes[0,1].set(xscale='symlog',title='Capachos anotados por imagen',xlabel='Cantidad (escala logarítmica)',ylabel='Fracción acumulada');axes[0,1].legend()
    for label,rows in [('Sintéticas500',features),(f'Corregidas{len(eligible)}',[features[i] for i in eligible])]:
        sizes=[v for f in rows for vv in f['sizes_by_class'].values() for v in vv];cdf(axes[0,2],sizes,label)
    cdf(axes[0,2],real['size_values'],'Reales train461');axes[0,2].set(xscale='log',title='Lado mínimo de caja, normalizado a960',xlabel='Píxeles',ylabel='Fracción acumulada');axes[0,2].legend()
    x=np.arange(3);width=.25
    for offset,label,s in [(-width,'500',all_),(0,'Corregidas',latest),(width,'Real train',real)]:
        axes[1,0].bar(x+offset,[s['class_fractions'].get(str(c),0) for c in range(3)],width,label=label)
    axes[1,0].set(xticks=x,xticklabels=['Pintona','Madura','Sobremadura'],title='Frecuencia por exposición de instancias',ylabel='Fracción');axes[1,0].legend()
    for label,values in [('Sintéticas500',[f['luminance_mean'] for f in features]),('Real train',real['luminance_values'])]:
        axes[1,1].hist(values,bins=20,alpha=.5,density=True,label=label)
    axes[1,1].set(title='Brillo medio global codificado (sRGB)',xlabel='0–1; no reflectancia',ylabel='Densidad');axes[1,1].legend()
    axes[1,2].hist(matrix.min(1),bins=np.arange(0,40,2),label='Vecino más próximo');axes[1,2].set(title='Similitud de composición: pHash63',xlabel='Distancia Hamming (menor = más parecido)',ylabel='Imágenes')
    fig.suptitle('Revisión al umbral500 · diversidad descriptiva, sin entrenamiento',fontsize=15)
    fig.tight_layout(rect=[0,0,1,.95]);fig.savefig(out/'overview.png',dpi=160);plt.close(fig)


def run(root,revision,reference_manifest):
    import numpy as np
    from PIL import Image
    out=revision/'assessment';out.mkdir(exist_ok=False)
    lock=read(revision/'review_500_lock.json');features=[];scene_cache={};plant_hashes={}
    for entry in lock['selected']:
        p=Path(entry['view_record']);assert sha(p)==entry['view_record_sha256'];v=read(p)
        for key in ('image','mask','label'):assert sha(v[key])==entry[key+'_sha256']
        folder=p.parents[2]/'scenes'/v['scene_id'];scene_key=str(folder)
        if scene_key not in scene_cache:
            a=read(folder/'accepted.json')
            scene_cache[scene_key]=dict(support=a['support_mode'],foliage=dict(Counter(x['foliage'] for x in a['foliage'].values())),
                plant_combination=sorted(p['seed'] for p in a['plants']))
            for plant in a['plants']:plant_hashes[plant['seed']]=plant['plant_sha256']
        meta=scene_cache[scene_key];f=image_features(v['image'],v['mask']);classes=Counter();sizes=defaultdict(list)
        for instance in v['instances']:classes[instance['class_id']]+=1;sizes[instance['class_id']].append(instance['min_side_960'])
        sky=v['lighting'].get('camera_background',{});visible=sorted({int(i['instance_id'].split(':')[0].replace('plant_','')) for i in v['instances']})
        f.update(view_id=v['view_id'],view_record=str(p),image=v['image'],mask=v['mask'],label=v['label'],
            image_sha256=v['image_sha256'],mask_sha256=v['mask_sha256'],scene=scene_key,scene_id=v['scene_id'],
            present_plants=sorted(v['plant_seeds']),visible_plants=visible,support=meta['support'],
            sky=sky.get('sky_type','historical_overcast'),sky_version=sky.get('sky_replacement_version','previous'),
            capture_variant=v.get('generation_variant','historical'),distance_m=v['camera_distance_m'],
            segment=v.get('depth_sampling',{}).get('segment'),instances=len(v['instances']),class_counts=dict(classes),sizes_by_class=dict(sizes))
        features.append(f)
        if len(features)%50==0:print('SYNTHETIC',len(features),'/500',flush=True)
    manifest=read(reference_manifest);real_rows=[r for r in manifest['records'] if r['split']=='train'];assert len(real_rows)==461
    real_classes=Counter();real_sizes=[];real_density=[];real_lum=[];real_aspects=[];real_sizes_by_class=defaultdict(list)
    for index,v in enumerate(real_rows):
        assert sha(v['image'])==v['image_sha256'] and sha(v['label'])==v['label_sha256']
        f=image_features(v['image']);real_lum.append(f['luminance_mean']);real_aspects.append(f['aspect'])
        labels=Path(v['label']).read_text(encoding='utf-8').splitlines();real_density.append(len(labels))
        for line in labels:
            values=line.split();c=int(values[0]);assert c in (0,1,2);real_classes[c]+=1
            side=min(float(values[3])*f['width'],float(values[4])*f['height'])*960/max(f['width'],f['height'])
            real_sizes.append(side);real_sizes_by_class[c].append(side)
        if (index+1)%100==0:print('REAL_TRAIN',index+1,'/461',flush=True)
    matrix=distances(features);crop_matrix=distances(features,'crop_phash')
    eligible=[i for i,f in enumerate(features) if f['sky_version']=='aligned_horizon_matte/3' and f['segment']]
    fresh=[features[i] for i in eligible];fresh_matrix=matrix[np.ix_(eligible,eligible)]
    exact=Counter(f['image_sha256'] for f in features)
    real=dict(images=461,source_split='train',used_validation=False,used_test=False,
        manifest=str(reference_manifest),manifest_sha256=sha(reference_manifest),classes=dict(real_classes),
        class_fractions={str(c):n/sum(real_classes.values()) for c,n in real_classes.items()},
        density=describe(real_density),min_side_960=describe(real_sizes),min_side_by_class={str(c):describe(a) for c,a in real_sizes_by_class.items()},
        instance_fraction_below_side={str(t):sum(v<t for v in real_sizes)/len(real_sizes) for t in (6,8,16,32)},
        image_luminance_mean=describe(real_lum),aspect=describe(real_aspects),density_values=real_density,size_values=real_sizes,luminance_values=real_lum)
    result=dict(review_images=500,verified_available=lock['available_verified'],extra_verified_preserved=len(lock['extra_verified_preserved']),
        exact_duplicate_image_groups=sum(n>1 for n in exact.values()),exact_duplicate_images_beyond_first=sum(n-1 for n in exact.values()),
        unique_plant_geometry_hashes=len(set(plant_hashes.values())),plant_hashes=plant_hashes,
        all500=summarize_subset(features),corrected_continuous=summarize_subset(fresh),real_train=real,
        source_versions=dict(Counter(f['sky_version'] for f in features)),
        global_hash_similarity=hash_review(features,matrix),central_crop_hash_similarity=hash_review(features,crop_matrix),
        corrected_hash_similarity=hash_review(fresh,fresh_matrix),
        chronological_curve=chronological_curve(features,matrix,[100,200,300,400,500]),
        corrected_chronological_curve=chronological_curve(fresh,fresh_matrix,[23,46,92,115,len(fresh)]),
        training_started=False,independent_plants_not_images=True,
        small_object_thresholds='descriptive sensitivity at6/8/16/32pixels; no labels removed; not a frozen training filter')
    chosen=candidate_order(features,eligible,matrix)
    candidates={str(n):dict(views=[features[i]['view_record'] for i in chosen[:n]],
        sky_segments={str(k):v for k,v in Counter((features[i]['sky'],features[i]['segment']) for i in chosen[:n]).items()},
        visible_plants=len(set(p for i in chosen[:n] for p in features[i]['visible_plants'])),
        scenes=len(set(features[i]['scene'] for i in chosen[:n]))) for n in (46,115) if len(chosen)>=n}
    write(out/'pilot_candidates.json',dict(selection='nested prefixes; preserve observed sky/segment proportions then farthest pHash; no validation/test/performance used',
        candidates=candidates,training_authorized=False))
    write(out/'results.json',result);write(out/'features.json',features)
    plot_review(out,features,eligible,result,matrix)
    selected=[]
    for sky in ('clear_blue','hazy_clear','overcast'):
        for segment in ('near_to_middle','middle_to_far'):
            group=[i for i in chosen if features[i]['sky']==sky and features[i]['segment']==segment]
            if group:selected.append(group[len(group)//2])
    cards=[]
    for i in selected:
        f=features[i];cards.append(f'<article><h3>{html.escape(f["view_id"])}</h3><img loading="lazy" src="{Path(f["image"]).as_uri()}"><p>{f["sky"]} · {f["distance_m"]:.2f}m · {f["instances"]} anotaciones · {f["segment"]}</p></article>')
    pairs=[];lookup={f['view_id']:f for f in features}
    for pair in result['global_hash_similarity']['nearest_pairs'][:6]:
        a,b=lookup[pair['a']],lookup[pair['b']];pairs.append(f'<article><h3>Vecinos pHash: {pair["hamming"]} bits</h3><img src="{Path(a["image"]).as_uri()}"><img src="{Path(b["image"]).as_uri()}"><p>{a["view_id"]} / {b["view_id"]}</p></article>')
    page='<html lang="es"><meta charset="utf-8"><title>Diversidad al umbral500</title><style>body{font:17px system-ui;background:#f3f1e8;max-width:1500px;margin:auto;padding:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px}img{width:100%}article{background:white;padding:12px}</style><h1>Revisión descriptiva de las primeras500 imágenes</h1><p>503 conservadas; generación pausada. Sin entrenamiento. Las similitudes perceptuales no miden independencia ni utilidad.</p><img src="overview.png"><h2>Muestras de la versión corregida</h2><main>'+''.join(cards)+'</main><h2>Pares visualmente próximos según pHash</h2><main>'+''.join(pairs)+'</main><p><a href="results.json">Métricas</a> · <a href="pilot_candidates.json">Candidatos46/115, sin entrenamiento</a></p></html>'
    (out/'index.html').write_text(page,encoding='utf-8')
    write(out/'analysis_manifest.json',dict(script=str(Path(__file__).resolve()),script_sha256=sha(__file__),
        review_lock_sha256=sha(revision/'review_500_lock.json'),real_manifest_sha256=sha(reference_manifest),
        outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()},training_started=False))
    print(json.dumps(dict(all500=result['all500'],corrected=result['corrected_continuous'],
        real={k:v for k,v in real.items() if not k.endswith('_values')},hash=result['global_hash_similarity']),ensure_ascii=False))


if __name__=='__main__':run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve())
