# Aplicación Android multipunto ArUco: entrega y verificación

Fecha local: 2026-09-03. Versión de aplicación: **0.2.0**.

La aplicación ahora proyecta origen, ejes X/Y y cuadrícula para cada ArUco
detectado. Cada capacho incluye posiciones respecto a todos los marcadores
válidos del cuadro. La selección por toque solo controla el resaltado y los
campos compatibles del JSON.

Las capturas nuevas se publican mediante MediaStore: JPEG en
`Pictures/UchuvaArUco` y JSON en `Download/UchuvaArUco`. Ambos archivos usan
el mismo `capture_id` y nombre base. Las capturas privadas de la versión 0.1
pueden exportarse sin eliminar el original.

## Entregable

- APK de pruebas: `outputs/mobile/apk/uchuva-aruco-debug.apk`.
- Tamaño: 140 565 774 bytes.
- SHA-256: `cef72ac0e3810d56e878147a83f654e666cac5824cb6622ca8bb363afe273497`.
- Modelo ONNX sin cambios, SHA-256:
  `19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca`.

## Resultados

| Comprobación | Resultado |
|---|---|
| Compilación APK y APK de pruebas | Correcta |
| Pruebas JVM | 16/16 aprobadas |
| Pruebas instrumentadas Android 10 | 3/3 aprobadas |
| Lint Android | 0 errores, 29 advertencias |
| Validador del grafo | Correcto, 128 nodos y 236 aristas |
| Pruebas del grafo | 3/3 aprobadas |
| Firma APK | Esquema v2 verificado, un firmante de depuración |
| Alineación ZIP | Correcta |
| Permisos declarados | Solo cámara; sin internet ni almacenamiento general |

Las pruebas JVM verifican homografía directa e inversa, cuadrícula proyectada,
perspectiva, giro, signos, unidades, tarjetas dentro del fotograma, referencias
múltiples, IDs duplicados, pérdida de selección y esquema JSON 1.1 compatible.

La prueba nativa genera y detecta ArUcos ID 0 e ID 1, calcula dos posiciones
para la misma caja y guarda el fotograma anotado. Verifica la pareja pública,
`capture_id`, rutas, hash, estado `IS_PENDING = 0` y lectura desde MediaStore.
También fuerza un fallo después de escribir el JPEG pendiente y confirma que
no queda un archivo huérfano. Las otras pruebas cubren CameraX y ciclo de vida,
además de la equivalencia del detector Android sobre una imagen real de `val`.

El emulador 37.1.11 dejó de exponer cámara con la fuente `emulated`; el log de
CameraX informó cero dispositivos. El script se actualizó para usar
`virtualscene`, fuente sintética del emulador independiente de una webcam. Con
esa configuración la suite completa terminó correctamente.

## Límites pendientes

Continúan pendientes la instalación y medición en un teléfono físico, el error
en centímetros sobre un montaje real y el objetivo sostenido de cinco análisis
por segundo. Las posiciones siguen siendo estimaciones del centro de la caja
sobre cada plano ArUco, sin profundidad ni corrección de distorsión óptica.
