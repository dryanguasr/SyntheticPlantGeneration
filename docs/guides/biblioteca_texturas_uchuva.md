# Modelo inicial de texturas de hoja y capacho de uchuva

## Alcance

Esta primera etapa reemplaza el ruido visual genérico por una red vascular 2D
reproducible. La geometría morfológica continúa definiendo la silueta; los
mapas de albedo, altura, normal, rugosidad y máscara de venas aportan el relieve
fino sin crear miles de venas como objetos 3D.

Los valores con estado `literature_reported` provienen de mediciones o
descripciones publicadas. Los valores `dataset_inferred_camera_srgb` se
estimaron de las imágenes JPEG de `Dataset Original/` y por ello mezclan
albedo, luz, exposición, balance de blancos y respuesta de cámara. No deben
presentarse como espectros de reflectancia intrínseca.

## Taxonomía vascular implementada

### Hoja

El estudio de arquitectura foliar de Bhat et al. describe *P. peruviana* con:

- vena primaria suprabasal;
- 5–7 venas laterales por lado;
- secundarias semicraspedódromas y de ángulo agudo respecto de la primaria;
- terciarias alternas percurrentes, de curso sinuoso;
- cuaternarias reticulares poligonales regulares;
- areolas moderadamente desarrolladas y terminaciones libres con dos o más
  ramificaciones;
- orden máximo observado: cuarto.

La hoja es además pubescente, anfistomática y tiene estomas anomocíticos; se
reportaron 29,68 estomas/mm² en la superficie adaxial y 43,33 estomas/mm² en la
abaxial. La textura v1 modela la pubescencia como microrelieve y respuesta de
reflexión, no como pelos individuales. Fuente primaria:
[Bhat et al., 2018](https://www.plantarchives.org/18-02/2229-2238%20%284374%29.pdf).

### Capacho

El tratamiento taxonómico de Kew describe el cáliz fructífero como ovoide,
reticulado, persistentemente piloso, normalmente 10-costillado o ligeramente
10-angulado; al madurar puede ser amarillo oscuro, con base y venación
púrpuras. La interpretación v1 separa cinco nervios medios dominantes de los
sépalos y cinco nervios intercostales más débiles, enlazados por una red
reticular. Esto coincide también con el patrón repetido visible en las cajas
del dataset. Fuente:
[Plants of the World Online, Kew](https://powo.science.kew.org/taxon/urn%3Alsid%3Aipni.org%3Anames%3A195473-2/general-information).

## Colorimetría

Rodrigues et al. midieron el cáliz a 20, 27, 34 y 41 días después de antesis.
Reportaron medias globales `L*=52,53`, `C*=31,34`, `h°=94,91`, y un aumento
lineal de luminosidad de 26 % hasta `L*=61,90` a 41 días. Es una restricción
útil para la progresión verde → amarilla, pero no proporciona un albedo RGB
directamente utilizable en Blender. Fuente primaria:
[Rodrigues et al., 2021](https://ojs.uel.br/revistas/uel/index.php/semagrarias/article/download/40197/29151).

La calibración local tomó, sin modificar el dataset:

- una muestra determinista de 400 imágenes y 300.000 píxeles verdes para
  follaje; mediana sRGB `(111, 136, 74)`;
- 800 de las 3.820 cajas de capacho; medianas de los cuatro grupos cromáticos
  principales `(81,94,37)`, `(122,125,60)`, `(164,164,94)` y
  `(199,192,133)`.

Los colores base elegidos se mantienen dentro de esos rangos, con menor
saturación que los materiales anteriores:

| Preset | sRGB base | CIELAB D65 aproximado | Estado |
|---|---:|---:|---|
| `leaf_healthy` | 105, 132, 74 | 51,8; -20,3; 28,2 | inferido del dataset |
| `leaf_senescent` | 151, 145, 72 | 59,2; -8,1; 39,1 | estimación inicial |
| `calyx_green` | 125, 141, 70 | 55,9; -17,3; 35,7 | inferido del dataset |
| `calyx_straw` | 199, 186, 121 | 75,2; -4,8; 34,6 | inferido del dataset |
| `calyx_dry` | 168, 145, 103 | 61,3; 2,5; 25,5 | inferido del dataset |

Las conversiones CIELAB son las del color sRGB digital elegido, no lecturas
directas de órganos reales.

## Reflexión y microrelieve

No se encontró una medición BRDF específica de hoja o capacho sano de esta
colección de uchuva. Sí existe una medición hiperespectral directa sobre hojas
de *P. peruviana*: las plantas control mantuvieron reflectancia visible cercana
a 0,10, mientras la enfermedad elevó la reflectancia hasta 0,32. La v1 usa ese
resultado como restricción cualitativa de hoja sana oscura, no como textura
espectral completa. Fuente primaria:
[Giraldo-Betancourt et al., 2020](https://doi.org/10.17584/rcch.2020v14i3.10938).

Como límite físico de referencia, mediciones BRDF en otras hojas obtuvieron
parámetros de rugosidad de 0,078 (laurel), 0,29 (haya) y 0,46 (avellano
piloso), con índices efectivos de refracción de 1,22, 1,56 y 1,68. El mismo
trabajo cita aproximadamente 1,48 para cera foliar y pelos vivos. Esos
parámetros no son numéricamente equivalentes al control `Roughness` del shader
Principled de Blender. Fuente primaria:
[Bousquet et al., 2005](https://www.ipgp.fr/~jacquemoud/publications/bousquet2005a.pdf).

La configuración inicial, por tanto, queda explícitamente como aproximación:

| Preset | Roughness Principled | IOR | Subsurface | Sheen | Estado |
|---|---:|---:|---:|---:|---|
| `leaf_healthy` | 0,64 ± 0,045 | 1,45 | 0,045 | 0,12 | acotado por literatura |
| `leaf_senescent` | 0,72 ± 0,055 | 1,45 | 0,030 | 0,08 | estimación inicial |
| `calyx_green` | 0,68 ± 0,055 | 1,45 | 0,055 | 0,13 | estimación inicial |
| `calyx_straw` | 0,74 ± 0,065 | 1,45 | 0,035 | 0,09 | estimación inicial |
| `calyx_dry` | 0,82 ± 0,075 | 1,45 | 0,012 | 0,045 | estimación inicial |

## Activos y regeneración

La primera biblioteca versionada se conserva en
`assets/textures/legacy/uchuva_v1/`. Cada preset
incluye:

- `albedo`: color sRGB;
- `height`: relieve escalar auditable;
- `normal`: normal tangente derivada de la altura;
- `roughness`: rugosidad espacial en datos lineales;
- `vein_mask`: máscara escalar de la red;
- `vein_debug`: órdenes vasculares codificados por color.

Regeneración determinista, sin Blender ni dependencias externas:

```powershell
python scripts/generate_uchuva_texture_library.py --seed 1701 --resolution 512
```

`manifest.json` registra versión, semilla, resolución, taxonomía, parámetros,
estado de evidencia y SHA-256 de cada PNG. Blender carga estos mapas por UV y
conserva el shader procedural anterior únicamente como fallback si los activos
no están disponibles.

## Próxima medición recomendada

Para convertir las estimaciones en parámetros `to_be_measured` se requiere una
carta de color y un patrón de reflectancia mate en la misma iluminación que las
plantas, además de fotografías RAW de haz y envés y de los tres estados del
capacho. Una segunda fase ideal añadiría espectros 400–700 nm y una serie
multiángulo para ajustar BRDF; no es válido recuperar rugosidad física sólo a
partir de JPEG sin calibración.

## Calibración v2 basada en 0007, 0022, 0062 y 0079

La calibración v2 se conserva en `assets/textures/legacy/uchuva_v2/`; v1 no
se sobrescribió. Los cambios históricos fueron:

- cuatro variantes verdes con contraste vascular 0,30--0,90;
- tres variantes pajizas y tres secas;
- oscurecimiento apical localizado en el primer 20--25 % del UV del capacho;
- reducción independiente del relieve de las venas primarias, sin perder el
  contraste cromático ni la retícula fina;
- hojas oscuras y mates, con roughness 0,78--0,90, sheen máximo 0,05 y menor
  normal vascular.

La relación alto/ancho medida sobre las cajas de las cuatro referencias queda
entre 1,14 y 1,53, con mediana aproximada 1,37. El generador usa 1,15--1,55 y
marca este rango como `dataset_inferred_camera_bbox`, no como constante
botánica. El perfil geométrico asociado es `lantern_squash`.

## Calibración v3 mate y depresiones intercostales

La biblioteca activa es `assets/textures/current/`; v1 y v2 permanecen
intactas bajo `assets/textures/legacy/` para comparación. Las hojas usan
`Roughness` 0,92--0,96. Los capachos
verdes usan 0,93--0,97 y los estados pajizo/seco al menos 0,94. En todos los
materiales orgánicos `Coat=0`, `Sheen=0`, transmisión nula,
`Subsurface <= 0,005` y `Specular IOR Level <= 0,15`.

La silueta del capacho conserva crestas discretas de 2,5--3,5 %, pero añade
depresiones intercostales hacia dentro: 7--10 % en verdes, 5--7 % en pajizos y
4--6 % en secos. La retícula vascular continúa principalmente en albedo y
normal, sin curvas 3D superpuestas.

Las hojas ignoran `curl`, `twist_deg` y `margin` durante la interpretación
geométrica. Ambos bordes comparten altura; la única deformación fuera del plano
es una caída cuadrática y monótona a lo largo del nervio central. La silueta
transversal usa un perfil polinómico suave sin términos periódicos.

## Calibración v4: superficie papirácea y variación no periódica

La biblioteca activa `assets/textures/current/` usa el generador `0.4.3`. Esta
iteración responde a la revisión comparativa en la que los capachos sintéticos
mostraban una apariencia plástica y ondulaciones regulares ausentes en las
referencias naturales.

- El albedo y la rugosidad reciben variación espacial coherente y no periódica;
  se retiraron las rejillas sinusoidales visibles de escala media.
- La normal vascular aplicada en Blender queda entre `0.22` y `0.28` para
  capachos verdes, `0.24` y `0.28` para pajizos, y `0.28` y `0.34` para secos.
  El material vuelve a limitarla por órgano para que la venación se lea
  principalmente por color, no como un grabado profundo.
- La revisión 0.4.1 reduce además la mezcla cromática de los cinco nervios
  dominantes. Permanecen legibles, pero dejan de formar bandas negras en los
  verdes de mayor contraste.
- La revisión 0.4.2 recupera nervadura clara y variación de rugosidad en las
  hojas manteniendo `sheen=0` y peso subsuperficial máximo de 0,005. La mejora
  de lectura se apoya en color y microrelieve, sin añadir una respuesta cerosa.
- La revisión 0.4.3 aumenta la densidad y el contraste cromático de la red
  vascular del capacho, cambia su muestreo a interpolación lineal y añade
  microrrelieve de baja amplitud para evitar la lectura plástica sin inventar
  ondulaciones periódicas de la pared.
- La depresión intercostal geométrica se mantiene acotada a 1,4--2,4 % en
  verde, 1,3--2,3 % en pajizo y 1,2--2,1 % en seco. Las cinco crestas
  estructurales quedan en 5,5--8,0 % para recuperar la lectura del sépalo sin
  reintroducir macroarrugas.
- Se eliminan las macroarrugas periódicas. Los estados pajizo y seco pueden
  recibir pocos pliegues localizados, correlacionados por sépalo; el estado
  verde no los recibe.
- La lámina foliar vuelve a interpretar margen, torsión, acopamiento y daño
  localizado con amplitud acotada. El espesor renderizado pasa de una constante
  de 3 mm a 0,12--0,35 mm, todavía etiquetado como `manual_initial_guess`.

Estos controles son hipótesis de ingeniería orientadas a cerrar la brecha
visual. No equivalen a una medición de espesor, rugosidad física o BRDF. El
cuestionario para expertos solicita precisamente esas mediciones y fotografías
calibradas antes de promover los valores a evidencia botánica local.

## Calibración v5: variantes condicionadas por madurez

La biblioteca activa usa el generador `0.5.0` y contiene 14 conjuntos. Añade
variantes `transitioning_yellow` y deja de escoger de manera uniforme entre
todos los estados del capacho. `literature_cohort_v1` selecciona únicamente
variantes compatibles con el progreso continuo de maduración de cada unidad.

La madurez compartida condiciona albedo, rugosidad, normal vascular,
pubescencia visual y los rasgos geométricos de turgencia, inflación, asimetría
y pliegues. Las variantes siguen siendo procedurales y no contienen recortes
del dataset real. `legacy_independent` mantiene la selección histórica para
comparaciones controladas.

Esta revisión elimina la contracción adicional por etiqueta fenológica: el
cambio de tamaño se aplica una sola vez a partir del área relativa continua.
Así se evita que textura, etapa discreta y geometría reduzcan simultáneamente
el mismo capacho y generen un encogimiento u ondulación artificial.
