# Adaptación conjunta de plantas de uchuva

La escena de cultivo ya no interpreta individuos completamente independientes.
Después de generar los árboles morfológicos se ejecuta
`adapt_cultivation_morphologies`, una relajación pura y reproducible anterior a
Blender.

## Influencias representadas

- disponibilidad lateral de espacio y dirección de la vecina más cercana;
- crecimiento tangencial hacia huecos de una copa compartida;
- guía del eje principal hacia una estaca individual;
- carga reproductiva descendiente y brazo de palanca de cada eje;
- solapamiento permitido de hojas/copas, separado de colisión física.

La rutina ejecuta tres iteraciones acotadas. No es una simulación temporal ni
un modelo mecánico calibrado: cargas, rigidez y ángulos son
`manual_initial_guess_dataset_guided`. El resultado sí queda escrito en el
árbol: cada eje registra carga normalizada, influencia de vecinas, influencia
del tutor y deflexión mecánica.

## Tutores y condición de planta

Cada instancia tiene una estaca visible con dos o tres amarres. Estacas y
amarres se etiquetan como fondo y nunca producen cajas `calyx`; el contacto del
amarre con el tallo es intencional. El 8 % determinista de las instancias se
marca `drying`. Una planta sana conserva una única familia verde; una planta en
secado usa coherentemente una familia oliva/café en todos sus ejes.

## Validación

Las bases, ejes estructurales, capachos y estacas son restricciones duras. Las
hojas y copas pueden ocluirse visualmente. El reporte de adaptación enumera
ejes ajustados, pares de copas, soportes, contactos intencionales y colisiones
físicas por separado.

## Calibración densa estricta v3

`dense_staked_crop` crea exactamente 20 plantas reales en dos filas
escalonadas. Cada soporte usa sección rectangular, ancho igual a tres diámetros
máximos del tallo principal limitado a 0,08--0,14 unidades, profundidad 1,25
veces el ancho y dos o tres amarres. El antiguo
`procedural_non_uchuva_background` no se instancia.

Después de las tres iteraciones de cultivo, `collisions.py` construye un
registro global en coordenadas de escena. La fase amplia usa una rejilla
espacial; la fase estrecha distingue cápsulas, prismas orientados, elipsoides y
cajas orientadas. Ocho iteraciones modifican primero hojas y pedicelos y luego
ejes laterales. Una búsqueda discreta final evita oscilaciones entre dos poses,
elige un corredor vertical del tutor y vuelve a despejar los órganos cercanos.

Las uniones nodales, el fruto contenido por su capacho y los amarres son
contactos intencionales. Cualquier otro conflicto queda en
`collision_resolution.unresolved_pairs`. Blender no reorienta pedicelos ni
hojas: `audit_scene_mesh_collisions` comprueba las mallas evaluadas mediante
BVH y la escena falla cerradamente si el conteo exacto es distinto de cero.
El piloto prueba hasta 20 semillas iniciales derivadas de forma determinista;
sólo los rechazos por colisión física activan el siguiente intento.

La escena de aceptación `seed=1` registra 5.068 proxies, 1.258 ajustes, cero
conflictos proxy y cero interpenetraciones en 2.025 objetos auditados. Estas
cifras describen el piloto, no parámetros botánicos universales.
