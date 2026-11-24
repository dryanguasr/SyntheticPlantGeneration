# Interfaces compartidas

**Estado: PROYECTADO.** Esta carpeta es una reserva documental, no un paquete ROS 2 implementado.

## Propósito y alcance

El equipo es responsable de definición futura y versionado de contratos entre visión, brazo y locomoción. No ejecuta control ni sustituye la validación de los subsistemas; aún no hay mensajes ROS definitivos.

## Entradas y salidas conceptuales

Recibe requisitos de productores y consumidores; ofrecerá contratos únicamente cuando sean aprobados. Los mensajes, tópicos, estados y frecuencias están pendientes de acuerdo; no son interfaces implementadas.

## Dependencias y organización futura

Se prevén ROS 2 Jazzy y los contratos compartidos; Python, Gazebo Harmonic y sistemas embebidos se evaluarán según necesidad y compatibilidad. No se afirma que estén instalados o integrados. Cuando exista código, el equipo acordará la distribución de fuentes, configuración y pruebas dentro de un paquete real, con manifiesto y dependencias declaradas; no se anticipan directorios.

## Reproducción y pruebas

En esta etapa solo corresponde revisar documentos y ejecutar los verificadores disponibles según [entorno reproducible](../../../docs/entorno-reproducible.md). Cuando existan paquetes y entorno, registrar versiones, entradas y resultados de compilación y pruebas; no presentar un SKIP como validación. Exigir revisión conjunta de productores, consumidores e integración antes de cambiar mensajes, TF, QoS, estados o semántica. No introducir incompatibilidades por decisión unilateral; registrar versión, migración, pruebas y aprobación.

Consulte las [instrucciones locales](AGENTS.md), la [política general](../../../AGENTS.md), la [integración](../../../docs/integracion/README.md) y los [contratos propuestos](../../../docs/interfaces/contratos-ros2.md).
