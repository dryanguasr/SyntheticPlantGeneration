# Banco ROS 2 del chasis 2WD

Destino de trabajo `feat/2WD`. Este paquete implementa la etapa F0 del banco de locomoción. El receptor recibe y valida XYZ y publica un diagnóstico ROS 2. La prueba sintética y la adquisición calibrada usan el mismo receptor. Los [ensayos ESP32](../../../../firmware/bench_2wd/README.md) documentan el eco serial con una muestra real, la secuencia en seco y el giro observado de las ruedas en banco. La navegación por objetivos queda pendiente.

## Reproducir F0 en Ubuntu 24.04

Usar ROS 2 Jazzy y `colcon`. En Windows, los comandos Bash se ejecutan en Ubuntu 24.04 sobre WSL 2. En otro equipo, instalar Jazzy desde el repositorio oficial de ROS y disponer de `ros-jazzy-rclpy`, `ros-jazzy-geometry-msgs`, `ros-jazzy-std-msgs`, `python3-colcon-common-extensions`, `python3-setuptools` y `python3-pytest`. Registrar las versiones con `dpkg-query -W` para las dependencias utilizadas. [Instalación oficial de Jazzy](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)

Desde la raíz del repositorio en Bash:

```bash
source /opt/ros/jazzy/setup.bash
test "$ROS_DISTRO" = jazzy
command -v ros2 colcon
cd ros2_ws
colcon build --packages-select bench_2wd
colcon test --packages-select bench_2wd --return-code-on-test-failure
colcon test-result --verbose
source install/setup.bash
export ROS_DOMAIN_ID=83 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 run bench_2wd receiver
```

En una segunda terminal, desde `ros2_ws`:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=83 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 run bench_2wd smoke_test
```

El test registrado en `colcon` arranca su propio receptor en el dominio local 84. El ensayo manual usa el 83. Reservar estos dominios para el banco y evitar publicar muestras reales durante la prueba sintética. El test genera ocho observaciones y termina con código 0 si coinciden los diagnósticos y el XYZ conservado. Expone fallos de descubrimiento o recepción con código distinto de 0. La entrada Astra durante este test también es sintética. Terminar el receptor manual con Ctrl+C.

### Interfaz local F0

| Tópico | Tipo | Marco / contenido |
| --- | --- | --- |
| `/bench_2wd/synthetic_xyz` | `geometry_msgs/msg/PointStamped` | `bench_2wd_synthetic_optical_frame` |
| `/astra/xyz` | `geometry_msgs/msg/PointStamped` | `astra_depth_optical_frame`, contrato del productor externo |
| `/bench_2wd/receipt` | `std_msgs/msg/String` | JSON diagnóstico con tópico, sello en ns y resultado. Los puntos aceptados incluyen `xyz_m`. |

QoS fiable, volátil y profundidad 10. XYZ en metros. En el marco óptico, +X apunta a la derecha, +Y abajo y +Z delante. Se rechazan marco incorrecto, sello inválido, muestras con más de 1 s de antigüedad o más de 100 ms en el futuro, valores no finitos y profundidad axial no positiva. Usar reloj de sistema compartido o sincronizado entre Windows y WSL. El sello Astra corresponde a recepción de la pareja en Windows. El resultado `received` confirma recepción y validación en el proceso ROS.

## Reusar la calibración RGB–depth de la Astra Pro

La captura usa Windows con Python 3.11 x64, Orbbec OpenNI 2.3.0.86 (carpeta NiViewer) y DirectShow para RGB. Verificar primero la cámara con las herramientas de diagnóstico del clon externo. Usar el sensor y modo RGB/depth de 640 × 480 correspondientes al registro y comprobar visualmente la superposición en una escena estática. El adaptador reutiliza la proyección experimental con profundidad cruda y publica los XYZ del píxel de profundidad de origen. [Referencia Astra fijada al commit utilizado](https://github.com/amayadiegoalejandro05/astra-rgbd-ros2-integration/tree/7b4cd1b50ddecae7ea30494160e519d9e4191038)

En este equipo se encontró el clon hermano `COORDENADAS_ORBBECASTRA` y su archivo local `resultados/calibracion_caja_evaluada.json`. El archivo está excluido del Git externo. En otro equipo, preparar el mismo commit del clon y suministrar el JSON de forma autorizada fuera del checkout del banco. El SHA-256 observado del archivo local es `4b06398231164640534c33fe549be33a85165a2ca5e61eb9fdc1819a79ce0583`. Si cambia el sensor o el modo, comprobar la correspondencia con una referencia independiente antes de adoptar la calibración. La calibración RGB–depth y la pose de la cámara respecto al chasis se obtienen por separado.

En PowerShell, desde la raíz de PhysalisHarvest, con el receptor ROS abierto en el mismo dominio:

```powershell
$astra = (Resolve-Path ../COORDENADAS_ORBBECASTRA).Path
$sdk = Read-Host 'Ruta a la carpeta NiViewer de OpenNI 2.3.0.86'
[int] $rgbIndex = Read-Host 'Índice DirectShow verificado de la Astra Pro'
$calibration = Join-Path $astra 'resultados/calibracion_caja_evaluada.json'
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r "$astra/diagnostico/requirements-rgb.txt"
& .\.venv\Scripts\python.exe .\ros2_ws\src\robot_locomocion\bench_2wd\astra_click.py `
    --source $astra --sdk $sdk --rgb-index $rgbIndex --calibration $calibration `
    --sha256 4b06398231164640534c33fe549be33a85165a2ca5e61eb9fdc1819a79ce0583 --domain-id 83
```

Para instalaciones con otro nombre de distro, usar `--distro <nombre>`. Cerrar otras aplicaciones que usen la cámara. Con alimentación de motores desconectada, hacer clic en una región con profundidad válida. Observar `ros2 topic echo /bench_2wd/receipt`. El criterio de aceptación de transporte es ver `received` y un XYZ coherente con la muestra publicada. Registrar el SHA, hash de calibración, modo, reloj y salida. Usar Esc para cerrar el visor. Evitar los modos `--enviar-ros` y `--rostros` del visor externo y el puente serie del servo durante este ensayo.

## Visor local ArUco

Para la primera prueba, coloca [el ID 0](marcadores_aruco/aruco_4x4_50_id_00.png)
en un respaldo plano y opaco, con el margen blanco visible. Los IDs 1 y 2
quedan disponibles para futuras pruebas. El marcador puede imprimirse o
mostrarse en una pantalla para comprobar el reconocimiento RGB. La prueba de
distancia requiere una superficie que entregue profundidad estable.

El visor usa OpenCV en Windows y la misma captura, calibración y proyección
RGB–depth de la prueba anterior. Con la potencia de motores desconectada y el
puerto serie cerrado, ejecútalo desde la raíz en PowerShell con el entorno
`.venv-astra` existente:

```powershell
$astra = (Resolve-Path ../COORDENADAS_ORBBECASTRA).Path
$sdk = Read-Host 'Ruta NiViewer de OpenNI 2.3.0.86 Win64'
$calibration = Join-Path $astra 'resultados/calibracion_caja_evaluada.json'
& .\.venv-astra\Scripts\python.exe -B .\ros2_ws\src\robot_locomocion\bench_2wd\astra_aruco.py `
    --source $astra --sdk $sdk --calibration $calibration --rgb-index 1 --id 0
```

La ventana muestra el ID, su centro, la profundidad alineada y una muestra
XYZ en metros en el marco óptico de la Astra. Las indicaciones son visuales.
El criterio inicial de centrado es ±3° sobre `atan2(X, Z)`. Z es axial y la
parada a 0,50 m se refiere a la cámara. Con un marcador centrado, comprueba
la referencia con cinta. El alcance útil cerca de 0,50 m queda por medir.
Si no hay una muestra interior consistente, se pierde el ID o hay dos
marcadores con el ID objetivo, el visor indica PARAR. Pulsa Esc para cerrar.

Para regenerar los tres PNG, usa el mismo script con `--generar`. OpenCV
codifica los marcadores de forma determinista. Conserva el margen blanco
al recortar la página.

La opción `--ros` entrega el ID 0 al [banco experimental DRV8833](../bench_2wd_drv8833/README.md).

## Montaje declarado y trabajo físico pendiente

| Elemento | Datos de montaje declarados, pendientes de inspección |
| --- | --- |
| Motor izquierdo | `AIN1` GPIO25, `AIN2` GPIO26. Salidas `A01/A02`. |
| Motor derecho | `BIN1` GPIO27, `BIN2` GPIO14. Salidas `B01/B02`. |
| Habilitación | Etiqueta informada `STBY` a 3,3 V. Confirmar la función en el módulo. TI denomina `nSLEEP` al pin del DRV8833. |
| Alimentación | 6 V al borne informado como `VN`, GND común y `NC` libre. Confirmar identificación del borne del módulo y consumo de bloqueo de los motores. TI denomina `VM` a la alimentación de potencia del integrado. |
| Cámara | Encima de la rueda loca. Confirmar físicamente el lado que será el frente, altura y orientación del montaje. |

La habilitación fija a 3,3 V exige comprobar el estado del módulo durante reset y disponer de un corte físico de potencia. Antes de energizar, verificar serigrafía y esquema del módulo, fuente y protecciones, límites acordados, watchdog y estado de arranque. [Hoja de datos del DRV8833](https://www.ti.com/lit/ds/symlink/drv8833.pdf)

Como referencia comercial, el kit acrílico ROBOT05 declara placa de 200 × 100 mm y neumáticos de 60 × 27 mm. El modelo del carro del equipo sigue sin identificar. Medir diámetro efectivo, separación entre centros de ruedas motrices y pose de la Astra respecto al punto medio del eje motriz antes de usar parámetros cinemáticos. [Ficha técnica ROBOT05](https://cdn-reichelt.de/documents/datenblatt/C700/ROBOT05-DB_EN.pdf)

Para la primera sesión física autorizada, empezar con motores desconectados y comprobar protocolo y estados de fallo. Después, inmovilizar el chasis con ruedas motrices libres y corte accesible. Probar una rueda a la vez con el procedimiento y los límites supervisados que se acuerden. Registrar para cada canal el sentido de giro que produciría avance, así como la reacción a reset, parada y pérdida de enlace.

Para la fase de desplazamiento, transformar el punto óptico con una extrínseca medida al marco de la base y definir el destino planar con margen frente al objeto. El control del ESP32 requiere un enlace acordado, realimentación de pose, caducidad, parada y confirmación de llegada mediante una referencia independiente. Un punto XYZ por sí solo deja indeterminada la trayectoria del chasis.
