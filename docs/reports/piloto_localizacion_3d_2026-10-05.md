# Piloto de localización 3D y conciliación respecto a ArUco

## Contrato y presupuesto

Campaña independiente autorizada el 5 de octubre de 2026: doce horas efectivas,
sin heredar el límite de medianoche de la campaña anterior. Presupuesto y
registro en `outputs/localization_pilot_20261005`. Se preservan todos los
resultados de segmentación anteriores. El heartbeat horario comprueba procesos
y progreso; la cola secuencial encadena los trabajos sin esperar al heartbeat.

Objetivo: más del 50 % de los capachos distintos observables localizados en el
ArUco correcto con error ≤5 cm y precisión ≥90 %. Los 5 cm son una tolerancia
de ingeniería. Se conservan todos los tamaños y tránsitos en el denominador;
los totalmente ocultos se informan aparte. Las tres clases describen apariencia
del capacho, no madurez agronómica. La prioridad es procesamiento posterior.

Las semillas finales 520300–520305 se congelaron antes de generar o examinar sus
imágenes. No se sustituirán por otras elegidas según métricas. Desarrollo usa
capturas ya inspeccionadas. Las posiciones verdaderas, identidades anatómicas,
máscaras y odometría se mantienen en el evaluador.

## Implementación inicial

- Contrato de mapa `calyx-marker-map/1.0`: identificador persistente, marco
  canónico, XYZ métrico, clase, observaciones, estado y rechazos. La incertidumbre
  inicial es sensibilidad al retirar observaciones, no un intervalo calibrado.
- Paquete público con RGB a 5 Hz, tiempos, intrínsecos y calibración relativa de
  pares rígidos de marcadores de 10 cm separados 36 cm. Es una configuración
  ideal diseñada para simulación; no se presenta como medición de campo. No se
  exportan posiciones mundiales ni geometría de las plantas al estimador.
- Baseline: seguimiento anterior y triangulación multivista, ahora alimentados
  por segmentación de recortes a escala nativa. Inferencia inicial a 1 Hz y
  recortes sobre toda la imagen para evitar pérdidas silenciosas por ROI.
- Primera revisión: flujo LK agrupado a 5 Hz, memoria de dos segundos,
  correspondencias ambiguas rechazadas, descriptor de apariencia y cajas;
  triangulación robusta con tres o más vistas, paralaje ≥3° y reproyección ≤3 px.
- Conciliación: mismo marco ArUco, proximidad de 3,5 cm, apariencia compatible y
  ausencia de observaciones simultáneas. Los umbrales son heurísticos de
  desarrollo. Un estado confirmado es una decisión del estimador, no validación
  mediante verdad de referencia.
- El centro visible de máscara se usa como aproximación al centro del capacho.
  Su sesgo por oclusión queda incluido en el error frente al centro geométrico;
  no se estima el centro del fruto oculto.

La asociación a planta utiliza una envolvente pública común y rechaza decisiones
ambiguas. No recibe la planta objetivo del recorrido ni identidades del simulador.
La auditoría anatómica comprueba la asignación nativa mediante proyecciones de
las envolventes de las mallas, no solo rangos de contadores. Si no pasa, bloquea
las métricas de objetos únicos.

## Validación y continuidad

Pasaron pruebas iniciales de transformación entre caras, triangulación robusta
con observación errónea y preservación de dos objetos simultáneos. Quedan por
completar pruebas de cruces, interrupciones, aislamiento y evaluación reservada.

En ejecución: baseline, revisión de seguimiento y auditoría independiente del
inventario. No hay resultados de éxito 3D todavía. Las siguientes etapas son
diagnóstico, segunda revisión de cobertura/percepción, vuelo con paralaje,
congelación, evaluación de las seis morfologías reservadas e informe con video.
El presupuesto reserva tres horas para evaluación final y hora y media para
cierre. Un único trabajo pesado de GPU, con al menos 4 GiB de RAM libres.

Solo se propondrá ejecución en línea tras sostener 5 Hz, percentil 95 ≤200 ms,
sin cola creciente y con pérdida de recall 3D ≤2 puntos porcentuales. Ningún
resultado exclusivamente Gazebo demuestra transferencia al cultivo real.

## Primer diagnóstico y corrección de pose
La auditoría anatómica pasó con acuerdo geométrico 100 % en muestras frente a 3,74 % con el orden alternativo; desarrollo tiene 388 capachos visibles y dos totalmente ocultos. Baseline: 1/388 correcto a 5 cm; seguimiento persistente: 18/388. Se detectaron esquinas ArUco sin refinamiento. En diagnóstico de desarrollo, el refinamiento subpíxel redujo el error angular mediano aproximadamente de 28 grados a 0,33 grados. Reprocesando las mismas detecciones con pose refinada: 166/388 correctos (42,78 %), precisión 45,36 %, mediana de error 1,58 cm entre identidades respaldadas del marcador correcto. El objetivo conjunto NO se alcanza. Persisten asociaciones de poco soporte, duplicados y ArUcos de plantas vecinas. Se inicia muestreo adaptativo: 5 Hz mientras la mediana de observaciones de trayectorias activas sea menor de cinco, y 1 Hz el resto. Sigue sin usar verdad en el estimador. La evaluación y generación pura de las seis morfologías reservadas quedan encadenadas. Las latencias del replay con detecciones en caché no representan extremo a extremo.


## Muestreo adaptativo y revisión del soporte geométrico
El muestreo adaptativo detectó 383 de 388 objetos visibles, pero localizó correctamente 163 (42,01 %) con precisión de 19,06 %: regresión frente a 166 y 45,36 % con muestreo fijo. No se atribuye esta diferencia a la apariencia ni se inicia otro entrenamiento. Se conservan ambos resultados. La revisión siguiente reconstruye exclusivamente desde observaciones RGB los soportes geométricos y separa inliers de observaciones rechazadas: mínimo de cinco u ocho inliers, fracción mínima 0,7 y sensibilidad leave-one-out de hasta 3 cm. Estos parámetros son heurísticas de desarrollo, no intervalos de confianza calibrados. Las trayectorias insuficientes se mantienen provisionales. Se comparan las cuatro combinaciones sobre desarrollo; no se consulta evaluación reservada. Quedan encadenadas las auditorías geométricas de las seis semillas reservadas, sin capturas RGB finales ni cambio de semillas por desempeño.

## Recuperación de auditoría y resultados de confirmación
La auditoría 520302 se detuvo por el límite individual de 1200 s, con más de 12 GiB libres; no hay evidencia de agotamiento de memoria. Se retoma desde morphology_in_progress.json en un directorio nuevo, con la misma semilla, preservando el intento fallido. El periodo 09:42:28–10:36:47 UTC queda fuera del consumo efectivo. Los siguientes trabajos admiten hasta 2400 s y el supervisor limita cada ejecución al saldo disponible después de reservar 4,5 h para evaluación y cierre.
En desarrollo, soporte fijo de cinco observaciones: 87/388 y precisión 86,14 %; ocho: 32/388 y 100 %. Con muestreo adaptativo: cinco, 104/388 y 36,75 %; ocho, 78/388 y 51,66 %. El filtrado aumenta precisión a costa de cobertura y ninguna variante satisface el objetivo conjunto. No se interpreta 100 % sobre 32 objetos como éxito del piloto.

## Preparación reservada y alternativa de 960 píxeles
Cinco auditorías completas pasaron; 520304 no presentó intersecciones físicas, pero tuvo dos separaciones entre tallos por debajo del margen de 0,024 unidades geométricas (0,0217806 y 0,022852). La búsqueda angular fina no resolvió las restricciones. Se preparó una variante morfológica de la misma semilla alargando 15 % dos entrenudos parentales, para separar las inserciones vecinas: heurística de ingeniería, no parámetro botánico medido. Se preservan órganos e identidades y se repite reparación y auditoría completa; no se aprueba por anticipado ni se reemplaza la semilla.
Quedó encadenada la alternativa de recortes nativos de 960 píxeles, con las mismas capturas, pesos, poses subpíxel y umbrales de desarrollo. A continuación: evaluación, soporte de cinco/ocho vistas y auditoría restante. La aprobación, ensamblaje y exportación del escenario reservado se bloquean si cualquiera de las seis auditorías falla. Esta preparación no ejecuta captura RGB ni evaluación del modelo reservado. La comparación de ROI y el nuevo recorrido con paralaje siguen pendientes.

## Comparación nativa y cobertura fuera de ROI
Con recortes de 960 píxeles se localizaron 171/388 objetos (44,07 %) con precisión 49,85 %. La confirmación de ocho observaciones alcanzó 38/388 (9,79 %) y precisión 97,44 %; cinco observaciones, 95/388 y 84,07 %. Sigue sin alcanzarse el objetivo conjunto. Las seis morfologías reservadas pasaron finalmente la auditoría y fueron exportadas; se corrigió un lanzamiento de bmesh que exigía Blender y se conservaron los registros del fallo.
Se ejecuta comparación ROI a 960 con cobertura explícita de todos los píxeles fuera de las propuestas vegetales mediante recortes completos adicionales. Esta variante no puede ahorrar todo el procesamiento de fondo: la heurística de color no certifica ausencia de capachos secos. Pasó una prueba sin GPU que verifica cobertura incluso fuera de una ROI incorrectamente pequeña. La cola prepara después LOD conservando capachos, encuadre cerrado, límites físicos y marcadores agrupados. No se ejecuta todavía inferencia en el escenario reservado; falta congelar selección y completar vuelos.

## Congelación para evaluación reservada
La variante ROI con cobertura completa obtuvo 178/388 localizaciones y precisión 45,41 % sin filtrado; con ocho observaciones, 31/388 y 100 %. No superó los 38/388 y 97,44 % del recorte completo de 960 sujeto a precisión mínima 90 %. Se congeló native960_support_8 antes de capturar el reservado; pesos, código, configuración y métricas de selección quedan registrados en winner_selection.json.
La cola ejecuta diez segundos técnicos, validación, recorrido completo, validación de sincronización y encuadre, exportación pública RGB/calibración, auditoría anatómica independiente, baseline y variante congelada sobre las mismas capturas. Mantiene una reserva de 1,5 h para cierre. La revisión específica del recorrido con vistas oblicuas no se completó: se conserva el recorrido lateral exterior seguro. Esta desviación y el objetivo no alcanzado en desarrollo se reportan explícitamente, sin afirmar que el plan completo ya esté satisfecho. Ningún resultado reservado permitirá ajustar la variante.
