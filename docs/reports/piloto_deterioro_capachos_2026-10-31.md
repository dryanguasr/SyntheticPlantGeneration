# Piloto visual de secado y deterioro del capacho

La revisión vigente contiene cuatro láminas Blender: dos ejemplares derivados de unidades del modelo morfológico y cinco estados por ejemplar, bajo dos luces. Son **órganos aislados para revisión visual**, no nuevas plantas admitidas ni nuevas imágenes del banco de entrenamiento.

## Observación y representación

El usuario observó cambios de textura, tonos marrones, oscurecimiento próximo al pedicelo, pérdida de color/tamaño y compresión progresiva en parte de los capachos etiquetados Sobremadura. Se conserva la validez de la apariencia pajiza existente: deterioro visible y clase no son equivalencias obligatorias. No se añaden clases ni se reetiqueta el banco actual.

La secuencia compara Madura, Sobre pajiza actual y deterioro leve/intermedio/avanzado. La segunda variante aumenta la decoloración y reduce el ennegrecimiento para evitar que negro sea una condición universal de la clase. Se mantienen semilla de malla, cámara y escala dentro de cada ejemplar; cambian explícitamente las hipótesis de superficie/forma.

## Implementación

- `calyx_deterioration.py`: estado puro, serializable y determinista. Los valores numéricos son `engineering_heuristic_pending_visual_review`; no edades ni medidas botánicas.
- `blender_calyx_deterioration.py`: interpreta esa hipótesis sobre una copia de la malla y del material; manchas marrones irregulares, oscurecimiento proximal, decoloración, rugosidad y pliegues. Mantiene el polo de unión al pedicelo. No modifica el intérprete histórico.
- La forma se comprime asimétricamente, con pliegues locales y torsión suave; no es sólo un escalado uniforme. La apariencia anterior se conserva como columna de control.

![Comparación principal](../../outputs/calyx_deterioration_pilot_20261031/revisions/phenotype_variation_02/comparison_plate.png)

## Alcance y comprobaciones

Las cuatro pruebas puras pasaron: determinismo, identidad sin deterioro, conservación del polo proximal, compresión y variación sin ennegrecimiento obligatorio. En Blender se comprobó ausencia de aristas no manifold y error de unión inferior a1e−6cm en los diez estados geométricos. Esto **no certifica** ausencia de toda autointersección ni sustituye la auditoría de una planta completa.

La lámina muestra sólo el cáliz y su pedicelo de referencia. No se instancia el fruto interior: la compatibilidad de una envoltura comprimida con el tamaño/estado del fruto necesita un modelo explícito y nueva auditoría antes de aplicar la variante a escenas admitidas. No se simula ni se valida reabsorción fisiológica ni se atribuye todo oscurecimiento a envejecimiento normal.

El estudio de de Souza et al.2022 distingue propiedades de cáliz y fruto de Physalis y sus relaciones con pérdida de agua, pero no calibra esta secuencia ni demuestra el mecanismo de reabsorción propuesto. Referencia consultada: [Multifunctional Contribution of the Inflated Fruiting Calyx](https://doi.org/10.3389/fpls.2022.888930). No se usaron imágenes de publicaciones como texturas ni fondos.

## Preservación y revisión

Hubo12 renders diagnósticos en tres iteraciones; los8 preliminares permanecen archivados. La revisión inicial y la de pliegues permanecen archivadas; la vigente es `revisions/phenotype_variation_02`, con fuentes/hashes, planos JSON, cuatro RGB y escena Blender. Se inspeccionaron las láminas; no se afirma fotorealismo ni mejora del detector. El banco continúa con503 imágenes y20 árboles originales intactos, con presupuesto y lock históricos sin cambios. No hubo entrenamiento ni reanudación de la campaña.

La instrucción para próximas variantes queda en `future_calyx_revision.json`, sin liberar la pausa ni modificar escenas actuales. El siguiente paso depende de revisar esta propuesta visual; no se admiten automáticamente estas formas como plantas válidas.
