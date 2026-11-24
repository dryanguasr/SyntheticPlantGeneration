# Integración entre subsistemas

**Estado: PROYECTADO.** Visión propone objetivos y trayectorias; brazo decide factibilidad y ejecución; locomoción comunica y controla el estado de la plataforma. Las dependencias son conceptuales y no prueban comunicación real. La coordinación debe considerar posición y estado de la base antes de cualquier movimiento, según acuerdos futuros.

Los [contratos](../interfaces/contratos-ros2.md) y la [propuesta de integración](../interfaces/propuesta-integracion-ros2.md) no están aprobados. Antes de implementar una interfaz, los tres equipos deben acordar productor, consumidor, tipos, unidades, TF, tiempos y vigencia, QoS, estados, errores, cancelación y compatibilidad. Una recepción no autoriza actuación.

Para pruebas futuras de productor y consumidor: definir criterio de aceptación, versiones, ejemplos, mocks identificados, casos válidos e inválidos, pérdida de comunicación y datos vencidos; conservar comandos, logs y resultados. Una prueba de transporte no prueba seguridad física. Consulte [entorno reproducible](../entorno-reproducible.md) y [CI](../pruebas/ci.md).
