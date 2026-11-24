# Sobremadura tras las nuevas texturas y galería de cuatro modelos

## Resultado y alcance

**Las nuevas texturas no resolvieron la transferencia de Sobremadura.** En la
pareja reciente el AP50–95 de esta clase pasa de 11,87 % a 9,32 % de media:
−2,54 puntos, con descenso en las tres semillas. Los errores guardados muestran
confusiones de clase y cambios de confianza, junto a brechas de escala y
exposición que la mejora visual no corrigió. No se aisló una causa de
aprendizaje: también cambiaron proporciones de clases, cielos e iluminación.

Esta revisión usa las **94 fotos reales de evaluación** que confirmó el usuario,
con las mismas etiquetas. Hay 58 cajas Sobremadura en 28 fotos. El test sigue
siendo desarrollo, consultado históricamente. No se entrenó, infirió, renderizó
ninguna planta ni modificó etiqueta alguna; todo procede de cachés verificadas.
La generación permanece pausada.

Raíz nueva: `outputs/sobremadura_four_models_20261113/`.

## Galería solicitada: modelos disponibles y procedencia

`index.html` permite revisar las 94 fotos, seleccionar las tres semillas,
activar/desactivar etiquetas y predicciones, enfocar el mismo recorte en los
cuatro paneles y mostrar candidatos Sobre bajo el umbral. Conserva todas las
clases competidoras por defecto; no oculta Pintona cuando también aparece Sobre.

| Panel | Datos / receta | Procedencia |
|---|---|---|
| Sin aumentación | 461 reales, sin clásica | Campaña histórica 22–26/10 |
| Clásica | 461 reales, clásica y repetición emparejada | Piloto reciente 12/11 |
| Sintética | 461 reales + 389 sintéticas, sin clásica | Campaña histórica 22–26/10 |
| Híbrida | 461 reales + 115 sintéticas nuevas, clásica | Piloto reciente 12/11 |

Cada familia conserva las semillas 20261022/23/24 y 4.000 actualizaciones por
corrida, con selección de checkpoint por validación. El panel Sintética **no**
significa entrenamiento exclusivamente virtual. Los históricos no usan las
nuevas texturas; su banco, dosis y plan de muestreo difieren de los recientes.
Por ello **los cuatro paneles son una inspección cualitativa entre campañas,
no una ablación controlada de cuatro tratamientos**. El diagnóstico cuantitativo
de la caída actual se limita a la pareja reciente realmente emparejada.
Para cuatro tratamientos actuales comparables faltarían dos entrenamientos
emparejados; no se han iniciado por cuenta propia.

Se verificaron los doce checkpoints y cachés (cuatro familias × tres semillas),
contra sus locks y los hashes históricos de `confirmation_evaluation_20261026`.
Todas las cachés contienen las mismas 94 filas y coinciden con las cajas/clases
leídas de las etiquetas reales originales. Se verifican imágenes por SHA.

El umbral visual común es **0,076076**, elegido en val del control reciente;
no se retocó con estas fotos. Los históricos tenían su calibración original
distinta: sus conteos de galería no deben confundirse con las métricas publicadas
entonces. Los scores entre modelos no son probabilidades calibradas equivalentes.

### Etiquetas y ausencia

- Blanco discontinuo: caja original; cajas sólidas por color: predicciones.
- Predicción Sobre ausente y etiqueta Sobre ausente son estados distintos.
- El filtro de fotos sin GT Sobre muestra candidatos donde la clase no está
  anotada; en la semilla 20261023 son 25 fotos distintas con algún candidato
  entre los cuatro modelos. No se certifica que haya o no haya Sobre biológicas.
- Un filtro adicional encuentra candidatos sin caja próxima de ninguna clase
  (IoU máximo <0,1), con botones para revisar la región. Es una categoría
  diagnóstica, no un nuevo umbral de entrenamiento ni una adjudicación.
- Si hay una etiqueta Madura/Pintona cerca del candidato, se muestra esa clase
  e IoU. Las predicciones nunca se convierten automáticamente en anotaciones.
- Los TP/FP/FN Sobre de cada panel corresponden a la foto completa, incluso al
  acercar un recorte, con matching por clase y el mismo umbral común.

Las previsualizaciones son copias reducidas para inspección, con enlace al RGB
original. Los datos fuente permanecen intactos. Los tres PNG de `samples/`
muestran cuatro modelos con recorte idéntico y procedencia explícita.

## Qué tipo de error empeora

| Semilla | AP Sobre clásica | AP Sobre híbrida | Delta |
|---|---:|---:|---:|
| 20261022 | 11,43 % | 9,77 % | −1,66 pp |
| 20261023 | 11,17 % | 10,02 % | −1,14 pp |
| 20261024 | 13,00 % | 8,18 % | −4,82 pp |

Al umbral común, sumando las tres apariciones de cada una de las mismas
58 verdades (no 174 objetos independientes):

| Medida Sobre | Clásica | Híbrida |
|---|---:|---:|
| TP por clase | 41 | 35 |
| FP respecto de las etiquetas | 139 | 121 |
| FN por clase | 133 | 139 |
| Objetivos atribuidos a Pintona, diagnóstico por objetivo | 38 | 57 |
| Objetivos atribuidos a Madura, diagnóstico por objetivo | 15 | 8 |
| Clase Sobre por debajo del umbral | 43 | 34 |
| Sin predicción localizada relevante | 34 | 38 |

Se conservan 25 TP comunes, se pierden 16 y aparecen 10 nuevos. En esos 25 TP
comunes la mediana de IoU es 0,918 clásica y 0,938 híbrida. Es una comparación
condicionada a acertar en ambos: no prueba que todas las cajas mejoren, pero
no respalda culpar a un deterioro geométrico general. El AP Sobre ya cae a
IoU 0,5, por lo que no es sólo una exigencia de contornos muy precisos.

Los FP totales Sobre **bajan**, mientras se pierden TP y cambian las confianzas.
Esta vez no corresponde explicar el descenso principalmente como más FP.
Dentro de esos FP, los candidatos sin solapamiento relevante con ninguna
etiqueta (IoU máximo <0,1) suben de 25 a 38; los que recaen sobre otra clase
anotada bajan de 97 a 75. El primer grupo puede incluir fondo, órganos omitidos
o exclusiones de la política de anotación: no se adjudica automáticamente.
Por eso la galería permite buscar ausencia de cualquier caja cercana, además
de ausencia de la clase Sobre a escala de foto.
La confusión por objetivo de esta tabla no equivale al emparejamiento global
agnóstico de la matriz de confusión; no se mezclan sus diagonales.

La sensibilidad post hoc al retirar por separado cualquiera de los seis grupos
mantiene negativo el delta medio Sobre, entre −4,63 y −2,35 pp. La caída no se
limita a uno de los ejemplos destacados. El intervalo descriptivo del bootstrap
condicionado de 200 sorteos sigue siendo amplio [−6,87; +1,28] pp: no demuestra
un daño generalizable ni significación confirmatoria.

## Tres ejemplos y una precisión sobre la lámina anterior

**Fila 113, tejido oscuro con venas verdes, semilla 20261023.** La clásica
produce Sobre 0,100, pero también Pintona 0,478 sobre casi la misma caja.
La híbrida da Pintona 0,928 y Sobre 0,059, bajo el umbral. El control no era
inequívocamente correcto. La lámina resumida anterior mostraba el candidato
Sobre del control sin esa competencia: la galería actual y su tabla muestran
ambas clases, corrigiendo esa limitación de presentación.

**Fila 183, tejido seco claro y plegado, semilla 20261022.** La clásica tiene
Sobre 0,496 y la híbrida Sobre 0,051 bajo el umbral. Este caso recuerda que la
clase real incluye secado claro, además de tejido oscuro; no es suficiente
aprender “más negro = más sobremaduro”.

**Fila 364, etiqueta Madura y zona proximal oscura, semilla 20261024.** La híbrida
propone Sobre 0,669 donde la etiqueta es Madura. El control tampoco ofrece una
predicción Madura fiable en ese objetivo; es un ejemplo de nuevo candidato
incorrecto respecto a las etiquetas, no de acierto claro del control.

Los casos fueron elegidos para examinar errores y no representan una frecuencia
aleatoria de éxito. Las etiquetas reales se conservan sin adjudicar si una
predicción discrepante revela una confusión o un problema de anotación.

## Por qué mejores texturas pueden no ayudar aquí

### Escala y densidad observadas

Después del filtro nativo, el lado mínimo mediano de Sobre a 960 px es
**100,51 px en train real y 14 px en sintético**. El 53,43 % de las Sobre
sintéticas retenidas sigue por debajo de 16 px, frente a 0,55 % de las reales.
16 px describe una distribución; no se introdujo ese corte. El filtro nativo
>2 px no garantiza que las venas o el secado sean visibles para el aprendizaje.

La mediana sintética bruta mejoró de 7 px en el banco anterior a 13 px en el
nuevo, pero sigue lejos de la real. La media de etiquetas retenidas es
675,82 por foto sintética frente a 10,25 por foto real. Mejorar una textura
que luego ocupa pocos píxeles no resuelve esa brecha de señal.

### Exposición y composición de los lotes

El 3,93 % de las etiquetas del banco son Sobre, pero el **90,23 % de las
apariciones Sobre en los tres entrenamientos mixtos completos es sintético**:
139.700 sintéticas frente a 15.132 reales. Los controles ven 18.875 reales
(la mezcla reduce la exposición real Sobre 19,83 %). En los checkpoints
seleccionados la reducción es 13,59 %, con 81.785 Sobre sintéticas y 8.841 reales
frente a 10.232 reales en controles.

Estos son conteos, **no cuotas de gradiente**. Sólo 35,8 %, 36,1 % y 35,9 % de
las actualizaciones de las tres mezclas contienen alguna imagen sintética.
La implementación instalada de la pérdida normaliza términos por scores de
asignación (`target_scores_sum`), no por un simple total de cajas. Los scores
de asignación y gradientes por dominio no se guardaron. La gran densidad puede
alterar la ponderación efectiva de un lote mixto, pero no se puede cuantificar
esa influencia ni atribuirle causalidad usando sólo la exposición registrada.

### Cobertura visual y factores que cambiaron juntos

En las fotos reales observadas hay secado pajizo/claro, plegado de tejido,
tejido oscuro con venas aún verdes y manchas en capachos etiquetados Madura.
Los casos enseñan límites de una asociación simple entre oscuridad y clase.
El banco nuevo mantiene la geometría admitida: **no aplicó contracción ni
compresión geométrica** a las plantas, aunque cambió su apariencia superficial.
No se ha probado que la textura nueva reproduzca toda esa variedad de forma
y estados intermedios.

El híbrido anterior daba Sobre 11,11 % y el reciente 9,32 %; esta comparación
antes/después no aísla la textura. También cambiaron la proporción/asignación
de clases y la luz/cielos. La evidencia más fuerte es que la corrección visual
no bastó frente a las brechas de escala, exposición y cobertura restantes.

## Qué decidir antes de corregir

Mantener la generación pausada. Prioridades propuestas, **sin ejecutarlas**:

1. Igualar mejor el tamaño informativo y la densidad por encuadre usando las
   mismas plantas y conservando todas las etiquetas; no agrandar órganos ni
   borrar los del fondo para ocultar el problema.
2. Separar un contraste de exposición/dosis o representación visual, cambiando
   un factor cada vez y preservando la exposición real de la clase de interés.
3. Revisar en train real los estados claro/oscuro, venas retenidas y plegado,
   y adjudicar discrepancias de etiquetas sin corrección automática basada en
   predicciones o en este test de desarrollo.

No se decide una nueva cuota, filtro ni umbral a partir de estas 94 imágenes.
No se inició ampliación, render, entrenamiento o promoción de modelo.

## Artefactos y verificación

- `index.html`: galería, 94 fotos / 28 con etiqueta Sobre / tres semillas.
- `model_registry.json`: doce modelos/checkpoints, dosis, fuentes y hashes.
- `samples/four_models_row_113_seed_20261023.png`, fila 183 y fila 364:
  comparación estática de los cuatro modelos.
- `texture_transfer_diagnosis.json`, `diagnosis_inputs.json`, `input_lock.json`:
  cálculos y procedencia verificados sin modificar las cachés originales.
- `runtime_checks.json`: pruebas de contrato del JavaScript en Node, sin
  navegador; `unit_checks.txt`: cuatro pruebas de semántica de etiquetas/caché.

La apertura automatizada de `file://` fue rechazada por la política del
navegador de verificación. No se intentó evadirla con otro navegador, servidor
ni canal. Se comprobaron sintaxis, filtros, semillas, cambios de recorte,
estados vacíos y cajas en pruebas locales, y se inspeccionaron visualmente los
tres PNG. **La interfaz no se declara verificada visualmente en un navegador.**

El validador del grafo reproduce exactamente los diez errores de localizadores
preexistentes registrados antes de esta intervención; no añade errores.
