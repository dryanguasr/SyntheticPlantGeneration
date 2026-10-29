"""Read-only review and optional final report for the eight-hour plant pool."""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.nodal_automation import read,write,sha,unique_admissions
from uchuva_lsystem.spatial_admission import validate_plan
from uchuva_lsystem.nodal_repulsion import protected_anatomy
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.budget_lineage import verify_frozen_inputs


def main(root,final=False):
    state=read(root/'state.json');results=read(root/'results.json');valid=unique_admissions(results['rows'])
    lock=read(root/'source_lock.json')
    changed=[p for p,h in lock['sources'].items() if sha(ROOT/p)!=h]
    changed += verify_frozen_inputs(root,lock['inputs'])
    assert not changed,changed
    rows=[];manifest={}
    for row in valid:
        folder=Path(row['folder']);plant=Plant.from_dict(read(folder/'plant.json'))
        raw=Plant.from_dict(read(folder/'raw.json'));proof=validate_plan(plant)
        mesh=read(folder/'final_independent_mesh.json');ground=read(folder/'ground.json')
        orientation=read(folder/'orientation.json');morphology=read(folder/'morphology.json')
        assert mesh['physical_collision_count']==0 and not mesh['truncated']
        assert ground['status']=='valid' and orientation['status']=='valid' and not morphology['errors']
        original=protected_anatomy(raw)['counts'];retained=protected_anatomy(plant)['counts']
        assert original==row['original_counts'] and retained==row['counts']
        if proof.get('applied'):assert proof['original_counts']==original
        losses=dict(fruit=(original['fruits']-retained['fruits'])/max(1,original['fruits']),
                    leaf=(original['leaves']-retained['leaves'])/max(1,original['leaves']),
                    nominal_leaf_area=proof.get('leaf_nominal_area_loss_fraction',0))
        assert all(0<=v<.05 for v in losses.values()),losses
        rows.append(dict(seed=row['seed'],origin=row['origin'],original=original,retained=retained,
                         loss_fractions=losses,physical_crossings=0,proximity_warnings=mesh['clearance_violation_count'],
                         image_exists=(folder/'preview.png').exists()))
        for name in ['raw.json','plant.json','admission.json','space_admission_plan.json','space_validation.json','ground.json','orientation.json','morphology.json','final_independent_mesh.json','preview.png','process.json','parent_completion.json']:
            p=folder/name
            if p.exists():manifest[str(p.relative_to(root))]=sha(p)
    summary=dict(state=state,verified_valid_plants=len(rows),rows=rows,
                 fresh_admissions=sum(r['origin'].startswith('fresh_seed') for r in rows),
                 recovered_admissions=sum(not r['origin'].startswith('fresh_seed') for r in rows),
                 attempts_in_results=len(results['rows']),changed_frozen_files=changed,
                 training_started=False,dataset_generated=(bool(read(root/'dataset/manifest.json').get('complete_images',0)) if (root/'dataset/manifest.json').exists() else False),human_visual_review='pending')
    write(root/'review_summary.json',summary)
    write(root/'review_manifest.json',dict(files=manifest,source_lock_sha256=sha(root/'source_lock.json')))
    if final:
        assert state['status']=='complete' and (root/'closure.json').exists()
        path=ROOT/'docs/reports/plantas_admision_espacial_8h_2026-10-29.md'
        dataset=read(root/'dataset/manifest.json') if (root/'dataset/manifest.json').exists() else {}
        phase_note=(f"Se generaron {dataset.get('complete_images',0)} pares completos de imágenes y anotaciones tras alcanzar veinte plantas. No hubo entrenamiento."
                    if (root/'plant_pool_complete.json').exists() else "No hubo dataset ni entrenamiento: no se activó la condición de veinte plantas.")
        if (root/'authorized_budget_revision.json').exists():
            phase_note+=' El usuario autorizó después hasta ocho horas efectivas adicionales, con parada anticipada en mil imágenes. Se preservan el presupuesto original y el reloj acumulado mediante una revisión por hash.'
        title='Plantas con admisión espacial y dataset: cierre' if (root/'authorized_budget_revision.json').exists() else 'Plantas con admisión espacial: cierre de ocho horas'
        text=f'''# {title}

Se verificaron **{len(rows)} plantas admitidas**, de las cuales {summary['fresh_admissions']} proceden de semillas nuevas y {summary['recovered_admissions']} de posturas antes rechazadas. Se registraron {len(results['rows'])} intentos. Tiempo efectivo: {state['active_seconds']/3600:.4f} h. Motivo de parada: `{state['stop_reason']}`. {phase_note}

Cada admisión reconstruida presenta cero cruces duros auditados, suelo plano válido a 1 mm, orientación/unión de cálices válida y morfología sin errores. Se comprobaron los hashes, el original, el árbol final y los límites acumulados. La pérdida es estrictamente menor del 5 % para frutos y hojas por separado; se controla también el proxy nominal foliar largo*ancho, sin confundirlo con superficie medida.

| Semilla | Origen | Hojas retenidas/originales | Frutos retenidos/originales | Pérdida hojas | Pérdida frutos | Proximidades |
|---|---|---:|---:|---:|---:|---:|
'''
        for r in rows:
            text+=f"| {r['seed']} | {r['origin']} | {r['retained']['leaves']}/{r['original']['leaves']} | {r['retained']['fruits']}/{r['original']['fruits']} | {100*r['loss_fractions']['leaf']:.3f}% | {100*r['loss_fractions']['fruit']:.3f}% | {r['proximity_warnings']} |\n"
        text+='''
La admisión es una heurística de ingeniería con realimentación de mallas, no un modelo medido de abscisión o aborto. Se conservan dimensiones y posturas de los órganos supervivientes. Hoja–hoja sigue como ocupación blanda y las proximidades como advertencias; no se certifican exhaustivamente flores ni contexto, mecánica, realismo fotométrico o utilidad para un detector. Revisión visual humana pendiente.

La cola adaptativa priorizó tres recuperaciones y después semillas nuevas por coste anatómico original. No se podaron los originales para esa prioridad. El inventario puro no cuenta como admisión y esta selección no permite estimar una tasa de éxito uniforme de la población. Las tres plantas ya válidas históricamente quedan excluidas del contador nuevo.

[Galería de plantas](../../outputs/spatial_plant_pool_20261028/review.html), [todos los intentos](../../outputs/spatial_plant_pool_20261028/results.json), [verificación independiente](../../outputs/spatial_plant_pool_20261028/review_summary.json) y [presupuesto](../../outputs/spatial_plant_pool_20261028/budget.json). Los rechazos y parciales permanecen en cada carpeta; no se mezclan con las admisiones.

El contrato está documentado en [la guía](../guides/plantas_admision_espacial_8h.md). Las comprobaciones del grafo deben distinguir los diez errores preexistentes de localizadores de cualquier regresión nueva.
'''
        path.write_text(text,encoding='utf-8')
        write(root/'report_manifest.json',dict(files={str(p.resolve()):sha(p) for p in [path,Path(__file__),ROOT/'docs/guides/plantas_admision_espacial_8h.md',ROOT/'docs/repository_context_graph.json']}))
    print(json.dumps({k:summary[k] for k in ['verified_valid_plants','fresh_admissions','recovered_admissions','attempts_in_results']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--final',action='store_true');a=p.parse_args();main(a.root.resolve(),a.final)
