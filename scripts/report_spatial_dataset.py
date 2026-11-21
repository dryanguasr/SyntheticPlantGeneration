"""Verify committed pairs and show actual dataset images, never candidates."""
from pathlib import Path
from collections import Counter
import statistics
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.spatial_dataset import committed_views
from uchuva_lsystem.nodal_automation import write,sha


def main(root):
    bank=root/'dataset';rows=committed_views(bank)
    depths=Counter(r['depth_stratum'] for r in rows);classes=Counter(i['class_id'] for r in rows for i in r['instances'])
    exposures=Counter(seed for r in rows for seed in r['plant_seeds'])
    visible_exposures=Counter()
    for r in rows:
        identities=[i['instance_id'] for i in r['instances']]
        for seed in r['plant_seeds']:
            if any(identity.startswith('plant_'+str(seed)+':') for identity in identities):visible_exposures[seed]+=1
    lineage=({r['view_id']:r for r in json.loads((bank/'source_lineage.json').read_text(encoding='utf-8'))['preserved_views']}
             if (bank/'source_lineage.json').exists() else {})
    variants=Counter(r.get('generation_variant',lineage.get(r['view_id'],{}).get('generation_variant','initial')) for r in rows)
    scenes=sorted({r['scene_id'] for r in rows})
    supports={scene:json.loads((bank/'scenes'/scene/'accepted.json').read_text(encoding='utf-8')).get('support_mode','unspecified') for scene in scenes}
    support_counts=Counter(supports[r['scene_id']] for r in rows)
    sizes=Counter();densities=[len(r['instances']) for r in rows]
    for r in rows:
        for i in r['instances']:
            side=i['min_side_960'];sizes['lt8' if side<8 else '8to16' if side<16 else '16to32' if side<32 else 'ge32']+=1
    excluded=json.loads((bank/'excluded_views.json').read_text(encoding='utf-8')) if (bank/'excluded_views.json').exists() else {}
    summary=dict(complete_images=len(rows),scenes=len({r['scene_id'] for r in rows}),generation_variants=dict(variants),
                 depth_counts=dict(depths),annotated_instances_by_class=dict(classes),
                 source_plant_view_exposure=dict(exposures),source_plant_count=len(exposures),
                 source_plant_exposure_scope='present in scene; not necessarily visible',
                 visible_plant_view_exposure=dict(visible_exposures),visible_plant_count=len(visible_exposures),
                 excluded_complete_images=len(excluded.get('view_ids',[])),images_by_support_mode=dict(support_counts),
                 scene_support_modes=supports,instance_min_side_960_bins=dict(sizes),
                 annotated_instances_per_image=dict(min=min(densities) if densities else 0,median=statistics.median(densities) if densities else 0,max=max(densities) if densities else 0),
                 training_started=False,independent_samples_not_claimed=True,
                 context_physical_certification='not exhaustive; inspect source scene audits')
    write(bank/'review_summary.json',summary)
    selected=[]
    for scene in scenes:
        for depth in ['near','middle','far']:
            group=[r for r in rows if r['scene_id']==scene and r['depth_stratum']==depth]
            if group:selected.append(group[len(group)//2])
    cards=[]
    for r in selected:
        image=Path(r['image']).relative_to(bank).as_posix()
        cards.append(f'<article><h2>{r["view_id"]}</h2><img loading="lazy" src="{image}"><p>{r["depth_stratum"]}, {supports[r["scene_id"]]}: {len(r["instances"])} capachos anotados; {r["camera_distance_m"]:.2f} m al objetivo. <a href="views/{r["view_id"]}/annotations.json">Anotaciones</a></p></article>')
    page=f'<!doctype html><html lang="es"><meta charset="utf-8"><title>Dataset de cultivo</title><style>body{{font:17px system-ui;max-width:1300px;margin:auto;padding:25px;background:#f5f4ef}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:20px}}article{{background:white;padding:15px}}img{{width:100%}}</style><h1>{len(rows)} imágenes y anotaciones completas verificadas</h1><p>Profundidades: {dict(depths)}. {len(exposures)} plantas presentes en {summary["scenes"]} escenas; {len(visible_exposures)} con capachos efectivamente visibles. Veinte árboles admitidos disponibles en el pool. Las vistas reutilizan plantas y no son muestras independientes. Sin entrenamiento. Revisión visual humana pendiente.</p><main>'+''.join(cards)+'</main><p><a href="review_summary.json">Resumen real</a> · <a href="manifest.json">Manifiesto completo</a></p></html>'
    (bank/'review.html').write_text(page,encoding='utf-8')
    write(bank/'review_manifest.json',dict(views={r['view_id']:{k:r[k+'_sha256'] for k in ['image','label','mask']} for r in rows},
        report_source_sha256=sha(__file__),gallery_views=[r['view_id'] for r in selected],
        gallery_selection='middle complete view of each scene/depth group; deterministic review illustration, not a statistical sample'))
    print(json.dumps(summary))


if __name__=='__main__':main(Path(sys.argv[1]).resolve())
