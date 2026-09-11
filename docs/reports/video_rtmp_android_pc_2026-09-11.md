# Validación de video RTMP y aplicación PC — 2026-09-11

## Entregables

- Android `0.3.0` (versionCode 5): selector cámara/RTMP, Media3 1.6.1, análisis
  local con el mismo detector y geometría, capturas públicas JPEG/JSON.
- Windows x64 `0.3.0`: receptor RTMP y lector de archivos, vista anotada, selección
  ArUco, medida en cm, umbral, guardado accesible y exportación MP4/JSONL.
- MediaMTX 1.21.0: servidor local de publicación/lectura, ruta `neo`, TCP 1935.
- JSON `1.4`: procedencia y reloj de recepción separados del reloj de cámara.
  No incluye claves RTMP. Sin medida confirmada, tamaño y posiciones son `null`.

Se reutiliza el ONNX original, hash
`19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca`.
No hubo reentrenamiento, segunda NMS ni cambio de clases.

## Evidencia ejecutada

| Prueba | Resultado | Alcance |
|---|---|---|
| JVM Android | 20/20 pasan | 18 de geometría/contratos y 2 de URL RTMP |
| Android lint + APK + APK de tests | Compilación correcta | SDK 35, mínimo Android 10, ARM64/x86_64 |
| `RtmpIntegrationTest` | 1/1 pasa, 6.872 s | RTMP local 640×480, dos ArUcos, captura MediaStore/hash/fotograma, pausa y recreación |
| Regresión instrumentada | 3/3 pasan, 11.184 s | Cámara, paridad de detector y ArUco/MediaStore en emulador API 29 |
| PC unitarias e integración Tk | 9/9 pasan | Signos, perspectiva, escala, rejilla, invalidación independiente, paridad, campos nulos, guardado y vista local |
| RTMP PC, emisor FFmpeg + MediaMTX | Pasa | Recepción continua durante 8 s, progreso de cuadros, dos ArUcos, hash de captura y desconexión |
| Exportación de archivo PC | Pasa | Seis cuadros de entrada, seis de MP4 y seis registros JSONL ordenados |
| Ejecutable Windows | Modelo cargado y ArUco detectado | Diagnóstico desde el paquete, sin usar el entorno de desarrollo para importar el modelo |
| Grafo de contexto | Válido | 134 nodos, 243 relaciones |

La muestra de paridad es el fixture real existente de **validación** `1064.jpg`,
preparado fuera de Git. La tolerancia PC fue 0.1 píxel por coordenada y 0.001 de
confianza. No se accedió al conjunto de test para ajustar estas aplicaciones.

El fixture RTMP muestra dos marcadores sintéticos y formas simples; prueba el
transporte, las referencias y el almacenamiento, no la detección de frutos en
vuelo. Una prueba separada usa una salida simulada del detector para verificar
que la misma caja recibe posiciones respecto a los dos marcadores, con signos
correctos y coordenadas nulas sin escala.

En la ejecución local registrada, un análisis PC tomó aproximadamente **37.34 ms**.
Es una medición de un cuadro de prueba, no una certificación de FPS sostenidos ni
de latencia extremo a extremo. Android limita la extracción de cuadros a un
máximo solicitado de cinco por segundo y descarta cuadros mientras analiza.

## Incidencias corregidas

- El tiempo inicial de apertura de OpenCV de 5 s interrumpía la negociación de
  algunos FLV y ocasionaba un falso corte posterior. Se aumentó a 15 s; lectura
  con límite de 5 s y dos hilos del decodificador. La prueba continua detectó el
  problema y pasó después de corregirlo.
- MediaMTX 1.21 habilitaba MoQ por defecto: se deshabilitó junto con los protocolos
  no usados. Solo RTMP forma parte de esta configuración.
- El empaquetado inicial bajo aislamiento no encontraba Tcl/Tk. Se reconstruyó
  con acceso a las bibliotecas gráficas y se ejecutó la prueba de interfaz.

## Límites pendientes de prueba física

### Comprobación previa a integración en main

El 11 de septiembre se volvió a comprobar el árbol completo antes de integrar
los avances, por solicitud del usuario:

- Suite del núcleo: 140 pruebas correctas en 64,718 s.
- PC: nueve pruebas correctas, incluida Tk y paridad. El primer intento aislado
  no pudo cargar Tcl/Tk; al permitir acceso a sus bibliotecas pasó en 0,995 s.
- Android: `build_android_app.ps1` finalizó correctamente (APK, APK de tests,
  lint y pruebas JVM); Gradle reutilizó las tareas vigentes. Los XML registran
  18 pruebas de geometría y dos de URL, sin errores. No se repitió instrumentación.
- RTMP local: dos marcadores, hash de captura, seis cuadros de exportación,
  continuidad y desconexión verificados de nuevo. No se conectó el dron.
- Grafo: 134 nodos y 243 relaciones; `git diff --check` sin errores.

Los logs de integración se conservan bajo
`outputs/audits/scientific_route_20260908/integration_20260911_*`; el último
fixture RTMP está en `outputs/desktop/rtmp-test/report.json`.

### Alcance físico

El usuario confirmó que DJI Fly muestra RTMP al operar su Neo de primera
generación solo con el celular. **No se conectó un Neo real durante estas pruebas**.
Faltan comprobar la ruta desde el teléfono conectado al Wi-Fi del Neo hasta el
PC, los permisos de red, el formato publicado, la continuidad durante un vuelo
y la latencia. Un receptor Android adicional necesita alcanzar el mismo servidor;
no se garantiza ejecutar DJI Fly y el receptor en primer plano en un solo móvil.

Tampoco se midió error físico, distorsión de lente, precisión a diferentes
profundidades ni rendimiento térmico en el teléfono. No se repitió una prueba
física en modo avión. La cámara y los archivos locales no necesitan red; RTMP
necesita conectividad al servidor aunque el análisis sea local.

La exportación de archivos produce MP4 con frecuencia nominal constante y sin
audio. No equivale a conservar el tiempo original de un video de frecuencia
variable. Las marcas temporales de recepción no son marcas de exposición del
dron. La rejilla no convierte la homografía en una medición tridimensional.

Los registros completos, paquetes, pesos y fixtures permanecen en `outputs/` y
fuera de Git. Las instrucciones están en
[Video del DJI Neo en Android y PC](../guides/video_dron_pc_rtmp.md).
