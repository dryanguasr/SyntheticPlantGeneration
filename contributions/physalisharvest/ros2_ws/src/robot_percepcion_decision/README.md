# Visión y decisión

**Estado: PROYECTADO.** Esta carpeta es una reserva documental, no un paquete ROS 2 implementado.

## Propósito y alcance

El equipo es responsable de RGB-D, detección del cáliz, XYZ superficial, accesibilidad, selección y trayectoria cartesiana candidata. No controla motores, no resuelve la cinemática del manipulador ni ejecuta cosecha. El XYZ del cáliz es un punto superficial, no el centro de la baya.

## Entradas y salidas conceptuales

Recibe imágenes y profundidad y, cuando exista, calibración; propone objetivo y trayectoria con marco, instante y vigencia. Los mensajes, tópicos, estados y frecuencias están pendientes de acuerdo; no son interfaces implementadas.

## Dependencias y organización futura

Se prevén ROS 2 Jazzy y los contratos compartidos; Python, Gazebo Harmonic y sistemas embebidos se evaluarán según necesidad y compatibilidad. No se afirma que estén instalados o integrados. Cuando exista código, el equipo acordará la distribución de fuentes, configuración y pruebas dentro de un paquete real, con manifiesto y dependencias declaradas; no se anticipan directorios.

## Reproducción y pruebas

En esta etapa solo corresponde revisar documentos y ejecutar los verificadores disponibles según [entorno reproducible](../../../docs/entorno-reproducible.md). Cuando existan paquetes y entorno, registrar versiones, entradas y resultados de compilación y pruebas; no presentar un SKIP como validación. Documentar unidades, calibración RGB-D y transformaciones; contrastar con una referencia independiente y declarar incertidumbre y límites. No usar verdad interna de simulación como percepción autónoma.

Consulte las [instrucciones locales](AGENTS.md), la [política general](../../../AGENTS.md), la [integración](../../../docs/integracion/README.md) y los [contratos propuestos](../../../docs/interfaces/contratos-ros2.md).
