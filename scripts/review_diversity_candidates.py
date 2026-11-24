"""Add a reviewed quality screen and fair size-policy sensitivities.

No image or label is modified. Original500 metrics remain intact; proposed
pilot lists exclude only near-black technical captures and use corrected views.
"""
from pathlib import Path
from collections import Counter
import sys,html
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha
from assess_dataset_diversity import distances,candidate_order,summarize_subset,describe


def run(assessment,reference_manifest):
    from PIL import Image
    features=read(assessment/'features.json');raw=read(assessment/'results.json');bad=[]
    for i,f in enumerate(features):
        if f['luminance_mean']<.005:
            with Image.open(f['image']) as image:extrema=image.convert('RGB').getextrema()
            if max(v[1] for v in extrema)<=1:
                bad.append(i)
    eligible=[i for i,f in enumerate(features) if f['sky_version']=='aligned_horizon_matte/3' and f['segment'] and i not in bad]
    matrix=distances(features);chosen=candidate_order(features,eligible,matrix)
    real_rows=[r for r in read(reference_manifest)['records'] if r['split']=='train']
    real_per_image=[]
    for r in real_rows:
        with Image.open(r['image']) as image:w,h=image.size
        values=[]
        for line in Path(r['label']).read_text().splitlines():
            v=line.split();values.append(min(float(v[3])*w,float(v[4])*h)*960/max(w,h))
        real_per_image.append(values)
    synthetic_per_image=[[v for vv in features[i]['sizes_by_class'].values() for v in vv] for i in eligible]
    sensitivity={}
    for threshold in (6,8,10,16,24,32):
        def describe_policy(rows):
            counts=[sum(v>=threshold for v in row) for row in rows]
            return dict(density=describe(counts),sizes=describe(v for row in rows for v in row if v>=threshold),retained_instances=sum(counts))
        sensitivity[str(threshold)]=dict(synthetic=describe_policy(synthetic_per_image),real_train=describe_policy(real_per_image))
    top_sizes={}
    for k in (1,3,5):
        def top(rows):return describe(__import__('statistics').median(sorted(v,reverse=True)[:k]) for v in rows if v)
        top_sizes[str(k)]=dict(synthetic=top(synthetic_per_image),real_train=top(real_per_image),
            meaning='per-image median of largest k box minimum sides; foreground size proxy, not measured depth')
    candidates={}
    for n in (46,115):
        if len(chosen)<n:continue
        subset=[features[i] for i in chosen[:n]];sizes=[v for f in subset for vv in f['sizes_by_class'].values() for v in vv]
        raw_count=len(sizes);exposures={}
        for threshold in (6,10,16,32):
            s=sum(v>=threshold for v in sizes);r=sum(v>=threshold for row in real_per_image for v in row)
            exposures[str(threshold)]=dict(synthetic_annotations=s,real_annotations=r,synthetic_nominal_annotation_fraction=s/(s+r))
        candidates[str(n)]=dict(views=[f['view_record'] for f in subset],summary=summarize_subset(subset),
            synthetic_fraction_of_images=n/(461+n),raw_synthetic_annotations=raw_count,
            raw_real_annotations=raw['real_train']['min_side_960']['n'],
            raw_synthetic_nominal_annotation_fraction=raw_count/(raw_count+raw['real_train']['min_side_960']['n']),
            annotation_exposure_sensitivity=exposures)
    result=dict(corrected_raw_images=raw['corrected_continuous']['images'],reviewed_corrected_images=len(eligible),
        technical_quality_flags=[dict(view_id=features[i]['view_id'],reason='RGB channel maxima <=1/255; full-frame single target mask',
            action='preserve raw files; exclude from proposed pilot lists',cause='complete camera obstruction/inside a surface is a hypothesis, not independently audited') for i in bad],
        reviewed_corrected_summary=summarize_subset([features[i] for i in eligible]),
        shared_min_side_sensitivities=sensitivity,largest_box_size_proxies=top_sizes,
        candidates=candidates,selection='nested46/115; corrected capture version, technical black-frame exclusion, observed sky/segment strata, then farthest pHash',
        small_filter_not_applied=True,labels_modified=False,used_validation=False,used_test=False,training_started=False,
        limits='annotation count/exposure is not gradient weight or independent organisms; size filtering is sensitivity only, not a frozen consumer policy')
    write(assessment/'review_addendum.json',result)
    cards=[]
    for n in (46,115):
        candidate=candidates[str(n)]
        cards.append(f'<p>Candidato{n}: {candidate["summary"]["scenes"]}escenas, {candidate["summary"]["visible_plants"]}plantas visibles; no entrenado.</p>')
    selected=[]
    for sky in ('clear_blue','hazy_clear','overcast'):
        for segment in ('near_to_middle','middle_to_far'):
            options=[i for i in chosen if features[i]['sky']==sky and features[i]['segment']==segment]
            if options:selected.append(options[len(options)//2])
    for i in selected:
        f=features[i];cards.append(f'<article><h3>{f["view_id"]}</h3><img src="{Path(f["image"]).as_uri()}"><p>{f["sky"]} · {f["distance_m"]:.2f}m · {f["segment"]} · {f["instances"]}capachos anotados</p></article>')
    exceptions=''.join(f'<article><h3>Excepción: {features[i]["view_id"]}</h3><img src="{Path(features[i]["image"]).as_uri()}"><p>Casi negra. Conservada, fuera de candidatos.</p></article>' for i in bad)
    page='<html lang="es"><meta charset="utf-8"><title>Revisión500</title><style>body{font:17px system-ui;background:#f3f1e8;max-width:1450px;margin:auto;padding:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px}article{background:white;padding:12px}img{width:100%}</style><h1>Revisión de diversidad:503 preservadas, primeras500 evaluadas</h1><p>Generación y seguimiento pausados. Sin entrenamiento ni reetiquetado. Los candidatos no prueban utilidad.</p><img src="overview.png"><h2>Versión corregida y candidatos revisados</h2><main>'+''.join(cards)+'</main><h2>Excepciones conservadas</h2><main>'+exceptions+'</main><p><a href="review_addendum.json">Sensibilidades y candidatos revisados</a> · <a href="results.json">Estadísticas originales</a> · <a href="index.html">Pares perceptuales</a></p></html>'
    (assessment/'reviewed.html').write_text(page,encoding='utf-8')
    write(assessment/'review_manifest.json',dict(script=str(Path(__file__).resolve()),script_sha256=sha(__file__),
        input_manifest_sha256=sha(assessment/'analysis_manifest.json'),
        outputs={p.name:sha(p) for p in [assessment/'review_addendum.json',assessment/'reviewed.html']},training_started=False))
    print('Reviewed usable corrected images',len(eligible),'quality flags',[features[i]['view_id'] for i in bad])
    print('Largest box proxies',top_sizes)
    print('Sensitivity10px',sensitivity['10'])
    print('Candidates',{k:dict(images=v['summary']['images'],scenes=v['summary']['scenes'],visible_plants=v['summary']['visible_plants'],instances=v['raw_synthetic_annotations'],exposure=v['raw_synthetic_nominal_annotation_fraction']) for k,v in candidates.items()})


if __name__=='__main__':run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
