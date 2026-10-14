# Cierre del piloto 3D de uchuvas — 5 de octubre de 2026

**El objetivo no se alcanzó.** La variante congelada localizó correctamente 37 de 388 capachos observables, con precisión conjunta de 80.43 %. Se exigían más del 50 % y al menos 90 %, respectivamente. Son resultados de Gazebo; no demuestran transferencia al cultivo real.

| Variante | Correctos / visibles | Recall 3D | Precisión conjunta | Duplicados | ArUco incorrecto | Error mediano (cm) | P95 (cm) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 0/388 | 0.00 % | 0.00 % | 0 | 0 | 23.88 | 58.15 |
| Variante congelada | 37/388 | 9.54 % | 80.43 % | 1 | 0 | 0.89 | 25.78 |

La precisión conjunta exige identidad respaldada, marcador correcto, error ≤5 cm y ausencia de duplicación. Los errores mediano/P95 incluyen identidades respaldadas del marcador correcto aunque excedan 5 cm; no describen los objetos perdidos. El denominador conserva todos los tamaños y capturas de tránsito. Hubo 2 capachos totalmente ocultos, informados aparte. La posición estima el centro del capacho a partir del centroide de su silueta visible, no el fruto interior.

## Separación y selección

Las seis semillas 520300–520305 se reservaron antes de generar imágenes. Se conservaron todas, corrigiendo geometría sin selección por desempeño. Pasó la auditoría independiente de correspondencias panópticas y anatómicas. El estimador recibe RGB, tiempos y calibración pública, incluido el soporte rígido de marcadores opuestos; no recibe máscaras, anatomía ni odometría. La selección quedó congelada antes del vuelo reservado y no se ajustó posteriormente.

En desarrollo, 960 píxeles y ocho observaciones alcanzaron 38/388 y 97,44 % de precisión. El reservado muestra una caída a 80.43 %. Se preservan regresiones del muestreo adaptativo y de ROI. No se entrenó otro modelo porque detectar más no resolvió la continuidad de identidad ni la geometría.

## Vuelo, pérdidas y tiempos

El vuelo completó 17/17 puntos, con separación mínima 0.360 m. Pasaron las verificaciones de sincronización, ArUco RGB y encuadre: aprobadas. El modelo detectó al menos una vez 361 objetos distintos; detectar no equivale a localizarlos.

Fallos entre hipótesis confirmadas: {'error 3D mayor de 5 cm': 5, 'identidad insuficiente o mezclada': 3, 'duplicado': 1}. El diagnóstico JSON conserva rechazos por falta de observaciones, paralaje y consistencia; son trayectorias, no conteos independientes de capachos. No se dispone de una descomposición causal completa por objeto.

El estimador bruto tardó 503.8 s. El P95 por fotograma segmentado fue 2.704 s, por encima de 200 ms; además falta sumar conciliación global. No se propone ejecución en línea. Los tiempos separados de captura, auditoría, estimación y conciliación están en diagnostico.json. El video es una presentación de muestras a 1 Hz y no representa rendimiento en tiempo real.

## Entregables y pendientes

- Mapa: [C:\dev\SyntheticPlantGeneration\outputs\localization_pilot_20261005\presentation\mapa_conciliado.json](C:/dev/SyntheticPlantGeneration/outputs/localization_pilot_20261005/presentation/mapa_conciliado.json). Confirmado significa aceptado por el algoritmo; los candidatos ambiguos permanecen provisionales.
- Video: [C:\dev\SyntheticPlantGeneration\outputs\localization_pilot_20261005\presentation\localizacion_reservada.mp4](C:/dev/SyntheticPlantGeneration/outputs/localization_pilot_20261005/presentation/localizacion_reservada.mp4). Segmentaciones repetidas con pesos congelados y correspondencias con observaciones guardadas; no se usan para nuevas métricas.
- Gráfico: [C:\dev\SyntheticPlantGeneration\outputs\localization_pilot_20261005\presentation\mapa_3d.png](C:/dev/SyntheticPlantGeneration/outputs/localization_pilot_20261005/presentation/mapa_3d.png).

No se completó la revisión específica del recorrido con vistas oblicuas; se mantuvo la pasada lateral exterior segura. Tampoco se cuantificó por separado el sesgo de silueta por oclusión ; las pruebas finales sí cubren interrupciones breves, competencia ambigua en cruces y reproducción con archivos privados bloqueados, pero no constituyen una auditoría adversaria completa. Los aumentos de apariencia y entrenamientos adicionales no formaban el foco de esta fase. No se presenta este cierre como cumplimiento de todos los pasos del plan ni como éxito de localización.

La campaña conserva su presupuesto independiente de doce horas efectivas, excluyendo suspensión e inactividad. El saldo al generar este informe era 6.20 h; el consumo definitivo se registra al cerrar. No se empleará el reservado para seguir ajustando.

## Verificación y saldo de cierre
Se verificaron los 250 fotogramas del video y se revisaron ejemplos visuales. Pasaron 26 pruebas unitarias focalizadas. El estimador reprodujo exactamente el mapa congelado usando detecciones RGB guardadas, con acceso denegado a directorios de máscaras, anatomía, mallas y vuelo: cero intentos de lectura privada. Se verificaron también separación de semillas, esquema público, tiempos únicos y las tres clases.

Consumo registrado: **5.89 horas efectivas**; saldo no consumido: **6.11 horas**. No se agotó el presupuesto. Se cierra esta evaluación congelada con resultado negativo y pasos pendientes, sin ajustar después de examinar el reservado. No quedan trabajos propios activos.

Se reconciliaron 3.63 h de diferencia entre reloj UTC y reloj activo de Windows durante la verificación final. Se conserva el registro anterior y la evidencia del trabajo cubierto; ese intervalo no se carga al presupuesto. El heartbeat se eliminó al cerrar.
