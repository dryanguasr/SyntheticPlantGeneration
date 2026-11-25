# ESP32 del banco 2WD por WiFi

> El desarrollo vigente del robot está en
> [Robot-Cosechador](https://github.com/dryanguasr/Robot-Cosechador). Este
> transporte se publica aquí mientras se habilita el acceso a ese repositorio;
> debe trasladarse allí cuando sea posible.

Transporte WiFi/TCP para el firmware `DRV8833_ROS_V5` de
[PhysalisHarvest](integracion_physalisharvest.md). Sustituye el cable USB entre
el computador y el ESP32; el resto de la cadena no cambia:

```text
Astra Pro → XYZ del ArUco → controlador ROS 2 (WSL) → puente WiFi → ESP32 → DRV8833
```

**Estado:** verificado con simuladores sin placa (firmware C++ con red y GPIO
MOCK, y puente Python contra un ESP32 TCP falso). **No se ha compilado para
el ESP32 real, cargado en una placa ni probado con motores.** El primer ensayo
físico debe seguir las mismas precauciones del banco USB.

## Qué se añade y qué no se toca

| Archivo | Función |
| --- | --- |
| `firmware/drv8833_wifi/drv8833_wifi.ino` | Envoltorio: red, autenticación y un solo cliente |
| `firmware/drv8833_wifi/wifi_config.example.h` | Plantilla de red, clave y token |
| `scripts/prepare_drv8833_wifi.py` | Verifica el sketch original y genera los archivos locales |
| `firmware/drv8833_wifi/pca9685_servos.h` | Servos por PCA9685 (I2C): límites, velocidad y parada |
| `scripts/drv8833_wifi_bridge.py` | Puente del computador por TCP |
| `scripts/servo_wifi.py` | Órdenes de servo a través del puente |
| `firmware/drv8833_wifi/test/` y `tests/test_drv8833_wifi_bridge.py` | Simuladores y pruebas |

El snapshot `contributions/physalisharvest/` no se modifica. El envoltorio
incluye el sketch original sin cambios: protocolo, armado manual,
interbloqueo, pausa de 100 ms entre sentidos y watchdog de 250 ms. El script
de preparación lo copia como `drv8833_core.h` solo si su SHA-256 coincide con
`contributions/physalisharvest.provenance.json`. Ese archivo y
`wifi_config.h` están en `.gitignore`: el código de Diego sigue con su
licencia pendiente y las claves no se versionan.

## Seguridad del enlace

- **Token obligatorio.** La primera línea del cliente debe ser
  `AUTH <token>`. Sin ella no llega ninguna orden a los motores.
- **Un solo cliente.** Un segundo puente recibe `ERR BUSY` y se desconecta.
- **Parada al perder el enlace.** Si el cliente se desconecta, el ESP32 para
  los motores en el acto. Si la WiFi cae sin cerrar la conexión, el watchdog
  de 250 ms los para y la ranura se libera tras 3 s sin tráfico.
- **Sin valores de ejemplo.** El firmware no compila con el token o la clave
  de la plantilla.
- **Límite:** el token y las órdenes viajan sin cifrar dentro de la red WiFi.
  En una red compartida, cualquiera que la escuche puede leer el token. Usa el
  modo punto de acceso con su clave WPA2 propia. El corte físico de VM sigue
  siendo el medio de parada independiente.

## 1. Preparar el firmware

Desde la raíz del repositorio:

```powershell
python scripts/prepare_drv8833_wifi.py
```

Esto genera `firmware/drv8833_wifi/drv8833_core.h` y, si no existe,
`wifi_config.h` con un token y una clave WPA2 aleatorios. Hay dos modos:

- **Punto de acceso (por defecto, recomendado en campo):** el ESP32 crea la
  red `uchuva-2wd` y queda en `192.168.4.1`. La clave está en
  `AP_PASSWORD` de `wifi_config.h`.
- **Estación:** el ESP32 se une a una red existente.

  ```powershell
  python scripts/prepare_drv8833_wifi.py --ssid "MiRed" --password "clave-de-mi-red"
  ```

  Si `wifi_config.h` ya existe no se sobrescribe; bórralo o edítalo a mano.

## 2. Cargar en el ESP32

Con VM desconectada, abre `firmware/drv8833_wifi/drv8833_wifi.ino` en Arduino
IDE con la misma placa y núcleo del banco USB (`ESP32 Dev Module`, Arduino
ESP32 3.3.12) y cárgalo como indica la
[guía DRV8833](../../contributions/physalisharvest/ros2_ws/src/robot_locomocion/bench_2wd_drv8833/README.md).
Con Arduino CLI:

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/drv8833_wifi
arduino-cli upload --fqbn esp32:esp32:esp32 -p COM3 firmware/drv8833_wifi
```

Al conectarse, el ESP32 imprime por USB (115200 bit/s) una línea como
`DRV8833_WIFI 192.168.4.1:3333` con la dirección que usará el puente.

## 3. Comprobar sin movimiento

Conecta el computador a la red del ESP32 y, con VM desconectada:

```powershell
python scripts/drv8833_wifi_bridge.py --host 192.168.4.1 --check
```

Debe responder `DRV8833_ROS_V5` y `OK S 0000`. El token se toma de
`wifi_config.h`, o de la variable `DRV8833_WIFI_TOKEN` si el puente corre
en otro computador.

## 4. Ejecutar con ROS 2

Compila una vez los paquetes y lanza el puente; este inicia el controlador
ROS en WSL y le reenvía sus órdenes al ESP32:

```powershell
python scripts/physalisharvest_ros.py compilar
python scripts/drv8833_wifi_bridge.py --host 192.168.4.1 --ruta 0 1 2
```

En otras terminales, la fuente ArUco y la sesión se lanzan igual que con el
banco USB (`physalisharvest_ros.py fuente`, `armar`, `parar`). Antes de
habilitar VM aplica la lista del banco: chasis inmovilizado, ruedas libres,
GND común, límite de corriente y corte físico al alcance.

## 5. Servos por PCA9685

El firmware maneja hasta 16 servos con una placa PCA9685 por I2C. **Este
código es nuevo, no proviene del banco de Diego, y solo se ha verificado en
simulador.** Los rangos por defecto son genéricos, no medidos en el brazo.

### Conexión

| PCA9685 | ESP32 |
| --- | --- |
| VCC (lógica) | 3V3 |
| GND | GND |
| SDA | GPIO 21 |
| SCL | GPIO 22 |
| V+ (potencia de servos) | Fuente aparte de 5-6 V con GND común |

No alimentes los servos desde el ESP32. La dirección por defecto es `0x40`
(A0-A5 sin puentear). Los pines, la dirección y la frecuencia (50 Hz) se
cambian en `wifi_config.h`.

### Límites antes de mover

En `wifi_config.h`, fija el rango seguro de cada canal:

```c
// canal 0, canal 1, canal 2...
#define SERVO_LIMITS {{1100, 1900}, {1000, 1700}, {1200, 1800}}
```

Sin `SERVO_LIMITS`, todos los canales de `0` a `SERVO_CHANNELS - 1` usan
`SERVO_MIN_US`-`SERVO_MAX_US` (1000-2000 us). Mide el rango real con el
servo desacoplado del brazo y amplíalo poco a poco. Una orden fuera de rango
se rechaza (`ERR SV RANGO`), no se recorta.

### Uso

Inicia el puente con ROS, como en el paso 4, o solo para servos, sin ROS:

```powershell
python scripts/drv8833_wifi_bridge.py --host 192.168.4.1 --solo-servos
```

Con el puente en marcha, en otra terminal:

```powershell
python scripts/servo_wifi.py 0 1500
```

```powershell
python scripts/servo_wifi.py estado
```

```powershell
python scripts/servo_wifi.py off
```

El puente atiende estas órdenes en `127.0.0.1:3334` y las envía por la misma
conexión autenticada que los motores. Solo acepta conexiones del propio
computador, sin token: cualquier programa local puede mover los servos.

### Comportamiento

- **Arranque:** todos los canales sin pulso hasta la primera orden.
- **Primera orden de un canal:** va directa al objetivo, porque el ESP32 no
  conoce la posición previa del servo. Envía primero un valor cercano a la
  posición en reposo.
- **Velocidad:** después, el pulso avanza como máximo `SERVO_SLEW_US_PER_S`
  (500 us/s por defecto).
- **Pérdida del puente:** con `SERVO_HOLD_ON_DISCONNECT 0` (por defecto) los
  servos quedan sin pulso y sin par. Si el brazo cae por gravedad, evalúa `1`,
  que mantiene la última posición, con el corte de V+ al alcance.
- **Independencia de los motores:** las órdenes de servo no alimentan el
  watchdog de 250 ms de la base; los motores se paran igual sin órdenes.
- **Sin PCA9685 en el bus:** `SV` responde `ERR SV PCA9685`; los motores
  siguen funcionando.

| Orden | Respuesta |
| --- | --- |
| `SV <canal> <us>` | `OK SV <canal> <us>`, `ERR SV RANGO <mín>-<máx>`, `ERR SV CANAL`, `ERR SV FORMATO` o `ERR SV PCA9685` |
| `SVQ` | `OK SVQ <canal>:<actual>/<objetivo> ...`, o `OK SVQ -` sin canales activos |
| `SVOFF` | `OK SVOFF` |

## Diferencias frente al USB

- La latencia WiFi varía. Si una respuesta tarda más de 250 ms, el puente se
  detiene con un error y el watchdog del ESP32 para los motores: falla del
  lado seguro, pero puede cortar movimientos con mala cobertura.
- En reposo el puente envía `S` cada segundo para mantener vivo el enlace.
- La consola gráfica `consola_2wd.py` del snapshot sigue usando USB.

## Verificación

```powershell
python -m unittest tests.test_drv8833_wifi_bridge -v
```

En WSL o Linux, con g++:

```bash
python3 scripts/prepare_drv8833_wifi.py
bash firmware/drv8833_wifi/test/run.sh
```

El simulador comprueba: rechazo sin token, con token erróneo y con línea
desbordada; acuses idénticos al USB; `ERR BUSY` para un segundo cliente;
watchdog de 250 ms; parada al desconectarse; descarte de órdenes a medias; y
liberación por inactividad. Para los servos, con un PCA9685 simulado: frecuencia
de 50 Hz, rango por canal, límite de velocidad, `SVOFF`, corte al
desconectarse, independencia del watchdog de motores y placa ausente.
