# Localización retrospectiva de uchuvas en una hilera simulada con cultivo de fondo

## Resumen

Se evaluó una hilera de seis plantas con doce plantas de contexto en Gazebo. La variante offline localizó correctamente 62 de 388 capachos objetivo distintos observables: recall 15.98 %, precisión conjunta 32.98 % y precisión de asociación 48.94 %. Se contabilizaron 0 intrusiones del fondo. Estos resultados describen simulación retrospectiva; no prueban transferencia al cultivo real.

## Diseño experimental

Las tres hileras comparten el modelo morfológico de uchuva, materiales y tutorado diagonal. La hilera objetivo reutiliza seis morfologías anteriormente inspeccionadas; las doce plantas de fondo tienen semillas distintas y reproducibles. Sus roles y los códigos ArUco se declaran explícitamente. El fondo no recibe métricas individuales ni aumenta el denominador objetivo. La separación de hileras es una elección de ingeniería verificada mediante obstáculos individuales, no una distancia agronómica validada.

Se conservaron el modelo congelado del ciclo 4 y las clases pintona —incluye verdes—, madura y sobremadura por apariencia del capacho. La clasificación no certifica la madurez del fruto oculto. No hubo entrenamiento adicional. La configuración se congeló antes de la comparación reportada; fecha: 2026-10-09T12:09:02.962351-05:00.

## Captura y recorrido

Se capturaron 7972 pares RGB/máscara originales a 1280 × 720, con sensores a 30 Hz y timestamps del simulador. El recorrido pasó por ambas caras, con giro hacia el arbusto terminal. Se alcanzaron 51/51 puntos y una separación mínima de 0.360 m. El error máximo de orientación durante el giro fue 3.68°. Hubo 846 cuadros del giro sin ArUco objetivo decodificable; esta invisibilidad no se equipara automáticamente a mirar fuera de la hilera.

Los vídeos finales contienen cada PNG original una sola vez y fueron decodificados íntegramente. No se analizaron imágenes interpoladas ni fotogramas del vídeo comprimido. La simulación puede avanzar más lentamente que el tiempo real.

## Percepción, identidad y posición

La red procesa todos los fotogramas en recortes nativos de 960 píxeles con 20 % de solapamiento y cobertura completa. Las máscaras se conservan sin pérdida mediante bits comprimidos. La caché registra propuestas desde confianza 0,001, procedencia de recorte y supresión entre recortes. La ausencia de una propuesta no permite atribuir una causa interna específica a la red o a su NMS.

Las tres variantes reutilizan esa caché: muestreo a 1 Hz con seguimiento histórico, seguimiento histórico por fotograma y seguimiento por máscaras con conciliación offline. Se conserva una puerta geométrica común para separar frecuencia de observación y conciliación; no se presenta el primero como reproducción numérica idéntica de todos los ajustes del piloto anterior. El flujo óptico con comprobación inversa, la forma y la apariencia proponen continuidad sin usar la clase como barrera. Las fusiones offline exigen evidencia geométrica, prohíben coexistencia temporal de identidades distintas y recalculan conjuntamente la posición.

Las poses ArUco se estiman desde RGB y calibración pública con IPPE y consistencia temporal. Las caras se unen mediante la transformación pública del soporte rígido. Se requieren ocho apoyos espaciados al menos 0,2 s, paralaje de 3°, reproyección máxima de 3 píxeles y sensibilidad de 3 cm; se ajustan hasta treinta vistas y se comprueba el resto. La sensibilidad leave-one-out no es un intervalo de confianza calibrado. La posición aproxima el centro del capacho mediante centroides visibles; no localiza el fruto interno.

## Métricas y resultados

El emparejamiento usa máscaras uno a uno. Una localización correcta exige identidad respaldada por al menos tres coincidencias y 80 % de todo el soporte geométrico, ArUco correcto, error máximo de 5 cm y ausencia de duplicación. Los 2 capachos objetivo completamente ocultos se informan aparte. Todos los tamaños visibles permanecen en el denominador, incluso un solo píxel. Los rechazos y trayectorias fragmentadas no se suman como objetos biológicos independientes.

| Protocolo | Correctos / visibles | Recall 3D | Precisión conjunta | Intrusiones | Duplicados |
|---|---:|---:|---:|---:|---:|
| historical_1hz | 22/388 | 5.67 % | 61.11 % | 0 | 3 |
| historical_every_frame | 73/388 | 18.81 % | 36.50 % | 0 | 78 |
| offline_every_frame | 62/388 | 15.98 % | 32.98 % | 0 | 15 |

| Protocolo | Precisión 2D | Recall 2D | AP máscara 50–95 | AP clases colapsadas |
|---|---:|---:|---:|---:|
| historical_1hz | 37.55 % | 16.64 % | 0.0358 | 0.0610 |
| historical_every_frame | 37.33 % | 16.58 % | 0.0358 | 0.0603 |
| offline_every_frame | 37.33 % | 16.58 % | 0.0358 | 0.0603 |

El error 3D mediano fue 2.52 cm y el P95 25.35 cm entre identidades respaldadas con ArUco correcto, incluyendo errores superiores a 5 cm. Estas estadísticas no representan los objetos perdidos. Se registraron 149754 cambios de identidad y 374 objetos objetivo con trayectorias fragmentadas. Las matrices de confusión, estratos de tamaño y disponibilidad de vistas, centroides e interrupciones se conservan en los JSON de evaluación.

![Comparación de localización](../../outputs/continuous_row_20261008/presentation/comparacion_3d.png)

![Mapa por ArUco](../../outputs/continuous_row_20261008/presentation/mapa_3d.png)

## Diagnóstico de pérdidas y análisis privilegiado

El catálogo contiene 326 capachos objetivo no localizados correctamente. Frecuencia de motivos registrados —pueden coexistir—: apoyos temporalmente separados insuficientes: 260; soporte geométrico insuficiente: 87; sin pose del marcador objetivo: 76; reproyección incompatible: 64; localización incorrecta o duplicada: 58; otras vistas inconsistentes: 54; sin geometría consistente de tres vistas: 50; triangulación inestable: 5; confianza inferior al umbral: 3; supresión entre recortes: 3; delimitación deficiente: 2. Cada entrada enlaza un timestamp y la mejor propuesta observada, cuando existe. Fragmentación, tamaño y visibilidad se interpretan como factores asociados salvo evidencia que sustente una causa. Se conserva causa no determinada cuando corresponde.

Los análisis privilegiados sustituyen poses, correspondencias o centroides por información verdadera del simulador, manteniéndose fuera del estimador. Comparan trayectorias originales con pose verdadera, correspondencias anatómicas con centroides predichos, centroides visibles verdaderos y centros geométricos proyectados. Sus cifras no son desempeño desplegable. El desfase máximo entre pose de diagnóstico y timestamp fue 0,035 s. La distancia mediana entre centroide visible verdadero y centro geométrico proyectado fue 1,897 píxeles. Los resultados completos y las limitaciones están en `privileged_diagnostics.json`.

| Análisis privilegiado | Objetos a ≤5 cm | Mediana (cm) | P95 (cm) |
|---|---:|---:|---:|
| Pose verdadera, trayectorias originales | 145 | 1.34 | 8.49 |
| Pose e identidad verdaderas, centroide predicho | 174 | 0.39 | 1.53 |
| Pose e identidad verdaderas, centroide visible verdadero | 65 | 0.37 | 0.77 |
| Pose y centro geométrico verdaderos | 388 | 0.00 | 0.00 |

Estos análisis tienen soportes y criterios de selección distintos; no deben restarse como efectos causales independientes. El caso de centros geométricos es una comprobación ideal de coordenadas, no una detección desplegable.

## Coste computacional y reproducibilidad

La inferencia acumulada por fotograma duró 81827.2 s. Seguimiento y geometría por protocolo: historical_1hz: 284.7; historical_every_frame: 4557.3; offline_every_frame: 20607.5 segundos. El tiempo de evaluación privilegiada y de presentación se separa del coste de inferencia. Se priorizó procesamiento posterior; no se afirma ejecución en línea a 5 Hz.

Pesos SHA-256: 01b83330dac418df640c9bad85cf200350269a603745a1f9b56726a72b87402b. Versiones: OpenCV 5.0.0; Ultralytics 8.4.114. Las fuentes, calibración, semillas, misiones, auditorías y configuración congelada acompañan la campaña. La contabilidad excluye esperas inactivas y suspensión; el usuario retiró el antiguo límite de horas.

## Interpretación

La conciliación offline redujo los duplicados de 78 a 15 frente al seguimiento histórico por fotograma, pero redujo las localizaciones correctas de 73 a 62 y la precisión conjunta de 36,50 % a 32,98 %. No alcanzó el objetivo de localizar más de la mitad de los capachos observables con precisión de asociación de al menos 90 %. La fragmentación y la falta de apoyos espaciados son factores registrados; los experimentos privilegiados sugieren limitaciones de pose e identidad, sin demostrar una causa única.

Durante la estabilización inicial se registraron incumplimientos del margen de encuadre, conservados en las auditorías. La revisión del criterio de estación excluyó únicamente la espera inicial predeclarada de siete segundos; no se eliminaron sus capturas. El MP4 dura 265.73 s a frecuencia constante frente a 263.04 s entre timestamps originales; no se duplicaron ni interpolaron imágenes.

## Limitaciones

Una única hilera objetivo reutilizada no estima generalización a nuevas parcelas. El cultivo es estático y no reproduce toda la fotometría, viento ni dinámica de contacto real. Las superficies foliares toleradas por la auditoría no equivalen a una tasa de oclusión. Los umbrales geométricos son decisiones de ingeniería. La conciliación puede conservar duplicados o hipótesis provisionales; confirmar una hipótesis algorítmica no garantiza identidad verdadera. La pose monocular de marcadores pequeños, ocluidos o de canto puede ser ambigua. La evidencia privilegiada permite estudiar mecanismos de error, pero no convierte el ensayo en una evaluación de campo.

## Referencias

1. Bruce D. Lucas y Takeo Kanade. An Iterative Image Registration Technique with an Application to Stereo Vision. https://publications.ri.cmu.edu/an-iterative-image-registration-technique-with-an-application-to-stereo-vision-ijcai

2. OpenCV. Perspective-n-Point (PnP) pose computation. https://docs.opencv.org/4.13.0/d5/d1f/calib3d_solvePnP.html

3. OpenCV. Detection of ArUco Markers. https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html

4. Ultralytics. utils.metrics API Reference. https://docs.ultralytics.com/reference/utils/metrics

## Revisión computacional durante el estudio

Por solicitud del usuario se cambió a flujo óptico LK piramidal por lotes en CUDA. Se conservaron 4569 fotogramas con sus detecciones, identidades y poses previas; se reconstruyó el movimiento reciente para continuar sin reasignar ese prefijo. Los primeros 173 fotogramas usan flujo OpenCV y los posteriores CUDA; el prefijo recuperado incluye ambos. No es una ejecución homogénea desde cero. Las implementaciones no son idénticas numéricamente. Las validaciones locales están en cuda_flow_validation.json y cuda_tracking_smoke.json y no garantizan equivalencia en todo el recorrido. Los rechazos internos de seguimiento del prefijo no estaban persistidos y permanecen no disponibles. Los tiempos de la continuación no incluyen todo el trabajo de intentos anteriores, preservado en execution_jobs. Las congelaciones originales y las revisiones explícitas se conservan; no se presenta esta revisión retrospectiva como comparación preregistrada.
