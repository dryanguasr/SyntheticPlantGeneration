# Diagnóstico preliminar: plantas actuales del banco de apariencia

Muestra solicitada durante la generación: **cero imágenes RGB admitidas del banco definitivo y entrenamiento todavía pendiente**. Se reconstruyeron tres vistas nuevas de los dos árboles actuales de la escena 00 a partir de copias verificadas de sus estados guardados. Son previsualizaciones provisionales; no se incorporan al dataset. La campaña principal continuó sin interrupción.

Las vistas usan apariencia LT, resolución 768 × 576, ocho muestras Cycles en CPU y denoising. El banco previsto usa 24 muestras en GPU. Las cámaras de inspección no son la selección final del banco; persiste truncamiento superior. No se igualó la escala ni se modificó el color de las referencias reales.

[Galería y mediciones](../../outputs/appearance_factorial_20261026/diagnostics/user_requested_20261026/attempt_00/index.html).

## Plantas y diversidad realizada

| Planta actual | Perfil de follaje | Frutos/cálices completos | Hojas completas | Clases de capacho 0 / 1 / 2 |
|---|---|---:|---:|---:|
| 0 | green | 452 | 1257 | 312 / 89 / 51 |
| 1 | mixed | 252 | 693 | 197 / 30 / 25 |

La copa tiene ramificación y follaje bajos y las dos siluetas difieren. La muestra enseña perfiles verde y mixto; el estrato más amarillento está previsto, pero aún no se demuestra en estas imágenes. Los conteos de los árboles no equivalen a objetos visibles en una fotografía ni permiten inferir la carga completa de las plantas reales.

![Plantas actuales provisionales](../../outputs/appearance_factorial_20261026/diagnostics/user_requested_20261026/attempt_00/plantas_actuales.png)

## Comparación visual con entrenamiento real

- **Fondo:** horizonte recto, cielo uniforme y suelo repetitivo siguen marcando una brecha clara, pese al tutorado y la maleza. Las fotos reales tienen más estructura, textura, irregularidad y distractores.
- **Formas:** persisten hojas, ramificación y flores muy geométricas y repetidas. El detalle muestra flores de aspecto estrellado y superficies más uniformes. La menor calidad de este render limita cualquier conclusión sobre microtextura fina.
- **Clases:** los capachos amarillos aún se ven próximos entre sí y más oscuros que el centro de las referencias reales. La variación de desgaste y superficie dentro de cada clase resulta limitada. Es observación de apariencia, sin validación normativa ni inferencia de madurez interna.

![Detalle sintético provisional y referencia real de entrenamiento](../../outputs/appearance_factorial_20261026/diagnostics/user_requested_20261026/attempt_00/detalle_sintetico_real.png)

## Brillo y saturación: medición exploratoria

| Apariencia | Brillo codificado sintético / real | Saturación sintética / real | Observaciones sintéticas |
|---|---:|---:|---:|
| Pintona | 0.434 / 0.429 | 0.537 / 0.446 | 296 |
| Madura | 0.460 / 0.579 | 0.483 / 0.400 | 73 |
| Sobremadura | 0.435 / 0.516 | 0.517 / 0.393 | 48 |

Valores en escala 0–1, medianas de observaciones instancia/vista. El muestreo CPU de primeros impactos usa una rejilla de 128 × 96 y exige al menos dos muestras por capacho. Los reales proceden de polígonos o cajas documentadas de entrenamiento. Las poblaciones, encuadres e iluminaciones difieren; se infrarrepresentan objetos diminutos y una misma instancia puede repetirse en varias vistas. Estas cifras no son reflectancia calibrada, una diferencia de color normativa ni una prueba estadística.

Pintona tiene un brillo central parecido en esta muestra. Madura queda aproximadamente 0,119 por debajo del real y Sobremadura 0,082; las tres apariencias tienen mayor saturación central. Esto respalda revisar la apariencia de los amarillos, pero no demuestra por sí solo que perjudiquen al detector.

## Cómo sopesar las diferencias

1. Comparar las dosis previstas de 46, 115 y 230 sintéticas con las 461 reales; elegir por validación y revisar AP por clase, especialmente Madura. Una dosis menor reduce la exposición a la brecha sintética.
2. Exigir comparación contra real, B y repetición. Una ventaja de LT sobre B no demuestra por sí sola utilidad frente a entrenamiento real ni aporte específico del contenido sintético.
3. Medir tamaños, densidad y exposición por instancias cuando existan las máscaras finales. No imponer una cuota de frutos por encuadre ni asumir que una proporción de imágenes implica la misma proporción de objetos.
4. Para otra iteración, priorizar contexto más diverso e iluminación/apariencia por clase, después formas de flores/hojas y variación superficial independiente de la etiqueta. Incluir distintos vigores y fases de desarrollo puede diversificar la arquitectura sin fijar un límite arbitrario de frutos. Estas propuestas requieren otro experimento.

El diagnóstico no cambió los perfiles congelados ni la receta del entrenamiento. No hay resultados nuevos de AP. Los árboles permanecen en reparación y las previsualizaciones no acreditan admisión física.
