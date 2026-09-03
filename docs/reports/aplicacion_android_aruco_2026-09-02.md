# Aplicación Android con ArUco: entrega y verificación

Fecha local: 2026-09-02. Versión de aplicación: **0.1.0**.

Se implementó la aplicación Android local de detección de capachos, selección
de ArUco, coordenadas aproximadas en su plano y captura JPEG + JSON. Se generó
e instaló el APK en un emulador oficial Android 10 x86_64. El teléfono físico
de referencia y las pruebas de precisión en cultivo permanecen pendientes.

## Entregables

- APK de pruebas: `outputs/mobile/apk/uchuva-aruco-debug.apk` (140.4 MB decimales).
- Marcador A4: `outputs/mobile/marker/imprimir_aruco.html` y
  `outputs/mobile/marker/aruco_4x4_50_id0_100mm.svg`.
- Código Android: `mobile/android/`; instrucciones completas en
  [la guía de aplicación móvil](../guides/aplicacion_movil_aruco.md).
- Evidencia visual de cámara emulada en vertical y horizontal:
  `outputs/mobile/emulator/portrait.png` y `landscape.png`.

SHA-256 del APK entregado:
`0296a367c6f86367b277c3192a24fbaf20fe49712676744706ea4191fdd10afd`.

SHA-256 del modelo ONNX incorporado:
`19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca`.

## Resultados

| Comprobación | Resultado |
|---|---|
| Compilación APK y APK de pruebas | Correcta |
| Pruebas JVM de geometría, referencias y JSON | 11/11 aprobadas |
| Pruebas instrumentadas en Android 10 | 3/3 aprobadas |
| Pruebas del grafo de contexto | 3/3 aprobadas |
| Validador del grafo de contexto | Correcto |
| Lint Android | 0 errores; advertencias de estilo/localización y versiones fijadas |
| Instalación y apertura del APK entregado | Correctas en emulador |
| Firma APK v2 | Verificada con `apksigner` |
| Alineación ZIP del APK | Verificada con `zipalign` |
| Permiso de internet en APK | Ausente |
| Decodificación del marcador imprimible | ID 0, `DICT_4X4_50` |

Las pruebas instrumentadas verificaron recepción de fotogramas CameraX,
limpieza de resultados al pasar a segundo plano, reanudación y recreación;
la detección ArUco y el guardado consistente con hash del JPEG; y la detección
de un capacho real pasando por el preprocesamiento y ONNX Runtime de Android.
Se comprobó visualmente la interfaz después de girar el emulador.

La equivalencia PyTorch → ONNX se evaluó sobre 20 imágenes del directorio real
`val`, seleccionadas por orden de nombre, con 56 detecciones a umbral 0.25.
El IoU mínimo de las cajas emparejadas fue **0.9999991435** y la diferencia
máxima de confianza **0.000002116**, con igual cantidad y clase por imagen.
El tiempo ONNX CPU medio fue **37.0 ms en el computador**, sin incluir todo
el recorrido de cámara. No representa rendimiento de un teléfono.
La evidencia por imagen está en `outputs/mobile/model/validation_report.json`.

Durante la validación se corrigieron dos fallos observados: duplicación del
modelo en heap Java al cargarlo y enlace prematuro de CameraX durante `onStart`.
La versión entregada usa carga por flujo, un búfer directo reutilizable y
enlace al ciclo de vida después de alcanzar el estado STARTED.

## Límites de la evidencia

No se midieron error físico en centímetros, detección en cultivo con el
teléfono, autonomía, calentamiento ni cinco análisis por segundo sostenidos
en hardware móvil. El protocolo de campo está en la guía. Las coordenadas
siguen siendo `estimated`: proyección del centro de caja al plano ArUco,
sin profundidad ni corrección de distorsión de lente. No hubo reentrenamiento
ni uso del conjunto real de test para seleccionar o ajustar esta aplicación.

## Revisión para publicación — 2026-09-03

Se preparó para Git el código Android, sus pruebas, scripts de soporte y
documentación. Los entregables bajo `outputs/mobile/` son archivos locales:
esta publicación no distribuye APK, pesos, imágenes de validación, herramientas
Android ni claves de firma. La guía detalla los requisitos de un clon nuevo.
El detector sigue siendo el híbrido previo `natural_hybrid_alpha_045`, no una
receta promovida de Classical Augmentation v2.

Se repitió la compilación de ambos APK y el análisis lint en modo `--offline`,
usando únicamente dependencias ya instaladas. Resultado: compilación correcta,
lint sin errores y con 28 advertencias pendientes. También se verificaron el
grafo de contexto (128 nodos y 236 aristas), sus tres pruebas y los SHA-256 del
APK de entrega y del ONNX, que coinciden con los registrados arriba.

Se forzó además la ejecución de las pruebas JVM con `--rerun-tasks`:
11/11 aprobadas. El sandbox impidió crear un archivo temporal del daemon de
Kotlin fuera del proyecto; Gradle utilizó su alternativa automática de
compilación sin ese daemon y terminó correctamente (25 tareas ejecutadas).

Las tres pruebas instrumentadas y la equivalencia sobre 20 imágenes corresponden
a la evidencia del 2 de septiembre; no se repitieron en esta revisión. No se
reexportó el detector, no se reentrenó y no se consultó `test`. Continúa pendiente
la validación física en teléfono y cultivo.
