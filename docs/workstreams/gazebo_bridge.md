# Frente C: puente de morfologia hacia Gazebo

Gazebo es un nuevo interprete de `Plant`, no una conversion del archivo
`.blend` ni una dependencia del nucleo morfologico. El paquete
`src/uchuva_gazebo/` es puro y genera un plan semantico por nivel de detalle:

- LOD 0: fondo visual sin fisica.
- LOD 1: tallos con colision simplificada para navegacion y percepcion.
- LOD 2: capachos objetivo y pedicelos como candidatos a interaccion y
  desprendimiento.

El plan no emite SDF aun: la morfologia actual no contiene poses de mundo ni
parametros biomecanicos medidos. Rigidez, amortiguamiento, masa, friccion y
umbral de desprendimiento permanecen como `engineering_heuristic` o
`to_be_measured`.

El primer entregable tecnico es un plan JSON y tres spikes: importacion visual,
sensores semanticos e interaccion minima. El repositorio del robot debera
consumir esos planes sin conocer la implementacion interna del generador.
