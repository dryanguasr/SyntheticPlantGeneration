# Diagnóstico del aporte sintético y próximos pilotos

Fecha: 23 de octubre de 2026. Diagnóstico paralelo a la campaña en curso, sin cambiar datos, entrenador, selección ni presupuesto. No se consultaron nuevas métricas de test para elegir proporciones. Las cifras históricas se identifican como tales.

## Conclusión provisional

Todavía no puede concluirse que los sintéticos no ayudan en general. Su aporte es inestable y depende de proporción, cantidad real y receta. Con 461 reales y 389 sintéticas sin clásica, dos semillas finales completas presentan diferencias de +1,357 y −3,007 puntos de AP de validación respecto a su control real. Con 461 reales y 115 sintéticas con clásica, dos semillas presentan +0,997 y +0,055 puntos: una mejora apreciable y otra prácticamente nula. Falta completar la campaña y el control de repetición. Son mejores checkpoints de validación, no resultados externos independientes.

La explicación más defendible es una combinación de desajuste de contexto, tamaños por clase, exposición real, composición de clases y diversidad limitada. Los desajustes están medidos; su contribución causal al AP no está aislada. No corresponde atribuir porcentajes de responsabilidad a cada factor.

## Planta menos frondosa y escena con más maleza

La observación del usuario —arbustos recientes menos densos y más maleza— concuerda cualitativamente con los fotogramas existentes inspeccionados. En `125182_989_wide_recovered.jpg` aparecen tallos expuestos, follaje irregular y abundante vegetación acompañante, incluidas flores. Los pares sintéticos inspeccionados muestran hojas grandes en primer plano o fondos poco estructurados; el contexto no reproduce bien esa combinación. Esto es inspección de ejemplos, no una medición representativa de los tres videos ni una clasificación agronómica del estado del cultivo.

Conviene separar cuatro variables:

| Variable | Qué describe | Cómo medir en el próximo conjunto |
|---|---|---|
| Follaje de la uchuva | Frondosidad del arbusto objetivo | Cobertura foliar y huecos dentro de una región de planta revisada; distinguir hojas verdes/secas |
| Vegetación acompañante | Maleza y distractores alrededor o delante | Cobertura y tipo de distractor, dentro/fuera de la región objetivo |
| Densidad de objetivos | Capachos visibles por imagen o región | Conteos, tamaño y distribución espacial de anotaciones completas |
| Visibilidad del capacho | Cuánto contorno/superficie es observable | Revisión humana ordinal; en sintético, visibilidad geométrica contra una referencia sin oclusores |

Menos follaje de uchuva no implica una imagen más fácil: puede haber más fondo visible y más maleza que oculte o se parezca al objetivo. Tampoco un menor número de cajas demuestra menor densidad botánica: intervienen distancia, campo de visión, fructificación y criterio de anotación. No se vuelve a imponer densidad como criterio de admisión; se propone estratificarla para entender la transferencia.

![Ejemplo de video reciente](../../outputs/union_real_pilot_20261022/diagnosis_v1/125182_989_wide_recovered.jpg)

![Encuadres reales y sintéticos](../../outputs/augmentation_pilot_20261022/visual_review_size_pairs/pares_2.jpg)

## Desajustes medidos en el banco actual

Las siguientes estadísticas proceden exclusivamente del entrenamiento y del banco sintético disponible.

| Magnitud | Real | Sintética | Interpretación |
|---|---:|---:|---|
| Imágenes | 461 | 389 | Número de vistas no equivale a diversidad de plantas |
| Instancias | 4.723 | 6.718 | La proporción por imágenes subestima el peso sintético por objetos |
| Instancias por imagen, mediana | 7 | 13 | Descriptivo; no mide frondosidad ni maleza |
| Lado menor a 960, mediana | 55,99 px | 52,50 px | Medianas próximas, distribuciones distintas |
| Cajas <16 px | 2,43 % | 19,98 % | Exceso de objetivos muy pequeños |
| Mediana clase 0 | 46,85 px | 54,75 px | Escala condicionada por clase diferente |
| Mediana clase 1 | 77,42 px | 51,00 px | La clase 1 sintética aparece considerablemente menor |
| Mediana clase 2 | 100,51 px | 51,00 px | La clase 2 sintética aparece aproximadamente a mitad de tamaño |
| Clases 0/1/2 | 76,24/16,07/7,69 % | 35,08/43,76/21,15 % | Se cambia simultáneamente dominio y distribución de clases |

La clase minoritaria real tiene más presencia sintética, lo cual podría ayudar, pero no demuestra que su apariencia sea transferible. El cambio de balance impide atribuir el resultado únicamente al realismo. Las etiquetas siguen describiendo apariencia del capacho, no madurez interna.

### Anotaciones técnicamente correctas pueden ser poco informativas

El exportador sintético incluye todas las instancias con al menos un píxel visible y deriva la caja de la máscara visible. En las máscaras nativas hay 51 instancias con ≤4 píxeles visibles, 218 con ≤16 y 564 con ≤64, sobre 6.718. Estos son píxeles de máscara a resolución nativa; no son los intervalos de lado de caja a 960 ni una tasa de oclusión.

La integridad máscara–instancia–clase está comprobada, pero un fragmento de pocos píxeles puede no contener evidencia visual suficiente para distinguir tres apariencias. En el real las cajas provienen de polígonos humanos; falta revisar si ambos dominios usan la misma convención de extensión visible y tratamiento de fragmentos. No se debe borrar el objeto de la etiqueta dejándolo visible en RGB: lo convertiría en un falso fondo. Para futuros bancos, priorizar cámaras con visibilidad útil y mantener el contrato de anotación; cualquier regla de ignorar objetos requeriría una política explícita compatible con el entrenador y ambos dominios.

### El sintético desplaza exposición real

En el final `r100_s100_c0`, semilla 20261022, las 4.000 actualizaciones consumieron 8.000 imágenes: 4.332 reales y 3.668 sintéticas. El control real consume 8.000 reales. La exposición real baja un 45,85 % y las instancias sintéticas suman 62.363 de 106.792 exposiciones a objetos (58,40 %). La proporción nominal sintéticas/reales de 84,38 % no describe por sí sola lo que aprende el modelo.

Con 115 sintéticas y clásica, la primera semilla vio 6.412 reales y 1.588 sintéticas: desplazamiento real del 19,85 %. Una dosis menor podría conservar más señal real, pero aún no podemos asignarle causalidad. El control de repetición en curso permitirá comparar contenido sintético con repetición real manteniendo los pasos y los lugares del muestreo. No aislará por sí solo fondo, clases, tamaño y visibilidad.

### Diversidad y apariencia

El banco procede de cuatro plantas de entrenamiento. Cambiar cámaras añade vistas, pero mantiene estructuras y materiales correlacionados. En los ejemplos inspeccionados, la textura/nervadura, el aspecto de hojas y el fondo difieren de fotografías y videos. Es plausible que el modelo aprenda señales fáciles propias del render; todavía no se ha demostrado qué señales utiliza.

El diagnóstico histórico del piloto de unión, separado de esta campaña, encontró recall de localización de 17,4 %, 55,6 % y 87,2 % para 16–32, 32–64 y ≥64 px en el control real. También encontró AP colapsado muy superior al AP de tres clases. Esto orienta a distinguir localizar de clasificar; no es evidencia de rendimiento de los nuevos finalistas ni recall de los videos. Los videos carecen de anotación exhaustiva para esa estimación.

## Próximo piloto: cambios que permiten aprender la causa

Primero construir un pequeño conjunto diagnóstico de escenas recientes con anotación completa y revisión de calidad. Una propuesta de ingeniería es 60–90 fotogramas distribuidos entre videos y segmentos temporalmente separados; el tamaño definitivo dependerá de la cobertura de estratos. Registrar por imagen frondosidad objetivo, maleza, escala, movimiento/desenfoque y condiciones de luz; por instancia clase, tamaño y visibilidad. Incluir negativos difíciles revisados para que no contengan capachos sin anotar. Separar por planta/segmento/sesión, no por fotogramas aleatorios. Usar estos videos conocidos para desarrollo y reservar una nueva adquisición para una futura evaluación externa.

Después, no cambiar todos los aspectos del generador de una sola vez:

| Prioridad | Comparación propuesta | Mantener fijo | Qué permitiría concluir |
|---|---|---|---|
| 1 | Banco actual vs cámaras ajustadas por tamaño de cada clase y visibilidad | Plantas, materiales, fondos, cantidad y muestreo | Si el desajuste geométrico explica parte del daño |
| 2 | Factorial 2×2: uchuva frondosa/rala × maleza escasa/abundante | Cámaras, tamaños y clases comparables | Separar efecto del follaje objetivo, maleza y su interacción |
| 3 | Cuatro plantas con muchas vistas vs más plantas con menos vistas | Total de imágenes y distribución geométrica | Si falta diversidad estructural independiente |
| 4 | Apariencia actual vs variación medida de capacho/hojas/luz/captura | Arquitectura y composición | Si mejorar apariencia aporta una ganancia adicional |

En el factorial, «rala» significa menos follaje o una arquitectura más abierta documentada en el modelo morfológico, no achicar órganos ni colocar frutos arbitrarios. Mantener nodos, axilas, pedicelos y asociación de órganos. Modelar maleza como vegetación acompañante separada del modelo botánico de uchuva, con distractores delante y detrás; variar conjuntamente con el estado del arbusto según lo observado, sin asumir que toda combinación es igualmente frecuente. No generar todavía un lote grande.

Para la apariencia, medir rangos de color/textura/iluminación de entrenamiento real antes de aleatorizar. Variar suavemente desgaste, hojas secas, fondo, desenfoque y compresión solo donde exista evidencia de captura; preservar el significado de las clases de apariencia. Aleatorizar color indiscriminadamente puede eliminar precisamente la señal que se busca clasificar. La cámara cercana que iguala cajas pero llena la imagen de hojas no basta.

En cada fase incluir real solo, real con la misma clásica, mezcla y repetición real; tres semillas emparejadas. Evaluar dosis pequeñas además de las actuales (por ejemplo 10 % y 25 % por imágenes, valores propuestos, no óptimos demostrados). Registrar proporción por objetos y exposición real. Si se prueba preentrenamiento sintético seguido de ajuste real, comparar contra un control con igual cómputo y exposición real; no atribuir la mejora automáticamente al contenido sintético. Mantener separados el estudio a cómputo fijo y el de exposición real fija, porque no son el mismo presupuesto.

## Cómo decidir si ayuda

Mantener AP50–95 macro como métrica principal; añadir AP por clase y colapsado, precisión/recall y falsos positivos por imagen en negativos. Desglosar por tamaño, visibilidad, frondosidad y maleza. Revisar si una ganancia global oculta daño en escenas ralas con maleza. Fijar umbral operativo con validación, no con el test; reportar diferencias por semilla y remuestreo de grupos con sus límites. Un resultado favorable en fotogramas vecinos no es una confirmación independiente.

En particular, la hipótesis de maleza se apoyaría si el banco con maleza mejora frente a su par sin maleza en escenas reales con maleza, manteniendo geometría y exposición, y reduce confusiones con vegetación acompañante. Si solo mejora en fondos limpios, habría un desajuste de composición. Si ni el factorial ni la geometría ayudan pero la diversidad entre plantas sí, la prioridad cambiaría. Estas son reglas de interpretación propuestas, no resultados ya observados.

## Evidencia y límites

- `outputs/augmentation_pilot_20261022/diagnosis_synthetic_transfer_20261023/evidence.json`: métricas de entrenamiento, máscaras y snapshot de finales completos usados aquí.
- `synthetic_exploratory_extension/admissions/r100_s100.json`: distribuciones globales y por clase.
- `scripts/audit_augmentation_renders.py`: exportación de todas las instancias visibles.
- `docs/reports/diagnostico_piloto_real_y_aruco_2026-10-22.md`: diagnóstico histórico; no mezclar con esta campaña.
- Pares visuales y fotograma ya existente enlazados arriba: inspección cualitativa, no muestreo aleatorio representativo.

No hay estimación cuantitativa actual de cobertura de maleza ni de frondosidad por sesión. No se puede confirmar que el deterioro del cultivo sea la causa del cambio visual ni que ese cambio explique la variación entre semillas. Este diagnóstico no modifica la campaña activa ni sus finalistas.
