# Banco 2WD con DRV8833 y ArUco

Implementación experimental para buscar marcadores de **DICT_4X4_50**. La
Astra Pro aporta XYZ en metros. ROS 2 decide avance, giro o parada. El
puente USB envía la decisión al ESP32. La consola habilita **0, 1 y 2**
y selecciona el primer XYZ válido recibido. [Contrato ROS 2 y serial](../../../../docs/interfaces/bench-2wd-drv8833.md)

## Cableado del módulo

| Módulo DRV8833 | Conexión |
| --- | --- |
| AIN1 / AIN2 | GPIO 25 / 26 del ESP32 |
| BIN1 / BIN2 | GPIO 27 / 14 del ESP32 |
| AO1 / AO2 | Motorreductor izquierdo, cables 1 / 2 |
| BO1 / BO2 | Motorreductor derecho, cables 1 / 2 |
| STBY (serigrafía del módulo de referencia) | 3V3 del ESP32, tras verificar que es la entrada de habilitación de ese módulo |
| VM | Positivo del portapilas 4 × AA |
| GND | Negativo del portapilas y GND del ESP32 |
| USB del ESP32 | Computador |

TI denomina `nSLEEP` a la entrada de habilitación del integrado. Confirma
la serigrafía del módulo y la tensión y corriente admisibles de motores
y módulo antes de conectar VM. Los dos pines en bajo por puente dejan el
motor en rueda libre. Los acuses de GPIO no indican velocidad ni frenado.
Conserva un corte físico de VM y verifica la polaridad de las ruedas con
el chasis inmovilizado antes de cualquier ensayo de desplazamiento.
[Hoja de datos DRV8833, tabla 1](https://www.ti.com/lit/ds/symlink/drv8833.pdf)

## Preparar otro computador

1. Instala Windows con WSL 2, Ubuntu 24.04, ROS 2 Jazzy y `colcon`.
   En Ubuntu, instala los paquetes necesarios para compilar y probar:

   ```bash
   sudo apt install python3-colcon-common-extensions python3-pytest g++ \
     ros-jazzy-rclpy ros-jazzy-geometry-msgs ros-jazzy-std-msgs ros-jazzy-std-srvs
   ```

2. Clona `feat/2WD` y el proyecto Astra como carpetas hermanas. Usa Python
   3.11 x64 y OpenNI **2.3.0.86 Win64** con los controladores del sensor.
   Desde PowerShell:

   ```powershell
   git clone --branch feat/2WD --single-branch https://github.com/amayadiegoalejandro05/PhysalisHarvest.git
   git clone https://github.com/amayadiegoalejandro05/astra-rgbd-ros2-integration.git COORDENADAS_ORBBECASTRA
   git -C COORDENADAS_ORBBECASTRA switch --detach 7b4cd1b50ddecae7ea30494160e519d9e4191038
   cd PhysalisHarvest
   py -3.11 -m venv .venv-astra
   & .\.venv-astra\Scripts\python.exe -m pip install -r ..\COORDENADAS_ORBBECASTRA\diagnostico\requirements-rgb.txt pyserial==3.5
   ```

3. Coloca la calibración autorizada en
   `COORDENADAS_ORBBECASTRA/resultados/calibracion_caja_evaluada.json`.
   Es un archivo externo al repositorio. Para el perfil de referencia
   de 640 × 480 se espera SHA-256
   `4b06398231164640534c33fe549be33a85165a2ca5e61eb9fdc1819a79ce0583`.
   Un sensor distinto necesita su propio perfil verificado. El visor
   comprueba el hash antes de usarlo. [Perfil Astra y registro](../bench_2wd/README.md)

4. Compila los paquetes desde la raíz en PowerShell:

   ```powershell
   & .\.venv-astra\Scripts\python.exe -B .\firmware\bench_2wd\tools\reproducir_drv8833.py compilar
   ```

## Cargar el firmware DRV8833

Con VM desconectada, cierra puentes y monitores serie. En Arduino IDE abre
[`drv8833_ros.ino`](../../../../firmware/bench_2wd/drv8833_ros/drv8833_ros.ino),
selecciona `ESP32 Dev Module`, núcleo Arduino ESP32 3.3.12 y el puerto real
del ESP32. Si la placa requiere BOOT manual, mantenlo durante
`Connecting…`, suéltalo cuando empiece la escritura y espera la
verificación. Si después no responde, pulsa EN/RESET con BOOT suelto.

Verifica la firma y la salida en bajo manteniendo VM desconectada:

```powershell
& .\.venv-astra\Scripts\python.exe -B .\firmware\bench_2wd\tools\reproducir_drv8833.py identificar --puerto COM3
```

Se espera `DRV8833_ROS_V5` y `OK S 0000`. El comando libera COM3 al terminar.

## Ejecutar sin agente

### Consola Windows

Abre la consola con el Python 3.11 de Windows. Usa la misma instalación
del visor y de ROS 2 explicada arriba. La consola utiliza Tk incluido en
la instalación estándar de Python para Windows.

```powershell
& .\.venv-astra\Scripts\python.exe -B .\firmware\bench_2wd\tools\consola_2wd.py
```

Agrega `--vista-previa` para ver la interfaz sin abrir procesos, cámara ni
serie. La escena de ese modo es sintética. El conjunto inicial es
`0 1 2`; `--ids 0 3 4 8` habilita otro conjunto. Cada ID debe
ser único y estar entre 0 y 49. `--ids 0` habilita un solo marcador.
Para reproducir la configuración desde terminales, pasa la
misma lista `--ruta 0 1 2` a `visor` y `puente`.

1. Con VM cortada, abre una sola instancia. **Verificar conexiones** revisa
   puertos enumerados, SDK, hash y disponibilidad ROS. **Compilar ROS 2**
   instala también el monitor de la interfaz. Usa **Identificar ESP32**
   para verificar la firma del firmware y confirmar GPIO en bajo.
2. **Iniciar banco** abre el puente y el monitor. **Mostrar cámara** abre
   la Astra y publica el objetivo desde la misma captura que se ve en
   la consola. Ajusta **Profundidad** para variar la opacidad de la capa.
3. **Armar** llama al servicio ROS. Si los cuadros recientes tienen
   profundidad y los IDs elegibles están ausentes o visibles sin profundidad
   local válida, gira hacia la izquierda
   con pulsos de unos **100 ms al 100 % de PWM** y pausas de **500 ms**.
   Al detectar un marcador, lo alinea en ambos sentidos con pulsos de
   la misma duración y PWM. Las decisiones de giro usan cuadros
   capturados después de la pausa. El avance requiere dos cuadros centrados
   consecutivos y aplica **95 % de PWM a la izquierda y 100 % a la derecha**.
   Si faltan cuadros válidos, para y muestra **Esperando ArUco**.
   Al llegar a 50 cm, para y vuelve a buscar
   entre los IDs pendientes. Al alcanzar un marcador, lo ignora mientras
   siga visible. Vuelve a considerarlo si sale del encuadre y reaparece.
   La consola muestra
   el estado solicitado por ROS y el último acuse del ESP32 por separado.
   Un XYZ de más de 250 ms puede aparecer como **Solo visual** hasta
   los 800 ms. Las muestras de ese intervalo quedan fuera del control.
   **Parar** solicita el desarme. Si se pierde el monitor o la solicitud
   vence, se cierra el puente administrado y se intenta la parada.
4. Inspecciona **Tópicos**, **Nodos** y **Servicios**. El objetivo visible
   incluye frecuencia observada y edad de la muestra. **Copiar** guarda
   el registro mostrado en el portapapeles. Al cerrar el banco, verifica
   el acuse de parada y corta VM antes de intervenir el montaje.

Los parámetros `--distro`, `--dominio`, `--indice-rgb`, `--astra`, `--sdk`,
`--calibracion` y `--sha256` sirven para otra máquina. El puerto inicial
se pasa con `--puerto` o se edita en la ventana. La prueba con potencia
continúa limitada a ruedas suspendidas y corte físico al alcance.

Al perder el objetivo durante la aproximación, las ruedas paran y la
sesión sigue armada. **Parar** desarma la sesión. Un fallo del enlace
tiene su propio mecanismo de parada. El siguiente armado vuelve a
habilitar todos los IDs.
El escaneo gira sobre el sitio y aún
requiere una prueba física supervisada. La ruta carece de detección de
obstáculos.

**Verificación local de la consola.** En Ubuntu 24.04/WSL 2 con Jazzy,
`colcon build`, `colcon test` y `colcon test-result --verbose` sobre los dos
paquetes dieron 3 pruebas y 0 fallos. La prueba adicional usa el monitor,
el publicador y el controlador ROS reales en el dominio 90, con órdenes
seriales observadas en una tubería MOCK. Comprueba el grafo, el tipo del
servicio, rechazo de un armado vencido, armado sin ArUco, primera orden y
parada. En Windows, Tk abrió la vista previa y se comprobó el monitor
real en el dominio 91 vacío, el cierre de su proceso y los botones con
procesos simulados. El puerto serie y la cámara físicos quedaron fuera
de esta verificación.

### Terminales independientes

Para medir la cámara sin ESP32, inicia la consola con `--diagnostico`
y pulsa **Mostrar cámara**. El XYZ se publica en
`/bench_2wd/drv8833/aruco_target_diagnostico` con un límite de 800 ms.
El controlador sigue suscrito al tópico operativo, que conserva el límite
de 250 ms para muestras nuevas. El modo de diagnóstico deshabilita los
controles de actuación y muestra la edad real en el panel ROS.

Ejecuta cada bloque desde la raíz en una terminal PowerShell distinta.
Los comandos invocan Python directamente y funcionan con scripts
PowerShell deshabilitados.

```powershell
# Terminal 1. Conserva el puente abierto y comprueba la firma y el OK de parada.
& .\.venv-astra\Scripts\python.exe -B .\firmware\bench_2wd\tools\reproducir_drv8833.py puente --puerto COM3

# Terminal 2. Visor y publicación de XYZ en ROS.
& .\.venv-astra\Scripts\python.exe -B .\firmware\bench_2wd\tools\reproducir_drv8833.py visor

# Terminal 3. Envía cada comando por separado.
& .\.venv-astra\Scripts\python.exe -B .\firmware\bench_2wd\tools\reproducir_drv8833.py armar
& .\.venv-astra\Scripts\python.exe -B .\firmware\bench_2wd\tools\reproducir_drv8833.py parar
```

La acción `estado` muestra eventos ROS en una cuarta terminal. El puerto
por defecto es COM3, la distribución Ubuntu-24.04, el dominio 83 y el
índice RGB 1. Usa `--help` para ajustar `--puerto`, `--distro`, `--dominio`,
`--indice-rgb`, `--astra`, `--sdk`, `--calibracion` y `--sha256`. El dominio
y la distribución deben coincidir en todas las terminales. `--sdk` apunta
a la carpeta **NiViewer** que contiene `OpenNI2.dll` x64.

Ensaya primero con VM cortada. `armar` devuelve éxito aunque todavía no se
vea el ArUco y espera a que se muestre. Coloca el
[ID 0](../bench_2wd/marcadores_aruco/aruco_4x4_50_id_00.png) fijo sobre un
respaldo opaco, inicialmente a unos 70 cm. En el puente, `DRIVE F/L/R`
identifica la decisión ROS y `OK …` el acuse GPIO del ESP32. Busca el giro
desplazando el marcador lateralmente y la parada al llegar a Z ≤ 0,50 m
desde la Astra. Una
observación inválida, su caducidad, la llegada o la parada manual
desarman. Para repetir se vuelve a llamar a `armar`.

Con potencia, usa solo el chasis inmovilizado y las ruedas suspendidas,
con supervisión y corte físico de VM al alcance. Al terminar ejecuta
`parar`, comprueba `OK S 0000` y corta VM. Cierra el visor con Esc y el
puente con Ctrl+C.

## Si falla un paso

| Síntoma | Comprobación |
| --- | --- |
| Acceso denegado a COM3 | Cierra el puente anterior o el Monitor Serie, verifica el puerto real y vuelve a abrir una sola instancia. |
| Firma incompatible o silencio en COM3 | Verifica qué sketch cargaste. Con VM cortada, pulsa EN/RESET con BOOT suelto si se quedó en modo de carga. |
| Servicio no disponible | Deja abierto el puente, confirma la firma y revisa que la distribución y el dominio sean iguales. Si cambiaste de rama o clon, ejecuta `compilar`. |
| Armado confirmado, salidas en bajo | Comprueba el ID activo y que lleguen cuadros recientes. Sin profundidad disponible, la búsqueda espera con las salidas en bajo. El acuse del puente confirma GPIO. |
| ArUco visible sin XYZ | Comprueba índice RGB de Astra Pro, OpenNI x64, enlace USB, perfil y calibración. Prueba con una superficie plana estable. |
| Lecturas RGB-D retrasadas | ROS descarta muestras con más de 250 ms. El aviso aparece tras tres descartes consecutivos. El vídeo usa un búfer de un cuadro para que la codificación de la vista no retenga la captura. |
| Relojes Windows/WSL desalineados | La cámara mide y renueva el desfase en segundo plano. El vídeo sigue disponible mientras reintenta. La publicación de XYZ espera una referencia validada en los últimos 30 s. El puente y el cliente gráfico miden al iniciar. Tras suspender Windows, reinicia el banco antes de armar. |
| Orden vencida | El puente rechaza una orden que excede su plazo. Revisa latencia y relojes antes de armar. |

El firmware usa dirección fija sin PWM. La parada deja los motores en
rueda libre. Aún requieren medición la distancia final de parada y el
comportamiento físico de la ruta con el DRV8833 actual. El banco carece
de detección de obstáculos y odometría.

La prueba ROS de la ruta, con datos y transporte simulados, verifica
búsqueda inicial, selección por disponibilidad en el orden de ensayo
2 → 0 → 1, rechazo de un competidor durante el seguimiento, pausa al
adquirir, parada final y búsqueda por pulsos más allá de 5 s.
Se comprobaron asimismo los estados de ArUco ausente, ID duplicado y
profundidad inválida en imágenes sintéticas de OpenCV.

## Auditoría del 20 de noviembre de 2026

**Prueba real en seco, VM desconectado.** La Astra publicó el ID 0 y
ROS recibió XYZ `(0,100; 0,085; 0,567) m` con 91 ms de edad. En COM3,
el ESP32 con `DRV8833_ROS_V1` confirmó `OK CR 1001`, `OK R 1001` y
`OK S 0000` al vencer la observación. También confirmó la parada
manual final. Un intento anterior confirmó avance `OK CF 1010` y
cerró por plazo al variar la referencia de reloj. El puente ahora vuelve
a medir si rechaza una orden por edad y verifica el mismo plazo antes de
transmitir. La recepción de GPIO se comprobó sin alimentar motores.

**Sentido de avance con ruedas suspendidas.** Con VM alimentado y el
chasis inmovilizado, se usó una observación sintética centrada en el
dominio ROS 93. El operador observó avance de ambas ruedas en el primer
pulso. El ESP32 confirmó `OK CF 1010`, `OK F 1010` y `OK S 0000` en
el primer pulso y en la repetición. Un intento intermedio se canceló
sin comando de dirección por medición inestable del reloj. La nueva
medición admite hasta siete intentos para reunir tres muestras estables
y conserva la caducidad de la orden antes de transmitir.

**Correcciones con ruedas suspendidas.** En el dominio 93 se enviaron dos
pulsos separados de aproximadamente 0,66 s, con Z sintético de 0,80 m.
Con X = +0,12 m ROS solicitó derecha y el ESP32 confirmó `OK CR 1001`
y `OK R 1001`. Con X = −0,12 m solicitó izquierda y el ESP32 confirmó
`OK CL 0110` y `OK L 0110`. Ambas paradas confirmaron `OK S 0000`.
Los acuses corresponden a las salidas GPIO. El sentido físico observado
de cada giro queda por confirmar con el operador.

Rama `feat/2WD`, base `fdfd135`. Windows con Python 3.11.9 y OpenCV
4.11.0, WSL 2 con Ubuntu 24.04 y Jazzy. Clon Astra en `7b4cd1b` y hash
de calibración conforme al perfil. La compilación del firmware usa
Arduino ESP32 3.3.12 y FQBN `esp32:esp32:esp32`.

| Comprobación | Resultado |
| --- | --- |
| `colcon build`, `colcon test --return-code-on-test-failure` y `colcon test-result --verbose` en ambos paquetes | 2 pruebas, 0 fallos. Incluye el diagnóstico histórico y productor/controlador ROS con entradas sintéticas, frontera serial MOCK, armado sin marcador, avance, ambos giros, umbral, dato inválido, caducidad y parada manual. |
| `python -m unittest discover -s firmware/bench_2wd/tools/test -v` | 3 pruebas del puente sin COM. Identidad incompatible, acuses y vencimiento antes de transmitir. |
| Arduino CLI y simulador C++ | Sketch compilado para ESP32. GPIO, interbloqueo, watchdog, vencimiento de sesión, error de formato y desbordamiento de `millis()` verificados con reloj y pines MOCK. |
| Lanzador y visor | `compilar` funcionó desde Windows. El comando `armar` en un dominio sin controlador terminó con salida 1 y diagnóstico. OpenCV leyó los tres PNG y se comprobó la orientación y el umbral del visor con XYZ sintético. |

La primera ejecución de integración detectó que el controlador emitía
`C` y `F` por separado. La repetición verificó el token único `CF`.
La captura adjunta aportó el cableado. El texto exacto del error previo
del tercer comando no estuvo disponible. El lanzador nuevo evita depender
de la política de PowerShell y el cliente detecta un servicio ausente o
una respuesta vencida. No se abrió COM3, cargó firmware ni actuaron motores
durante esta auditoría.

Para repetir la comprobación C++ desde la raíz en WSL:

```bash
g++ -std=c++17 -Wall -Wextra -Werror -I firmware/bench_2wd/drv8833_ros/test \
  firmware/bench_2wd/drv8833_ros/test/firmware_mock.cpp -o /tmp/physalis-drv8833-firmware-mock
/tmp/physalis-drv8833-firmware-mock
```
