# Instrucciones: Brazo

La política general está en [AGENTS.md](../../../AGENTS.md); las [interfaces propuestas](../../../docs/interfaces/contratos-ros2.md) aún requieren acuerdo. Las instrucciones locales la complementan; mantienen sus reglas de seguridad, IA, licencias y revisión.

## Alcance

Responsabilidad: modelado, cinemática, límites, control, efector y seguridad del manipulador. Una trayectoria recibida no es factible ni ejecutada por defecto; no le corresponde seleccionar visualmente el fruto.

## Trabajo y evidencia

- Validar límites, marco, vigencia y factibilidad; documentar rechazo, confirmación, supervisión y parada segura antes de cualquier movimiento autorizado.
- Acuerde cambios compartidos con los equipos afectados antes de implementar contratos. No convierta recepción de datos en autorización de movimiento.
- Conserve trazabilidad de IA y licencias según la política general; no incorpore materiales externos sin comprobar derechos.
- Documente entorno, comandos, evidencia, fallos y limitaciones; distinga MOCK, simulación y pruebas físicas. No afirme validación sin criterios y evidencia.
- Use `feat/arm` como base y destino habitual de los PR del área.
- Solicite revisión según la política general; no altere experimentos o trabajo ajeno.

Antes de cada commit y PR aplique la preparación y la política de ramas de las secciones 1 y 4 de [AGENTS.md](../../../AGENTS.md), indicando destino y subsistema.
