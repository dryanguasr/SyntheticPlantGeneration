# Aplicación Android de uchuva y ArUco

La app `Uchuva · ArUco` detecta **capachos**, clase `0 = calyx`, y muestra
su posición aproximada sobre el plano de un marcador. Funciona localmente,
sin permiso de internet, cuentas, servicios de nube ni un computador durante
el uso. Es un consumidor del detector entrenado, separado de la morfología,
Blender, aumentación y Gazebo.

## Qué incluye el repositorio

Se versionan el proyecto Android, las pruebas, el wrapper de Gradle, los scripts
de preparación/exportación y esta documentación. **El APK no se distribuye en
Git**: la ruta de instalación indicada abajo corresponde a un archivo generado
localmente. Tampoco se incluyen el checkpoint, ONNX, manifiesto generado del
modelo, imágenes de validación, capturas, SDK/JDK, cachés ni claves de firma.

Para compilar desde un clon nuevo se necesita, además del código:

1. Python 3.11 o posterior y un entorno de entrenamiento compatible con las
   versiones registradas más abajo; `.venv-training/` no viene en el clon.
2. Acceso autorizado al checkpoint híbrido indicado en la sección de
   compilación y a las imágenes originales de `val`. Se pueden indicar otras
   rutas mediante `--checkpoint` y `--validation-dir`, respetando el mismo
   contrato de modelo y sin usar `test`.
3. Preparar herramientas, dependencias y assets con los comandos documentados.
   Las dependencias de Android ya están declaradas en Gradle; no se añaden al
   entorno Python del generador morfológico.

El detector predeterminado es `natural_hybrid_alpha_045`, procedente del
[experimento híbrido previo](../reports/resultado_dataset_hibrido_2026-08-01.md).
**No es un ganador de Classical Augmentation v2**, cuya confirmación terminó
sin recetas promovidas. Esta app no altera aquella decisión ni su lock.
La validación en emulador no sustituye las pruebas físicas pendientes.

## Instalar y usar

Requisitos: Android 10 o superior, cámara trasera y arquitectura ARM64.
El APK también incluye x86_64 para pruebas de emulador. El dispositivo de
referencia todavía no se ha seleccionado.

1. Copiar `outputs/mobile/apk/uchuva-aruco-debug.apk` al teléfono y abrirlo.
   Permitir la instalación desde la aplicación usada para abrir ese archivo.
   Es un APK de pruebas firmado con una clave local de depuración.
2. Abrir la app y conceder permiso de cámara. Si se deniega permanentemente,
   el botón **Permitir cámara** abre los ajustes de Android.
3. Imprimir `outputs/mobile/marker/imprimir_aruco.html` en A4, al 100 %, sin
   ajustar a página. También se entrega `aruco_4x4_50_id0_100mm.svg`.
4. Medir el lado exterior del cuadrado negro, **sin el margen blanco**.
   El diseño nominal mide 10 cm. Registrar la medida real en **Ajustes** y
   marcar **Medí y confirmé el lado impreso**. Hasta confirmarlo, la detección
   funciona pero las coordenadas permanecen no disponibles.
5. Montar el marcador sobre una superficie plana y rígida. Mantenerlo visible,
   preferiblemente a una profundidad parecida a los capachos de interés.
6. Un único marcador se selecciona automáticamente. Cuando aparecen varios,
   tocar el elegido. El identificador permanece seleccionado incluso cuando
   sale de escena; tocar otro permite cambiarlo. Todos los marcadores usados
   en una sesión deben tener el mismo lado configurado y pertenecer a `DICT_4X4_50`.
7. Pulsar **Capturar** para guardar la imagen anotada y su JSON. La app ofrece
   compartir ambos archivos. **Guardadas** permite compartir capturas anteriores.

Las capturas quedan en el almacenamiento privado de la aplicación, bajo
`files/captures/`. Persisten entre aperturas; se eliminan al desinstalar la app.
Compartirlas permite conservarlas fuera de ese almacenamiento. No se solicitan
permisos generales de archivos ni se inicia una transmisión automática.

## Interpretar las medidas

La posición corresponde al **centro de la caja de detección**, no al centro
anatómico del fruto. El origen está en el centro del marcador; X apunta a su
derecha y Y hacia arriba según la orientación decodificada. La distancia `d`
es `sqrt(X² + Y²)` dentro del plano y se expresa en centímetros.

Se calcula una homografía de las cuatro esquinas del ArUco a un cuadrado
métrico. En cultivo, los capachos a otras profundidades introducen error:
**la app no mide profundidad ni distancia 3D**. Tampoco corrige distorsión de
lente. La etiqueta permanente es «Estimación sobre el plano del ArUco».
No interpretar las cifras como precisión centimétrica garantizada.

El estado **Sin detecciones** describe el resultado del modelo, no demuestra
ausencia física de uchuvas. Si desaparece el marcador elegido, se conservan
las detecciones pero se eliminan las coordenadas. IDs duplicados, cuadriláteros
degenerados, marcadores pequeños y proyecciones que cruzan el horizonte del
plano invalidan las medidas. Los límites de tamaño y geometría son
`engineering_heuristic`, no límites botánicos ni garantías metrológicas.

El umbral de confianza inicial es 0.25, editable entre 0.05 y 0.95. Una
confianza del detector no es una incertidumbre de posición en centímetros.

## Arquitectura e interfaces

El proyecto independiente está en `mobile/android/`. La actividad controla
permisos y ciclo de vida; `VisionEngine` contiene OpenCV y ONNX Runtime;
`Geometry` contiene funciones sin Android; `ReferenceResolver` gestiona el
marcador elegido y `CaptureStore` conserva el par imagen/JSON.

CameraX entrega imágenes RGBA con `KEEP_ONLY_LATEST` a un ejecutor serial.
Cada imagen se recorta según `cropRect` y se gira según `rotationDegrees`.
La misma imagen verticalizada alimenta ArUco y el detector. `AnalysisView`
muestra **el fotograma analizado**, con ajuste proporcional y bandas; no
superpone resultados atrasados sobre otra imagen de cámara. La vista se
actualiza al ritmo del análisis. Sus transformaciones inversas resuelven
los toques sobre marcadores en vertical y horizontal.

Los cambios de configuración y ciclo de vida invalidan resultados en vuelo.
Un resultado sin actualización durante 1.5 segundos se retira. La captura
mantiene una referencia al fotograma y a su resultado inmutable: la inferencia
siguiente no altera lo que se guarda. Un directorio temporal pasa a definitivo
solo cuando se escribieron ambos archivos; el JSON registra el SHA-256 del JPEG.

Contratos internos:

- `Detection`: caja XYXY en píxeles verticalizados, confianza y clase.
- `MarkerObservation`: ID y cuatro esquinas TL/TR/BR/BL según la orientación
  decodificada del marcador, no ordenadas de nuevo por coordenada de pantalla.
- `FrameAnalysis`: identidad y tamaño de imagen, configuración, observaciones,
  referencia, posiciones opcionales y tiempo de análisis.

`analysis.json` usa `schema_version = "1.0"`. Incluye versión de app y modelo,
hash del modelo, fecha UTC de recepción, timestamp monotónico de cámara,
rotación aplicada, dimensiones, umbral, marcadores, referencia, detecciones y
tiempo. `position_cm` es `null` si no hay medida válida. El bloque `estimation`
registra `status = estimated`, `object_depth_measured = false` y
`lens_distortion_corrected = false`. No se generan identificadores de seguimiento
persistente de frutos entre cuadros.

## Compilación reproducible en Windows

Desde la raíz del repositorio, con el entorno de entrenamiento existente:

```powershell
& .venv-training/Scripts/python.exe scripts/setup_android_toolchain.py --accept-sdk-licenses
& .venv-training/Scripts/python.exe -m pip install --target outputs/mobile/python-deps --no-deps -r scripts/mobile_export_requirements.txt
& .venv-training/Scripts/python.exe scripts/export_mobile_detector.py
& .venv-training/Scripts/python.exe scripts/generate_mobile_marker.py
& scripts/build_android_app.ps1
```

La preparación descarga herramientas oficiales en `outputs/mobile/toolchain`,
verifica sus checksums y no modifica el registro ni PATH del sistema.
`--accept-sdk-licenses` acepta las licencias que presenta SDK Manager.
Las dependencias de exportación se instalan en un directorio separado, sin
actualizar el entorno de entrenamiento. En entornos con sandbox, la descarga
y el uso de bibliotecas recién instaladas pueden requerir ejecución autorizada
fuera del sandbox.

Versiones fijadas:

| Componente | Versión |
|---|---|
| JDK Amazon Corretto | 17.0.14.7.1 |
| Gradle / Android Gradle Plugin | 8.11.1 / 8.9.2 |
| Android SDK / Build Tools | 35 / 35.0.0 |
| Kotlin | 2.1.20 |
| CameraX | 1.4.2 |
| OpenCV Android | 4.11.0 |
| ONNX Runtime Android y Python | 1.22.0 |
| Exportador Ultralytics usado | 8.4.114 |
| ONNX Python / opset | 1.17.0 / 17 |

`export_mobile_detector.py` usa por defecto el checkpoint
`outputs/experiments/checkpoint_interpolation_scale80_seed_1000_v1/interpolated_checkpoints/natural_hybrid_alpha_045.pt`.
Comprueba clase y cabeza `end2end`, exporta FP32 con entrada `[1,3,640,640]`
y salida `[1,300,6]`. Las columnas son XYXY, confianza y clase; no se aplica
otra NMS. El preprocesamiento usa RGB, relleno 114, interpolación lineal y
división por 255. Las cajas vuelven a los píxeles de imagen deshaciendo el
relleno y la escala.

Se comparan 20 imágenes ordenadas por nombre de `Dataset Original/IMAGENES/val`.
Se exige igual cantidad de detecciones por encima de 0.25, misma clase,
IoU ≥ 0.99 y diferencia de confianza ≤ 0.001. El script rechaza un directorio
de test y no reentrena. Si falla, no prepara nuevos assets de la aplicación.
El manifiesto registra versiones, hashes y el contrato del modelo.

El APK incorpora `detector.onnx` y `model_manifest.json`, preparados en assets
pero ignorados por Git. La compilación y la app verifican su correspondencia
mediante SHA-256. Una clonación nueva requiere el checkpoint local y ejecutar
el exportador. Los APK, SDK, cachés, pesos, capturas y resultados permanecen
en rutas ignoradas. El código original conserva la licencia del repositorio;
las bibliotecas y pesos mantienen sus términos y atribuciones propios.

## Pruebas automatizadas y protocolo físico

En Android el modelo se copia por flujo a una caché privada verificada, y
el búfer de entrada se reutiliza fuera del heap Java para reducir las copias
y la presión de memoria.

`build_android_app.ps1` ejecuta compilación, lint y pruebas JVM. Compila además
el APK de pruebas instrumentadas, pero no afirma haberlo ejecutado en un teléfono.
`GeometryTest` cubre perspectiva, signos y unidades, giro del marcador,
restauración de cajas, toques, selección, pérdida y duplicación de IDs y JSON
con posiciones nulas. `VisionSmokeTest` está preparado para cargar las bibliotecas
nativas, detectar un marcador generado y comprobar una captura consistente.
`CameraLifecycleTest` comprueba recepción de imágenes de CameraX, retirada de
resultados al pasar a segundo plano, reanudación y recreación de la actividad.
`DetectorParityTest` comprueba el recorrido Bitmap → RGB/letterbox → ONNX →
cajas restauradas con una imagen real de validación y los mismos límites de
IoU/confianza del exportador. El exportador prepara ese PNG y su referencia
en assets de pruebas ignorados por Git; no se incluyen en el APK de usuario.

Para preparar y ejecutar esas pruebas en el emulador oficial Android 10,
sin una ventana visible, usar:

```powershell
& .venv-training/Scripts/python.exe scripts/setup_android_toolchain.py --with-emulator
& scripts/test_android_emulator.ps1
```

Se descarga una imagen x86_64 adicional y se usa el dispositivo virtual
`uchuva_api29`, con puerto 5580. El script detiene el emulador si lo inició
durante esa ejecución. `-StartOnly` permite dejarlo abierto para inspección;
para cerrarlo después: `adb -s emulator-5580 emu kill`.

Con un teléfono o emulador conectado y autorizado, ejecutar desde
`mobile/android`, con JAVA_HOME, ANDROID_HOME y GRADLE_USER_HOME configurados:

```powershell
& ../../outputs/mobile/toolchain/gradle-8.11.1/bin/gradle.bat connectedDebugAndroidTest
```

La validación física permanece **pendiente de dispositivo**. Registrar modelo
de teléfono, versión Android, hash del APK, cámara/resolución, temperatura y
condiciones de iluminación. Ejecutar:

1. Abrir con permiso denegado, concederlo después, rotar pantalla y alternar
   segundo plano diez veces; comprobar recuperación sin resultados antiguos.
2. Probar en modo avión escenas sin objetos, solo capachos, solo ArUco y ambos;
   introducir oclusión, dos IDs distintos y dos impresiones del mismo ID.
3. Retirar el marcador elegido mientras permanece otro; las medidas deben
   desaparecer y no cambiar de referencia automáticamente.
4. Guardar y compartir capturas; comprobar que cajas, número de cuadro y JSON
   corresponden a la imagen y que siguen disponibles después de reiniciar.
5. Medir diez puntos conocidos en un montaje plano con regla, desde vista
   frontal y oblicua. Separar error de homografía de error del centro de caja;
   registrar error absoluto por punto, mediana y máximo, sin atribuir precisión
   3D a capachos fuera del plano.
6. Mantener análisis durante diez minutos. Medir actualizaciones reales por
   segundo, latencia mediana/p95, memoria y calentamiento. El objetivo de cinco
   análisis/s es inicial y queda por medir. No confundir latencia ONNX de PC
   con rendimiento del teléfono.

Fuentes técnicas: [CameraX](https://developer.android.com/media/camera/camerax/analyze),
[homografía](https://docs.opencv.org/4.13.0/d9/dab/tutorial_homography.html),
[ArUco](https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html),
[ONNX Runtime móvil](https://onnxruntime.ai/docs/get-started/with-mobile.html) y
[exportación Ultralytics](https://docs.ultralytics.com/integrations/onnx/).
