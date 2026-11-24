# Revisión de copa ramificada y frondosa

Fecha: 26 de octubre de 2026. Revisión estructural posterior a la segunda galería de apariencia. El usuario considera que el color mejoró, pero que la planta v4 sigue demasiado estrecha y poco parecida a los arbustos reales. **La arquitectura v5 está implementada y las ocho vistas comparativas están terminadas.** La inspección muestra una copa más amplia y frondosa, pero persisten bases poco ramificadas e intersecciones. Sigue pendiente la revisión humana; no hay aprobación física ni entrenamiento ni mejora de detección demostrada.

## Referencias reales y alcance de la observación

Se verificaron hashes de las 461 imágenes y etiquetas del entrenamiento vigente. Se inspeccionaron visualmente 24 encuadres de sus nueve grupos y se eligieron ocho para cubrir copas frondosas, abiertas y ramas cercanas. No se abrieron imágenes de validación ni test para esta revisión. Las láminas conservan los encuadres completos y el color; únicamente reducen la resolución para mostrarlos juntos.

| Filas de entrenamiento | Grupo | Observación útil |
|---|---|---|
| 350 | component_14 | Masas laterales de follaje, alturas irregulares y tutorado; varias plantas superpuestas y recortadas. |
| 625, 438 | component_25 | Volumen foliar a varias alturas, ramas oblicuas y profundidad de hilera; los límites individuales no siempre son visibles. |
| 95, 602 | component_83 | Copa frondosa y copa más abierta dentro del mismo grupo, ambas con vegetación acompañante. |
| 176 | component_25 | Encuadre amplio con tutorado, suelo y vegetación baja; solo dos capachos anotados no describen la carga de los arbustos. |
| 547 | component_174 | Rama cercana con hojas en varios planos y capachos parcialmente tapados. |
| 612 | component_35 | Capachos y hojas intercalados en una toma vertical cercana; no muestra una copa completa. |

![Referencias de volumen lateral](../../outputs/appearance_factorial_20261026/revisions/crown_feedback_20261026/real_references_panel_1.png)

![Referencias de copa abierta y ramas](../../outputs/appearance_factorial_20261026/revisions/crown_feedback_20261026/real_references_panel_2.png)

Estas imágenes apoyan revisar **extensión lateral, reparto del follaje y contexto por separado**. Un eje más alto no garantiza una copa más ancha. La imagen más frondosa tampoco tiene necesariamente más capachos anotados: las filas 95 y 602 contienen nueve y trece, respectivamente, con puntos de vista diferentes. Eso no constituye un experimento de carga botánica.

La selección es cualitativa, no una estimación de frecuencias. `component_N` no identifica necesariamente una planta ni una sesión independiente. El manifiesto no permite vincular con certeza esos grupos a los videos recientes 125180–125182; no se atribuyen fechas o condiciones de manejo a partir de su apariencia. Plantas superpuestas, recorte y partes ocultas impiden deducir cantidades totales de hojas, ramas o frutos.

## Diagnóstico de v4

La inspección humana de v4 identifica una copa demasiado estrecha. La revisión del código y de sus árboles muestra dos mecanismos que merece la pena comparar: desarrollo lateral todavía corto y reducción de la longitud foliar tanto por orden como por vigor del eje. Cambiar únicamente la pose foliar en v4 no resuelve necesariamente esas restricciones.

La reconstrucción de direcciones también encontró una limitación del marco anterior: proyectar el azimut global sobre el plano normal de un eje casi horizontal reduce la diversidad de direcciones alrededor de ese eje. El nuevo marco local evita esa dependencia del plano global.

Los diagnósticos guardados de geometría y pose usan árboles, envolventes evaluadas y proxies de orientación. Sus AABB y cosenos proyectados no equivalen a área visible de hoja, oclusión física ni verdad botánica. Los objetos internos ocultos se excluyen de cualquier interpretación de silueta visible. Persisten las auditorías físicas como requisito separado.

## Hipótesis v5 implementada

El preset nuevo es `trained_trellis_broad_crown_audit_v5`, con política `architecture_driven`, contrato `audit-morphology/2` y procedencia de ingeniería explícita. Los presets v2, v3 y v4 conservan su configuración para reproducir las galerías anteriores.

| Cambio | Interpretación y límite |
|---|---|
| Desarrollo nodal y presupuesto de los laterales ampliados | La extensión lateral procede de módulos nodales; el presupuesto del eje principal se conserva respecto a v4. No se duplican hojas ni se colocan ramas globalmente para llenar una cámara. |
| Escala de hoja adulta separada del vigor del eje | Se conserva el rango base de longitud 4,6–9,2 cm y la relación ancho/longitud, pero cambian los factores por orden y se elimina la reducción adicional por vigor. Por ello las hojas laterales efectivas pueden ser mayores que en v4. Es una hipótesis de desarrollo, no una medición local nueva ni un agrandamiento dependiente del encuadre. |
| Apertura de ramas por orden y marco local tridimensional | Las orientaciones se expresan respecto a la tangente del eje. Blender y los proxies comparten el cálculo; las hojas no giran para mirar a la cámara. |
| Carga reproductiva emergente | No se impone mínimo, máximo ni objetivo global de frutos. Los estados se asignan a unidades existentes; conteos finales y snapshots siguen siendo auditables. |

Los valores concretos permanecen en `parameters.py` y en el snapshot efectivo de cada árbol; no se presentan como parámetros botánicos calibrados. La comparación v4/v5 cambia conjuntamente desarrollo lateral, escala adulta y marco de orientación: **no permite aislar el efecto de cada modificación**.

## Comparación visual ejecutada

Se ejecutaron ocho imágenes técnicas, separadas de las dos rondas completas y de cualquier banco de entrenamiento: cuatro en `crown_v4_control` y cuatro en `crown_v5_candidate`. Ambas variantes comparten semillas, cámara, distancia, objetivo, configuración y anclaje de iluminación, materiales y contexto. Sus árboles y máscaras cambian, pues la intervención es estructural; la invariancia de geometría se exigirá después dentro de B/L/T/LT sobre la arquitectura que se apruebe. La recursión más extensa cambia el consumo posterior del RNG: compartir semilla entre v4 y v5 no implica correspondencia órgano por órgano ni idéntico eje principal realizado, aunque sus parámetros principales se conserven.

La revisión debe comprobar que la ganancia lateral no sea un efecto de acercar la cámara o escalar toda la planta. Conviene contrastar ancho/alto proyectado y perfil de anchura por alturas, reparto espacial de follaje, huecos y capachos visibles. Un autoencuadre distinto podría ocultar cambios de escala o de altura.

Para comparar con el real hacen falta regiones de planta y máscaras de hojas revisadas cuando se cuantifique cobertura. Un umbral de verde mezcla uchuva y maleza. La razón área visible de hoja/capacho no representa hojas por fruto; las cajas no sustituyen las máscaras sin declarar esa aproximación. Estas propuestas no introducen umbrales nuevos de admisión.

La aceptación visual no reemplaza la auditoría final de mallas y separación respecto al terreno. Una copa mayor puede aumentar contactos inválidos. Se preservarán rechazos e intentos, sin eliminar órganos para superar el control ni llamar oclusión a una intersección. Las intersecciones hoja–hoja admitidas como ocupación blanda y la cobertura incompleta de contactos con maleza siguen siendo limitaciones explícitas.

## Resultados posteriores de las ocho vistas

![Cuatro comparaciones con encuadre fijo](../../outputs/appearance_factorial_20261026/calibration/crown_v5_candidate/review/comparacion_copas.jpg)

La copa se extiende lateralmente y las hojas ocupan más planos. La segunda semilla muestra el volumen completo; en las otras tres la parte superior alcanza o sale del encuadre original. Se conservó ese truncamiento, sin alejar la cámara ni recortar adicionalmente las imágenes para ocultarlo. En especial la cuarta planta conserva una base larga y poco ramificada. V5 corrige la escasez lateral, pero todavía no reproduce toda la variación de arquitectura de las referencias reales.

| Planta / semilla | Ejes v4 → v5 | Hojas v4 → v5 | Frutos v4 → v5 | Ancho horizontal máximo evaluado v4 → v5 | Capachos visibles v4 → v5 |
|---|---:|---:|---:|---:|---:|
| 1 / 2026102600 | 27 → 85 | 145 → 632 | 37 → 236 | 0,69 → 1,12 m | 37 → 193 |
| 2 / 2026102601 | 42 → 129 | 212 → 934 | 61 → 343 | 0,68 → 1,25 m | 61 → 271 |
| 3 / 2026102602 | 31 → 88 | 161 → 644 | 33 → 225 | 0,79 → 1,41 m | 32 → 166 |
| 4 / 2026102603 | 29 → 61 | 161 → 464 | 53 → 178 | 0,61 → 1,24 m | 53 → 160 |

Los conteos son del árbol completo; los visibles proceden de la máscara de esta captura y pueden incluir fragmentos pequeños. No son cuotas ni medidas de carga real. El ancho usa el máximo de las extensiones X/Y de envolventes evaluadas de tallos y hojas visibles, con 0,125 m por unidad Blender; no es ancho segmentado de la fotografía ni prueba de volumen sólido. Los capachos mantienen sus rangos dimensionales previos. La mayor carga surge de más sitios nodales, sin recortarla para obtener una composición conveniente.

Las matrices de cámara e intrínsecos coinciden exactamente entre los pares guardados. Se verificaron perfiles de apariencia, semilla y registro de entorno, fuente congelada y anclaje de luz comunes. Una limitación de instrumentación quedó registrada: `lighting_geometry.matrix_world` se capturó antes de actualizar el depsgraph y no acredita por sí sola la pose observada. La igualdad de iluminación se sustenta en los mismos datos de entrada y código congelado; se corrigió el orden para futuras capturas, conservando intactos los ocho registros y sus snapshots.

La auditoría de mallas v5 devuelve **310/510/279/218 intersecciones** y **180/418/162/128 violaciones de separación**. Las intersecciones reportadas son cáliz–tallo, cáliz–cáliz y tallo–tallo: no desaparecen aplicando una excepción hoja–hoja ni se deben llamar oclusión visual. Los recuentos previos v4 fueron 35/63/40/47 y 21/38/27/36. Estas escenas no se admiten para entrenamiento. La siguiente corrección debe resolver disposición y separación nodal de órganos y revisar contactos permitidos, conservando frutos y evidencia de los intentos.

Se corrigió además un defecto independiente de auditoría: frutos ocultos con `hide_viewport` se medían erróneamente cerca del origen. La evaluación temporal del depsgraph restaura la visibilidad mediante `finally`, sin cambiar `hide_render` ni mallas. Dos pruebas Blender CPU verifican el caso normal y una excepción inyectada. Las ocho auditorías nuevas ya usan esta corrección; sus envolventes fruto–cáliz no indican frutos fuera de la AABB. Esto no demuestra contención sólida ni invalida las intersecciones registradas por separado.

**Verificación:** 110 pruebas CPU y dos pruebas Blender CPU aprobadas; ocho árboles revalidados sin errores de integridad, con advertencias conservadas; correspondencia color de máscara–instancia–clase comprobada. Las flores mantienen cero píxeles en la máscara de capachos y no reciben clase de apariencia. Se verificaron hashes y grupos de las 643 imágenes, los 13 archivos congelados del piloto anterior y su informe. El ledger acumula 878,97 segundos activos en seis trabajos, incluidos 282,08 segundos de esta comparación; 114 imágenes diagnósticas acumuladas, cero corridas de entrenamiento. La revisión humana sigue pendiente y no se creó `review_lock.json`.

El protocolo de entrenamiento, las dosis 46/115/230 y la matriz de 26 screenings y 36 confirmaciones permanecen como se describe en [la guía](../guides/piloto_apariencia_factorial.md). No se extrae ninguna conclusión de AP de este diagnóstico estructural.

## Evidencia y verificación

- Código y contratos: `parameters.py`, `grammar.py`, `organ_frames.py`, intérprete Blender y proxies; `tests/test_audit_broad_crown.py` comprueba compatibilidad histórica, rangos, procedencia e independencia de captura. Los tests CPU no certifican semejanza visual ni ausencia de colisiones.
- Evidencia local: `outputs/appearance_factorial_20261026/revisions/crown_feedback_20261026/`, incluidos `selected_references.json`, los diagnósticos v4 y `observaciones_copa_real.md`. Los artefactos generados son evidencia de ejecución, no autoridad del modelo en el grafo.
- Atribución de fotografías: Uchuva Naranja / Diego Amaya; licencia CC BY 4.0 según la exportación original del dataset.
- Se ejecutó `validate_repository_context_graph.py`: conserva los diez errores de localizadores preexistentes y no añade otros por identidad/ruta. El log anterior contiene caracteres de reemplazo en texto acentuado; esa diferencia de codificación se registra en `graph_validation_v5_comparison.json` y no se presenta como una regresión nueva. La validación global sigue sin pasar.

Las clases conservan su interpretación de apariencia del capacho. No se afirma madurez interna, calibración botánica absoluta ni generalización externa.
