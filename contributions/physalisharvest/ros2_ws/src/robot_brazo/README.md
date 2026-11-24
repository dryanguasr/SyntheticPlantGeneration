# Brazo

**Estado: PROYECTADO.** Esta carpeta es una reserva documental, no un paquete ROS 2 implementado.

## Propósito y alcance

El equipo es responsable de modelado, cinemática, límites, control, efector y seguridad del manipulador. Una trayectoria recibida no es factible ni ejecutada por defecto; no le corresponde seleccionar visualmente el fruto.

## Entradas y salidas conceptuales

Recibe propuestas de objetivos o trayectorias; evalúa factibilidad y comunica aceptación, rechazo, estado o error. Los mensajes, tópicos, estados y frecuencias están pendientes de acuerdo; no son interfaces implementadas.

## Dependencias y organización futura

Se prevén ROS 2 Jazzy y los contratos compartidos; Python, Gazebo Harmonic y sistemas embebidos se evaluarán según necesidad y compatibilidad. No se afirma que estén instalados o integrados. Cuando exista código, el equipo acordará la distribución de fuentes, configuración y pruebas dentro de un paquete real, con manifiesto y dependencias declaradas; no se anticipan directorios.

## Reproducción y pruebas

En esta etapa solo corresponde revisar documentos y ejecutar los verificadores disponibles según [entorno reproducible](../../../docs/entorno-reproducible.md). Cuando existan paquetes y entorno, registrar versiones, entradas y resultados de compilación y pruebas; no presentar un SKIP como validación. Validar límites, marco, vigencia y factibilidad; documentar rechazo, confirmación, supervisión y parada segura antes de cualquier movimiento autorizado.

Consulte las [instrucciones locales](AGENTS.md), la [política general](../../../AGENTS.md), la [integración](../../../docs/integracion/README.md) y los [contratos propuestos](../../../docs/interfaces/contratos-ros2.md).
