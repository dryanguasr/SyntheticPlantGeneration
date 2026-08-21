# Diagnóstico de la rama de aumento tradicional

Fecha: 2026-08-17  
Commit auditado: `29e69ca0e45615dbf0d0385ec66957d004de3493` (`main`)  
Equipo: NVIDIA GeForce RTX 4050 Laptop GPU (6 GB), Windows 11  
Entorno medido: Python 3.12.13, PyTorch 2.12.1+cu130, CUDA 13.0, Ultralytics 8.4.114

## Dictamen

El workstream es una base trazable y ejecutable después de corregir rutas, pero todavía no es una rama experimental plenamente reproducible. E0 puede reconstruirse desde los datos naturales. E1 y E2 sólo existen como datasets precalculados: no se entregaron receta, parámetros, semilla ni manifiesto por transformación. Tampoco hay resultados de las 90 corridas confirmatorias en el repositorio.

La integridad estructural de los tres datasets completos sí es buena: todas las imágenes decodifican, todas tienen label YOLO válido, no faltan pares y no se detectó fuga de identidad ni duplicados de contenido entre train/val/test.

## Tiempos medidos

Protocolo del benchmark: semilla 1, 640 px, batch 8, workers 4, AdamW, AMP desactivado, `rect=True`, una GPU. Sólo se corrigieron las rutas mediante una unión local con nombre ASCII.

| Condición | Imágenes train | Lotes/época | 1 época: pared | 5 épocas: pared | Tiempo interno de las 5 épocas |
|---|---:|---:|---:|---:|---:|
| E0 natural | 1.062 | 133 | 38,5 s | 101,1 s | 82,8 s |
| E1 fuerte | 2.124 | 266 | 58,3 s | 226,5 s | 199,4 s |
| E2 suave | 2.124 | 266 | 58,7 s | 288,6 s | 227,9 s |

Campaña de una época completa: 159,1 s.  
Campaña de cinco épocas completa: 621,1 s (10 min 21,1 s).

Tiempos internos por época en la campaña de cinco épocas:

- E0: 18,9; 15,7; 16,0; 15,9; 16,4 s.
- E1: 34,2; 37,8; 42,1; 43,6; 41,8 s.
- E2: 33,7; 40,2; 42,5; 40,9; 70,6 s.

La degradación de E2 demuestra que no es defendible usar sólo `n_imágenes × tiempo de la primera época`. Una lectura puntual durante la ralentización mostró GPU a 63 °C, 14 W y 11 % de utilización; eso apunta más a cuello de botella de entrada/CPU o administración de potencia que a saturación de VRAM o temperatura de GPU.

### Proyección a 50 épocas

Estas cifras son extrapolaciones, no corridas completas. Usando el promedio de las cinco épocas y, como límite conservador, el promedio de las tres últimas:

| Condición | Promedio de 5 épocas | Ritmo de las 3 últimas |
|---|---:|---:|
| E0 | 14,1 min | 13,7 min |
| E1 | 33,7 min | 35,9 min |
| E2 | 39,0 min | 43,8 min |
| Tripleta E0+E1+E2 | 86,8 min | 93,4 min |
| Estudio de 30 semillas | 43,4 h | 46,7 h |

Para conocer el tiempo total con precisión operativa todavía hace falta una tripleta completa de 50 épocas con telemetría; el intervalo anterior sirve para planificación.

## Integridad de datos

| Condición | Train/val/test | Objetos train/val/test | Duplicados internos | Fuga train-val-test |
|---|---|---|---:|---:|
| E0 | 1062/109/109 | 2882/312/311 | 0 | 0 |
| E1 | 2124/109/109 | 5764/312/311 | 0 | 0 |
| E2 | 2124/109/109 | 5764/312/311 | 0 | 0 |

- E1 y E2 conservan byte a byte las 1.062 imágenes naturales de train y añaden una derivada diferente por original.
- Validación y test son byte a byte idénticos en E0, E1 y E2, lo cual mantiene un banco de evaluación común.
- Los 1.062 labels derivados de E1 y los 1.062 de E2 son byte a byte iguales a su label base. Esto es coherente con transformaciones sólo fotométricas/oclusivas, pero no permite saber si una oclusión hizo invisible un objeto que sigue etiquetado.
- E1 y E2 no contienen imágenes aumentadas idénticas entre sí.
- No hay manifiestos de E1/E2 que registren transformación, parámetros, semilla o hash de origen.

## Auditoría de código y experimento

### Fortalezas

- El snapshot del lanzador coincide con el SHA-256 declarado.
- El peso inicial coincide con el SHA-256 congelado.
- Se validan conteos, pares imagen-label, clase, rango de cajas y dimensiones positivas antes de entrenar.
- Se parte del mismo peso en cada corrida; las aumentaciones geométricas/fotométricas comunes de Ultralytics se fijan en cero; `deterministic=True` y AMP está desactivado.
- Hay registro básico de entorno, estado, reanudación y checkpoints.
- Las siete pruebas unitarias relevantes ejecutadas pasaron.

### Hallazgos prioritarios

1. **Bloqueante científico — recetas ausentes.** E1/E2 no pueden regenerarse ni auditarse causalmente. Los nombres “strong” y “soft” no sustituyen parámetros medibles.
2. **Bloqueante de evidencia — resultados ausentes.** No hay `execution_state.csv`, métricas multisemilla ni pesos de las 90 corridas originales; no es posible auditar conclusiones, dispersión o significancia.
3. **Operabilidad local — layout inconsistente.** El lanzador busca `data/` dentro de la entrega de código, pero los datasets completos están en la carpeta hermana `*_clean_20260817`; la copia no limpia además está incompleta.
4. **Operabilidad Windows — ruta Unicode.** OpenCV 4.13 no pudo abrir imágenes desde la ruta con `Aumentación clásica`; el benchmark necesitó una unión con ruta ASCII.
5. **Confusión por orden.** Las 30 semillas usan siempre E0→E1→E2. El benchmark mostró deriva temporal fuerte; condición y posición de ejecución quedan confundidas. Debe usarse orden contrabalanceado o enfriamiento/telemetría.
6. **Entorno no congelado en la práctica.** La entrega exige Ultralytics 8.4.66 y recomienda Python 3.11; el entorno disponible usa Ultralytics 8.4.114 y Python 3.12.13. El reporte de entorno del lanzador tampoco guarda la versión de Ultralytics/OpenCV/YAML ni el commit Git.
7. **Observabilidad insuficiente.** `execution_state.csv` no registra duración, épocas efectivas, temperatura, potencia, utilización, VRAM ni motivo de terminación. La campaña tuvo que derivar tiempos desde timestamps y `results.csv`.
8. **Cobertura de pruebas superficial.** Las pruebas actuales verifican sólo metadatos del protocolo y layout; no cubren parser de semillas, validación de datos, reanudación, detección de corrida completa ni configuración efectiva de entrenamiento.
9. **Detalles sensibles a versión.** Los argumentos resueltos muestran `auto_augment=randaugment` y `erasing=0.4`, aunque para detección normalmente no son la ruta activa. Deben fijarse explícitamente o demostrarse inactivos. `rect=True` fuerza `shuffle=False`, advertencia que hoy no se registra como decisión experimental.
10. **Finalización débil.** Una corrida se considera completa sólo por número de filas en `results.csv`; no se verifica `best.pt`, integridad del checkpoint ni estado `complete`.

## Recomendación de salida

No lanzar todavía las 90 corridas. Primero: recuperar o formalizar las recetas E1/E2; generar manifiestos por imagen; normalizar rutas ASCII; fijar y registrar todo el entorno; añadir duración y telemetría; contrabalancear el orden; y ejecutar una tripleta completa de 50 épocas como benchmark de aceptación. Después sí puede presupuestarse el estudio confirmatorio alrededor de 44–47 horas en este portátil, sujeto a la tripleta completa.
