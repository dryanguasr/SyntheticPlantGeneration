# Ensayos ESP32 del banco 2WD

El firmware actual para un marcador ArUco está en
[`drv8833_ros`](drv8833_ros/drv8833_ros.ino). Su cableado, contrato y
procedimiento están en la [guía DRV8833](../../ros2_ws/src/robot_locomocion/bench_2wd_drv8833/README.md).
Los ensayos descritos más abajo son antecedentes del banco.

Este directorio conserva el código desarrollado con asistencia de Codex y los registros textuales de los ensayos del 19 de noviembre de 2026. El montaje y la observación de las ruedas estuvieron a cargo del operador. El [paquete ROS 2](../../ros2_ws/src/robot_locomocion/bench_2wd/README.md) describe el cableado declarado, la calibración externa y la reproducción de F0.

## Reproducción

Entorno ensayado: Windows y Ubuntu 24.04 sobre WSL 2, ROS 2 Jazzy, Arduino ESP32 3.3.12, placa `esp32:esp32:esp32` con ESP32-D0WD-V3, Python 3.11 y pySerial 3.5. El ESP32 se conectó por CP210x en COM3 a 115200 bit/s. Los scripts de los ensayos históricos usan COM3. Para la cámara se usó la Astra Pro con OpenNI 2.3.0.86 x64 y DirectShow índice 1.

Desde la raíz del repositorio, con Arduino CLI y el núcleo indicado instalados:

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/bench_2wd/motor_both_full
```

Con la potencia del driver apagada, seleccionar el puerto real y coordinar la carga y los botones BOOT/EN con el operador. Tras cargar el sketch, la consulta por defecto del cliente comprueba la identidad del firmware y termina con una orden de parada:

```powershell
python firmware/bench_2wd/tools/motor_both_full_serial.py --port COM3
```

El cliente reserva `--run` para un ciclo deliberado y supervisado. Antes de usarlo, verificar el cableado revisado, GND común, el límite de corriente del montaje, chasis inmovilizado, ruedas libres y corte de potencia al alcance. Con potencia apagada, el mismo comando permite comprobar la secuencia lógica. Con potencia habilitada, las ruedas pueden moverse. El ESP32 acepta un ciclo por reinicio, exige armado manual y vuelve a bajo por `STOP` o si deja de recibir `KEEP` durante 300 ms. El límite de 0,25 A usado en el ensayo fue un ajuste de la fuente, externo al firmware. El paro físico sigue siendo el medio de corte independiente.

Para repetir el eco Astra y la secuencia en seco, ejecutar los siguientes comandos desde la raíz en Windows, cada uno con su propio sketch cargado y los 6 V apagados. Usar el entorno de captura indicado en el README del paquete ROS. Los scripts reutilizan el clon hermano `COORDENADAS_ORBBECASTRA`, su matriz local verificada por SHA-256 y el nombre de distribución `Ubuntu-24.04`. Ajustar las rutas e índice RGB si cambia el entorno.

```powershell
python firmware/bench_2wd/tools/camera_xyz_bench.py
python firmware/bench_2wd/tools/camera_sequence_dry.py --arm-dry
```

## Evidencia y límites

| Sketch o prueba | Resultado observado |
| --- | --- |
| Calibración Astra | Una captura de caja a 640 × 480 y dos esquinas superiores anotadas visualmente. RMS de 21,07 a 4,61 px. Exactitud 3D y repetibilidad pendientes. [Medición](evidence/astra-resultados.txt) |
| `xyz_echo` | Una muestra real llegó a `/astra/xyz` y el ESP32 devolvió el XYZ coincidente a seis decimales. La política de ejecución de PowerShell impidió usar el primer lector serie. La repetición con pySerial pasó. [Eco](evidence/astra-ros-esp32-resultado.txt) |
| `motor_gpio_check` | Tras reinicio manual, se leyeron GPIO 25/26/27/14 en bajo por COM3. [Lectura](evidence/motor-gpio-resultado.txt) |
| `motor_sequence_dry` | Muestra real, rechazo sin habilitación, secuencia lógica de 1.000/250/1.000 ms, pérdida de enlace a 500 ms y cancelación manual. Los GPIO se leyeron en bajo. [Traza](evidence/motor-secuencia-seca.txt) |
| `motor_pulse_check` y `motor_pulse_check_2` | Pulsos izquierdos a 1 kHz, de 100 ms al 20 % y 150 ms al 35 %. El ESP32 confirmó inicio y fin. El operador no distinguió giro. |
| `motor_pwm_10khz` y `motor_pwm_10khz_right` | A 10 kHz y 35 %, la primera lectura inmediata de LEDC mostró el ciclo anterior al entrar en pausa o parada. La revisión con 300 microsegundos antes de la lectura confirmó cero. Con potencia, el giro izquierdo fue leve e indeterminado y el derecho no fue visible. El operador reportó cerca de 6 V en VM bajo ensayo y lecturas de magnitud aproximada de 0,25 V en las salidas derechas con PWM. [Repetición](evidence/motor-pwm-10khz-verificado.txt) |
| `motor_right_no_load` | Diagnóstico al 100 % en el canal derecho, con el motor desconectado. La telemetría confirmó señales y tiempos. La tensión diferencial en vacío quedó sin registro cuantitativo. [Traza](evidence/motor-derecho-100-sin-carga.txt) |
| `motor_both_full` | Ambos motores, un segundo al 100 % en el primer sentido, 250 ms en bajo y un segundo al 100 % en el sentido contrario. El operador confirmó el giro esperado y el ESP32 registró parada con los cuatro GPIO en bajo. Al 100 % la señal activa queda en alto continuo. [Traza](evidence/motor-both-full-ensayo.txt) |

La etiqueta serial `FORWARD` corresponde a GPIO 25 y 27 en alto, y `REVERSE` a GPIO 26 y 14. Se mantiene la polaridad observada en este montaje. Volver a comprobarla tras cambiar el cableado. Los registros no incluyen imágenes, calibración privada ni binarios. La observación física del giro fue cualitativa. La corriente del motor, la tensión instantánea de salida, la velocidad y la distancia de frenado quedaron pendientes de caracterización.

La etapa actual emplea un marcador ArUco fijo. La extrínseca de cámara,
la distancia final de parada, el accionamiento mínimo y la gestión de
obstáculos siguen pendientes para ensayos con desplazamiento.
