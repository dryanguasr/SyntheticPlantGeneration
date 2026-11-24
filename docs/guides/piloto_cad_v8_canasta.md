# Piloto CAD V8 con canasta a bordo

El perfil de demostración conserva el CAD local de referencia y las tres plantas
V8 del manifiesto histórico. Añade una canasta abierta a bordo, dos envolventes
internas para baterías LiFePO₄ y una caja blanca para electrónica. Las masas y el
montaje de estos accesorios son hipótesis de la simulación. La pinza emplea una
mordaza prismática por esfuerzo y una oposición fija. Su abertura flexible de
6 mm se deriva del recorrido aproximado comunicado y de la geometría CAD cerrada.

La caja electrónica queda 50 mm hacia atrás respecto de la primera colocación
interna. Dos rieles la apoyan sobre abrazaderas instaladas en el travesaño
inferior CAD 119. La canasta conserva su posición y apoya sobre otros dos rieles
anclados al travesaño CAD 117. Los herrajes contribuyen a la inercia del chasis
y conservan colisión externa. Al cambiar sus posiciones, volver a verificar
las caras de apoyo y el espacio libre de baterías, suspensión y brazo.

## Preparar una revisión

Desde la raíz del repositorio, usar directorios de salida nuevos. Mantener el
reporte `derivation.json` junto al perfil y a sus mallas. El preparador guarda los
hashes y los parámetros efectivos. Para ajustar la carga o el montaje, partir de
`parameters.json` y regenerar el SDF y la auditoría geométrica de los accesorios.
El CAD y sus mallas permanecen en `outputs/`.

```text
python scripts/prepare_cad_v8_demo_robot.py --help
python scripts/screen_cad_v8_demo.py --profile <perfil> --asset-root <assets> --exact-calyx --output <criba.json>
python scripts/prepare_cad_v8_experiment.py --robot-directory <directorio-del-perfil> --cut-screen <criba.json> --rgb-comparison <resumen-rgb.json> --output <seleccion> --package <paquete>
```

La criba de herramienta es un filtro inicial. La selección contrasta después el
robot completo, la aproximación, la retirada y la ruta a la canasta. El informe
retiene las parejas limitantes. Un paquete parcial puede contener de uno a ocho
objetivos, con un máximo de tres por planta. Conservar sus resultados con el
número real de depósitos.

Para la demostración con la excepción de contacto, agregar
`--ignore-finger-blade-crop-contacts` a `prepare_cad_v8_experiment.py`. El
planificador y el SDF omiten el contacto del cultivo con los dedos CAD 104 y
106, las cuchillas 109 y 110, y las gomas montadas en los dedos 113 y 114. Los
soportes 111 y 112, la carcasa y la muñeca conservan sus colisiones. Se mantienen
las parejas de autocontacto, el contacto con la canasta y el suelo, y el umbral
de 4 mm. El manifiesto registra las parejas excluidas y las máscaras emitidas.
La omisión se usa para la demostración virtual.

Para la edición que también omite contactos del cultivo con la muñeca y la
carcasa, agregar `--ignore-wrist-housing-crop-contacts` junto al primer flag.
Esta edición incluye las dos piezas «Mordaza blanda» del Inventor, 111 y 112,
como componentes de los dedos. El manifiesto distingue la muñeca, la carcasa
y las piezas de mordaza. Las plantas, los límites de corte y los contactos
del brazo, chasis y canasta conservan la configuración vigente.
El cálculo de autocontacto reutiliza pares con la misma configuración
relativa en el árbol de articulaciones. Los segmentos aprobados conservan
el paso articular máximo de 0,004 rad. Las posiciones previas al corte
pueden variar su orientación, y la posición de corte conserva el eje del
pedicelo. Tras el corte, el tramo terminal virtual del fruto apartado
deja de ser un obstáculo fijo. El tramo proximal real permanece activo.
Cuando la esfera envolvente de un capacho vecino queda cerca del paso, se
consulta la malla cerrada derivada de su geometría V8, con el mismo margen.

La superficie cerrada del capacho V8 se usa como colisión en el perfil nuevo.
El cierre y corte idealizados reservan hasta 8 mm terminales del pedicelo elegido.
El tallo proximal sigue siendo rígido y los visuales mantienen sus posiciones.
El planificador conserva el tramo terminal como obstáculo virtual para el resto
del robot. Sólo las cuchillas y gomas identificadas pueden entrar en ese tramo
durante la interacción con el objetivo correspondiente. El criterio de 4 mm
permanece para las demás parejas. El latch es una restricción ideal observada y
no representa fractura del pedicelo ni fuerzas reales de agarre.

## Ejecutar y revisar evidencia

En WSL, con Gazebo Harmonic y FFmpeg instalados, preparar los plugins y empezar
por un fruto. Soltar sobre la apertura y verificar el asentamiento tras mover el
chasis. Lanzar nueve sólo después de un ciclo aceptado y con tres objetivos
admitidos por planta.

```sh
bash scripts/build_harvest_plugin.sh outputs/cad_v8_plugins
python3 scripts/run_harvest_pilot.py <paquete> --plugin-dir outputs/cad_v8_plugins --mode harvest --max-targets 1 --record-video --output <corrida-uno>
python3 scripts/audit_harvest_pilot.py <paquete> <corrida-uno>
python3 scripts/run_harvest_pilot.py <paquete> --plugin-dir outputs/cad_v8_plugins --mode harvest --max-targets 9 --single-cycle-audit <corrida-uno>/audit.json --record-video --output <corrida-nueve>
```

La auditoría une RGB y panóptico por tiempo nativo y contrasta los píxeles de
etiqueta con la observación registrada. El caso de respaldo se presenta como
**detección simulada**. La [guía de percepción](percepcion_cosecha_diagnostica.md)
describe la comparación RGB independiente. Las coordenadas de corte provienen
del simulador. El depósito se evalúa con la pose y geometría nativas del fruto
en el marco móvil de la canasta. La revisión física y los resultados simulados
quedan registrados por escenario y perfil.

## Toma continua con movimiento prescrito

El perfil de vídeo conserva las plantas y las mallas V8 del paquete verificado.
Las cinco fases son acercamiento del carro, acercamiento de la pinza, corte,
separación y depósito. El avance, las ruedas, el brazo y la mordaza siguen
trayectorias acotadas. El plugin de cosecha comprueba las guardas con poses
observadas y mantiene una sola restricción para sostener el fruto hasta la suelta.
La gravedad, la canasta, el suelo y el contacto entre frutos siguen activos.
La suspensión queda en la postura CAD y se omite la respuesta de contacto entre
el robot guiado y el cultivo. Los resultados corresponden a esta demostración
cinemática y se registran aparte del ensayo de actuación por fuerzas.

Usar un archivo de rutas que se refiera al hash del manifiesto de origen. Cada
objetivo conserva el identificador y eje de corte del paquete. La secuencia fija
un punto de suelta por encima del fondo y con el capacho libre dentro de la apertura.
El contador se genera a partir de la liberación aceptada y de las poses nativas
de los frutos que permanecen dentro al final.

```sh
bash scripts/build_harvest_plugin.sh outputs/cad_v8_demo_plugins
python3 scripts/prepare_cad_v8_demo_take.py <paquete> <rutas> <toma> --physics-step .004 --fps 12
python3 scripts/run_cad_v8_demo_capture.py <toma> --source-package <paquete> --plugin-dir outputs/cad_v8_demo_plugins --output <grabación> --compact
```

La edición compacta acorta los intervalos de desplazamiento y conserva los
fotogramas en orden. Los intervalos cercanos al corte y la suelta se reproducen
a velocidad original.
