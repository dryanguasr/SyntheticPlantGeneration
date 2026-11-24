# Cierre del piloto de apariencia y controles reales — 27 de octubre de 2026

**Cierre parcial: el factorial sintético no pudo ejecutarse.** Ninguna escena
superó la admisión física. Se completaron los dos screenings y los seis controles
reales nuevos, con tres semillas por receta. En la prueba de desarrollo, la
clásica alcanzó **19,14 %** de AP50–95 macro frente a
**19,17 %** sin clásica. La diferencia emparejada
media fue **-0,03 puntos porcentuales**: una
semilla mejora y dos empeoran. No se observa una ganancia macro consistente.

Este resultado no evalúa el aporte de iluminación o texturas sintéticas. La
ausencia de imágenes admitidas es un resultado negativo de generación/validación,
no evidencia de que esos cambios de apariencia sean inútiles.

## Alcance, datos y receta congelada

Se conservaron 461 imágenes reales de entrenamiento, 88 de validación y 94 de
prueba de desarrollo, con aislamiento por grupos y hashes verificados. Las
clases Pintona/Madura/Sobremadura describen **apariencia del capacho**; no validan
madurez interna. La prueba ya fue consultada históricamente y no es un holdout
externo independiente. Sus 955 instancias se distribuyen en 806/91/58 por clase.

Todos los controles se reentrenaron desde `yolo26n.pt`, SHA256
`9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef`:
960 px, batch/nbs 2, AdamW, LR inicial 0,0002 y calendario lineal por actualización
hasta 0,01×LR inicial, sin warmup. La clásica fue exclusivamente reflejo
horizontal 0,5 y variación HSV de valor 0,1. Se mantuvieron desactivadas las
otras transformaciones. No se modificó el entrenador durante la ejecución.

Se verificaron actualizaciones exactas, validación cada 500 pasos, secuencias
reales y LR emparejados, decisiones de aumentación registradas, integridad de
datos/pesos/fuentes y versiones de paquetes. Los seis checkpoints se congelaron
antes de evaluar la prueba; su selección fue por validación. No se eligió un
modelo para producción a partir del test.

## Banco sintético: qué se consiguió y qué falló

Se implementaron la separación planta/captura, carga reproductiva
`architecture_driven`, copa baja y ramificación revisadas, follaje y clase del
capacho independientes, y postura colgante serializada. Se conservaron órganos,
dimensiones y clases al reparar poses; no se impusieron cuotas de frutos para
conseguir encuadres. La orientación del capacho se separó del pedicelo axilar.
El cono 0–25° desde abajo, moda 8°, es una **heurística no medida**, no una norma.

Se corrigieron dos fallos técnicos detectados durante el banco: pérdida de
precisión del marco casi vertical y ausencia de proxies para pedicelos florales
sin cáliz. Las correcciones conservaron tolerancias y criterios físicos, con
regresiones y casos capturados reconstruidos. Véase el
[registro botánico y técnico](revision_capachos_colgantes_2026-10-27.md).

El objetivo de 24 plantas/12 escenas y 230 vistas comunes no se alcanzó.
Cinco intentos completos con diez árboles terminaron así:

| Escena / intento | Intersecciones | Hoja–tallo | Suelo |
|---|---:|---:|---|
| scene_00 / 00 | 462 | 204 | Válido |
| scene_00 / 01 | 1261 | 549 | Válido |
| scene_00 / 02 | 504 | 298 | Válido |
| scene_00 / 03 | 423 | 201 | Válido |
| scene_01 / 00 | 758 | 381 | Válido |

No hubo escenas admitidas, candidatos de cámara ni vistas de entrenamiento.
Los positivos de margen interórgano siguieron siendo descriptivos; los cruces de
malla y el suelo de 1 mm siguieron bloqueando. Hoja–hoja se trató como ocupación
blanda. El auditor no certifica exhaustivamente todos los contactos de flores,
frutos interiores, maleza o contexto. Solapamiento proyectado y ocupación de
caja no se interpretaron como intersección ni oclusión física.

El consumo de generación fue 33.108,75 s (**9,20 h activas**). Se dejaron de
iniciar escenas al entrar en la reserva de 3 h para RGB, dentro del máximo de
12 h; al no quedar escenas elegibles, la reserva no produjo un banco. No se
amplió el presupuesto ni se fabricó diversidad mediante duplicados. Los intentos,
fuentes, hashes, errores y árboles originales permanecen preservados.

Estas comparaciones visuales son **previsualizaciones diagnósticas**, no capturas
admitidas ni evidencia de desempeño. Mantienen cámara, luz y materiales entre
antes/después y conservan frutos/follaje. El marco transversal numérico se
estabilizó posteriormente sin cambiar el contrato colgante:

![Corrección del capacho](../../outputs/appearance_factorial_20261026/revisions/pendulous_orientation_20261027/fixed_camera_preview/comparacion_capachos.png)

![Copa conservada](../../outputs/appearance_factorial_20261026/revisions/pendulous_orientation_20261027/fixed_camera_preview/comparacion_copa.png)

El [diagnóstico preliminar](diagnostico_preliminar_banco_apariencia_2026-10-26.md)
documenta fondo/horizonte repetitivos, señales geométricas y diferencias de brillo,
saturación y variación de clase frente a referencias solo de entrenamiento.
No fue una calibración normativa ni un diagnóstico de madurez interna.

## Matriz completa: ejecución y bloqueos

Cada celda de la tabla siguiente es un brazo de screening independiente.
Todos quedaron bloqueados por falta de vistas admitidas, no por tamaños o
densidad. B debía usar materiales/luz anteriores sobre las mismas plantas
corregidas, sin reutilizar RGB histórico.

| Sintéticas / 461 reales | Clásica | B | L | T | LT |
|---:|---|---|---|---|---|
| 46 (9,98 %) | Sí | Bloqueado | Bloqueado | Bloqueado | Bloqueado |
| 46 (9,98 %) | No | Bloqueado | Bloqueado | Bloqueado | Bloqueado |
| 115 (24,95 %) | Sí | Bloqueado | Bloqueado | Bloqueado | Bloqueado |
| 115 (24,95 %) | No | Bloqueado | Bloqueado | Bloqueado | Bloqueado |
| 230 (49,89 %) | Sí | Bloqueado | Bloqueado | Bloqueado | Bloqueado |
| 230 (49,89 %) | No | Bloqueado | Bloqueado | Bloqueado | Bloqueado |

| Fase | Planificadas | Completadas | Bloqueadas |
|---|---:|---:|---:|
| Screening, 2.000 pasos | 26 | 2 reales | 24 mezclas |
| Confirmación, 4.000 pasos | 36 | 6 reales | 24 sintéticas + 6 repeticiones |

Las dosis sintéticas no se seleccionaron: no había candidatos válidos. No existe
ganador sintético, contraste contra B, control de repetición aplicable ni efectos
L−B, T−B o interacción LT−L−T+B identificables. Esos resultados se declaran **no
ejecutados**, sin asignarles AP cero ni sustituirlos por el piloto histórico.

## Resultados reales por semilla

AP50–95 macro, en porcentaje. Cada corrida final completó 4.000 actualizaciones;
se informa su mejor checkpoint de validación.

| Semilla | Validación sin clásica | Validación con clásica | Desarrollo sin clásica | Desarrollo con clásica | Δ desarrollo, pp |
|---|---:|---:|---:|---:|---:|
| 20261022 | 23,44 | 21,51 | 19,15 | 18,14 | -1,00 |
| 20261023 | 21,95 | 23,14 | 16,91 | 19,41 | 2,50 |
| 20261024 | 19,08 | 22,69 | 21,46 | 19,87 | -1,60 |

Media ± DE en desarrollo: **19,17 ±
2,28 %** sin clásica y **19,14
± 0,89 %** con clásica. Diferencia emparejada:
**-0,03 ± 2,22 pp**.
La menor dispersión de la clásica es descriptiva con tres semillas; no demuestra
mayor robustez entre cultivos o sesiones.

Los screenings de 2.000 pasos dieron 22,317 % sin clásica y 23,333 % con clásica
en validación, semilla 20261022. No se comparan esos checkpoints como si tuvieran
el mismo presupuesto de 4.000 ni se usaron para inicializar los finales.

![Curvas de validación](../../outputs/appearance_factorial_20261026/final_review/figures/curvas_validacion.png)

| Apariencia del capacho | AP sin clásica | AP con clásica | Δ, pp |
|---|---:|---:|---:|
| Pintona | 38,77 | 39,41 | 0,64 |
| Madura | 7,81 | 8,18 | 0,37 |
| Sobremadura | 10,93 | 9,83 | -1,10 |

Son medias de las tres semillas. La ligera subida de Pintona/Madura convive con
una caída de Sobremadura; no es una mejora integral. Las clases minoritarias
siguen lejos de Pintona y tienen solo 91/58 instancias en esta prueba.

![Resultados de desarrollo](../../outputs/appearance_factorial_20261026/final_review/figures/ap_desarrollo.png)

| Métrica, media entre semillas | Sin clásica | Con clásica |
|---|---:|---:|
| AP50–95 colapsado | 40,68 % | 41,85 % |
| Precisión micro por instancia | 44,90 % | 41,73 % |
| Recall micro por instancia | 56,75 % | 60,35 % |

Precisión/recall y confusiones usan IoU 0,5 y umbral común **0,140140**, elegido
solo en validación del control clásico semilla 20261022, como establece el
evaluador. La clásica recupera más objetos a costa de más predicciones
adicionales respecto a la referencia. La matriz muestra confusión de las clases
minoritarias con Pintona. En Madura, los aciertos a este umbral bajan de 11,7 a
8,3 por semilla aunque su AP medio suba ligeramente: el comportamiento depende
del punto operativo, no solo del resumen AP.

![Confusiones](../../outputs/appearance_factorial_20261026/final_review/figures/confusiones.png)

## Tamaño, densidad e incertidumbre

El tamaño es el lado menor de la caja tras escalar el lado mayor de la imagen a
960. Los siguientes valores son **recall de localización a IoU 0,5**, ignorando
clase, al umbral común; no son AP por estrato ni una medición de oclusión.

| Estrato | Instancias de referencia | Sin clásica | Con clásica |
|---|---:|---:|---:|
| 16–32 px | 46 | 17,39 % | 22,46 % |
| 32–64 px | 410 | 47,64 % | 51,87 % |
| ≥64 px | 499 | 80,63 % | 84,97 % |
| 1–7 instancias/imagen | 157 | 68,15 % | 73,67 % |
| 8–22 instancias/imagen | 653 | 65,44 % | 68,50 % |
| >22 instancias/imagen | 145 | 49,20 % | 57,93 % |

No hay instancias de referencia <16 px en esta prueba; no se informa rendimiento
para ese intervalo. Las tasas agregan tres semillas sobre las mismas instancias;
no triplican el tamaño de muestra independiente.

El bootstrap usa 200 sorteos comunes por seis grupos, rechazando un sorteo sin
las tres clases y manteniendo fijas las tres semillas entrenadas. El intervalo
percentil de la diferencia media es **[-0,18,
1,63] pp**, e incluye cero.
Los grupos contienen 48/25/15/3/2/1 imágenes; los dos mayores concentran 73/94.
El AP es no lineal y la mezcla de grupos cambia al remuestrear: la distribución
puede desplazarse respecto al estimador original. Este intervalo condicionado
no prueba equivalencia, significación confirmatoria ni independencia por sesión,
y no integra toda la incertidumbre de selección/entrenamiento.

![Bootstrap](../../outputs/appearance_factorial_20261026/final_review/figures/bootstrap.png)

Durante la revisión se detectó saturación del tope de 300 predicciones en 77/94
imágenes de un control sin clásica. Se añadió una sensibilidad **post hoc**,
con pesos ya congelados y `max_det=1000` común a las seis corridas, sin selección
de modelos y sin reemplazar resultados primarios. El mayor cambio de AP macro
fue 0,014 pp; las medias quedaron 19,175 % sin clásica y 19,144 % con clásica.
La conclusión descriptiva permanece. Se conservaron protocolo, predicciones y
[resultados suplementarios](../../outputs/appearance_factorial_20261026/revisions/final_review_20261027/maxdet_sensitivity/summary.json).

## Muestras, exposición, tiempos y pesos

Se inspeccionaron curvas y tres muestras elegidas por menor fila fuente dentro
de cada banda de densidad, con la misma semilla 20261022 para ambos controles.
La [galería de predicciones](../../outputs/appearance_factorial_20261026/final_review/index.html) compara referencia
humana, sin clásica y con clásica. Los paneles limitan la visualización a 40
predicciones sobre umbral; las métricas conservan todas. Se observan detecciones
adicionales sobre fragmentos/follaje y errores de clase. Posibles ambigüedades u
omisiones de referencia requieren revisión humana; no se relabeló automáticamente.

Cada screening expuso 4.000 muestras reales y cada final 8.000; en todos se
recorrieron las 461 imágenes únicas. No son 8.000 imágenes nuevas ni frutos de
8.000 plantas. Exposición anotada por final y por receta, antes de redimensionar:

| Semilla | Pintona | Madura | Sobremadura | Total |
|---|---:|---:|---:|---:|
| 20261022 | 62.458 | 13.171 | 6.296 | 81.925 |
| 20261023 | 62.447 | 13.181 | 6.280 | 81.908 |
| 20261024 | 62.475 | 13.154 | 6.295 | 81.924 |

Las exposiciones son iguales entre recetas para cada semilla. Se guardan las
secuencias exactas y [conteos por instancias](../../outputs/appearance_factorial_20261026/final_review/exposure_instances.json).
Se verificaron 28.000 actualizaciones en total (2×2.000 + 6×4.000), con 56.000
presentaciones de imágenes. La ejecución principal consumió 11,065 h activas,
de las cuales 9,197 h fueron preparación/generación. La sensibilidad y los
artefactos de revisión se cobraron por separado en el mismo ledger; el cierre
registra el total definitivo, sin incluir suspensión ni revisión humana.

Los [ocho pesos, hashes, rutas y ejecuciones](../../outputs/appearance_factorial_20261026/final_review/pesos_y_ejecuciones.csv)
quedan disponibles para reproducir la evaluación. Se preservaron las 13 fuentes
congeladas y el informe del piloto histórico del 22 de octubre. No se promovió
ningún modelo a aplicaciones.

## Recomendaciones priorizadas para el siguiente piloto

1. **Resolver la generación física antes de otro lote.** Lo observado es que la
   reparación angular final deja cientos de cruces, especialmente hoja–tallo.
   Implementar y probar evitación local durante el crecimiento nodal, antes de
   aceptar cada nuevo segmento/pecíolo/hoja, con pruebas pequeñas de inserción y
   bifurcación. Es una propuesta de ingeniería por verificar; no una conclusión
   de que la carga de frutos deba limitarse. Conservar topología, registros de
   decisiones, dimensiones justificadas y separación de cámara.
2. **Exigir una prueba completa pequeña antes de escalar.** Generar un conjunto
   reducido de plantas independientes que complete auditorías, máscaras y los
   cuatro RGB emparejados. Medir aceptación, cruces por tipo, tiempo y causas de
   rechazo. No gastar el grueso del presupuesto en reparar escenas sin llegar
   a una vista admitida; cualquier nuevo reparto de tiempo se congela previamente.
3. **Revisar clases y referencias difíciles.** Madura/Sobremadura siguen con AP
   bajo y confusión con Pintona. Preparar revisión humana de casos claros y
   ambiguos, verificar exhaustividad de anotación y reunir variación real de
   color/textura por clase. Separar desgaste/manchas de Sobremadura; no convertir
   marrón u oscuridad en una regla automática ni inferir madurez interna.
4. **Retomar luz, materiales y contexto mediante la ablación pendiente.** Las
   previsualizaciones muestran fondo uniforme y repetición, y diferencias de
   amarillo/brillo. Calibrar órganos y contexto por separado usando solo train;
   variar luz ambiental/sol/relleno sin emisión, nervaduras, rugosidad y desgaste
   independiente de clase. Maleza, tutorado y heterogeneidad verde/amarillenta se
   conservan dentro de cada comparación B/L/T/LT. Son hipótesis visuales aún sin
   evaluación de transferencia del nuevo banco.
5. **Diseñar composición y dosis con exposición explícita.** La localización de
   objetos de 16–32 px y escenas densas sigue siendo débil. Seleccionar cámaras
   después de generar plantas válidas y documentar distribución de tamaños,
   clases e instancias por dominio. Si un futuro banco denso domina por número
   de etiquetas, estudiar menor dosis o ponderación en otra ablación; no ocultar
   diferencias eliminando objetos visibles ni duplicando vistas para simular
   diversidad. Usar suficientes plantas/escenas, sin afirmar diversidad a partir
   de muchas cámaras de pocos individuos.

Estas recomendaciones distinguen observaciones de hipótesis. El resultado
disponible confirma el bloqueo del generador y una comparación real/clásica
sin ganancia macro consistente; no resuelve el objetivo de transferencia
sintética del factorial.

## Evidencia y verificaciones de cierre

Se verificaron hashes de datos, pesos, fuentes y predicciones; aislamiento de
particiones; pasos, semillas, secuencias, LR y exposición; selección sin test y
denominador de tres clases. Se inspeccionaron curvas y predicciones persistidas.
El validador del grafo conserva diez errores preexistentes de localizadores,
sin regresiones nuevas. Las pruebas ejecutadas incluyen seis de orientación,
once fixtures Blender, 19 de ejes, 23 de banco, 15 de campaña y tres del cierre
de controles reales, además de las verificaciones de copa/diversidad previas.

Fuentes de resultados: [comparaciones primarias](../../outputs/appearance_factorial_20261026/evaluation/real_only_comparisons.json),
[resúmenes por corrida](../../outputs/appearance_factorial_20261026/evaluation/summary.json),
[diagnóstico de rechazos](../../outputs/appearance_factorial_20261026/revisions/real_controls_after_bank_rejection_20261027/synthetic_blockage_diagnosis.json),
[verificación de cierre](../../outputs/appearance_factorial_20261026/revisions/final_review_20261027/verification.json).

Antecedentes de implementación: [correcciones de la auditoría](revision_auditoria_para_siguiente_piloto_2026-10-26.md),
[copa y contactos](revision_contactos_y_ramas_bajas_2026-10-26.md),
[guía del protocolo](../guides/piloto_apariencia_factorial.md). Los registros
anteriores se conservan como historia, con sus estados de ejecución de entonces.
