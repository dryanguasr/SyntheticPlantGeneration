# Informe final — campaña mediana de aumento clásico

Fecha de cierre: 2026-08-21  
Diseño: 5 semillas × 3 escenarios, 50 épocas por corrida, orden contrabalanceado.  
Protocolo: YOLO11n, 640 px, batch 8, AdamW, AMP desactivado.  
Selección: máximo mAP50-95 de validación dentro de cada corrida.

## Conclusión ejecutiva

E0, entrenado sólo con datos naturales, es el ganador de esta campaña. Obtuvo el
mayor mAP50-95 en las cinco semillas frente a E1 y también en las cinco frente a
E2. El aumento fuerte E1 debe descartarse en su forma actual. El aumento suave E2
es menos perjudicial, pero tampoco justifica su coste: duplica el conjunto de
entrenamiento y reduce en promedio 0,0169 puntos el mAP50-95 frente a E0.

## Métricas agregadas de validación

Los valores son media ± desviación estándar entre cinco semillas.

| Escenario | Precisión | Recall | mAP50 | mAP50-95 | Época óptima mediana |
|---|---:|---:|---:|---:|---:|
| E0 natural | **0,861 ± 0,020** | **0,791 ± 0,019** | **0,870 ± 0,016** | **0,611 ± 0,012** | 14 |
| E1 aumento fuerte | 0,837 ± 0,013 | 0,772 ± 0,029 | 0,835 ± 0,016 | 0,586 ± 0,009 | 30 |
| E2 aumento suave | 0,825 ± 0,032 | 0,781 ± 0,021 | 0,856 ± 0,017 | 0,594 ± 0,007 | 12 |

## Resultado emparejado por semilla

| Semilla | E0 mAP50-95 | E1 mAP50-95 | Δ E1−E0 | E2 mAP50-95 | Δ E2−E0 |
|---:|---:|---:|---:|---:|---:|
| 1 | 0,6024 | 0,5871 | -0,0153 | 0,5997 | -0,0027 |
| 2 | 0,5966 | 0,5827 | -0,0139 | 0,5838 | -0,0128 |
| 3 | 0,6150 | 0,5722 | -0,0429 | 0,5921 | -0,0229 |
| 4 | 0,6147 | 0,5910 | -0,0237 | 0,5936 | -0,0211 |
| 5 | 0,6267 | 0,5950 | -0,0317 | 0,6018 | -0,0249 |
| **Media** | **0,6111** | **0,5856** | **-0,0255** | **0,5942** | **-0,0169** |

Intervalos de confianza t emparejados del 95 % para la diferencia en mAP50-95:

- E1−E0: -0,0255; IC 95 % [-0,0405, -0,0105].
- E2−E0: -0,0169; IC 95 % [-0,0282, -0,0055].

Las diferencias tienen dirección consistente (E0 gana 5/5), pero cinco pares
siguen siendo una muestra pequeña. Una prueba exacta bilateral de signos sólo
puede alcanzar p=0,0625 con cinco victorias de cinco, por lo que estos intervalos
paramétricos deben interpretarse como evidencia piloto, no como confirmación
estadística definitiva.

## Coste temporal observado

Tiempo acumulado registrado por el entrenador. En E1/semilla 5 se sumaron los
segmentos anterior y posterior a la suspensión; el lapso suspendido no se contó.

| Escenario | Mediana por corrida | Media | Rango observado | Imágenes train |
|---|---:|---:|---:|---:|
| E0 | 17 min 10 s | 24 min 59 s | 14:33–43:56 | 1.062 |
| E1 | 49 min 42 s | 53 min 57 s | 32:03–85:03 | 2.124 |
| E2 | 34 min 30 s | 48 min 03 s | 27:59–80:40 | 2.124 |

- Tiempo efectivo acumulado de las 15 corridas: 10 h 34 min 53 s.
- Mediana de una tripleta completa: 1 h 55 min 54 s.
- Rango de tripleta por semilla: 1 h 14 min 34 s a 3 h 19 min 49 s.
- La variación temporal es alta y refleja estado térmico/energético y carga del
  portátil; para planificación conviene presupuestar unas 2 horas por tripleta.

E1 y E2 contienen el doble de imágenes y lotes por época que E0. La campaña fija
épocas, no presupuesto de cómputo ni número de actualizaciones, por lo que los
aumentos recibieron además más optimización total.

## Integridad y límites

- Las 15 corridas terminaron con 50 filas de métricas y checkpoints `best.pt` y
  `last.pt`.
- La semilla 5/E1 se reanudó correctamente desde `last.pt` después de la
  suspensión; las épocas previas permanecen en `results.csv`.
- El conjunto test no se reutilizó para las semillas 2–5. Estas conclusiones se
  basan en validación; el test de la semilla 1 ya había favorecido también a E0.
- E1/E2 son datasets precalculados sin receta, parámetros ni semillas de las
  transformaciones. Se puede medir su efecto, pero no atribuirlo causalmente a
  una intensidad específica de oclusión o iluminación.
- La campaña compara datasets con distinto tamaño. Falta una comparación
  igualada por número de imágenes o pasos para separar efecto de aumento y
  presupuesto de entrenamiento.

## Decisión recomendada

1. Mantener E0 como baseline y candidato principal.
2. Retirar E1 de la siguiente fase hasta rediseñar su receta.
3. No promover E2: fue peor en 5/5 semillas y cuesta aproximadamente el doble.
4. Si se desea rescatar el aumento clásico, crear una receta trazable y ejecutar
   una prueba pequeña igualada por pasos, empezando con intensidades menores que
   E2 y sin consultar nuevamente el test durante la selección.
