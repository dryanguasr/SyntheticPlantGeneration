# Propuesta de verificación local

Estado: implementación inicial para revisión de los equipos. Las comprobaciones son estáticas y de contexto Git; no demuestran funcionamiento de ROS, seguridad física ni ausencia completa de secretos. No se requiere ROS ni se instala software.

Desde la raíz del repositorio, en PowerShell:

```powershell
python scripts/check_repository.py --json reporte-repositorio.json
python scripts/check_git_context.py --target main --json reporte-git.json
python -m unittest discover -s tests -p "test_*.py" -v
```

En Ubuntu o WSL2:

```bash
python3 scripts/check_repository.py --json /tmp/reporte-repositorio.json
python3 scripts/check_git_context.py --target main --json /tmp/reporte-git.json
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

En PowerShell se recomienda guardar los informes fuera del repositorio o eliminarlos manualmente después de revisarlos. `--json` es opcional. Las pruebas usan repositorios temporales. Los comandos no hacen fetch ni modifican referencias. Para una comparación actualizada, verificar primero `origin` y ejecutar `git fetch origin` con autorización. Use `--target` con `main`, `feat/vision`, `feat/arm`, `feat/locomotion` y `feat/2WD` según el destino, y opcionalmente `--subsystem vision|brazo|locomocion`. Para `feat/2WD` el área es `locomocion`. Sin destino explícito, el verificador usa la base del PR en CI, `main` para una rama permanente o la rama del área si el nombre temporal la identifica sin ambigüedad.

Cada comprobación produce ID, PASS, FAIL o SKIP, explicación y acción. Un FAIL devuelve 1; una ejecución sin FAIL devuelve 0, incluso con SKIP. Errores de invocación o escritura del informe también producen salida distinta de cero. Un árbol con cambios sin confirmar o archivos no rastreados, incluido AGENTS.md local, se informa como SKIP en contexto Git para que se revise; no implica que sea indebido. Las comparaciones son contra referencias locales y no certifican su vigencia remota. En PR de GitHub Actions se identifica el HEAD separado y la comparación describe el commit comprobado, que puede ser un merge temporal, no la divergencia de la rama fuente.

El análisis YAML se omite si falta PyYAML; no instalarlo automáticamente. Los enlaces se comprueban de forma básica, sin validar anclas o todos los formatos Markdown. El control de secretos es heurístico, no muestra valores y no sustituye una herramienta especializada ni la revisión de Git. Todas las comprobaciones de archivos usan el mismo conjunto: archivos rastreados y no ignorados por Git. `.env.example` se admite como plantilla y los enlaces dentro de bloques de código no se validan; no se recorre el historial ni se verifica contenido binario. Se señalan archivos mayores de 10 MiB como criterio preventivo. XML se comprueba de forma básica, no se ejecuta `colcon` ni se valida el esquema completo ROS. La detección de correspondencia entre rama y subsistema depende del nombre y no prueba propiedad o procedencia.

## Sincronización y limitaciones

El verificador compara el destino y, si es otra rama, también `origin/main`, y clasifica sincronización, atraso o divergencia respecto a referencias locales. Un atraso, cambios locales o conflicto se informa como SKIP para no bloquear commits; fallos críticos como origen incorrecto siguen siendo FAIL. La detección de conflictos simula la integración de árboles confirmados con `git merge-tree --write-tree` (Git 2.38 o posterior) y guarda los objetos temporales fuera del repositorio; detecta también conflictos de borrado y renombrado, pero no cubre cambios locales. `GIT-INCOMING` señala archivos modificados a la vez en la rama y en el destino desde la base común. Los archivos compartidos detectados requieren revisión humana. Los resultados no prueban vigencia del servidor: una actualización explícita de referencias, cuando esté autorizada, precede a la comprobación actual. En PR con HEAD separado se reporta el merge temporal como tal. No hace fetch, merge, reset, rebase ni push.

Propuesta administrativa pendiente: proteger `main` con PR, CI estable, revisión humana, rama actualizada, conversaciones resueltas, bloqueo de force push y eliminación; evaluar excepciones administrativas y revisores disponibles para no bloquear al responsable único. Las reglas no se aplican mediante esta documentación ni por el script.

## Clasificación de rutas

`GIT-OWNERS` agrupa rutas internas de cada subsistema modificadas por la rama, sin contar los cambios que llegaron al destino; `GIT-SHARED` identifica rutas conocidas de interfaces, integración, TF común, CI y dependencias compartidas; `GIT-CROSS` señala combinaciones de varios subsistemas o un subsistema con rutas compartidas. Las rutas desconocidas aparecen en `GIT-OTHER` para revisión manual. La clasificación es heurística: archivos internos también pueden alterar contratos o TF y sus responsables deben examinar la semántica. Un PASS de Git no demuestra compatibilidad ROS.

## Sincronización inicial mediante PR

Para sincronizar ramas ya publicadas, después de la revisión e integración de cambios de política en `main`, aplique estos pasos a `feat/vision`, `feat/arm`, `feat/locomotion` y `feat/2WD`:

1. Conserve cambios locales; confirme `git remote -v`, estado, worktrees y, si hay autorización y conectividad, ejecute `git fetch origin`. Registre `git rev-parse origin/main` y `git rev-parse origin/<rama>`.
2. Inspeccione `git log --left-right --oneline origin/<rama>...origin/main` y `git diff --stat origin/<rama>...origin/main`; compruebe commits exclusivos y cambios en contratos, TF, dependencias y CI. Si aparecen commits nuevos del equipo o conflictos, detenga esa sincronización y coordine su revisión. No resuelva sobrescribiendo trabajo.
3. Abra un PR independiente con `main` como origen y el subsistema como destino. Registre ambos SHA, archivos afectados, pruebas y revisores. Revise conflictos, verificaciones CI y compatibilidad; no fusione automáticamente. Un fast-forward directo es una excepción que exige autorización específica.
4. Tras la revisión y fusión humana, actualice referencias y registre los SHA finales. Compruebe `git merge-base --is-ancestor origin/main origin/<rama>` si se integró el main actual y compare contenido con `git diff --name-status origin/main origin/<rama>`. Si el equipo tiene cambios propios, interprete diferencias y compruebe los archivos comunes por separado. Verifique AGENTS general y especializados, README, entorno, CI y scripts en un clon limpio y ejecute los verificadores disponibles.

Un merge commit puede dejar SHA diferentes aun cuando el contenido de los árboles sea idéntico. No use la igualdad de SHA como prueba única de igualdad de archivos; compare árboles o rutas y registre cualquier diferencia. El SHA final solo se conoce después de la integración humana.
