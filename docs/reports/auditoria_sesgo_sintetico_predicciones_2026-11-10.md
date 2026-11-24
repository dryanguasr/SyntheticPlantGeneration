# Auditoría reproducible del sesgo sintético con predicciones existentes

Fecha: 10 de noviembre de 2026. Alcance: piloto revisado de 115 imágenes,
sus seis modelos y antecedentes ya terminados. **No se ejecutaron inferencia,
entrenamiento ni generación.** La pausa de generación permanece activa.

**El resultado publicado se reproduce, pero no identifica una causa del cambio
de desempeño.** La mezcla mejora el AP50-95 macro de desarrollo en 2,07 puntos
porcentuales (pp) y reduce Sobremadura en 0,76 pp. La evidencia permite estudiar
sensibilidad a clases, grupos, selección y límites del evaluador. No permite
retirar retrospectivamente una exposición de entrenamiento ni aislar el efecto
de materiales, oscuridad, escala o dosis. Ningún resultado de esta auditoría
constituye validación agronómica o autorización para reanudar trabajos pausados.

Dos hallazgos adicionales cambian la interpretación de la exposición:

- Los checkpoints evaluados proceden de 1.500–2.500 actualizaciones; sus
  exposiciones no son las de las corridas completas de 4.000 pasos. En los
  prefijos seleccionados, la mezcla recibió 6.956 apariciones reales de
  Sobremadura frente a 10.232 del control: **32,02 % menos**, además de 485.439
  sintéticas. La proporción sintética dentro de esa clase sigue siendo 98,59 %.
- Tras el filtro geométrico nativo, **84,12 %** de las etiquetas sintéticas
  Sobremadura tienen lado menor <16 px a escala 960. Ninguna de las 58 etiquetas
  Sobremadura de prueba tiene lado menor <32 px. El desfase de soporte persiste
  después del filtro; no basta con citar su umbral de 2 px.

## Evidencia y reproducibilidad

Se leyeron `AGENTS.md`, el grafo, el plan científico y su registro vivo, el
[diagnóstico de Sobremadura](diagnostico_sobremadura_piloto_115_2026-10-31.md),
el [cierre del piloto115](piloto_115_corregidas_2026-10-31.md), los protocolos de
[aumentación](../guides/piloto_aumentacion_geometrica.md) y
[apariencia](../guides/piloto_apariencia_factorial.md), las auditorías de la
unión real y los archivos locales que sustentan sus resultados.

Checkout inicial: rama existente `codex/uchuva-spatial-generator-20261029`,
HEAD `451ddd2c9070e67759b8e0b65c5ef3254d78814f`, con 224 archivos modificados o
nuevos preexistentes. Se conservaron; el registro vivo recibe únicamente una
fila de esta intervención. No se cambió de rama ni se hizo commit, push o
publicación. Los originales experimentales siguen en sus carpetas.

La ejecución nueva es un recálculo en CPU desde archivos existentes:

| Comprobación | Resultado observado |
|---|---|
| Lock de entrenamiento | 1.999 entradas coinciden por SHA-256 |
| Datos reales de prueba | Las 94 filas, imágenes, clases, cajas y grupos de la caché coinciden con el manifiesto y los labels congelados |
| Emparejamiento de predicciones | Recalculados los flags TP en los diez IoU, con clase y colapsados, en las seis cachés; coincidencia exacta |
| AP y punto operativo | AP reproducido con tolerancia absoluta 1e-12; TP/FP/FN coinciden exactamente |
| Selección y pesos | Hashes de mejores/últimos pesos, lock de evaluación, umbral y procedencia concordantes |
| Exposición | Secuencias, posiciones reales compartidas, LR y decisiones de aumentación emparejadas; conteos por dominio reconstruidos iguales a los logs |
| Incertidumbre original | Reproducidos los 200 sorteos comunes y los intervalos macro y Sobremadura |
| Integridad al terminar | 2.245 entradas de evidencia verificadas sin cambios; procedencia incluye además el hash del script, 2.246 rutas en total |
| Pruebas ligeras | 12 aprobadas: siete nuevas y cinco regresiones de diagnóstico/piloto |
| Grafo | Conserva los diez localizadores rotos preexistentes; no se presenta como aprobado |

Entorno comprobado: Python 3.12.14, NumPy 2.4.4, Ultralytics 8.4.114,
Torch 2.12.1+cu130 y OpenCV 5.0.0.93. Se registraron también hashes del evaluador
nativo y del filtro de cajas. No se instalaron dependencias. La auditoría final
tardó 42,52 s; eso mide el recálculo local, no el coste histórico de entrenamiento.

Artefactos principales, privados y excluidos de Git:

- `outputs/audits/cached_synthetic_bias_20261110/verification_v3/audit.json`:
  integridad, métricas, composición y exposición por corrida/checkpoint.
- `verification_v3/resampling.json`: soporte por grupo, AP por grupo cuando
  existe denominador, exclusiones de un grupo y los sorteos originales.
- `verification_v3/candidate_cap_sensitivity.json`: sensibilidad a 100/200/300
  candidatos y filas que alcanzaron el límite original.
- `verification_v3/provenance.json`: hashes de entradas, dependencias locales,
  script y resultados. `verification_v1/` y `verification_v2/` conservan las
  ejecuciones anteriores de la auditoría. Cada JSON final declara versión,
  preset de evaluación y semillas.
- `historical_context.json`: cifras recuperadas de dos campañas anteriores,
  claramente separadas del recálculo del piloto115.
- `preflight.json`, `plan_before.md`, `tests.log` y `closure.json`: conservación
  del trabajo previo y comprobaciones de cierre.

## Fugas, selección y población evaluada

**No se encontró fuga exacta entre los splits actuales.** En los 643 registros
reales depurados hay 461/88/94 imágenes de entrenamiento/validación/prueba,
cero hashes de imagen compartidos entre splits, cero grupos declarados cruzados
y cero prefijos de secuencia cruzados. Las 115 sintéticas están solamente en
entrenamiento. Esto no contradice los ocho pares de duplicados entre splits de
la exportación original de 673 imágenes: esa es otra revisión, preservada.

**La reutilización adaptativa de la prueba sí está documentada.** Los resultados
de estas 94 fotos se han inspeccionado en varias campañas y ahora orientan el
diagnóstico de Sobremadura. `selection_used_test=false` documenta que esta
selección de checkpoints usó validación; no certifica independencia de toda la
historia de diseño. Un nuevo lock o un nuevo bootstrap no convierte estas
imágenes en una captura externa intacta.

La agrupación combina prefijo de archivo, duplicados exactos y enlaces dHash
conservadores. La identidad de sesión/planta de campo no está verificada.
Secuencias con prefijos distintos podrían compartir adquisición; los hashes
no resuelven ese riesgo. Los originales también incluían fotografías similares
a material local de septiembre, según la auditoría histórica. No se volvió a
certificar identidad visual ni se reescribieron grupos en esta tarea.

El script de partición excluyó 22 imágenes con problemas geométricos y separó
ocho duplicados; las fotos sin secuencia identificable se anclaron a train.
Buscó un reparto por grupos equilibrando cantidades de imágenes y clases.
Esa estratificación no es evidencia de entrenamiento sobre test, pero restringe
la población evaluada y no proporciona una muestra aleatoria de campo. No hay
una evaluación representativa de negativos de campo sin capachos ni una medida
de exhaustividad de las anotaciones. Un FP sobre una región sin label sigue
siendo **fondo o instancia no anotada**, sin adjudicación biológica automática.

## Qué contraste está identificado

El piloto compara dos recetas completas: reemplazar posiciones de repetición
real por imágenes sintéticas, con la misma inicialización, calendario máximo,
batch, transformaciones y regla de selección por validación. Es un contraste
útil de estrategia bajo un presupuesto máximo común. No mantiene iguales las
exposiciones reales o las cantidades de objetos por lote.

Las épocas seleccionadas se infieren del máximo único del CSV de validación,
contrastado con `best_validation_ap` del cierre. No se cargaron modelos ni se
atribuyó metadata de checkpoint que no se hubiera inspeccionado. Los hashes de
`best.pt` sí se verificaron contra el lock de las predicciones.

| Semilla | Pasos del mejor real / mixto | Imágenes reales hasta esos checkpoints, control / mezcla | Sobremadura real, control / mezcla | Sobremadura sintética en mezcla |
|---|---:|---:|---:|---:|
| 20261022 | 2.000 / 1.500 | 4.000 / 2.402 | 3.173 / 1.892 | 131.720 |
| 20261023 | 2.000 / 2.000 | 4.000 / 3.199 | 3.145 / 2.529 | 177.251 |
| 20261024 | 2.500 / 2.000 | 5.000 / 3.201 | 3.914 / 2.535 | 176.468 |
| Suma descriptiva | 6.500 / 5.500 | 13.000 / 8.802 | 10.232 / 6.956 | 485.439 |

Estas sumas son apariciones a través de tres inicializaciones; no tamaños de
muestra independientes. En las corridas completas, las cifras originales de
18.875/15.132/1.056.777 apariciones Sobremadura se reproducen. Deben conservarse
como contabilidad de entrenamiento, acompañadas por los prefijos anteriores
cuando se interpreten los modelos evaluados.

No es un error seleccionar épocas distintas con una regla común. Sí es un
confusor para atribuir la diferencia exclusivamente al contenido sintético a
igual exposición efectiva. Hay además interacción posible con la regularización
y el sobreajuste: las curvas reales y mixtas no son monótonas. El promedio del
contraste macro en validación es +1,04 pp comparando los mejores checkpoints,
pero +0,24 pp a 2.000 pasos y +0,10 pp a 4.000. A 1.000 y 1.500 es negativo en
las tres semillas. Es sensibilidad retrospectiva de **validación**; no permite
inferir el AP de prueba de pesos sin predicciones guardadas ni escoger ahora
otro número de pasos.

## Composición de exposición y soporte

| Clase | Apariciones reales en control, corrida completa | Reales en mezcla | Sintéticas en mezcla | Fracción sintética de esa clase |
|---|---:|---:|---:|---:|
| Pintona | 188.546 | 150.119 | 1.040.560 | 87,39 % |
| Madura | 39.941 | 31.621 | 1.137.380 | 97,30 % |
| Sobremadura | 18.875 | 15.132 | 1.056.777 | 98,59 % |

En las mezclas completas, 19,93 % de las apariciones de imagen son sintéticas,
pero 94,26 % de las apariciones de instancia lo son. La composición por clase
cambia mucho: Sobremadura es minoritaria en lo real y recibe aproximadamente
70 apariciones sintéticas por cada real en la mezcla. Esto no equivale a 70
veces su peso de gradiente: intervienen asignación de objetivos, normalización
de pérdidas, resolución, dificultad y correlación entre instancias. No se
recuperaron gradientes y no se estimó una contribución causal a la pérdida.

| Sobremadura en train | Real | Sintética cruda | Sintética tras filtro nativo |
|---|---:|---:|---:|
| Etiquetas, antes de repetir imágenes | 363 | 30.673 | 25.389 |
| Mediana del lado menor a 960 | 100,51 px | 7,00 px | 8,00 px |
| Etiquetas <16 px | 2 (0,55 %) | 26.641 (86,85 %) | 21.357 (84,12 %) |
| Etiquetas ≥64 px | 258 (71,07 %) | 105 (0,34 %) | 105 (0,41 %) |

Las 58 etiquetas Sobremadura de prueba se dividen en 30 de 32–64 px y 28 de
≥64 px. No hay soporte de prueba para evaluar beneficio en Sobremadura <32 px.
Eliminar esas etiquetas pequeñas del análisis o ponderar métricas no cambia
lo que aprendieron los pesos. Tampoco debe convertir objetos visibles en fondo
durante un eventual entrenamiento. La política de anotación de pequeños/fondo
es una variable distinta de la escala de captura y requiere revisión explícita.

Las 115 imágenes corresponden a siete escenas y 20 plantas del mismo pool.
Contienen 93.603 apariciones anotadas de **5.815 identidades sintéticas**;
5.760 identidades aparecen en varias vistas y la mediana es 15 vistas por
identidad. No se detectaron cambios de clase para una misma identidad en este
subconjunto. Esto verifica coherencia interna, no la equivalencia visual de
las clases con las anotaciones humanas. Repartir aleatoriamente estas vistas
entre futuros splits sintéticos produciría dependencia por planta/órgano.

La apariencia, iluminación, materiales, fondo, carga por imagen, vistas y
clases están combinados en un único banco corregido. El perfil de Sobremadura
usa `calyx_straw_v2` y `wear_fraction=0`; son parámetros heurísticos. El
diagnóstico visual previo no aporta un brazo con idéntica geometría y una sola
intervención sobre oscuridad o deterioro. No se concluye que «oscurecer» resuelva
la caída, ni que un capacho pardo demuestre madurez interna.

## Ablaciones de evaluación ejecutadas

Todas son sensibilidades posteriores a observar los resultados. Preservan los
pesos y el conjunto original; no constituyen ablaciones causales del entrenamiento.

| Intervención analítica | Resultado | Qué permite afirmar |
|---|---|---|
| Colapsar clases con las mismas cajas guardadas | Delta AP50-95 +3,06 pp de media; +8,28/+1,22/−0,31 por semilla | Hay una señal media de localización, con heterogeneidad. No es un detector nuevo entrenado monoclase ni una nueva ejecución de NMS |
| Evaluar cada clase | Pintona +3,19 pp; Madura +3,76 pp; Sobremadura −0,76 pp | El beneficio macro no es uniforme; no demuestra madurez agronómica |
| Retirar cada grupo, de forma emparejada | Delta macro medio entre +1,32 y +2,64 pp; Sobremadura entre −2,66 y −0,002 pp | La señal macro media persiste en estas exclusiones; la magnitud de Sobremadura depende mucho de grupos concretos |
| Reutilizar los 200 sorteos originales | Macro [+0,40,+5,03] pp; Sobremadura [−3,69,+4,74] pp | Intervalos descriptivos condicionados a clases presentes y semillas fijas; no cobertura confirmatoria ni variación de nuevas inicializaciones |
| Truncar la caché a 100/200/300 candidatos e igualar la regla entre brazos | Delta macro +1,92/+2,03/+2,07 pp; Sobremadura −1,21/−0,82/−0,76 pp | El signo observado no desaparece al reducir este límite. No identifica el resultado por encima de 300 |
| Separar localización geométrica de clase al umbral congelado | Sobremadura: 94→114 localizaciones; 33→31 clases correctas dentro de esa asignación geométrica | Recuperar geometría no asegura clasificar correctamente; el denominador es 174 apariciones de las mismas 58 etiquetas |

El último contraste da 35,11 % frente a 27,19 % de clase correcta entre los
matches geométricos de cada brazo. Los objetos localizados no son exactamente
los mismos; es una descripción con selección diferente por brazo, no un efecto
causal condicionado en una población común. Los TP **con clase** son 41→47 y
no deben sustituirse por la diagonal geométrica 33→31. Ambos cálculos se
conservan con sus definiciones.

El AP colapsado reúne 806 etiquetas Pintona de las 955 totales; su mejora no
garantiza por sí sola una mejora de localización en cada clase minoritaria.

El emparejamiento operativo voraz y el nativo de AP tampoco son idénticos en
casos densos. Se observó un TP de diferencia en el mixto de la semilla 23
(611 operativos frente a 610 flags nativos IoU0,5 por encima del umbral), sobre
todas las clases. Una fixture reproduce esta posibilidad. Es una diferencia
de asignación declarada, no una discrepancia de las cajas o del AP reproducido.

El límite de 300 candidatos se alcanzó en 8/8/2 imágenes de los controles y
15/14/9 de las mezclas, respectivamente. Son ocurrencias por corrida, no
imágenes independientes al sumarlas. La confianza del último candidato en
esas filas fue 0,00100–0,00531, siempre por debajo del umbral operativo 0,076076.
No se observó saturación a ese punto operativo. Para AP, la cola queda censurada
por el límite y el suelo 0,001; la caché no permite recuperar candidatos ausentes.
No se eligió un nuevo límite o umbral según estos resultados.

## Grupos e incertidumbre

| Grupo | Imágenes | Pintona | Madura | Sobremadura | Delta macro del grupo, pp |
|---|---:|---:|---:|---:|---:|
| component_58 | 48 | 257 | 28 | 15 | +4,29 |
| component_8 | 25 | 372 | 5 | 23 | −1,96 |
| component_66 | 15 | 138 | 46 | 18 | +0,57 |
| component_149 | 3 | 0 | 12 | 1 | No definido: falta Pintona |
| component_177 | 2 | 26 | 0 | 0 | No definido: faltan dos clases |
| component_621 | 1 | 13 | 0 | 1 | No definido: falta Madura |

Los dos grupos mayores concentran 73/94 imágenes. La ausencia de una clase se
guarda como `null`, no como AP cero ni como macro con otro denominador.
AP no es aditivo: no se promedian los AP de esta tabla para reconstruir el
global. Los deltas por grupo usan sus propias listas de confianza y conservan
predicciones de otras clases como errores cuando corresponde.

Al retirar `component_58`, la media macro permanece positiva, pero dos de las
tres semillas ya no conservan el patrón original de mejora clara: una queda
en +0,02 pp y otra en −1,13 pp. Al retirar `component_8`, el descenso medio
Sobremadura casi desaparece. Las exclusiones muestran dependencia del soporte;
no justifican eliminar grupos desfavorables ni cambiar la población objetivo.

El bootstrap original rechazó un sorteo sin las tres clases. Se reprodujo esa
decisión, sin ocultar su condicionamiento. Sus 200 sorteos son suficientes para
reproducir el informe, no para justificar decimales finos en las colas. Más
sorteos sobre los mismos seis grupos no añadirían sesiones ni corregirían la
selección adaptativa. Repetir tres seeds no convierte 58 objetos en 174 objetos
independientes. No se hicieron pruebas de significación ni correcciones
retrospectivas de multiplicidad para declarar éxito.

## Qué aportan los antecedentes existentes

Se recuperaron los JSON de la extensión anterior y del factorial, con hashes;
no se volvieron a ejecutar sus modelos ni se reprodujeron todas sus predicciones:

- La extensión cerrada el 26/10 obtuvo +2,34 pp frente a real con clásica,
  pero solo +0,88 pp frente a repetición real, con dos seeds negativas en este
  último contraste. Sustenta la necesidad del control de repetición.
- El factorial de apariencia terminó con controles reales: clásica frente a
  no clásica, −0,03 pp medio. No tuvo vistas sintéticas admitidas y no contiene
  los contrastes B/L/T/LT que su protocolo había previsto.
- El piloto115 actual sí compara contra repetición emparejada, pero utiliza
  otro banco y entrenador/registro de aumentación. Comparar su +2,07 pp con
  el +0,88 pp anterior no aísla la mejora de materiales o morfología. También
  cambian plantas, escala, densidad y distribución de etiquetas. No se combinan
  ambas campañas como seis semillas de un único tratamiento.

## Estrategia de ablación y próximos pasos

La estrategia ejecutable con lo disponible es una **ablación del análisis y
sus supuestos**, con preguntas y límites explícitos:

| Pregunta | Evidencia disponible y acción | Límite para decidir |
|---|---|---|
| ¿Es un fallo de cálculo o procedencia? | Hashes, verdad desde labels, flags nativos y AP reproducidos | Resuelto para este entorno y caché; no demuestra reproducibilidad bit a bit de entrenar otra vez |
| ¿La mejora es principalmente localización o clase? | AP colapsado, AP por clase y asignaciones operativas separados | No atribuir a un mecanismo de aprendizaje; considerar diferencias de población localizada |
| ¿Depende de unas pocas adquisiciones? | Soporte, exclusiones de un grupo y sorteos emparejados ya entregados | No seleccionar grupos por rendimiento; sigue faltando identidad de sesión verificada |
| ¿Se debe al presupuesto o la selección de checkpoint? | Prefijos de exposición y curvas de val por paso ya entregados | No hay predicciones guardadas de todos los checkpoints; no estimar su prueba ni relanzar inferencia |
| ¿El límite de salida explica el signo? | Truncación común 100/200 y referencia 300 con matches recalculados | El signo persiste; no se conoce la cola excluida ni se selecciona otro límite |
| ¿Hay sesgo de dosis/escala por clase? | Conteos filtrados por clase y tamaños, tanto globales como en prefijos | Muestra un desajuste grande; no estima qué pasaría reentrenando con dosis o escalas distintas |
| ¿Es oscuridad, textura, desgaste o fondo? | Perfil congelado, casos y material visual existente | Sin pares de intervención y predicciones correspondientes, no identificable con estos archivos |
| ¿Las fronteras de clase son reproducibles? | Casos113/183/548 y originales ya disponibles para revisión | Pendiente de adjudicación humana cegada; no cambiar labels a partir del detector |

Orden recomendado de continuidad, manteniendo la pausa:

1. Revisar este informe y los casos existentes para acordar la semántica visual
   y la política de pequeños, truncamiento, negativos y anotaciones incompletas.
   La muestra de errores deliberadamente seleccionada debe complementarse con
   una muestra de desarrollo definida sin usar aciertos. No se enviaron mensajes
   ni se creó una aprobación humana ficticia.
2. Conservar el diagnóstico de exposición con dos cortes, corrida completa y
   checkpoint seleccionado. Fijar antes de una campaña futura cuál es el
   estimando: sustitución bajo cómputo máximo común o beneficio con igual
   exposición real. No son equivalentes. Con batch y pasos fijos, reemplazar
   imágenes reales por sintéticas necesariamente cambia la exposición real.
3. Mantener como resultado de desarrollo la ganancia macro con retroceso
   Sobremadura. No seleccionar ahora otra dosis, otra clase, otro umbral,
   otra poda o un modelo de producción usando estas mismas 94 fotos.
4. Si se aprueba posteriormente una intervención, separar dosis de apariencia
   y de escala/política de anotación. Exigir un contraste por componente sobre
   entradas comparables, pesos y seeds emparejados, selección solo en val y
   denominadores de exposición por clase. Es un requisito de identificación;
   aquí no se creó ni lanzó esa campaña.
5. Para una afirmación externa sigue haciendo falta una captura independiente
   separada antes de ajustar el siguiente generador o sus hiperparámetros,
   con grupos de adquisición e interpretación humana de etiquetas verificadas.
   Los análisis entregados no sustituyen esa evidencia.

## Repetir únicamente la auditoría

El script nuevo no importa ni construye un modelo YOLO y no contiene llamadas
a entrenamiento, render o inferencia. Exige una carpeta de salida nueva, fuera
del piloto congelado, y falla si encuentra hashes, verdad, métricas o versiones
incompatibles. Conserva las métricas históricas y los outputs anteriores.

```powershell
.venv-training/Scripts/python.exe scripts/audit_cached_synthetic_bias.py --root outputs/reviewed_augmentation_115_20261031 --out outputs/audits/cached_synthetic_bias_20261110/reproduction_01
.venv-training/Scripts/python.exe -m unittest discover -s tests -p test_cached_synthetic_bias.py -v
.venv-training/Scripts/python.exe scripts/validate_repository_context_graph.py
```

`reproduction_01` debe no existir. El último comando actualmente termina con
los diez localizadores preexistentes ausentes. Es un límite de mantenimiento
del grafo; no bloqueó el recálculo de este piloto. La inspección CIM de procesos
no estuvo disponible; una enumeración alternativa de procesos no observó
Python/Blender en ese instante. No se detuvo, relanzó ni modificó proceso ajeno,
y se verificó el archivo de pausa sin cambiarlo.

No quedan bloqueos para la entrega retrospectiva. Permanecen pendientes la
aprobación visual para cualquier nueva generación/entrenamiento, la adjudicación
semántica y la evidencia externa necesaria para atribuciones causales o de
generalización.
