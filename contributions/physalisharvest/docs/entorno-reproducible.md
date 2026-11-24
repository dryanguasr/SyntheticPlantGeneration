# Entorno reproducible de referencia

**Estado: PROYECTADO.** Ubuntu 24.04 y ROS 2 Jazzy son la referencia para integración; Gazebo Harmonic es el objetivo de simulación cuando corresponda. Su presencia y compatibilidad en cada equipo requieren comprobación. Consulte la [documentación ROS 2](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html) y la [guía de Gazebo con ROS](https://gazebosim.org/docs/harmonic/ros_installation/).

Ubuntu nativo es la referencia Linux. En Windows nativo, use los verificadores Python cuando estén disponibles; no presuponga que los comandos Linux o el hardware funcionan igual. WSL2 ejecuta un entorno Linux separado: documente distribución, acceso a archivos, red, gráficos y dispositivos comprobados. No se ha validado paridad entre entornos.

## Comprobar sin instalar

Use el remoto `https://github.com/amayadiegoalejandro05/PhysalisHarvest.git`. En Ubuntu o WSL2, desde la raíz del clon:

```bash
git status --short --branch
git rev-parse HEAD
cat /etc/os-release
python3 --version
command -v ros2; command -v colcon; command -v gz
printenv ROS_DISTRO
gz sim --versions
python3 scripts/check_repository.py
python3 scripts/check_git_context.py --target main
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Si faltan herramientas, registre el resultado como pendiente; `ROS_DISTRO` solo refleja el entorno cargado. Consulte [verificación local](pruebas/verificacion-local.md) para PowerShell y límites de los scripts. El verificador de contexto puede fallar si hay cambios locales; sus referencias no prueban por sí solas el estado remoto.

## Workspace y evidencia

Los futuros paquetes reales residirán en `ros2_ws/src/` con `package.xml` y dependencias declaradas. Las cuatro carpetas actuales son reservas documentales. Solo cuando existan paquetes y dependencias verificadas, cargue el entorno Jazzy apropiado y, desde `ros2_ws`, considere `colcon build`, `colcon test --return-code-on-test-failure` y `colcon test-result --verbose`; registre cualquier fallo y no declare un build de paquetes inexistentes. No instale ni modifique entornos existentes sin acuerdo y plan reproducible.

Para cada ejecución registre SHA (`git rev-parse HEAD`), estado Git, SO, arquitectura, versión de ROS/Gazebo/Python, dependencias y sus versiones, configuración, entradas, comandos, logs, resultados y limitaciones. No publique secretos ni datos sensibles. Véanse [integración](integracion/README.md) y [CI](pruebas/ci.md).
