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
| `scripts/drv8833_wifi_bridge.py` | Puente del computador por TCP |
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
liberación por inactividad.
