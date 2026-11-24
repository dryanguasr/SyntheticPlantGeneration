# Instrucciones: Visión y decisión

La política general está en [AGENTS.md](../../../AGENTS.md); las [interfaces propuestas](../../../docs/interfaces/contratos-ros2.md) aún requieren acuerdo. Las instrucciones locales la complementan; mantienen sus reglas de seguridad, IA, licencias y revisión.

## Alcance

Responsabilidad: RGB-D, detección del cáliz, XYZ superficial, accesibilidad, selección y trayectoria cartesiana candidata. No controla motores, no resuelve la cinemática del manipulador ni ejecuta cosecha. El XYZ del cáliz es un punto superficial, no el centro de la baya.

## Trabajo y evidencia

- Documentar unidades, calibración RGB-D y transformaciones; contrastar con una referencia independiente y declarar incertidumbre y límites. No usar verdad interna de simulación como percepción autónoma.
- Acuerde cambios compartidos con los equipos afectados antes de implementar contratos. No convierta recepción de datos en autorización de movimiento.
- Conserve trazabilidad de IA y licencias según la política general; no incorpore materiales externos sin comprobar derechos.
- Documente entorno, comandos, evidencia, fallos y limitaciones; distinga MOCK, simulación y pruebas físicas. No afirme validación sin criterios y evidencia.
- Use `feat/vision` como base y destino habitual de los PR del área.
- Solicite revisión según la política general; no altere experimentos o trabajo ajeno.

Antes de cada commit y PR aplique la preparación y la política de ramas de las secciones 1 y 4 de [AGENTS.md](../../../AGENTS.md), indicando destino y subsistema.
