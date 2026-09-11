# Video del DJI Neo en Android y PC — versión 0.3.0

La app recibe una transmisión **RTMP publicada por DJI Fly**. No controla el dron,
no sustituye DJI Fly y no se conecta directamente al protocolo inalámbrico del Neo.
El usuario confirmó que su DJI Fly muestra RTMP usando únicamente el celular.
Esa combinación de teléfono, firmware y Neo queda pendiente de prueba física:
la guía oficial de DJI describe el procedimiento con un control conectado.

## Conexión local

```text
DJI Neo → DJI Fly (celular emisor) → servidor MediaMTX en Windows
                                         ├→ Uchuva ArUco PC
                                         └→ Uchuva ArUco Android (otro teléfono)
```

1. En el PC, ejecuta `Iniciar servidor RTMP.cmd` incluido en el paquete. En el
   repositorio puedes ejecutar `scripts/setup_rtmp_server.ps1` una vez y después
   `scripts/start_rtmp_server.ps1`. Cerrar esa consola detiene el servidor.
2. Averigua la IPv4 del PC con `ipconfig`. Ejemplo ilustrativo: `192.168.1.10`.
   El teléfono emisor necesita poder alcanzar esa IP. Con el teléfono conectado
   por Wi-Fi al Neo, **no se debe asumir que también está en la red del PC**.
   Una conexión USB de red compartida puede dar una ruta, pero hay que comprobar
   que no interrumpa DJI Fly. Tener Internet por datos móviles no hace accesible
   automáticamente una IP privada del PC. Este punto requiere comprobarse con
   el teléfono concreto antes de una prueba en vuelo.
3. Si Windows solicita acceso a la red para MediaMTX, permite únicamente la red
   privada de pruebas. El servidor recibe TCP 1935. No se abren puertos del router
   ni se modifican reglas de firewall automáticamente.
4. En DJI Fly, entra a **Transmisión → Plataformas de transmisión en directo →
   RTMP**. Usa `rtmp://192.168.1.10:1935/neo`, sustituyendo la IP por la real.
   Si pide dirección y clave por separado, deben concatenarse hasta formar esa
   misma ruta. Comienza con 720p y H.264 si están disponibles.
5. En el mismo PC abre `UchuvaArUcoPC.exe`, deja
   `rtmp://127.0.0.1:1935/neo` y pulsa **Conectar RTMP**.
6. En otro Android instala el APK, pulsa **Fuente: cámara / RTMP**, elige RTMP e
   introduce `rtmp://192.168.1.10:1935/neo`. Mantén DJI Fly abierto en el emisor.
   La app receptora pausa la recepción al pasar a segundo plano y la reabre al
   volver. No se garantiza usar emisor y receptor simultáneamente en un teléfono.

El servidor suministrado permite publicar y leer `neo` sin contraseña dentro de
una LAN de confianza. RTMP no cifra el video. No publiques este servidor en
Internet tal como está configurado. Una URL de YouTube para espectadores no es
una entrada RTMP; una dirección de ingestión de YouTube tampoco es un servidor
desde el que estas apps puedan leer.

## ArUco y captura

Antes de estimar posiciones, introduce el **lado negro real en centímetros**, sin
margen blanco. La app pregunta al detectar el primer marcador sin escala
confirmada. Todos los marcadores deben tener esa medida. No se devuelven
coordenadas en “lados del ArUco”. Sin confirmación, las medidas son `null`.

Se detecta `DICT_4X4_50`, se dibujan las rejillas de todos los marcadores sobre el
fotograma y cada capacho tiene una línea por referencia. X apunta a la derecha
decodificada y Y arriba. Tocar/clicar un marcador selecciona la referencia de
compatibilidad; todos los demás continúan participando. ID duplicados,
geometrías degeneradas y puntos detrás del horizonte proyectivo no dan medidas.
La homografía es una estimación sobre el plano del marcador, no distancia 3D,
y no corrige la distorsión de la lente.

- **Android:** Capturar guarda JPEG anotado en Galería/Pictures/UchuvaArUco y JSON
  en Descargas/UchuvaArUco; Guardadas permite abrir y compartir ambos.
- **PC:** Guardar JPEG + JSON crea una carpeta por captura dentro de
  `Downloads/UchuvaArUco`, o de la carpeta elegida. Abrir guardadas abre el
  Explorador. Ambos archivos tienen el mismo nombre base, identificador de
  fotograma, procedencia y hash SHA-256 de la imagen. Se publica la carpeta
  cuando los dos archivos están escritos.

JSON `1.4` añade `source`, diferenciando `camera`, `rtmp` y `file`. La fecha de
RTMP indica recepción, **no la hora de exposición del dron**. Android registra
la marca temporal de la superficie del decodificador por separado del reloj de
cámara; PC registra el reloj de recepción. No se guardan URL ni claves RTMP en
los JSON. El tamaño corresponde al fotograma analizado: Android limita el lado
mayor a 1280 píxeles. El modelo sigue trabajando a 640 × 640 con relleno.

## Videos descargados y exportación en PC

**Abrir video** analiza MP4/MOV/AVI/MKV locales. Es útil cuando no hay una ruta de
red desde el teléfono al PC. En la vista interactiva se procesa el cuadro más
reciente; puede omitir cuadros para no acumular retraso.

**Exportar video completo + datos** procesa todos los cuadros de un archivo y
genera una carpeta con MP4 anotado, JSONL (una línea por cuadro) y JSON manifiesto
con el hash del MP4. Solicita primero la medida del ArUco. Conserva resolución y
usa la frecuencia nominal del archivo para una salida de frecuencia constante;
no conserva audio ni tiempos variables originales. `output_frame_index` empieza
en cero y vincula cada registro con el video. La vista previa no afecta los
ajustes tomados al iniciar la exportación. Cancelar exportación elimina la
carpeta parcial. Esta versión guarda capturas del directo; no graba un MP4 del
RTMP. Para exportar un vuelo completo, usa el archivo descargado del Neo.

## Compilación y pruebas reproducibles

- Android: `scripts/build_android_app.ps1` (requiere el entorno Android ya preparado).
- PC Windows x64: `scripts/build_desktop_app.ps1`. Entorno separado en
  `outputs/desktop/venv`; salida en `outputs/desktop/dist/UchuvaArUcoPC`.
  Mantén el ejecutable junto con su carpeta `_internal`; no copies el EXE solo.
- Código PC: `desktop/run_app.py`, con las dependencias de `desktop/requirements.txt`.
- Tests PC: `$env:PYTHONPATH='desktop'; outputs/desktop/venv/Scripts/python.exe -m unittest discover -s desktop/tests -v`.
- Prueba RTMP local: instalar `imageio-ffmpeg==0.6.0` en ese entorno de pruebas y
  ejecutar `scripts/test_rtmp_video.py`. `--hold-seconds 180` mantiene el emisor
  local para la prueba Android `RtmpIntegrationTest` con el argumento de
  instrumentación `rtmp_url=rtmp://10.0.2.2:1935/neo`.
- Grafo: `python scripts/validate_repository_context_graph.py`.

No se ha reentrenado el modelo, cambiado las clases ni usado el conjunto de test
para ajustar el detector. La prueba de paridad reutiliza una muestra de `val`.
Las pruebas locales no certifican latencia de vuelo ni precisión física.

## Fuentes y componentes

- [Guía oficial de transmisión DJI Fly](https://repair.dji.com/help/content?customId=01700006727&lang=en&paperDocType=ARTICLE&re=US&spaceId=17).
- [Receptor RTMP Android Media3](https://developer.android.com/reference/androidx/media3/datasource/rtmp/RtmpDataSource): Media3 1.6.1.
- [MediaMTX](https://github.com/bluenviron/mediamtx/releases/tag/v1.21.0): servidor 1.21.0.
- ONNX Runtime 1.22.0, OpenCV 4.11.0 y NumPy 2.2.6 en PC; empaquetado PyInstaller 6.15.0.

Los términos del modelo y de terceros no cambian por incluirlos en los paquetes.
