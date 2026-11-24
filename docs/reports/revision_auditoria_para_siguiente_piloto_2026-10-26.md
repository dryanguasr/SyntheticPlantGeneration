# Revisión de auditoría para el siguiente piloto

## Fuente y alcance

Se recuperó el informe de `docs/auditoria-generacion-sintetica-20261025`, commit
[`939f94f7c749a6e4fbdea1abe14c1700f1f17a9d`](https://github.com/dryanguasr/SyntheticPlantGeneration/commit/939f94f7c749a6e4fbdea1abe14c1700f1f17a9d),
mediante la sesión GitHub renovada el 26 de octubre. El identificador `e3a4d29`
proporcionado inicialmente no se resuelve en ese remoto; se conserva esta
diferencia de procedencia, sin asumir que son el mismo commit.

El [informe independiente](auditoria_generacion_sintetica_2026-10-25.md) examinó
`74b43d2` de main. Este checkout está en `db4daaa` y contiene cambios locales;
por eso sus tasas de 300/700 plantas no se trasladan automáticamente al estado
actual. No se hizo merge ni checkout de la rama remota ni se publicaron cambios.

La campaña de aumentación ya está cerrada con 24 screenings y 39 evaluaciones.
Sus fuentes, datasets, pesos, informes y resultados se conservan. Las siguientes
correcciones pertenecen a una nueva versión del generador, no a una reinterpretación
retrospectiva de los resultados cerrados.

## Contraste local y prioridades

| Prioridad / hallazgo | Evidencia en este checkout | Aplicación propuesta y aceptación |
|---|---|---|
| P0 — M1: radio del orden 3 | `grammar.py` todavía usa el rango del orden 1 como fallback; `parameters.py` define radios para 0–2. Inspección estática, sin repetir las 300 plantas. | Exigir cobertura de todos los órdenes habilitados y una regla explícita de continuidad padre/hijo. Tests de rangos, uniones y órdenes profundos; los valores botánicos seguirán etiquetados como estimaciones hasta medición. |
| P0 — M2: separar carga de la planta y conteo en imagen | Reproducción nueva con semillas 0–4: máximo configurado 4, conteos finales **10, 5, 6, 10, 8**. La normalización precede a las cohortes. Ese máximo proviene de una banda de objetos por imagen, no de evidencia botánica. | Desacoplar `object_count_band` de la carga reproductiva de la planta. Guiar el encuadre y la selección de vistas con la banda de imagen; permitir cargas por planta superiores a diez sin imponer otro tope arbitrario. Registrar los conteos finales después de cohortes y distinguir flores, frutos, órganos visibles y anotaciones. No resolver M2 podando plantas a cuatro frutos. |
| P0 — M3: validación por parámetros y etapa | El validador sigue cargando `get_initial_parameters()` y límites fijos de curl/twist. | Recibir snapshot/hash de parámetros efectivos y etapa. Separar integridad, contratos, plausibilidad y geometría final; no silenciar alarmas aumentando umbrales. Tests con overrides y estados pre/post crecimiento. |
| P0 — M4/M8: procedencia | La cohorte incorpora `first_bifurcation_node`; la ficha ofrece `measured_local` mientras el esquema canónico declara `real_dataset_measured`. Las tasas originales no se reprodujeron aquí. | Normalizar toda incorporación/override con método, unidad, fuente y evidencia. Hacer coincidir ficha y esquema, con migración explícita si procede. No convertir una heurística en medición ni en referencia verificada. |
| P1 — M5: aislamiento de ablaciones | Auditoría independiente: cambiar perfil puede cambiar estructura. | Para iluminación/materiales, congelar el mismo árbol morfológico y variar solo el intérprete. El aislamiento completo de RNG requiere otro contrato y regresiones; no exigir identidad entre edades si se pretende cambiar desarrollo. |
| P1 — M6/M7 y proxies | La auditoría distingue ratios nominales, alertas de ancho y discrepancias de sag de colisiones de malla. | Medir envolventes y AABB tras adaptación; contrastar proxies con mallas bajo las mismas transformaciones. No declarar colisión física a partir de ratios o suma de longitudes. |

La reproducción local solo generó cinco árboles Python: no ejecutó Blender,
Gazebo, nuevos renders ni entrenamiento. Parámetros, semillas, conteos y hashes
de las cuatro fuentes usadas están en
`outputs/audit_review_20261026/reproduction_current.json`. No se aplicaron todavía
los parches del generador; estas observaciones no se presentan como fallos resueltos.

## Corrección de interpretación: carga por planta y objetos por imagen

El usuario señaló el 26 de octubre que un arbusto puede tener más de una decena
de frutos. La recomendación anterior sobre un «tope después de cohortes» podía
interpretarse como una obligación de reducir esa carga a cuatro; se corrige aquí.
La inspección distingue dos configuraciones heredadas:

- `parameters.py`, `target_reproductive_units_range`: mínimo 4 y máximo 8 por
  planta, etiquetados `manual_initial_guess`. Ni el mínimo ni el máximo son
  límites botánicos validados.
- `blender_dataset.py`, `_morphology_params_for_target`: la banda de **objetos
  por imagen** `one_to_five` sobrescribe el rango de la planta a 2–4; otras bandas
  usan 10–13 y 16–20. La aceptación posterior cuenta `len(detections)`. Así se
  acoplan explícitamente dos magnitudes que deben distinguirse.

Una vista con pocas uchuvas anotadas puede corresponder a una parte de un arbusto
con más de diez frutos. El siguiente diseño debe modelar la carga de la planta
según su desarrollo y arquitectura, con perfiles explícitos y calibrables; la
cámara, la visibilidad y el encuadre determinan cuántos órganos aparecen en cada
imagen. La observación del usuario justifica admitir cargas superiores a diez,
pero no establece un nuevo máximo ni una distribución universal medida.

Se registrarán por separado unidades reproductivas totales, flores, unidades con
fruto, órganos visibles y anotaciones aceptadas, con el estado de la planta tras
las cohortes y demás transformaciones. Las pruebas deberán verificar que cambiar
solo la banda de conteo de la vista no elimina ni crea órganos en un árbol ya
generado, y que una planta con más de diez frutos no se rechaza solo por ese
conteo. Los órganos conservarán su asociación nodal y las demás validaciones.

El incumplimiento del parámetro anterior sigue siendo una inconsistencia del
software y de su reporte, pero **superar cuatro frutos no demuestra una planta
biológicamente incorrecta**. Se conserva sin editar el informe independiente y
la reproducción original; esta corrección cambia nuestra interpretación y el
diseño propuesto, no las fuentes ni los resultados del piloto cerrado.

## Integración con los resultados del piloto cerrado

La mezcla 461 reales + 115 sintéticas con clásica mejora +2,34 puntos de AP frente
al control real de igual receta en tres semillas, pero frente a repetición obtiene
−0,36/−2,56/+5,55: el aporte específico del contenido sintético no es consistente.
Madura retrocede −0,81 puntos frente al control clásico. Los contratos morfológicos
podrían contribuir a la brecha, pero este piloto no aisló esa causalidad.

El orden de trabajo para la próxima campaña será:

1. Corregir y probar los contratos P0 en una versión nueva, preservando el generador
   usado por la campaña anterior y sus hashes.
2. Preparar una calibración pequeña con árboles fijos: correspondencia visual de
   Madura/Sobremadura, luz sobre planta frente a fondo, texturas y tamaño por clase.
   La revisión de etiquetas y las medidas de campo no se sustituyen con metadatos
   sintéticos. No ajustar colores usando el test ya consultado.
3. Separar mediante ablaciones follaje de uchuva, maleza/distractores y diversidad
   entre plantas. Mantener morfología nodal, órganos unidos y escalas coherentes.
4. Congelar el nuevo banco y comparar real, clásica, mezcla y repetición con
   exposición registrada por imágenes e instancias, semillas emparejadas y nuevas
   sesiones independientes cuando estén disponibles.

Puedo implementar contratos, pruebas, trazabilidad, parámetros del render y
herramientas de comparación. Las medidas anatómicas, adjudicación humana de clases
y certificación de interacción física requieren evidencia adicional. No se asignan
valores físicos precisos por conveniencia.

La cosecha rígida y Springy quedan en su línea secundaria de Gazebo: no son
requisitos para probar transferencia de imágenes. No convertir órganos visuales
estáticos en objetos físicos cambiando solo una bandera, ni suponer que flexión
resuelve colisionadores ausentes. Esas implementaciones requieren frames, masas,
colisiones y validación propios, según el alcance delimitado por la auditoría.

## Estado

Credenciales renovadas y permiso `push=true` verificado; simulación de push correcta,
sin publicación. Auditoría localizada, copiada sin alterar su contenido y contrastada
parcialmente con evidencia local. Se implementaron las correcciones de contratos y
la nueva campaña factorial: [primera calibración ejecutada](calibracion_apariencia_2026-10-26.md).
La galería de 50 imágenes está pendiente de revisión humana; no se ha entrenado
el piloto nuevo. Persisten intersecciones en las plantas diagnósticas, documentadas
y excluidas del banco, y ajustes visuales pendientes. La campaña cerrada se conserva.
