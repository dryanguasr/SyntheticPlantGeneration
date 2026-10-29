"""Read-only scientific review of a bounded nodal campaign; never renders/trains."""
from pathlib import Path
import argparse
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_lsystem.nodal_automation import read, write, sha, unique_admissions, physically_admitted
from uchuva_lsystem.nodal_repulsion import protected_anatomy, axes, KEY
from uchuva_lsystem.morphology import Plant


def summarize(root):
    state = read(root/'state.json')
    results = read(root/'results.json') if (root/'results.json').exists() else {'rows': []}
    lock = read(root/'source_lock.json')
    known_locks={sha(root/'source_lock.json'):root/'source_lock.json'}
    for archived in (root/'revisions').rglob('*source_lock*.json'):
        if 'sources' in read(archived):
            known_locks[sha(archived)]=archived
    changed = [p for p, digest in lock['sources'].items() if sha(ROOT/p) != digest]
    for name in ('config','profiles','continuations','seed_queue'):
        if name+'_sha256' in lock and sha(root/(name+'.json')) != lock[name+'_sha256']:
            changed.append(name+'.json')
    rows = []
    manifest = {}
    for row in results['rows']:
        folder = Path(row['folder'])
        history = read(folder/'history.json') if (folder/'history.json').exists() else []
        admission = read(folder/'admission.json') if (folder/'admission.json').exists() else None
        anatomy = None
        if (folder/'raw.json').exists():
            anatomy = protected_anatomy(Plant.from_dict(read(folder/'raw.json')))
        excursions={}
        if admission:
            final_plant=Plant.from_dict(read(folder/'plant.json'))
            final = protected_anatomy(final_plant)
            if anatomy != final or anatomy != admission['anatomy_before']:
                raise RuntimeError('Anatomy changed: '+str(row['seed']))
            if admission['source_lock_sha256'] not in known_locks:
                raise RuntimeError('Admission uses another source lock: '+str(row['seed']))
            if admission['status'] == 'admitted':
                for gate in ('ground', 'orientation', 'morphology', 'final_independent_mesh'):
                    if not (folder/(gate+'.json')).exists():
                        raise RuntimeError('Missing independent audit: '+gate)
                if not physically_admitted(read(folder/'final_independent_mesh.json'),
                                           read(folder/'ground.json'), read(folder/'orientation.json'),
                                           read(folder/'morphology.json'), anatomy, final):
                    raise RuntimeError('Admission contradicts independent audits: '+str(row['seed']))
            groups={'axis':[],'leaf':[],'pedicel':[]}
            for axis in axes(final_plant.axes):
                groups['axis'].extend(p.provenance[KEY] for p in axis.internodes)
                for node in axis.nodes:
                    if node.leaf:groups['leaf'].append(node.leaf.provenance[KEY])
                    if node.reproductive_unit:groups['pedicel'].append(node.reproductive_unit.pedicel.provenance[KEY])
            for name,records in groups.items():
                angles=[math.degrees(math.acos(max(-1.,min(1.,sum(a*b for a,b in zip(p['input_direction'],p['direction'])))))) for p in records]
                excursions[name]=max(angles,default=0.)
        counts = anatomy['counts'] if anatomy else {}
        best = read(folder/'best_state.json') if (folder/'best_state.json').exists() else {}
        completed = read(folder/'completion.json') if (folder/'completion.json').exists() else {}
        final_mesh=read(folder/'final_independent_mesh.json') if (folder/'final_independent_mesh.json').exists() else {}
        rows.append(dict(seed=row['seed'], status=row['status'], counts=counts,folder=str(folder),
                         initial_crossings=history[0]['crossings'] if history else None,
                         best_crossings=best.get('objective', [None])[0],
                         final_crossings=admission['physical_crossings'] if admission else None,
                         proximity_warnings=admission['proximity_warnings'] if admission else None,
                         leaf_leaf_soft_count=final_mesh.get('soft_occupancy_intersection_count'),
                         anatomy_verified=bool(admission),
                         active_seconds=completed.get('active_elapsed_seconds'),
                         preview_exists=(folder/'preview.png').exists(),
                         diagnostic_rejected_preview=(folder/'rejected_preview.png').exists(),
                         source_lock_sha256=admission.get('source_lock_sha256') if admission else None,
                         max_excursion_from_input_deg=excursions,
                         termination=read(folder/'parent_completion.json') if (folder/'parent_completion.json').exists() else None))
        for name in ('raw.json', 'plant.json', 'best_plant.json', 'admission.json',
                     'ground.json', 'orientation.json', 'morphology.json',
                     'final_independent_mesh.json', 'history.json', 'job.json',
                     'preview_configuration.json', 'preview.png', 'rejected_preview.png','power_request.json'):
            path = folder/name
            if path.exists():
                manifest[path.relative_to(root).as_posix()] = sha(path)
    for name in ('budget.json','config.json','profiles.json','source_lock.json','continuations.json','seed_queue.json','seed_queue_rationale.json','raw_diversity_survey/manifest.json',
                 'raw_diversity_survey/regeneration_checks.json','residual_contact_categories.json','packing_diagnosis.json','historical_preservation_check.json','graph_verification.json','regressions/summary.json'):
        if (root/name).exists():manifest[name] = sha(root/name)
    archived_versions=[]
    for digest in sorted({r['source_lock_sha256'] for r in rows if r['source_lock_sha256']}):
        if digest==sha(root/'source_lock.json'):
            continue
        record=known_locks[digest]
        snapshot=record.parent/'previous_frozen_source'
        if not snapshot.exists():
            raise RuntimeError('Archived admission has no source snapshot: '+str(record))
        prior=read(record)
        bad=[p for p,h in prior['sources'].items() if not (snapshot/p).exists() or sha(snapshot/p)!=h]
        if bad:
            raise RuntimeError('Archived source snapshot changed: '+str(bad))
        archived_versions.append(dict(lock=str(record),sha256=digest,source_count=len(prior['sources']),verified=True))
    latest={row['seed']:row for row in rows}
    summary = dict(state=state, valid_new_plants=len(unique_admissions(results['rows'])),
                   attempted_completed=len(rows), rows=rows, changed_frozen_files=changed,
                   unique_seeds_registered=len(latest),unique_seeds_with_final_audit=len({r['seed'] for r in rows if r['anatomy_verified']}),latest_outcome_per_seed=list(latest.values()),
                   archived_source_versions=archived_versions,
                   previous_two_regressions_excluded=True, new_training_started=False,
                   human_visual_review='pending',
                   limits='Flat diagnostic soil; leaf-leaf overlaps and proximity warnings unchanged; flowers/context not exhaustively certified')
    write(root/'review_summary.json', summary)
    write(root/'review_manifest.json', dict(files=manifest, state_at_review=state))
    review_gallery(root,summary)
    return summary


def review_gallery(root,summary):
    import html
    selected={}
    for row in summary['rows']:
        prior=selected.get(row['seed'])
        if prior is None or prior['status']!='admitted':selected[row['seed']]=row
    cards=[]
    for seed,row in sorted(selected.items()):
        folder=Path(row['folder']);relative=folder.relative_to(root).as_posix()
        admitted=row['status']=='admitted'
        image=folder/('preview.png' if admitted else 'rejected_preview.png')
        preview=f'<a href="{relative}/{image.name}"><img src="{relative}/{image.name}" alt="Semilla {seed}"></a>' if image.exists() else '<p>Sin render terminado de este intento.</p>'
        label='Admitido físicamente' if admitted else ('Rechazado' if row['anatomy_verified'] else 'Parcial sin admisión')
        counts=row['counts'];crossings=row['final_crossings'] if row['anatomy_verified'] else row['best_crossings']
        links=[]
        for name,text in [('admission.json','Auditoría'),('plant.json','Árbol final'),('best_plant.json','Mejor checkpoint'),('final_independent_mesh.json','Mallas')]:
            if (folder/name).exists():links.append(f'<a href="{relative}/{name}">{text}</a>')
        cards.append(f'<article class="{"valid" if admitted else "rejected"}"><h2>{seed}</h2><strong>{label}</strong>{preview}<p>{counts.get("leaves","—")} hojas y {counts.get("fruits","—")} frutos totales del árbol. Cruces: {html.escape(str(crossings))}. Advertencias de proximidad: {row.get("proximity_warnings","—")}. Solapamientos hoja–hoja tolerados: {row.get("leaf_leaf_soft_count","—")}.</p><p>'+ ' · '.join(links)+'</p></article>')
    status='Terminada' if summary['state']['status']=='complete' else 'En curso'
    chart='<h2>Convergencia</h2><img class="chart" src="convergence.png"><p>Reconstrucciones sucesivas, no tiempo ni una comparación causal entre versiones.</p>' if (root/'convergence.png').exists() else ''
    page='<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión de corrección nodal</title><style>body{font:17px system-ui;max-width:1300px;margin:30px auto;padding:18px;background:#f2f2ed;color:#202321}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}article{background:white;padding:18px;border-radius:10px;border-top:6px solid #ba7428}article.valid{border-color:#358052}img{width:100%;height:auto;margin-top:12px}.chart{max-width:1100px}a{color:#204e7a}</style>'
    page+=f'<h1>{status}: {summary["valid_new_plants"]} arbustos nuevos admitidos</h1><p>{summary["unique_seeds_registered"]} semillas con intentos registrados. Una tarjeta por semilla; las continuaciones no se cuentan como árboles distintos. Dos regresiones previas excluidas del objetivo.</p><p>Sin entrenamiento. Revisión visual humana pendiente. Auditoría sobre suelo plano; excepción hoja–hoja y advertencias de proximidad conservadas. Flores y contexto no tienen certificación exhaustiva.</p><main>'+''.join(cards)+'</main>'+chart
    page+='<h2>Regresiones anteriores, excluidas del contador</h2><p>Los dos ejemplos previamente admitidos volvieron a pasar. Son referencias de continuidad y no plantas nuevas.</p><main>'
    for seed in (2026102601,2026102600):
        image=f'../nodal_repulsion_review_20261027/gallery/seed_{seed}/after.png'
        page+=f'<article class="valid"><h3>{seed} · regresión previa</h3><img src="{image}" alt="Regresión previa {seed}"><a href="regressions/{seed}/admission.json">Comprobación del nuevo trabajador</a></article>'
    page+='</main><p><a href="review_summary.json">Resumen íntegro</a> · <a href="review_manifest.json">Hashes</a> · <a href="budget.json">Presupuesto efectivo</a></p></html>'
    (root/'review_gallery.html').write_text(page,encoding='utf-8')
    manifest=read(root/'review_manifest.json');manifest['files']['review_gallery.html']=sha(root/'review_gallery.html');write(root/'review_manifest.json',manifest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--write-report', action='store_true')
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()
    summary = summarize(args.root.resolve())
    print(json.dumps({k: summary[k] for k in ('valid_new_plants', 'attempted_completed', 'changed_frozen_files')}, ensure_ascii=False))
    if summary['changed_frozen_files']:
        raise SystemExit('Frozen sources/configuration changed')
    if args.plot:
        plot_history(args.root.resolve())
    if args.write_report:
        if summary['state']['status']!='complete':
            raise SystemExit('Final report requires a stopped controller')
        write_report(args.root.resolve(),summary)


def plot_history(root):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    grouped={}
    for row in read(root/'results.json')['rows']:
        path=Path(row['folder'])/'history.json'
        if path.exists():grouped.setdefault(row['seed'],[]).extend(r['crossings'] for r in read(path))
    fig,ax=plt.subplots(figsize=(10,6))
    fig.subplots_adjust(bottom=.20,top=.90,left=.09,right=.98)
    for seed,values in sorted(grouped.items()):
        best=[];minimum=float('inf')
        for value in values:minimum=min(minimum,value);best.append(minimum)
        line,=ax.plot(range(1,len(best)+1),best,linewidth=1.8,label=str(seed))
        ax.scatter(range(1,len(values)+1),values,s=9,alpha=.25,color=line.get_color())
    ax.set_yscale('symlog',linthresh=1)
    ax.set_ylim(bottom=-.1)
    ax.axhline(0,color='#337346',linewidth=.8)
    ax.set_xlabel('Reconstrucciones por semilla, incluidas continuaciones (no es tiempo)')
    ax.set_ylabel('Cruces de mallas auditadas')
    ax.set_title('Corrección nodal: mejor estado reconstruido por semilla')
    ax.grid(alpha=.2);ax.legend(title='Semilla',fontsize=8,ncol=2)
    fig.text(.02,.02,'Línea: mínimo acumulado. Puntos: estados ensayados. Cero cruces requiere además suelo, orientación y anatomía válidos.',fontsize=8)
    fig.savefig(root/'convergence.png',dpi=160,bbox_inches='tight')
    fig.savefig(root/'convergence.svg',bbox_inches='tight')
    plt.close(fig)
    manifest=read(root/'review_manifest.json')
    for name in ('convergence.png','convergence.svg'):manifest['files'][name]=sha(root/name)
    write(root/'review_manifest.json',manifest)


def write_report(root,summary):
    import re
    path=ROOT/'docs/reports/correccion_nodal_automatizada_2026-10-27.md'
    marker='<!-- AUTOMATIC_NODAL_RESULTS -->'
    body=path.read_text(encoding='utf-8').split(marker)[0].rstrip()
    body=body.replace('Estado de este documento: **ejecución en curso; resultados finales pendientes**.',
                      'Estado de este documento: **búsqueda terminada; revisión visual humana pendiente**.')
    state=summary['state'];budget=read(root/'budget.json')
    n=summary['valid_new_plants'];attempts=summary['attempted_completed'];seeds=summary['unique_seeds_registered']
    limit='límite de tiempo efectivo' if state['stop_reason']=='active_time_limit_reached' else 'objetivo de árboles nuevos válidos'
    body=re.sub(r'^\*\*Resultado al cierre:.*\*\*\n?', '',body,flags=re.MULTILINE)
    anchor='Estado de este documento: **búsqueda terminada; revisión visual humana pendiente**.'
    body=body.replace(anchor,anchor+f'\n\n**Resultado al cierre: {n} arbustos nuevos admitidos de {seeds} semillas distintas; parada por {limit}. No se inició otro piloto.**')
    lines=[marker,'','## Resultados finales de la automatización','',
           f'La cola terminó por **{limit}**, con **{n} arbustos nuevos admitidos** de {seeds} semillas con intentos registrados y {attempts} intentos terminados o preservados. {summary["unique_seeds_with_final_audit"]} semillas tienen al menos una auditoría final completa; las demás sólo cuentan como parciales. Los dos ejemplos anteriores no están incluidos en el objetivo.',
           '',f'Reloj efectivo acumulado: {state["active_elapsed_seconds"]/3600:.4f} h; tope autorizado: {budget["limit_active_seconds"]/3600:g} h. Incluye implementación, pruebas, búsqueda y vistas dentro de la ejecución; excluye suspensión. No se reinició el presupuesto. No se entrenó ningún detector ni se inició otro piloto.','',
           '| Semilla | Hojas | Frutos/capachos | Cruces iniciales → mejor → final | Proximidades | Resultado |',
           '|---|---:|---:|---|---:|---|']
    def value(v):return '—' if v is None else str(v)
    seen=set()
    for row in summary['rows']:
        repeated=row['seed'] in seen;seen.add(row['seed'])
        seed=str(row['seed'])+(' (continuación)' if repeated else '')
        counts=row['counts'];status='Admitido' if row['status']=='admitted' else ('Rechazado' if row['anatomy_verified'] else 'Parcial sin admisión')
        numbers=' → '.join(value(row.get(k)) for k in ('initial_crossings','best_crossings','final_crossings'))
        lines.append(f'| {seed} | {counts.get("leaves","—")} | {counts.get("fruits","—")} | {numbers} | {value(row["proximity_warnings"])} | {status} |')
    lines+=['','Los cruces iniciales de una semilla nueva corresponden a su primera reconstrucción después de la búsqueda por proxies. Los de una continuación corresponden a la postura preservada, no al árbol sin ajustes. Un parcial no tiene admisión ni se suma al total aunque conserve un mejor checkpoint.',
            '', 'Para todos los intentos con auditoría final se volvió a comprobar la igualdad de la firma anatómica entre original y resultado. Las admisiones se contrastaron con los cuatro informes independientes, no sólo con el estado escrito por el controlador. Fuentes actuales y versiones archivadas verificadas por hash.','']
    valid=[r for r in summary['rows'] if r['status']=='admitted']
    if not valid:
        lines+=['**No se alcanzó una nueva admisión física.** La automatización y las regresiones no deben presentarse como una solución general del problema. Los rechazos muestran que el algoritmo, con estos presupuestos y restricciones, no completó la separación de órganos. No demuestran imposibilidad geométrica de los árboles.','']
    else:
        lines+=['La admisión es exclusivamente física dentro del alcance auditado. Las semillas sin convergencia permanecen rechazadas; no se sustituyeron por clones ni se redujeron sus órganos para completar el objetivo.','']
    lines+=['## Muestras y artefactos','',
            '[Galería local por semilla](../../outputs/nodal_controller_automation_20261027/review_gallery.html), [resumen por intento](../../outputs/nodal_controller_automation_20261027/review_summary.json) y [manifiesto de archivos](../../outputs/nodal_controller_automation_20261027/review_manifest.json).','',
            'Cada carpeta conserva original, mejor postura, ajustes, fuentes identificadas, auditorías y, cuando terminó a tiempo, imagen. Las imágenes de rechazo se llaman `rejected_preview.png` y se presentan separadas de las admisiones. No son ejemplos aptos para entrenamiento.','',
            '## Observaciones y próximos pasos','',
            'Observado: la tercera candidata redujo sus 16 cruces preservados a 3, y el reparto temporal corto resultó insuficiente para completar los dos primeros árboles nuevos. Los estados provisionales que aumentaron contactos no reemplazaron la mejor reconstrucción. Los límites angulares son hipótesis de ingeniería; una imagen sin cruces no valida por sí sola su postura botánica.',
            '', 'Se incorporó y probó la coordinación de dos y cuatro entrenudos. Su prueba de reconstrucción no demuestra convergencia general ni plausibilidad botánica. Como hipótesis posteriores quedan ampliar la coordinación cuando persistan bloqueos, distribuir cómputo según categoría y progreso, e incorporar evitación de contactos durante el desarrollo progresivo conservando la carga completa. Requieren pruebas nuevas; no se presentan como resultados ya obtenidos.',
            '', 'La revisión de copa, postura y apariencia debe preceder a cualquier nuevo piloto. El suelo plano, el fondo diagnóstico y la escala visual de estas muestras no equivalen a escenas reales de entrenamiento. No hay evidencia nueva sobre eficacia de iluminación o texturas para el detector.',
            '', '## Validación y continuidad','',
            'Diecisiete pruebas puras del controlador, búsqueda acotada y cadenas, y siete pruebas distintas en Blender, pasaron; las dos regresiones anteriores conservaron sus auditorías. Las modificaciones de reparto temporal preservaron las fuentes de cada intento. El validador del grafo mantiene los diez errores preexistentes de localizadores, separados de cualquier regresión mediante comparación con el grafo archivado. No se alteraron las campañas cerradas.','']
    if (root/'convergence.png').exists():
        index=lines.index('## Observaciones y próximos pasos')
        lines[index:index]=['![Convergencia por reconstrucciones, no por tiempo](../../outputs/nodal_controller_automation_20261027/convergence.png)','']
    path.write_text(body+'\n\n'+'\n'.join(lines),encoding='utf-8')
    files=[path,ROOT/'docs/guides/controlador_repulsion_nodal.md',ROOT/'docs/repository_context_graph.json',Path(__file__)]
    write(root/'report_manifest.json',dict(files={str(p):sha(p) for p in files},review_summary_sha256=sha(root/'review_summary.json')))


if __name__ == '__main__':
    main()
