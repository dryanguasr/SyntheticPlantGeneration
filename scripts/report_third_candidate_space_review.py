"""Publish a local review only after the single candidate passed all gates."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main(out):
    result=read(out/'admission.json')
    assert result['status']=='admitted' and result['physical_crossings']==0
    assert read(out/'process_exit.json')['exit_code']==0
    assert (out/'passed_fixed_camera.png').exists()
    lock=read(out/'source_lock.json')
    assert all(sha(ROOT/p)==h for p,h in lock['files'].items())
    before=read(out/'baseline_mesh.json');after=read(out/'final_mesh.json')
    comparison=read(out/'geometry_comparison.json');plan=read(out/'admission_plan.json')
    omitted=len(plan['selected_units']);counts=result['counts'];original=plan['source_anatomy']['counts']
    loss=100*omitted/original['fruits']
    old='../../outputs/nodal_controller_automation_20261027/plants/seed_2026102602_retry03/rejected_preview.png'
    current='../../outputs/third_candidate_generation_fix_20261028/passed_fixed_camera.png'
    report=ROOT/'docs/reports/tercera_candidata_admision_reproductiva_2026-10-28.md'
    text=f'''# Tercera candidata: diagnóstico y admisión reproductiva — 28/10/2026

**Semilla 2026102602 admitida en la auditoría física estática: 0 cruces, {counts['leaves']} hojas y {counts['fruits']} frutos/capachos.** Se omiten {omitted} unidades completas ({loss:.3f} % de los frutos originales), ninguna hoja. No se prueban otras semillas ni se inicia entrenamiento. Revisión visual humana pendiente.

## Por qué persistían los tres contactos

Una reconstrucción nueva del árbol preservado reprodujo los tres cruces:

- Un capacho cruza su propio tallo en el nodo 9 del eje principal.
- Dos parejas de capachos se cruzan en los nodos 1–2 y 3–4 de un ramal de orden 3.

La asignación de cohortes propone cálices completos sin admisión espacial. El generador reduce los entrenudos por orden, edad y vigor, mientras el pedicelo y el capacho se muestrean por otras reglas. En ese ramal los entrenudos nominales son de 1,33–1,84 cm, los pedicelos de 1,07–1,48 cm y los capachos de 3,85–5,90 cm de largo. Son valores del modelo, no medidas de campo. Las proporciones no prueban una intersección; ésta se confirmó separadamente en las mallas evaluadas.

La búsqueda angular de longitud fija dejó estos tres conflictos dentro de sus límites y presupuesto. No se ha demostrado que sea imposible conservar los 408 frutos con otra geometría o una búsqueda diferente.

## Corrección antes de construir la geometría

Se añade una admisión explícita y optativa en la gramática. Recibe conflictos verificados, ligados por hash a la anatomía original y a la evidencia. Un solucionador puro busca el conjunto mínimo de unidades que cubre esos contactos, preservando los índices nodales bajos al desempatar. El 1 % es un techo de reducción permitido para esta revisión; no impone una carga reproductiva ni una cuota global a las plantas.

La semilla se regenera con los parámetros originales: primero se verificó que recupera exactamente la anatomía anterior. Antes de materializar la geometría se omiten estas unidades propuestas:

'''
    text+='\n'.join('- `'+u+'`' for u in plan['selected_units'])
    text+='''

Se omite cada unidad completa —pedicelo, fruto y capacho— en el árbol, manteniendo nodo, hoja y estructura de la rama. La yema queda sin unidad reproductiva aceptada, con procedencia explícita. Es una decisión de ingeniería, no una simulación ni una medición de aborto floral. No se borran objetos Blender ni fragmentos de anotaciones.

La cámara, luz, materiales y clases visuales de los órganos retenidos se conservan respecto de la vista anterior. Las posturas se reproducen desde el mejor árbol preservado. El plan procede de esa postura auditada: es una regeneración asistida por realimentación, no un modelo autónomo que garantice plantas sin contactos desde cualquier semilla. La generación histórica sin plan conserva su comportamiento.

## Verificación independiente

'''
    text+=f'''| Comprobación | Resultado |
|---|---|
| Cruces duros auditados, antes → después | {before['physical_collision_count']} → {after['physical_collision_count']} |
| Hojas | {original['leaves']} → {counts['leaves']} |
| Frutos/capachos | {original['fruits']} → {counts['fruits']} |
| Flores | {original['flowers']} → {counts['flowers']} |
| Ejes / nodos | {counts['axes']} / {counts['nodes']}, conservados |
| Objetos retenidos con vértices mundiales y caras orientadas idénticos | {comparison['retained_object_count']} |
| Objetos de las unidades omitidas | {comparison['removed_object_count']}, ausentes en la reconstrucción |
| Suelo plano, margen requerido 1 mm | {result['ground_status']} |
| Orientación colgante y unión proximal | {result['orientation_status']}, {result['checked_calyces']} capachos |
| Errores de morfología | {len(result['morphology_errors'])} |
| Advertencias de proximidad | {result['proximity_warnings']} |
| Intersecciones hoja–hoja de ocupación blanda | {result['leaf_leaf_soft_occupancy']} |

Se verifica la identidad de las {counts['calyces']} instancias de cáliz y de los {counts['fruits']} frutos, incluidos los ocultos. Los IDs omitidos no permanecen en RGB ni en los objetos anotables. La comparación canónica conserva exactamente coordenadas y caras orientadas, sin redondeo ni tolerancia; no exige el mismo orden interno de índices de bmesh. El primer intento de comparación por índices se preservó tras detectar ese reordenamiento. Dos fixtures de Blender verifican que se ignoran sólo las permutaciones, que se detecta un desplazamiento de 1e-10 y que se conserva la orientación de las caras. No se generó un banco de entrenamiento ni se exportó una nueva partición YOLO.

La admisión conserva el alcance anterior: hoja–hoja se tolera como ocupación blanda y la proximidad es advertencia. No certifica todas las flores ni el contexto, terreno irregular, mecánica o plausibilidad botánica. Cero cruces auditados tampoco demuestra realismo fotográfico o utilidad para el detector.

## Muestras

Antes, rechazado por tres cruces:

![Antes]({old})

Después, misma cámara y órganos retenidos idénticos:

![Después]({current})

## Pruebas y continuidad

Pasaron nueve pruebas nuevas de admisión pura: cobertura mínima, contactos compartidos, límites de reducción, evidencia e identidades inválidas, alteración del plan, conservación reversible de la anatomía, serialización y ruta explícita de la gramática. Pasaron también las catorce regresiones puras de repulsión nodal. La prueba integral en Blender reconstruyó el antes y el después, comparó todos los órganos retenidos y ejecutó las auditorías de malla, suelo, orientación y morfología.

Se conservan las fuentes de entrada y de esta revisión, el plan, la evidencia y los árboles. Los resultados anteriores cerrados permanecen intactos. La validación del grafo mantiene los diez errores preexistentes de localizadores; la comparación con el grafo archivado separa regresiones nuevas.

Para una próxima revisión del modelo conviene contrastar espacio nodal, pedicelo y crecimiento del capacho de forma conjunta antes de fijar el volumen adulto. Aquí se demuestra sólo la admisión de esta candidata con una reducción acotada; no una tasa de éxito para otras plantas. El siguiente ensayo permanece pendiente de mostrar y revisar este arbusto.
'''
    report.write_text(text,encoding='utf-8')
    html=f'''<!doctype html><html lang="es"><meta charset="utf-8"><title>Tercera candidata: auditoría física</title>
<style>body{{font:17px system-ui;background:#f5f4ef;max-width:1300px;margin:30px auto;padding:20px}}main{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}article{{background:white;border-radius:12px;padding:18px}}img{{width:100%}}aside{{padding:16px;background:#e0eddc}}@media(max-width:700px){{main{{grid-template-columns:1fr}}}}</style>
<h1>Tercera candidata: 0 cruces físicos auditados</h1><aside>{counts['leaves']} hojas conservadas · {counts['fruits']}/{original['fruits']} frutos · reducción {loss:.3f}% · sin otras semillas ni entrenamiento.</aside>
<main><article><h2>Antes: rechazado, 3 cruces</h2><img src="../nodal_controller_automation_20261027/plants/seed_2026102602_retry03/rejected_preview.png"></article><article><h2>Después: admitido</h2><img src="passed_fixed_camera.png"><p>Misma cámara, posturas y geometría de los órganos retenidos.</p></article></main>
<p>{result['proximity_warnings']} advertencias de proximidad; hoja–hoja tolerado como ocupación blanda. Suelo plano válido a 1 mm, {result['checked_calyces']} capachos con orientación y unión válidas, sin errores morfológicos. Revisión visual humana pendiente. No certifica flores/contexto exhaustivos, mecánica ni eficacia del detector.</p>
<p>Regeneración con plan espacial derivado de la postura anterior auditada; no garantiza nuevas semillas.</p>
<p><a href="admission.json">Admisión</a> · <a href="diagnosis.json">Diagnóstico</a> · <a href="geometry_comparison.json">Geometría retenida</a> · <a href="admission_plan.json">Unidades omitidas</a> · <a href="plant.json">Árbol final</a></p></html>'''
    (out/'review.html').write_text(html,encoding='utf-8')
    files=[report,Path(__file__),*out.glob('*.json'),out/'passed_fixed_camera.png',out/'review.html']
    (out/'report_manifest.json').write_text(json.dumps(dict(files={str(p.resolve()):sha(p) for p in files
        if p.name!='report_manifest.json'}),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(report),status=result['status'],counts=counts)))


if __name__=='__main__': main(Path(sys.argv[1]).resolve())
