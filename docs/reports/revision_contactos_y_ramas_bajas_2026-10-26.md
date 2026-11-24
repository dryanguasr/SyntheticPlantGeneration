# Revisión de contactos y ramas bajas antes del piloto

Fecha: 26 de octubre de 2026. La copa v5 amplió el follaje, pero la revisión visual del usuario identifica intersecciones y ramas bajas que deben corregirse antes de entrenar. Este documento separa los defectos de contacto comprobados, las limitaciones del validador y la hipótesis arquitectónica. **Todavía no acredita una planta reparada ni autoriza el banco de entrenamiento.**

## Evidencia y reconstrucción

Se conservaron las cuatro plantas, los renders y los reportes de `calibration/crown_v5_candidate`. La reconstrucción usa sus 57 fuentes congeladas, perfiles, semillas y árboles verificados por SHA-256, sin volver a muestrear la morfología ni cambiar cámaras, materiales o visibilidad. Las envolventes evaluadas reconstruidas coinciden exactamente con las guardadas; en planta 00 se comprobaron 3.385 objetos con diferencia máxima cero.

La planta 00 se reconstruyó además con la auditoría estricta completa. Una instrumentación registra todas las clasificaciones y candidatos exentos, conservando los resultados de las funciones originales. Las otras tres se reconstruyeron para verificar identidades y distancias verticales de vértices al terreno. Ninguna comprobación generó imágenes ni utilizó GPU. Los 13 archivos congelados del piloto anterior mantienen sus hashes.

Evidencia reproducible: [resumen](../../outputs/appearance_factorial_20261026/revisions/lower_crown_contacts_20261026/contact_summary.json), [hallazgos y límites](../../outputs/appearance_factorial_20261026/revisions/lower_crown_contacts_20261026/findings.json) y [manifiesto](../../outputs/appearance_factorial_20261026/revisions/lower_crown_contacts_20261026/artifact_manifest.json).

## Intersecciones de v5: qué cuenta cada reporte

La calibración llamó `audit_scene_mesh_collisions()` con `tolerate_only_leaf_leaf=False`. Ese modo clasifica como `soft_occupancy` toda intersección en la que participa una hoja. El banco exige `True`: conserva únicamente hoja–hoja en esa categoría y cuenta hoja–tallo y hoja–cáliz entre las intersecciones físicas.

| Planta v5 | Pares físicos en calibración | Pares con hojas clasificados como soft | Separaciones insuficientes |
|---|---:|---:|---:|
| 00 | 310 | 514 | 180 |
| 01 | 510 | 904 | 418 |
| 02 | 279 | 369 | 162 |
| 03 | 218 | 407 | 128 |

**La planta 00 tiene 714 pares físicos bajo el criterio del banco, no 310.** La diferencia son 404 pares con hojas; otros 110 pares hoja–hoja permanecen como ocupación permisiva. Los 714 pares afectan a 773 objetos únicos.

| Tipo de par en planta 00 estricta | Cantidad | Porcentaje de los 714 pares |
|---|---:|---:|
| Cáliz–hoja | 228 | 31,9 % |
| Cáliz–tallo, incluido pecíolo/pedicelo | 224 | 31,4 % |
| Hoja–tallo | 176 | 24,6 % |
| Cáliz–cáliz | 62 | 8,7 % |
| Tallo–tallo | 24 | 3,4 % |

Estos son pares de mallas con intersección, no volúmenes penetrados, porcentajes de oclusión visual ni cantidades de plantas inválidas. Las 180 separaciones insuficientes son un criterio distinto: puede fallar la separación mínima sin que las mallas se corten.

Los reportes históricos guardan como máximo 500 detalles por colección. La planta 01 conserva 500 de sus 510 pares físicos; los detalles soft también están truncados en 00 y 01, aunque el campo `truncated` solo considera la colección física. El desglose estricto completo anterior procede exclusivamente de la reconstrucción instrumentada de 00, sin extrapolar su composición a las demás.

## Inserciones anatómicas y excepciones

Los 1.307 pares físicos persistidos disponibles no incluyen uno que las reglas congeladas consideren exento. Tampoco incluyen cáliz–pedicelo de la misma unidad reproductiva ni pares de tallos que compartan un extremo nodal explícito. No se extiende esta afirmación a los diez detalles no guardados de la planta 01.

En 00 ya se omitían 236 candidatos cáliz–pedicelo propio, 632 hoja–pecíolo propio y 2.952 tallo–tallo por relaciones topológicas. Esos 3.820 candidatos se descartan antes de BVH: **no representan 3.820 intersecciones demostradas**. Las excepciones de inserción ya funcionan; ampliar indiscriminadamente su alcance ocultaría cruces entre órganos distintos.

Un ejemplo comprobado es el entrenudo 5 de `axis_0_0_branch_5_branch_1`, entre nodos 4 y 5, que cruza el entrenudo inicial de su rama hija `branch_0`. La hija se inserta realmente en el nodo 3. Que ambas pertenezcan a la misma bifurcación no convierte ese cruce posterior en una inserción permitida.

Las excepciones futuras deben exigir identidad anatómica y contacto localizado junto a la inserción, con dimensiones efectivas. Las reglas actuales eximen la pareja completa antes de medir triángulos, por lo que no certifican que cualquier contacto remoto de esa pareja sea correcto. No se añaden excepciones generales para la misma planta, rama hija o nodo cercano. Corregir poses debe conservar órganos, identidades, dimensiones y anotaciones.

## Ramas bajas y contacto con el terreno

Las cuatro reconstrucciones no muestran vértices visibles de hojas, cálices, flores o tallos bajo el terreno, ni rayos fuera de su cobertura. En esta comprobación, la categoría hoja incluye las mallas de lámina y nervadura; no equivale a contar dos hojas biológicas por nodo.

| Planta | Mínimo hoja–terreno por vértices | Mínimo cáliz–terreno por vértices |
|---|---:|---:|
| 00 | 7,06 cm | 56,40 cm |
| 01 | 8,41 cm | 39,82 cm |
| 02 | 7,89 cm | 34,89 cm |
| 03 | 9,63 cm | 62,17 cm |

Estos resultados no descartan un corte entre interiores de triángulos ni un contacto con maleza. Tampoco validan botánicamente la altura de las ramas. La percepción de una copa baja sigue siendo una observación válida para revisar desarrollo basal, posición de laterales y contexto; no debe presentarse como una penetración del terreno demostrada por estos datos.

La función histórica `audit_calyx_ground_clearance()` solo revisa vértices de cálices. Sus distancias se calculan en unidades Blender, aunque algunos campos terminan en `_m`. Con `scale_length=0.125`, su valor por defecto `0.008` BU corresponde a **0.001 m**, no a 8 mm. Se conserva su implementación y sus resultados para reproducibilidad.

## Nueva auditoría de suelo

Se añadió [`audit_plant_ground_clearance()`](../../src/uchuva_lsystem/blender_environment.py) sin alterar la función histórica. Su versión `plant-evaluated-terrain/2` declara un umbral de **1 mm** en metros y lo convierte usando la escala efectiva de escena. Revisa triángulos evaluados contra el terreno y, por separado, la distancia vertical de vértices de hojas, cálices, flores, tallos —incluidos pecíolos y pedicelos— y frutos. Informa penetraciones, déficit positivo de separación y cobertura desconocida; cualquiera de ellos invalida el resultado.

El contacto intencional de suelo queda acotado al inicio del eje principal, dentro de dos radios del tallo renderizado alrededor de su origen. La pertenencia al primer entrenudo no exime el resto de su superficie. Los cruces basales coplanares cuya posición no puede localizarse se rechazan conservadoramente. El código no mueve, borra ni oculta órganos.

Los frutos se identifican mediante `organ_kind`, aunque su clase de anotación siga siendo `ignore`. Incluye tanto los expuestos como los interiores ocultos: estar dentro de su cáliz no permite penetrar el terreno. Para evaluar su posición efectiva, restaura temporalmente la presencia en el grafo de dependencias del viewport y después devuelve esos flags a su estado original, incluso al fallar. Nunca cambia `hide_render`. Se registran identidad reproductiva, visibilidad y escala renderizada; esta medición no sustituye el radio morfológico nominal.

La nueva auditoría no incluye maleza ni distractores, ni calcula la distancia positiva exhaustiva entre interiores de triángulos. La nervadura auxiliar se excluye porque se audita la lámina. La auditoría general entre órganos sigue sin cubrir flores ni frutos; permitir un fruto contenido dentro de su cáliz no justificaría eximir un corte de la pared. Tolerar hoja–hoja tampoco demuestra contacto físicamente válido.

Validación realizada: cinco pruebas puras de identidad/localización basal y catorce [fixtures Blender CPU](../../tests/blender_plant_ground_clearance_probe.py), incluidos frutos `ignore` visibles e interiores bajo suelo, fruta interior sobre suelo y restauración de flags al fallar. Todos pasaron. Los dos intentos iniciales fallidos se preservaron: detectaron que la limpieza del fixture dejaba objetos ocultos de casos previos. La prueba aislada de `cleanup_scene()` reprodujo el mismo defecto de selección; se documenta sin atribuirlo a RGB ni al árbol serializado. La corrección posterior usa limpieza explícita de ocultos en las rutas nuevas; las evidencias previas se conservan. La función histórica de suelo permanece intacta.

## Primer probe de reparación: v6, planta 00

`repair_probe_00` usa `trained_trellis_lower_crown_audit_v6`, una arquitectura distinta de v5. Su comparación antes/después conserva el mismo árbol v6: **no se deben comparar sus 1.018 pares iniciales con los 714 de v5 como si fueran la misma planta**. El solver ensayó 10.213 candidatos durante 600,36 segundos activos y agotó ese límite.

| Comprobación sobre reconstrucción completa | Antes v6 | Después de poses |
|---|---:|---:|
| Pares físicos estrictos | 1.018 | 128 |
| Separaciones insuficientes | 256 | 74 |
| Pares hoja–hoja tolerados | 137 | 151 |
| Objetos auditados | 3.557 | 3.557 |

La reducción es del 87,4 % de pares físicos y del 71,1 % de déficits. **El resultado continúa inválido.** El residuo completo contiene 87 hoja–tallo, 22 cáliz–hoja, diez tallo–tallo, siete cáliz–cáliz y dos cáliz–tallo. Dentro de hoja–tallo, los nombres de los constructores identifican 51 pecíolos, 28 ejes, siete pedicelos y un ápice. Hay un cruce eje–eje que una búsqueda limitada a hojas y pedicelos no puede resolver. El reparto semántico inicial no se calcula como total: el archivo conserva solo 500 de sus 1.018 pares.

Se recalcularon invariantes desde `generated.json` y `adapted.json`: mismo hash protegido `9282458accb8799b770a18bcd8f36667d35be4c31c51b0c1c218a7f022847d6e`, topología, tamaños, formas, fenología e identidades. Se mantienen 125 ejes, 909 nodos/hojas, 375 unidades reproductivas, 45 flores y 330 frutos/cálices. [Comparación verificable](../../outputs/appearance_factorial_20261026/revisions/lower_crown_contacts_20261026/repair_probe_00_comparison.json).

Este probe conserva la auditoría histórica de suelo, solo de cálices, y precede a la corrección de limpieza de ocultos. Las envolventes tras reconstruir pueden contener frutos internos residuales de la construcción previa; no se usan para aprobar integridad física. Los conteos anteriores provienen del árbol y la auditoría estricta excluye esos frutos. El siguiente intento debe reconstruir desde una escena limpia y usar la nueva comprobación de suelo.

## Resultado de la reparación v6

La ramificación vegetativa comienza en nodos inferiores y se separa de la elegibilidad reproductiva. En las cuatro semillas, la altura nominal del primer lateral primario generado pasa de 63,0/43,6/37,0/59,4 cm en v5 a 14,8/38,1/13,1/21,5 cm en v6. Son resultados de una hipótesis de ingeniería, no alturas medidas en campo. La cámara no participa en la generación ni en la reparación.

Se preservaron los intentos 00–07 y se seleccionó por planta la mejor auditoría disponible: suelo, número de cruces, número de déficits y suma de déficits, en ese orden. No se utilizaron imágenes ni resultados de entrenamiento para esa selección. El intento 05 sufrió un `PermissionError` al leer el ledger durante su reemplazo atómico en Windows. Se preservó el fallo, se verificó la ausencia de procesos, se reutilizaron los árboles completos y se retomó el árbol serializado del ajuste de ejes de 02. La lectura reintenta como máximo un segundo; si falla persistentemente, se detiene sin omitir tiempo ni reiniciar presupuesto.

| Planta | Frutos/cálices conservados | Hojas conservadas | Cruces estrictos v6 original → reparada | Déficits finales | Pares hoja–hoja tolerados |
|---|---:|---:|---:|---:|---:|
| 00 | 330 | 909 | 1018 → 0 | 0 | 157 |
| 01 | 274 | 762 | 919 → 0 | 0 | 179 |
| 02 | 408 | 1122 | 1230 → 0 | 3 | 251 |
| 03 | 297 | 747 | 1103 → 0 | 0 | 214 |

Se conservan **1.309 frutos, 3.540 hojas, 178 flores y 487 ejes**. El hash protegido verifica topología, identidades, dimensiones, formas y estados de cada árbol v6 original; solo excluye los ángulos declarados de ejes, hojas y pedicelos y su procedencia de reparación. Las asignaciones de clase también coinciden. Esto no afirma igualdad anatómica entre v5 y v6, que son arquitecturas diferentes.

La reconstrucción independiente desde JSON arroja cero errores de validación y suelo válido en las cuatro plantas. Persisten 2.764/2.308/3.417/2.285 advertencias, principalmente campos de irradiancia/desarrollo no producidos por esta adaptación de poses y advertencias de plausibilidad/proxies. No se presentan como validación fisiológica completa. La admisión física aplicada pasa en 00, 01 y 03; **02 sigue sin admisión por tres márgenes insuficientes**, aunque sus mallas no se cortan.

### Residuo de la planta 02

Los tres pares afectan al entrenudo inicial de `axis_0_0_branch_9_branch_2_branch_3`, que nace en el nodo 8 de su madre, y órganos del nodo 9 o su ápice. No son inserciones compartidas que justifiquen una nueva exención. Sus separaciones evaluadas son:

| Otro órgano | Separación medida | Margen exigido |
|---|---:|---:|
| Pecíolo del nodo 9 | 2,625 mm | 3,000 mm |
| Pedicelo del nodo 9 | 1,069 mm | 3,000 mm |
| Ápice de la rama madre | 1,617 mm | 3,000 mm |

Se mantiene el criterio y el límite acumulado de giro, sin encoger órganos, borrar frutos ni ocultar etiquetas. Una siguiente corrección deberá resolver ese grupo local y reconstruir su entorno completo; mejorar un proxy no basta. Estos márgenes son criterios de ingeniería, no medidas de tolerancia biológica demostradas.

### Evidencia y límites

- [Árboles seleccionados y hashes](../../outputs/appearance_factorial_20261026/revisions/lower_crown_contacts_20261026/repair_review_selected/plants.json).
- [Invariantes y reconstrucción independiente](../../outputs/appearance_factorial_20261026/revisions/lower_crown_contacts_20261026/repair_review_selected_independent_verification.json).
- [Selección por auditoría](../../outputs/appearance_factorial_20261026/revisions/lower_crown_contacts_20261026/repair_review_selected/selection.json).

Las 4.270 intersecciones iniciales auditadas se reducen a cero bajo el criterio aplicado, que **tolera hoja–hoja y no cubre exhaustivamente flores, fruto–cáliz, maleza ni todos los contactos con el entorno**. Las 801 parejas hoja–hoja toleradas no quedan físicamente certificadas. El suelo usa un contrato ampliado independiente que incluye frutos internos. No confundir una superposición en imagen con un cruce de mallas ni el llenado de una caja con oclusión física.

Pruebas de esta continuación: 18 de reparación de ejes, nueve de reparación de órganos, siete del contrato de poses adaptadas y 15 de campaña, incluida recuperación de lectura del ledger; todas pasan. Se conservan además los fixtures Blender de terreno, reparación y limpieza de ocultos de esta intervención. El validador del grafo mantiene sus diez errores de localizadores preexistentes; no se afirma validación global correcta.

## Galería y revisión humana

Se recaptura v5 y se captura v6 con las mismas fuentes de render, contexto, cámaras, luz y materiales dentro de cada par. Las imágenes completas se rotulan **Antes v5 / Después v6** y se acompañan de referencias reales exclusivamente de entrenamiento. La igualdad de matrices de cámara, geometría de luces, perfiles efectivos, contexto y fuentes quedó verificada en los cuatro pares. Se inspeccionaron los ocho RGB y el panel de referencias reales. En 00 y 02 hay más continuidad del follaje hacia la base; 01 muestra dos masas separadas por un hueco central y 03 añade follaje basal. Persiste truncamiento superior con las cámaras originales: no se corrigió mediante zoom ni desplazamiento. No se afirma una mejora uniforme de todas las siluetas.

La comprobación exacta de las ocho máscaras verificó paleta, píxeles por instancia, cajas, correspondencia con identidades y clases, además de hashes RGB/máscara. Las vistas nuevas conservan 287/256/320/236 capachos visibles anotados, separados del conteo de frutos completos de los árboles.

[Galería antes/después y referencias reales](../../outputs/appearance_factorial_20261026/calibration/lower_crown_v6_contact_candidate/review/index.html) · [Comparación verificable](../../outputs/appearance_factorial_20261026/calibration/lower_crown_v6_contact_candidate/review/comparison.json) · [Comprobación de máscaras](../../outputs/appearance_factorial_20261026/revisions/lower_crown_contacts_20261026/gallery_mask_verification.json).

No se modificaron la receta de entrenamiento ni la selección por validación. **El entrenamiento permanece detenido y la revisión humana pendiente**. También falta integrar y comprobar la reparación en las nuevas escenas del banco; estas cuatro plantas no las admiten automáticamente. La campaña anterior permanece cerrada y separada. Esta revisión no demuestra mejora del detector ni madurez interna.
