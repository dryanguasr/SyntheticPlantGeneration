# Evaluación de diversidad al umbral de 500 imágenes

**Recomendación: mantener la pausa y probar primero un piloto exploratorio de
baja dosis. El banco tiene diversidad suficiente para comprobar utilidad;
todavía no hay evidencia que justifique producir otras 500 vistas con la misma
receta antes de esa prueba.** Esto no demuestra que 1.000 sean inútiles ni que
el aumento sintético mejore el detector: no se entrenó ningún modelo.

## Pausa, preservación y alcance

Cuando llegó la instrucción, el último bloque ya había cerrado **503 pares**.
Se detuvieron únicamente controlador y trabajador propios, comprobando PID
y creación nativa. Se conservaron todos los RGB, máscaras, etiquetas, árboles,
checkpoints, parciales, fuentes y presupuesto. Las tres vistas adicionales
no se borraron. El seguimiento horario quedó **PAUSED** y una guarda impide
arrancar el controlador mientras `pause_requested.json` esté activo.

La evaluación usa las **primeras 500** en el orden congelado: 144 heredadas y
356 nuevas, sin selección estética ni por resultados de un modelo. Las tres
adicionales quedan fuera de esta evaluación, preservadas. El lock con sus
hashes está en
`outputs/spatial_dataset_completion_20261030/revisions/pause_diversity_500_20261030/review_500_lock.json`.
Se verificaron las 136 fuentes/entradas/assets, las vistas y sus hashes. No se
reinició ni amplió presupuesto alguno.

La comparación real usa exclusivamente **461 imágenes de entrenamiento** y
sus 4.723 cajas, con hashes comprobados. No se leyeron imágenes ni etiquetas
de validación o prueba para esta revisión. La prueba histórica del proyecto
ya se consultó durante desarrollo; esta revisión no cambia ese antecedente.

## Diversidad observada y reutilización

| Dimensión | Resultado en las primeras 500 |
|---|---:|
| Geometrías de plantas distintas y efectivamente visibles | 20 |
| Escenas y combinaciones de 12 plantas | 21 |
| Identidades sintéticas de capachos visibles | 5.835 de las 5.835 del pool |
| Apariciones anotadas de esos órganos | 482.925 |
| Mediana de apariciones por identidad | 84 |
| Vistas con las tres clases | 499/500 |
| Tutorados horizontal / hilos | 261 / 239 |
| Cubierto histórico / despejado / bruma / cubierto variable | 158 / 115 / 114 / 113 |
| Duplicados exactos de RGB por SHA | 0 |

Las primeras 100 vistas ya mostraban 5.812 identidades: **99,6 % de los
capachos del pool**. Entre las vistas 100 y 500 se añadieron 23 identidades,
16 escenas y nuevos encuadres/condiciones, sin nuevas plantas. Más vistas
pueden aportar información de observación de los mismos órganos, pero no
añaden automáticamente diversidad botánica independiente.

El eje óptico ocupa azimuts de mundo de 76,1–104,6° y las plantas se colocan
con rotación de 0°. Por tanto, la captura explora principalmente un mismo
lado de las hileras. No se midió el rango angular real, así que esto describe
la cobertura sintética y no una equivalencia con las fotos de campo.
Hay tres perfiles foliares configurados, verde/mixto/amarillento, con 84
asignaciones por perfil en las 21 escenas; no son 252 plantas distintas.
Todo el sintético es horizontal 4:3; train contiene 326 imágenes horizontales
y 135 verticales.

Los hashes perceptuales DCT de 63 bits, globales y del centro de la imagen,
no detectaron vecinos a distancia ≤8 bits. La mediana del vecino global más
próximo fue 18 bits. Son descriptores de composición y umbrales heurísticos:
**no prueban independencia, novedad semántica ni utilidad**. Tampoco permiten
declarar agotada la diversidad visual a 500. La saturación clara observada
corresponde al inventario de plantas/órganos, no a todas sus proyecciones.

## La versión final es un subconjunto del banco

De las primeras 500, **152** usan horizonte `aligned_horizon_matte/3` y
distancia continua. Cubren las 20 plantas en siete escenas, los tres cielos
y ambos tutorados. El sorteo realizado fue 108 cerca–medio y 44 medio–lejos
(71,1/28,9 %), compatible descriptivamente con la política 70/30.

Se detectó una excepción técnica: `scene_026_view_001` es casi negra
(máximos RGB ≤1/255) y su máscara corresponde a un único capacho que ocupa
todo el fotograma. Es compatible con una obstrucción completa o cámara
dentro de una superficie; esa causa geométrica no se auditó de forma
independiente. Se conserva como evidencia y se excluye de las **listas
propuestas para piloto**, sin alterar los datos originales. Quedan **151
candidatas de la versión corregida** dentro del grupo evaluado. No se afirma
que todas hayan recibido revisión visual humana exhaustiva.

## Comparación con train real y política de pequeños

Los lados de caja se normalizan al lado mayor de imagen de 960 píxeles.
Los números son exposición de anotaciones, no organismos independientes.

| Medida | Corregidas con cribado técnico, 151 | Reales train, 461 |
|---|---:|---:|
| Mediana de cajas por imagen, todas | 755 | 7 |
| Mediana de lado mínimo, todas las cajas | 7 px | 56 px |
| Mediana de cajas por imagen, sólo lado mínimo ≥10 px | 286 | 7 |
| Mediana de lado mínimo, sólo cajas ≥10 px | 14 px | 56 px |
| Mediana de la mayor caja de cada imagen, lado mínimo | 60 px | 152 px |
| Mediana de brillo global codificado, 0–1 | 0,301 | 0,527 |

El contraste bruto está influido por anotar todos los capachos diminutos de
fondo en sintético. Se hicieron sensibilidades comunes a 6/8/10/16/24/32 px,
**sin quitar ninguna etiqueta ni fijar un filtro de entrenamiento**. El
umbral de 10 px es una comparación descriptiva, no una nueva norma. Incluso
con ese umbral y usando la mayor caja por imagen como proxy de primer plano,
persisten diferencias de densidad y escala. El brillo es global, afectado
por encuadre/fondo; no es reflectancia ni demuestra por sí solo luz incorrecta.

Las clases sintéticas están próximas a 33/35/33 % por exposición; en train
son aproximadamente 76/16/8 % para Pintona/Madura/Sobremadura. Ese balance
puede ser útil para clases minoritarias, pero su efecto debe comprobarse por
clase. No se infiere madurez interna a partir de apariencia del capacho ni
se reetiquetan fotografías reales.

![Diversidad y brechas descriptivas](../../outputs/spatial_dataset_completion_20261030/revisions/pause_diversity_500_20261030/assessment/overview.png)

![Sensibilidad a pequeños y reutilización](../../outputs/spatial_dataset_completion_20261030/revisions/pause_diversity_500_20261030/assessment/policy_and_reuse.png)

## Decisión propuesta

1. **No reanudar automáticamente hacia 1.000.** La cantidad actual permite
   una prueba de utilidad y las brechas principales no se corrigen sólo
   añadiendo vistas de la misma receta.
2. **Empezar con 46 sintéticas corregidas** y control real+clásica, con
   pasos/receta emparejados y tres semillas. Se preparó también una lista
   anidada de 115 para una respuesta a dosis, sin ejecutar entrenamiento.
   Ambas cubren siete escenas y las 20 plantas; sus intervalos de distancia
   quedan aproximadamente 70/30 y conservan todas las anotaciones visibles.
3. Congelar antes del piloto la política efectiva de pequeños/ignorados del
   consumidor. Con 46 imágenes candidatas hay 35.330 anotaciones sintéticas
   frente a 4.723 reales: un 9,1 % de imágenes totales representa un 88,2 %
   de anotaciones nominales. A lado mínimo ≥10 px esa fracción es 70,9 %.
   **No equivale al peso del gradiente**: depende de la normalización de loss.
   Debe reportarse exposición por imágenes e instancias y compararse con un
   control de repetición real emparejado.
4. Seleccionar por validación real y revisar AP macro/por clase, en especial
   Madura; una ganancia media con deterioro de una clase es un intercambio.
   Esta revisión no autoriza entrenar ni consultar de nuevo la prueba.
5. Si hace falta ampliar después, priorizar información adicional: escalas
   de capachos principales más próximas al train, otros puntos de vista,
   contexto/materiales y, si se autoriza, nuevas plantas. Añadir rechazo de
   cámaras completamente obstruidas sin podar órganos ni ocultar etiquetas.
   Son recomendaciones e hipótesis para una iteración; no cambios ejecutados.

## Entregables y límites

La carpeta `assessment` de la revisión conserva `results.json` (primeros500
sin cribado), `features.json`, `review_addendum.json` (sensibilidades y listas
46/115 revisadas), `structure.json`, gráficos, manifiestos y `reviewed.html`
con ejemplos y la excepción casi negra. Las listas son propuestas de
curación, no un bloqueo de entrenamiento ya aprobado. No usan rendimiento,
validación o prueba para seleccionarse.

Las 503 vistas, la imagen señalada y las tres adicionales permanecen en
su sitio. No se elimina ninguna fuente ni se promueve modelo alguno.
La campaña y el seguimiento están pausados hasta decisión del usuario.
La validación del grafo distingue sus diez errores preexistentes de
localizadores, sin regresiones añadidas por esta intervención.
