# Frente C: puente de morfologia hacia Gazebo

Gazebo es un nuevo interprete de `Plant`, no una conversion del archivo
`.blend` ni una dependencia del nucleo morfologico. El paquete
`src/uchuva_gazebo/` es puro y genera un plan semantico por nivel de detalle:

- LOD 0: fondo visual sin fisica.
- LOD 1: tallos con colision simplificada para navegacion y percepcion.
- LOD 2: capachos objetivo y pedicelos como candidatos a interaccion y
  desprendimiento.

El plan semántico original no emite SDF: la morfologia actual no contiene poses de mundo ni
parametros biomecanicos medidos. Rigidez, amortiguamiento, masa, friccion y
umbral de desprendimiento permanecen como `engineering_heuristic` o
`to_be_measured`.

El primer entregable tecnico es un plan JSON y tres spikes: importacion visual,
sensores semanticos e interaccion minima. El repositorio del robot debera
consumir esos planes sin conocer la implementacion interna del generador.

## Campo estático ejecutable (2026-09-28)

La nueva línea autorizada añade un intérprete SDF separado del plan puro:
`src/uchuva_gazebo/field.py` ensambla el mundo en metros;
`scripts/export_gazebo_field.py` interpreta el JSON morfológico con Blender y
exporta mallas evaluadas, sin vegetación contextual ni plántulas triangulares.
Incluye 36 uchuvas, 72 ArUcos, tutorado y cámaras de inspección. La integración
del control de vuelo y la física de cosecha siguen pendientes.
Véase [la guía del campo](../guides/campo_gazebo.md).
