# Dataset de cultivo con plantas admitidas: cierre del 29 de octubre de 2026

Se cerró la generación con **144 pares RGB–máscara–etiquetas completos**, seis escenas de cultivo y veinte árboles admitidos disponibles y efectivamente visibles. **No se alcanzaron las 1.000 imágenes**: el controlador terminó al no quedar tiempo suficiente para continuar una unidad completa dentro de la ventana autorizada. No hubo entrenamiento ni promoción de modelos.

## Resultado verificado

| Resultado | Cantidad |
|---|---:|
| Imágenes activas de suelo natural v5 | 144 |
| Cercanas / intermedias / lejanas | 48 / 48 / 48 |
| Tutorado horizontal / hilos superiores | 72 / 72 |
| Escenas con imágenes completas | 6, con 24 vistas cada una |
| Árboles disponibles / presentes / con anotaciones visibles | 20 / 20 / 20 |
| Semillas nuevas / recuperaciones previamente no admitidas | 17 / 3 |
| Anotaciones visibles acumuladas | 147405 |
| Variantes abiertas o de suelo gris preservadas y excluidas | 192 |
| Entrenamientos ejecutados | 0 |

Las seis escenas son `007`, `008`, `010`, `011`, `012` y `013`; cada una contiene doce árboles en cuatro hileras de tres. Reutilizan geometrías, por lo que 144 vistas **no son 144 muestras independientes** ni representan 144 plantas. El color foliar y la apariencia de capachos son metadatos sintéticos por escena; no modelan una serie temporal de maduración real.

## Presupuesto y parada

El consumo anterior a la ampliación fue **7.508005 h efectivas**. La nueva autorización abrió hasta ocho horas adicionales desde ese punto o mil imágenes nuevas válidas, lo primero que ocurriera. Se preservaron el reloj inicial, los intervalos excluidos y el presupuesto anterior mediante una revisión por hash; no hubo reinicio ni otra ampliación.

El estado final del controlador registra **7.982955 h en la ampliación** (aproximadamente 7 h 59 min) y **15.490960 h acumuladas**. El rendimiento agregado fue 18.04 pares por hora de esa ventana, incluyendo ingeniería, auditorías y recuperación: no es un benchmark aislado de GPU. La suspensión queda excluida por el reloj nativo de Windows.

La razón persistida es `insufficient_time_for_next_complete_scene`. El controlador y el trabajador registraron respectivamente **61.36 s** y **16.99 s** remanentes en sus estados finales; se conservan ambos registros sin normalizarlos. No se autorizó otra tanda para completar la cifra. La escena `014` quedó auditada/aceptada pero sin capturas completas; `009` conserva auditorías parciales e interrupción. Ninguna se cuenta entre las seis escenas con imágenes.

## Plantas y alcance de la auditoría

Se verificaron los veinte árboles, sus originales, la admisión reversible y los hashes. No hubo nueva poda al componer escenas. Las pérdidas máximas individuales respecto al original fueron **4.8718 % de frutos**, **4.5005 % del número de hojas** y **4.9439 % del proxy foliar largo×ancho**; cada límite se mantiene estrictamente por debajo del 5 %. El proxy no es superficie medida.

| Escena | Tutorado | Vistas | Cruces duros | Proximidades advertidas | Cálices con unión/orientación comprobada |
|---|---|---:|---:|---:|---:|
| scene_007 | horizontal | 24 | 0 | 2864 | 3467 |
| scene_008 | overhead_strings | 24 | 0 | 2954 | 3484 |
| scene_010 | overhead_strings | 24 | 0 | 2895 | 3505 |
| scene_011 | horizontal | 24 | 0 | 2639 | 3436 |
| scene_012 | overhead_strings | 24 | 0 | 2811 | 3398 |
| scene_013 | horizontal | 24 | 0 | 2725 | 3452 |

Todas las escenas con capturas tienen suelo plano válido con margen de 1 mm y orientación/unión de cálices válida. Cero cruces duros se refiere a las categorías auditadas; hoja–hoja permanece como ocupación blanda y las proximidades como advertencias. El `status=invalid` de algunos reportes corresponde a estas proximidades y no se oculta. Flores, maleza, tutorado y demás contexto no tienen certificación exhaustiva de contacto. La oclusión visual no se interpreta como intersección física.

## Anotaciones, clases y procedencia

Se verificaron los hashes de todos los pares activos y de las 192 vistas excluidas, que permanecen intactas. Una auditoría de píxeles de las 144 máscaras comprobó **las 147.405 anotaciones**: todos los colores objetivo observados tienen etiqueta, cada caja coincide con los extremos de sus píxeles, la clase coincide con la asignación de escena y el formato YOLO conserva sus coordenadas. El error máximo de normalización fue 4,45×10⁻¹¹. Se conservaron fragmentos visibles válidos de un píxel; no se retiraron etiquetas dejando objetos visibles sin anotar.

Las clases conservan los nombres del proyecto y describen apariencia del capacho, no madurez fisiológica demostrada del fruto:

| Clase | Nombre | Anotaciones sintéticas | Porcentaje sintético | Cajas de entrenamiento real | Porcentaje real train |
|---|---|---:|---:|---:|---:|
| 0 | Pintona | 49628 | 33.67% | 3601 | 76.24% |
| 1 | Madura | 50198 | 34.05% | 759 | 16.07% |
| 2 | Sobremadura | 47579 | 32.28% | 363 | 7.69% |

La revisión humana integral del banco y la discriminación de estas clases siguen pendientes; la revisión visual por el agente no sustituye esa validación. Los IDs y posturas se conservan para el contrato Gazebo, cuya exportación tampoco certifica dinámica, masas o rigidez del simulador.

## Exposición de árboles reutilizados

«Presente» significa instanciado en la escena; «visible» exige al menos una anotación de capacho. La última columna acumula anotaciones de vistas repetidas, no órganos únicos ni observaciones independientes.

| Semilla fuente | Imágenes presente | Imágenes con capachos visibles | Anotaciones acumuladas |
|---|---:|---:|---:|
| 2026102702 | 72 | 65 | 7976 |
| 2026102703 | 72 | 51 | 6902 |
| 2026102708 | 96 | 69 | 8350 |
| 2026102805 | 72 | 50 | 5537 |
| 2026102808 | 72 | 40 | 5564 |
| 2026102809 | 96 | 62 | 7570 |
| 2026102813 | 96 | 95 | 8225 |
| 2026102815 | 72 | 41 | 4484 |
| 2026102827 | 72 | 61 | 6926 |
| 2026102829 | 96 | 46 | 5789 |
| 2026102834 | 96 | 80 | 9542 |
| 2026102835 | 96 | 61 | 7985 |
| 2026102836 | 144 | 102 | 10120 |
| 2026102837 | 96 | 86 | 10966 |
| 2026102842 | 72 | 66 | 10448 |
| 2026102843 | 96 | 58 | 6059 |
| 2026102844 | 72 | 50 | 6322 |
| 2026102849 | 48 | 32 | 3689 |
| 2026102860 | 96 | 65 | 6499 |
| 2026102863 | 96 | 78 | 8452 |

## Brechas observadas respecto al entrenamiento real

La comparación utilizó **sólo las 461 imágenes de entrenamiento real y sus 4.723 cajas**, verificadas contra los hashes congelados. No se abrieron imágenes de validación/prueba ni se consultaron métricas de detector en este cierre. Los conteos describen **cajas anotadas disponibles**, no la cantidad física total de frutos de un cultivo; el banco sintético anota todos los fragmentos visibles válidos.

| Lado menor de caja, normalizado a imagen de lado largo 960 px | Sintético | Real train |
|---|---:|---:|
| <8 px | 94413 | 0 |
| 8–<16 px | 40314 | 115 |
| 16–<32 px | 9696 | 1282 |
| ≥32 px | 2982 | 3326 |

El **64.05 %** de las anotaciones sintéticas tiene lado menor inferior a 8 px, frente a cero cajas anotadas de ese tamaño en train. La mediana de cajas anotadas por imagen es **875 frente a 7**, y los rangos son **64–2.248 frente a 1–70**. La distribución sintética de clases es casi equilibrada y difiere claramente de train. Estas son brechas descriptivas importantes; no demuestran por sí solas una caída o una ganancia de AP.

Las muestras muestran capas de cultivo, hilos o espaldera, tierra con variaciones tonales y restos vegetales. Persisten repetición de formas y texturas, manchas de suelo estilizadas y tonos de capacho que pueden resultar próximos entre clases. La iluminación LT, los órganos y sus dimensiones no se cambiaron para disimular estas diferencias. La escala de escena es una entrada de ingeniería, no una calibración métrica contra plantas medidas.

## Hipótesis y recomendaciones para la próxima iteración

1. **Controlar la dosis también por instancias y tamaños.** Con el promedio actual, una selección hipotética de 46 vistas aportaría unas 47088 anotaciones sintéticas frente a las 4.723 reales: alrededor del 90.9 % de las etiquetas aunque sólo se añada aproximadamente un 10 % de imágenes. Es una estimación ilustrativa, no una exposición de entrenamiento ejecutada; debe recalcularse para los IDs y secuencias realmente seleccionados.
2. **Seleccionar vistas completas y preparar nuevos encuadres cercanos** que acerquen los histogramas de tamaño y cajas anotadas al train, manteniendo árboles intactos y todas las etiquetas visibles. No resolver la brecha borrando anotaciones diminutas de imágenes que aún contienen esos capachos. Las vistas amplias pueden conservarse como estrato contextual explícito y con exposición limitada, cuya utilidad requiere contraste.
3. **Revisar la apariencia con personas y medir los componentes del suelo/luz por separado.** Ajustar especularidad, contraste, tintes y diversidad de maleza es una hipótesis de mejora visual, no una causa demostrada de utilidad para un detector. No convertir desacuerdos de apariencia en relabelado automático de fotos reales.
4. **Agrupar por geometría fuente y escena** en una evaluación posterior; no dividir vistas del mismo árbol entre particiones pretendidamente independientes. La reutilización de veinte árboles limita la diversidad efectiva aunque aumente el número de capturas. La coocurrencia de las fuentes instanciadas conecta las seis escenas en un único componente conservador: no existe un split sintético independiente por fuente dentro de este banco. Harían falta plantas disjuntas para ese contraste; destinar estas vistas sólo al entrenamiento mantiene separada la validación real, si se conserva su partición.
5. **Optimizar interpretación, caché y gestión de memoria antes de otra tanda grande**, sin reducir órganos ni relajar auditorías. El reciclado de Blender evitó retener toda la sesión; cualquier nuevo LOD o cambio de malla necesitaría su propia reconstrucción y auditoría.

No se inició un piloto de aumentación, no se compararon modelos y no se afirma mejora de rendimiento. El test real fue consultado históricamente durante desarrollo; una selección futura no puede convertirlo en holdout externo intacto.

## Incidencias y preservación

La presión de memoria alcanzó el 94 % del sistema; Blender retenía unos 17 GB privados. La recuperación preservó 48 pares completos y la escena `009`, y se detuvieron sólo procesos propios con PID y creación nativa comprobados. Una reanudación mediante el controlador histórico falló de forma segura al intentar consultar PIDs antiguos reutilizados/protegidos: no se detuvo ningún proceso ajeno. La continuación exclusiva del dataset evita esos PIDs y recicla su hijo propio después de cada bloque de 24 pares. Los códigos de salida de esos reciclados están marcados como intencionales, no como fallos de admisión.

Se preservaron presupuestos, locks, árboles, intentos, logs y parciales. Los 110 archivos de fuente/datos congelados del banco no cambiaron; el nuevo supervisor tiene un lock separado. El código reutilizable se publicó en `codex/uchuva-spatial-generator-20261029`, commits `5d5ea63` y `7671370`, con 231 pruebas puras de la publicación inicial y dos pruebas negativas de reanudación. El grafo publicado enfocado valida; el grafo local conserva diez errores de localizadores preexistentes de otros cambios, sin sobrescribirlos.

## Artefactos locales

- [Galería por escena y profundidad](../../outputs/spatial_plant_pool_20261028/dataset/review.html): 18 ejemplos deterministas de revisión, no una muestra estadística.
- [Manifiesto de todos los pares activos](../../outputs/spatial_plant_pool_20261028/dataset/manifest.json) y [resumen de exposición](../../outputs/spatial_plant_pool_20261028/dataset/review_summary.json).
- [Auditoría completa de píxeles/cajas/YOLO](../../outputs/spatial_plant_pool_20261028/dataset/final_pixel_audit.json), [cierre físico y de hashes](../../outputs/spatial_plant_pool_20261028/dataset/final_review.json) y [comparación sólo train](../../outputs/spatial_plant_pool_20261028/dataset/train_only_comparison.json).
- [Pérdidas por planta](plantas_admision_espacial_8h_2026-10-29.md), [guía de reutilización/Gazebo](../guides/generador_actual_y_contrato_gazebo.md) y [presupuesto con revisión autorizada](../../outputs/spatial_plant_pool_20261028/budget.json).

Las imágenes, etiquetas, árboles de campaña y pesos no se suben a Git. Los enlaces a `outputs/` requieren la copia local preservada; el repositorio publica código y documentación, no el banco generado.
