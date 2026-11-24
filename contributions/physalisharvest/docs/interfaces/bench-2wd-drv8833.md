# Contrato experimental del banco DRV8833 v1

Windows captura RGB y profundidad con la Astra. `astra_aruco.py --ros`
envía JSON por stdin a `aruco_source` en WSL al recibir `ARUCO_READY`.
ROS 2 decide el movimiento en `controller`. El puente Windows lleva las
órdenes por USB al ESP32. Usa un único publicador y un único controlador.
El alcance es localhost, dominio 83 por defecto. Este contrato pertenece
al banco 2WD.

El parámetro ROS `ruta` contiene el conjunto de IDs habilitados. El ID 0
conserva el tópico base y los demás usan `/aruco_target_id_<ID>` bajo
`/bench_2wd/drv8833`. Se añade `_visual` o `_diagnostico` al tópico
correspondiente. Z = −1 indica una muestra inválida, Z = −2 indica ID
ausente y Z = −3 indica ID visible sin profundidad local válida.
Los estados −2 y −3 requieren profundidad global disponible. Si todos
los IDs elegibles tienen uno de esos dos estados, el controlador puede
sondear. El primer XYZ válido selecciona el objetivo. `TARGET <ID>`, `SCAN buscando_aruco` y
`ARRIVED <ID>` informan selección, giro de búsqueda y llegada.
La búsqueda izquierda y la alineación alternan pulsos de unos 100 ms con
500 ms de reposo. El sondeo continúa mientras lleguen cuadros frescos. Ante datos
inválidos o falta de cuadros, para y publica `WAIT esperando_aruco`.
Al detectar un objetivo, abandona la búsqueda y pasa a la alineación.
Las decisiones tras un pulso requieren cuadros capturados después del reposo.
El avance requiere dos cuadros centrados consecutivos del mismo marcador.

`bench_2wd_drv8833_console` observa el grafo, se suscribe al objetivo y al
estado con los QoS existentes y llama al servicio de control cuando el
operador pulsa **Armar** o **Parar**. La consola recibe acuses GPIO del
puente por separado. Un tópico descubierto puede tener solo suscriptores;
la interfaz muestra si falta su publicador.

La consola muestra observaciones de `/bench_2wd/drv8833/aruco_target_visual`
hasta 800 ms. El controlador sigue recibiendo el tópico operativo por separado,
con el límite de 250 ms para muestras nuevas. El armado gráfico usa una
autorización de un solo uso emitida por el monitor, con caducidad medida
dentro de WSL. La orden de parada no requiere esa autorización.

| Recurso ROS 2 | Tipo | Productor → consumidor | Contenido |
| --- | --- | --- | --- |
| `/bench_2wd/drv8833/aruco_target` | `geometry_msgs/msg/PointStamped` | `bench_2wd_drv8833_aruco` → `bench_2wd_drv8833_controller` | ID 0 de DICT_4X4_50, punto superficial XYZ en metros. Marco `astra_depth_optical_frame`, X a la derecha, Y abajo, Z axial hacia delante. Sello de recepción RGB en Windows. XYZ cero indica detección ausente o profundidad inválida. QoS volátil, mejor esfuerzo, profundidad 1. |
| `/bench_2wd/drv8833/state` | `std_msgs/msg/String` | `bench_2wd_drv8833_controller` → operador | `ARMED esperando_aruco`, `DRIVE F/L/R`, `STOP` con motivo. QoS volátil, fiable, profundidad 10. |
| `/bench_2wd/drv8833/enable` | `std_srvs/srv/SetBool` | `bench_2wd_drv8833_session` → `bench_2wd_drv8833_controller` | `true` habilita la espera aunque falte el ArUco. `false` cancela la espera o para y desarma. El resultado corresponde a la aceptación de la solicitud ROS. Verifica el GPIO en los acuses del puente. |

Ejemplos ROS en WSL después de cargar Jazzy y el workspace:

```bash
export ROS_DOMAIN_ID=83 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 topic echo /bench_2wd/drv8833/state
ros2 service call /bench_2wd/drv8833/enable std_srvs/srv/SetBool '{data: true}'
ros2 service call /bench_2wd/drv8833/enable std_srvs/srv/SetBool '{data: false}'
```

La espera admite observaciones ausentes o Z ≤ 0,50 m con salidas en bajo.
El movimiento empieza con una lectura recibida tras armar, de hasta
180 ms y Z > 0,50 m. El productor y el controlador descartan muestras
entrantes con más de 250 ms de edad o adelantadas más de 30 ms. El
controlador refresca la dirección cada 50 ms y deja de utilizar la última
observación a los 450 ms de edad. La espera y el seguimiento carecen
de cronómetros generales. Una observación inválida del objetivo en
movimiento o un XYZ caducado detienen los motores y conservan el armado.
La parada explícita desarma. Al alcanzar un marcador, se para y se
selecciona otro ID válido. Un marcador alcanzado vuelve a ser elegible
tras confirmarse su ausencia.

El controlador emite `CMD sello_ns vence_ns orden` por stdout. El puente
rechaza órdenes que ya vencieron o pasaron más de 125 ms en la tubería.
Los plazos de tubería usan reloj monótono. Windows mide su desfase
monótono respecto a WSL. El publicador convierte la edad de captura
a un sello ROS al emitir el `PointStamped`.
El canal stdin del controlador se usa para detectar el cierre del puente,
y se bloquea una segunda instancia por usuario y dominio.

El serial USB funciona a 115200 bit/s. `ID` desarma y responde
`DRV8833_ROS_V5`. `CF`, `CL`, `CR` y `CQ` inician una sesión ESP32 con la
primera dirección. `F`, `L`, `R` y `Q` renuevan la dirección de una sesión
vigente. `S` para y desarma. Cada mensaje termina en salto de línea. Los
acuses `OK orden GPIO` indican qué canales se han activado según la
consigna, en el orden 25/26/27/14. No miden el nivel instantáneo ni
la velocidad. Los patrones F, L/R y Q son `1010`, `0110`/`1001` y
`0110`, respectivamente. F usa 242/255 en el motor izquierdo y 255/255
en el derecho para compensar la deriva observada. L, R y Q usan 255/255
en ambos motores. El PWM usa LEDC a 1 kHz. Un fallo de PWM bloquea el movimiento.
`0000` indica rueda libre y también se admite durante el interbloqueo.
El ESP32 impone 100 ms en bajo entre direcciones, un watchdog de 250 ms
desde la última orden. Un comando inválido desarma y
devuelve `ERR COMMAND`. Un error de enlace o acuse cierra el puente con
un intento de parada. [Procedimiento y cableado](../../ros2_ws/src/robot_locomocion/bench_2wd_drv8833/README.md)
