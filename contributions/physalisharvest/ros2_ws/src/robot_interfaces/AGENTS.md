# Instrucciones: Interfaces compartidas

La política general está en [AGENTS.md](../../../AGENTS.md); las [interfaces propuestas](../../../docs/interfaces/contratos-ros2.md) aún requieren acuerdo. Las instrucciones locales la complementan; mantienen sus reglas de seguridad, IA, licencias y revisión.

## Alcance

Responsabilidad: definición futura y versionado de contratos entre visión, brazo y locomoción. No ejecuta control ni sustituye la validación de los subsistemas; aún no hay mensajes ROS definitivos.

## Trabajo y evidencia

- Exigir revisión conjunta de productores, consumidores e integración antes de cambiar mensajes, TF, QoS, estados o semántica. No introducir incompatibilidades por decisión unilateral; registrar versión, migración, pruebas y aprobación.
- Acuerde cambios compartidos con los equipos afectados antes de implementar contratos. No convierta recepción de datos en autorización de movimiento.
- Conserve trazabilidad de IA y licencias según la política general; no incorpore materiales externos sin comprobar derechos.
- Documente entorno, comandos, evidencia, fallos y limitaciones; distinga MOCK, simulación y pruebas físicas. No afirme validación sin criterios y evidencia.
- Coordine los PR de interfaces con los equipos afectados en `feat/vision`, `feat/arm`, `feat/locomotion` y, cuando corresponda, `feat/2WD`.
- Solicite revisión según la política general; no altere experimentos o trabajo ajeno.

Antes de cada commit y PR aplique la preparación y la política de ramas de las secciones 1 y 4 de [AGENTS.md](../../../AGENTS.md), indicando destino y subsistema.
