# Locomoción

**Estado: PROYECTADO.** Esta carpeta es una reserva documental, no un paquete ROS 2 implementado.

## Propósito y alcance

El equipo es responsable de plataforma móvil, desplazamiento, localización, control y seguridad. No asumir que la plataforma puede moverse o navegar; no controla el manipulador ni decide el objetivo visual.

## Entradas y salidas conceptuales

Recibe solicitudes de posicionamiento y comunica estado o rechazo de forma acordada. Los mensajes, tópicos, estados y frecuencias están pendientes de acuerdo; no son interfaces implementadas.

## Dependencias y organización futura

Se prevén ROS 2 Jazzy y los contratos compartidos; Python, Gazebo Harmonic y sistemas embebidos se evaluarán según necesidad y compatibilidad. No se afirma que estén instalados o integrados. Cuando exista código, el equipo acordará la distribución de fuentes, configuración y pruebas dentro de un paquete real, con manifiesto y dependencias declaradas; no se anticipan directorios.

## Reproducción y pruebas

En esta etapa solo corresponde revisar documentos y ejecutar los verificadores disponibles según [entorno reproducible](../../../docs/entorno-reproducible.md). Cuando existan paquetes y entorno, registrar versiones, entradas y resultados de compilación y pruebas; no presentar un SKIP como validación. Documentar condiciones para permitir, detener o rechazar movimientos, límites, vigencia, supervisión y parada segura. No ejecutar desplazamientos físicos no autorizados.

Consulte las [instrucciones locales](AGENTS.md), la [política general](../../../AGENTS.md), la [integración](../../../docs/integracion/README.md) y los [contratos propuestos](../../../docs/interfaces/contratos-ros2.md).
