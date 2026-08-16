# Decisiones tecnicas

## 2026-07-09 - Migracion estructural inicial

- Se creo la estructura `src/uchuva_lsystem/`, `scripts/`, `docs/`,
  `examples/`, `legacy/` y `outputs/`.
- No se encontro `planta_procedural_v05.py` como archivo `.py` suelto en la raiz
  del proyecto durante la primera busqueda.
- Luego se verifico que `planta_code_01.blend` contiene el script version 0.5
  como Text Block interno. Se recupero una copia canonica en
  `legacy/prototypes/generic_blender_plant_v0_5.py`.
- Se movio `referencias_uchuva_lsystem.bib` a `docs/`.
- Los JSON generados `plant_specs_seed_*.json` que estaban en la raiz se
  movieron a `outputs/specs/` para mantener la raiz orientada a codigo y docs.
- Los archivos `planta_code_01.blend` y `planta_code_01.blend1` se conservan
  como `legacy/prototypes/generic_blender_plant_v0_5.blend` y
  `legacy/prototypes/generic_blender_plant_v0_3_backup.blend1`.
- Se verifico que ambos archivos `.blend` pueden abrirse con Blender 5.1 en
  modo background y que contienen un Text Block Python recuperable.
- Se exportaron esos Text Blocks a `legacy/extracted_scripts/` para que el
  código legacy quede disponible como texto plano.
- No se agregaron dependencias externas ni tooling de paquete.

## 2026-07-09 - Separacion planta individual vs escena de cultivo

- Se separa explicitamente `Plant L-System` de `CultivationScene`.
- `Plant L-System` representa un individuo de uchuva: eje principal, ramas
  moderadas, nodos, hojas, yemas axilares y unidades reproductivas.
- `CultivationScene` representa cultivo, hilera, cama, camara, fondo vegetal y
  superposicion de multiples plantas.
- Una planta individual no debe inflarse artificialmente para explicar una
  escena ancha o densa. Si se necesita apariencia arbustiva de cultivo, debe
  venir de varias `PlantInstance`, manejo agronomico, tutorado, poda, canopia y
  posicion de camara.
- Se agrego `src/uchuva_lsystem/scene.py` con stubs serializables para
  `CultivationScene` y `PlantInstance`.
- Se documentan tres presets conceptuales:
  `single_plant_study`, `foreground_plant_with_neighbors` y `row_canopy`.
  El modo `row_canopy` queda reservado para mas adelante y no debe usarse para
  calibrar la morfologia inicial.

## 2026-07-09 - Capacho de uchuva como modelo hibrido

- El capacho no se modelara como esfera visible con varillas rectas.
- La geometria debe representar solo lo que afecta silueta, sombras y lectura
  3D: forma inflada, lobulos principales, costillas longitudinales principales,
  apertura parcial y cierre inferior.
- La venacion secundaria fina, manchas, envejecimiento, variacion pardo/verde/
  amarillo se delegan a materiales o texturas procedurales.
- Se agregaron parametros explicitos para `ribs`, `openness`, `inflation`,
  `fruit_visibility` y `calyx_state`.
- El fruto queda dentro del volumen del capacho y su visibilidad se controla
  como `hidden`, `partial` o `visible`, asociada al mismo
  `ReproductiveUnit`.

## 2026-07-09 - Escena multi-planta inicial

- Se implemento una escena de 10 plantas con el preset
  `foreground_plant_with_neighbors`.
- La politica inicial es `canopy_permissive`: se evitan colisiones fisicas
  graves de base/tallo/capacho, pero se permite la oclusion visual entre hojas
  y canopia.
- Cada planta individual mantiene una carga objetivo de 4 a 8 unidades con
  fruto y capacho. Las flores adicionales pueden coexistir como mezcla
  fenologica.
- La escena usa dos hileras escalonadas con jitter de posicion, rotacion y
  escala por `PlantInstance`.
- Las venas menores de hojas, manchas del capacho y textura del fruto se
  modelan con materiales procedurales de ruido/bump, no como geometria fina.

## 2026-07-09 - Limpieza visual, luz exterior y curvatura

- La escena multi-planta ya no deja los organos parentados a `Empty` visibles,
  porque Blender muestra esas relaciones como lineas punteadas negras en el
  viewport. Las plantas se organizan por coleccion y las transformaciones de
  instancia se aplican directamente a los objetos.
- Los `Empty` de raiz se conservan ocultos solo como referencia liviana de
  instancia, sin hijos, para evitar lineas de construccion visibles.
- La iluminacion se cambio a una luz de area lejana y aleatorizada por semilla,
  con posicion, energia y tamano acordes con una escena abierta.
- Tallo y ramas usan curvas 3D con una caida gravitacional suave segun su
  horizontalidad. Las hojas incorporan una curvatura longitudinal mayor cuando
  su orientacion es mas plana.

## 2026-07-09 - Capachos cerrados, venacion y colisiones finas

- Se fija temporalmente `openness = 0.0` para todos los capachos. La visibilidad
  marginal del fruto queda pospuesta hasta evaluar si conviene abrir el
  capacho en una iteracion posterior.
- Los frutos se mantienen en el arbol morfologico, pero se ocultan en Blender
  cuando estan dentro de un capacho cerrado.
- `exposed_fruit` se mapea temporalmente a un capacho cerrado seco o
  deteriorado (`dry_deteriorated`) para conservar mezcla fenologica sin crear
  aperturas.
- Los materiales del capacho son opacos. La lectura de maduracion se controla
  por color, rugosidad, venacion secundaria procedural y manchas, no por
  transparencia.
- La nervadura primaria de la hoja usa la misma linea central curvada que la
  lamina y termina en el apice.
- Se agregan proxies locales para mitigar choques de capacho con tallos,
  peciolos, hojas y otros capachos antes de crear la geometria final.

## 2026-07-14 - Piloto contextual listo para anotaciones

- Se agrega `annotation_foreground_pilot`: una planta objetivo y entre dos y
  cuatro vecinas parciales. `PlantInstance.role` diferencia `foreground` de
  `neighbor` sin mezclar la composicion de escena con la gramatica individual.
- El entorno usa terreno y residuos procedurales, textura PBR de suelo `Brown
  Mud` y HDRI `Farmland Overcast` a 2K. Los cuatro archivos son CC0, se verifican
  por hash y se empaquetan dentro del `.blend`.
- La vegetacion generica de fondo pertenece a la clase `background`; no se
  interpreta como una planta de uchuva ni entra en la validacion morfologica.
- Se crean tres perfiles reproducibles: `robot_close_oblique`,
  `human_oblique_mid` y `context_wide`. EEVEE y Cycles comparten pose, geometria,
  mundo e iluminacion; la profundidad de campo se aplica solo al RGB.
- Cada objeto renderizable lleva propiedades persistentes para clase semantica,
  instancia de planta, organo e instancia reproductiva. Pecíolo se agrupa con
  `stem`, nervadura primaria con `leaf` y costillas con `calyx`.
- Las mascaras se generan con materiales emisivos temporales y paletas exactas.
  Se exportan mascara semantica, instancia de planta e instancia reproductiva,
  junto con cajas visibles, conteo de pixeles y un proxy de oclusion basado en
  ocupacion de la caja.
- El proxy de oclusion no se presenta como fraccion amodal real. Una medida
  amodal requeriria render aislado por instancia y queda fuera de este piloto.
- El Text Block `RUN_UCHUVA_ANNOTATION_PILOT.py` contiene el mismo pipeline que
  la linea de comandos y reutiliza los assets empaquetados.

## 2026-07-15 - Dataset piloto YOLO / MakeSense

- El dataset piloto contiene 200 imagenes EEVEE: 50 escenas morfologicamente
  distintas con cuatro condiciones de luz por escena. Doce renders Cycles se
  reservan para control visual y no forman parte de las 200 imagenes.
- Las clases definitivas son `calyx_green`, `calyx_straw`, `calyx_dry` y
  `flower`. Los frutos permanecen ocultos dentro de capachos cerrados y opacos.
- La identidad reproductiva global usa `plant_id:reproductive_id`; el ID local
  del arbol se conserva como metadato. Esto impide fusionar en una caja organos
  de plantas diferentes que compartan el mismo nombre morfologico local.
- Las cajas se calculan desde la mascara de instancia reproductiva visible, no
  desde proxies geometricos. Se descartan componentes aislados de menos de tres
  pixeles introducidos por cuantizacion y se exige un minimo de 24 pixeles
  visibles y una caja de 6 x 6 pixeles.
- La geometria se reparte por escena completa en `train`, `val` y `test`, con
  40, 5 y 5 escenas respectivamente. Las cuatro iluminaciones de una misma
  escena permanecen siempre en el mismo split.
- `manifest.jsonl` registra camara, luz, fenologia, IDs, cajas, visibilidad,
  truncamiento, colisiones y hashes. `rejected_scenes.jsonl` conserva de forma
  auditable las semillas rechazadas.
- El Text Block `RUN_UCHUVA_DATASET_PILOT.py` comparte el mismo orquestador que
  el CLI y permite generar o reanudar el dataset desde el `.blend` portable.

## 2026-07-16 - Primera convergencia real-matched

- `Dataset Original/` se trata como referencia inmutable. El analizador
  `scripts/compare_real_vs_synthetic_domain.py` reporta 1328 imagenes reales, la etiqueta
  ausente de `0117.jpg` y un riesgo de correlacion por rangos de captura entre
  validacion y prueba, sin corregir ni mover archivos de origen.
- El contrato YOLO se reduce a `0 = calyx`. Los capachos verdes, pajizos y secos
  comparten clase; `calyx_state`, `maturity` y `reproductive_stage` permanecen
  en el manifiesto. Las flores son contexto visual y no generan cajas.
- El perfil real gobierna de forma determinista orientacion, formato, banda de
  objetos, banda de area, recorte y ambiente. Para 100 imagenes se programan
  59 verticales y bandas 89/10/1 para 1--5, 6--10 y mas de 10 capachos.
- Los capachos se mantienen cerrados, sin transparencia alpha y con el fruto
  oculto. La nueva geometria añade una proporcion mas alargada, cinco costillas
  dominantes, punta, arruga por estado y metadatos reproducibles.
- La captura RGB aplica variacion de exposicion, gamma, balance de blancos,
  profundidad de campo, filtrado, dithering y calidad JPEG despues de calcular
  mascaras y cajas. Los fondos reales no se copian ni se usan como texturas.
- Los parametros nuevos siguen marcados como `manual_initial_guess` o
  `to_be_measured`; el reporte de alineacion explicita brechas mayores de cinco
  puntos porcentuales para no confundir una aproximacion inicial con una
  equivalencia de dominio demostrada.
- No se agregan frameworks de ML. El benchmark real/sintetico/mixto queda como
  fase siguiente y requiere aprobacion explicita.
- El piloto final `seed=0` contiene 100 escenas y 383 cajas. Todas las brechas
  de orientacion, bandas de objetos, bandas de area y truncamiento quedaron por
  debajo de cinco puntos porcentuales; la brecha media de composicion fue 1.27.

## 2026-07-22 - Texturas vasculares 2D y suelo sin borde visible

- Se sustituye la onda genérica de venación por mapas PNG reproducibles de
  albedo, altura, normal, rugosidad y máscara vascular, generados sin Blender.
- La hoja implementa arquitectura suprabasal, secundarias semicraspedódromas,
  terciarias alternas percurrentes y cuaternarias reticulares; el capacho usa
  cinco nervios medios dominantes y diez líneas longitudinales en total.
- Los colores sRGB iniciales se infieren del dataset original en modo de solo
  lectura y se etiquetan como valores de dominio de cámara, no reflectancia
  intrínseca. Los parámetros de reflexión quedan como estimaciones acotadas por
  literatura hasta disponer de carta de color y medición multiángulo.
- Blender usa UV explícitas `leaf_uv` y `calyx_uv`; las imágenes cargadas se
  marcan para empaquetado y el material procedural anterior queda como fallback.
- El terreno contextual y el plano de referencia miden como mínimo 260
  unidades: sus límites quedan más allá del `clip_end=120` de las cámaras y no
  pueden aparecer como el corte cuadrado del parche. El material del suelo usa
  coordenadas de objeto para conservar densidad de texel.

## 2026-07-22 - Capacho compacto y adaptación conjunta tutorada

- Se adopta `lantern_squash` con alto/ancho 1,15--1,55; las costillas dejan de
  ser curvas 3D superpuestas y pasan a una modulación de silueta de 2,5--4 %.
- `uchuva_v2` conserva v1 y añade diez variantes de capacho. La mitad de las
  verdes usa venación oscura y gradiente próximo al pedúnculo.
- La condición de color se decide una vez por planta. La tasa inicial de
  individuos `drying` es 8 % y no se mezclan entrenudos cafés en plantas sanas.
- La composición multiplanta usa tres iteraciones morfológicas antes de Blender.
  Las vecinas, el tutor y la carga cambian ejes serializables; no son una
  deformación de render.
- Cada planta tiene una estaca y dos o tres amarres visibles etiquetados como
  fondo. El contrato YOLO continúa siendo `0 = calyx`.

- La mediana de luminancia sintetica paso de 88.55 en el piloto anterior a
  103.83 en el real-matched, frente a 124.71 en el real. Es una mejora sensible
  pero no cierra la brecha tonal.
- La revision visual mantiene como deuda explicita: fondo low-poly, pubescencia
  de shader, venacion secundaria aproximada y calibracion dimensional local.

## 2026-07-16 - Grafo de contexto para agentes

- Se adopta `docs/repository_context_graph.json` como mapa descriptivo y
  respaldado por evidencia de la arquitectura. `AGENTS.md` conserva la
  autoridad prescriptiva y enlaza el grafo solo para tareas arquitectonicas,
  cientificas, de validacion o de datasets.
- El esquema registra subsistemas, entrypoints, artefactos, pruebas,
  restricciones y decisiones. Cada nodo y relacion cita una ruta relativa y
  un simbolo o encabezado verificable; no usa numeros de linea.
- La cadena principal conserva la separacion entre parametros, gramatica,
  morfologia pura, validacion, interpretacion Blender, anotaciones YOLO,
  orquestacion de dataset y comparacion de dominio.
- El validador `scripts/validate_repository_context_graph.py` comprueba esquema,
  cobertura de modulos, evidencia, recorridos e invariantes. Rechaza outputs
  generados como autoridad, el legado sin marcar como reemplazado, mutabilidad
  del dataset original y dependencias de la morfologia pura hacia Blender.
- No se instalan 2context, Graphiti, bases de grafos ni bibliotecas externas.
  La implementacion usa JSON y biblioteca estandar; el historial Git local esta
  vacio y no permite una extraccion confiable basada en commits.
- La mejora reportada por RIG se considera evidencia exploratoria, no garantia
  para este repositorio. Una comparacion A/B con agentes queda como evaluacion
  posterior opcional.

## 2026-07-22 - Cultivo denso con auditoría estricta de mallas

- Se adopta `dense_staked_crop` con 20 plantas morfológicas y 20 tutores
  rectangulares; no se usan sustitutos low-poly para completar el fondo.
- La lámina elimina ondulación, torsión y rizado geométrico. Su altura es una
  caída cuadrática monotónica y sus dos bordes permanecen coplanares.
- `collisions.py` separa la resolución pura anterior a Blender de la auditoría
  exacta posterior. Los proxies usan una rejilla espacial y ocho iteraciones
  deterministas; la BVH evaluada es la autoridad final de aceptación.
- Blender deja de reorientar unidades reproductivas por su cuenta. Toda pose
  válida debe estar registrada en el árbol morfológico y en el reporte de
  adaptación.
- Se conservan oclusiones proyectadas, uniones nodales y amarres; cualquier
  otra interpenetración invalida la escena. El piloto aceptado de semilla 1
  obtuvo 0 conflictos proxy y 0 interpenetraciones BVH.

## 2026-07-30 - Competencia lumínica, tutorado por capas y fondo vegetal

- Se incorpora un campo de luz puro y serializable con estratos `lower`,
  `middle` y `upper`.
- Cinco direcciones solares aproximan la oportunidad de cobertura durante el
  día. La métrica es un proxy de intercepción proyectada, no una tasa física de
  fotosíntesis.
- La postura foliar prioriza celdas proyectadas libres y registra sombreo
  intraespecífico e interespecífico. El solapamiento hoja-hoja continúa siendo
  oclusión visual permitida.
- El tutorado usa dos fases auditables: expansión del estrato y elevación hacia
  la línea superior. Tres objetivos laterales producen una primera lectura de
  trípode invertido.
- `trained_trellis` aumenta moderadamente estructura nodal y ramificación sin
  crear hojas fuera de nodos.
- El entorno mezcla formas `lolium_perenne_like`, `kikuyu_like` y malezas de
  hoja ancha, todas fuera de las clases de anotación de la uchuva.
- Los valores proceden de la observación agronómica aportada por Omar y se
  conservan como hipótesis de ingeniería o estimaciones iniciales pendientes
  de medición.

## 2026-07-30 - EEVEE como render normal

- `standard_eevee` reemplaza a `photoreal_final` como perfil predeterminado de
  aceptación humana.
- Los pilotos no generan Cycles por defecto y el dataset fija
  `cycles_qa_count=0`.
- Los pases auxiliares de la ruta estándar no cambian de motor a Cycles de
  manera implícita.
- Cycles y sus perfiles se conservan como opt-in para retomar el detalle cuando
  exista una ventaja observable que justifique su coste.
- Un baseline y su candidato deben usar el mismo perfil de render.

## 2026-07-31 - Copa cerrada, fondo verde y máscara conservadora

- Las composiciones de contexto y plano medio usan una segunda morfología
  completa para representar competencia interespecífica; no se agregan hojas
  decorativas sin nodo.
- La vegetación acompañante combina formas semejantes a *Lolium perenne*,
  kikuyo y malezas de hoja ancha. Un terreno verde multiescala y una envolvente
  distante procedural eliminan el horizonte vacío sin incorporar píxeles del
  dataset natural.
- La copa se densifica con más estructura nodal y mayor retención foliar. La
  postura mantiene variación orgánica y busca claros proyectados durante cinco
  direcciones solares aproximadas.
- El resolver de contactos puede elevar una lámina hasta 4,5 mm cuando su proxy
  se aproxima al capacho. La unión del pecíolo al nodo no cambia y la corrección
  queda serializada; la oclusión visual sin interpenetración sigue permitida.
- La cuantización de máscaras solo acepta colores auxiliares próximos a la
  paleta de anotación. Brillos, amarres y fondo fuera de tolerancia se asignan a
  fondo para evitar cajas falsas de capacho.
- Los amarres se conservan visibles, pero con radio reducido para que guíen la
  lectura del tutorado sin dominar la escena.

## 2026-07-31 - Protocolo de mezcla natural y sintética

- El conjunto `Dataset Original` permanece inmutable. La calibración visual y
  estadística usa únicamente `train` y `val`; `test` queda reservado como
  evaluación final natural.
- Se adopta una matriz reproducible con baseline natural completo, adición de
  todo el sintético y mezclas de presupuesto fijo 75/25, 50/50 y 25/75.
- Validación y prueba son siempre reales. Solo el split de entrenamiento recibe
  muestras sintéticas, con selección determinista y procedencia registrada en
  un manifiesto por experimento.
- La materialización prefiere enlaces físicos y recurre a copia si el sistema de
  archivos no los admite. Ninguna fuente se modifica.
- El criterio de éxito es igualar o superar el baseline natural en el mismo
  test, con arquitectura, inicialización, épocas y criterio de selección
  constantes. El entrenador externo se incorpora únicamente con aprobación
  explícita del usuario.

## 2026-08-01 - Calibración espacial y checkpoint híbrido final

- El análisis de dominio identificó una brecha de escala aparente: 33.42 % de
  las cajas sintéticas originales ocupaban menos de 1 % del cuadro y 17.66 %
  ocupaban al menos 5 %, frente a 15.03 % y 34.25 % en `train+val` naturales.
- Se adopta una copia derivada e inmutable con acercamientos adaptativos. El
  ajuste usa únicamente `train+val` naturales y `train` sintético, transforma
  imagen y caja de forma conjunta y descarta una caja si conserva menos de
  75 % de su área visible.
- La distribución de `train` calibrada queda en 15.18 % de cajas pequeñas,
  50.00 % medianas y 34.82 % grandes, con 2.800 objetos por imagen frente a
  2.795 naturales.
- La mezcla aditiva de 80 imágenes calibradas alcanzó 0.677963 mAP50–95 frente
  a 0.682706 del baseline. Aunque no cumplió el target por sí sola, redujo la
  brecha de la mezcla original de −0.014487 a −0.004743.
- Se permite interpolar checkpoints de arquitectura e inicialización idénticas
  como etapa de consolidación. El coeficiente se elige solo con validación
  natural; test no participa en la selección.
- La interpolación seleccionada, 55 % natural y 45 % híbrida, obtuvo 0.690637
  mAP50–95 en test natural, delta +0.007930. El target operativo se considera
  alcanzado para esta semilla y partición, no demostrado estadísticamente.
- Se registra como limitación que el mismo test fue consultado en varias
  iteraciones de desarrollo. La confirmación futura deberá usar varias semillas
  y un nuevo holdout natural no consultado.

## 2026-08-04 - Fidelidad papirácea, fondo botánico y escala del dataset

- El diagnóstico real/sintético separa composición de textura. La composición
  de cajas ya era cercana, pero el fondo y los recortes de objeto sintéticos
  tenían menos alta frecuencia, bordes y entropía que las imágenes naturales.
- Se retiran del capacho las macroondas periódicas. La variación de albedo y
  rugosidad pasa a ser coherente y no periódica; el relieve normal y las
  depresiones intercostales se reducen de forma conservadora.
- Los pliegues quedan localizados y dependientes del estado. Verde no recibe
  pliegues de secado; pajizo y seco reciben pocos, sin convertir el capacho en
  una superficie acanalada regular.
- La hoja recupera variación morfológica acotada de margen, torsión y
  acopamiento, siempre asociada al nodo. Su espesor de render se reduce a un
  rango provisional submilimétrico.
- *Lolium perenne* se interpreta como macollas altas y kikuyo como tapete bajo
  con estolones. Sus dimensiones se acotan por Kew/GrassBase; la mezcla y
  cobertura del predio continúan pendientes de inventario local.
- Se conserva `standard_eevee` y `cycles_qa_count=0`. El primer lote a escala
  tendrá 640 imágenes con una morfología por captura y reparto 512/64/64. La
  generación masiva solo se inicia después de aprobar un piloto visual.
- El primer piloto reveló que las copas procedurales distantes y el cilindro
  verde producían hojas poligonales, tubos y una pared uniforme. Se eliminan de
  la ruta activa: el HDRI agrícola CC0 aporta horizonte lejano y el suelo,
  malezas y plantas morfológicas aportan profundidad finita.
- Los porcentajes naturales de área son porcentajes de cajas, no de imágenes.
  La agenda de cámara aplica compensación de rendimiento reproducible: cerca
  de 5 % contexto, 40 % plano medio y 55 % acercamiento para cerrar la brecha
  observada del baseline sintético (demasiadas cajas pequeñas).
- El suelo verde conserva variación amplia y añade modulación cromática media;
  no usa píxeles del dataset natural ni geometría low-poly de relleno.
- La auditoría visual contra muestras reales bloquea la generación masiva si
  las hojas se leen mayoritariamente de canto. El intervalo preferido del
  preset tutorado pasa a 55--86 grados y el optimizador puede llegar a 94
  grados, conservando búsqueda azimutal diaria y evitando un dosel plano único.
- Las malezas de hoja ancha dejan de ser rombos verticales: se interpretan como
  láminas ovadas, inclinadas, acopadas y agrupadas en roseta. *Lolium* y kikuyo
  mantienen sus rangos publicados y reciben variación cromática no periódica.
- Se recupera la lectura geométrica de las cinco costillas principales del
  capacho (cresta 5,5--8,0 %; valle 1,2--2,4 % según estado) sin recuperar las
  macroondas periódicas descartadas. Estos rangos siguen siendo hipótesis de
  ingeniería pendientes de perfilado físico.
- La comparación directa con el dataset real mostró que la textura 0.4.2 aún
  perdía la red reticulada a resolución de captura. La revisión 0.4.3 aumenta
  su densidad y contraste y encadena un microrrelieve fino al mapa normal. El
  microrrelieve representa señal pubescente/papirácea, no pliegues
  macroscópicos.
- Las malezas de hoja ancha aumentan su relación ancho/largo y resolución de
  silueta. La sección de los postes se reduce para evitar que el tutor domine
  composiciones cercanas; ambos cambios siguen siendo hipótesis manuales.
- El piloto de aceptación 680 conservó una mediana de luminancia 14,88 niveles
  por debajo de `train+val` natural. La exposición del sensor EEVEE aumenta
  0,18 EV de forma uniforme; el intervalo mantiene variación por captura y su
  procedencia queda registrada en cada manifiesto.

## 2026-08-11 - Estudio híbrido multisemilla con evaluación real sellada

- Se usan tres semillas (`20260811`, `20260812`, `20260813`) con YOLO26n,
  40 épocas, 640 px, batch 16, paciencia 10 y ejecución determinista.
- La selección usa únicamente validación real. El test real se consulta solo
  después de bloquear por validación un ganador y se limita al baseline y al
  candidato seleccionado. Se conserva la advertencia de que este test fue
  consultado en experimentos históricos.
- La auditoría perceptual confirmó cinco secuencias de captura que cruzaban los
  splits originales. Se agrupan completas en un solo cohorte y se compensan
  los conteos mediante once movimientos documentados, sin modificar
  `Dataset Original`. La partición derivada conserva 1061/133/133 y queda sin
  candidatos perceptuales cruzados al umbral dHash adoptado.
- Fase A conserva las 1061 imágenes reales y agrega dosis sintéticas anidadas.
  Fase B, solo si A no mejora de forma práctica, fija 512 sintéticas y aumenta
  progresivamente subconjuntos reales anidados. Dos cohortes con
  empeoramiento detienen la búsqueda.
- Toda lectura del test requiere un archivo de selección bloqueado con hashes
  de checkpoint. Los entrenamientos son secuenciales, reanudables y verifican
  al menos 4 GB de RAM disponible antes de cada corrida.

## 2026-08-14 - Iteración virtual de fidelidad v2 antes de escalar

- El generador puro conserva `legacy_independent` como comportamiento por
  omisión para leer y reproducir morfologías anteriores. El dataset v2 activa
  explícitamente `literature_cohort_v1`; ambas rutas quedan disponibles para
  ablaciones.
- La fenología v2 se ordena por edad topológica y admite únicamente
  solapamiento entre estados adyacentes. La primera bifurcación se restringe a
  8--12 nodos. El modelo térmico de Salazar se registra como prior diagnóstico
  y no crea nodos automáticamente.
- Para que esa bifurcación no vacíe la escena de entrenamiento, el preset de
  composición usa 16--17 nodos principales y mayor probabilidad de ramas. Es
  una hipótesis de ingeniería `manual_initial_guess`, no una distribución
  poblacional inferida del arbusto disponible.
- El estado del capacho pasa a un continuo verde, transición verde--amarillo,
  pajizo y seco. Color, textura, turgencia, inflación, área, circularidad,
  pubescencia, asimetría y pliegues comparten el mismo progreso. Se eliminan
  las contracciones geométricas duplicadas que producían doble encogimiento y
  macroondulaciones.
- `layered_understory_v2` mezcla el suelo PBR CC0 ya disponible con pasto,
  malezas, follaje y hojarasca procedural a varias escalas y profundidades. No
  incorpora activos nuevos ni copia texturas o píxeles del dataset real. Se
  conserva `legacy_green_carpet_v1` para ablación.
- La composición se calibra solo contra `train` real. La búsqueda determinista
  recomienda 0 % contexto, 36 % plano medio y 64 % acercamiento, con brecha
  media predicha de 4,562 puntos porcentuales y máxima de 6,843. Se guardan
  matriz de rendimiento, objetivo, mezcla y hashes de entrada.
- No se aplica corrección global de luminancia: el antecedente redujo el
  mAP50--95 aproximadamente 0,0156. La comparación de dominio añade el proxy
  `non_calyx_scene_context`, calculado fuera de cajas expandidas.
- El diagnóstico del detector usa exclusivamente las 133 imágenes reales de
  `val`, seis checkpoints y emparejamiento IoU determinista. Es secuencial,
  reanudable y diferencia detección ausente de localización insuficiente. El
  `test` real permanece cerrado.
- El arbusto aislado continúa como referencia cualitativa. Ninguna observación
  suya se promueve a `literature_reported` o `real_dataset_measured`.
- El piloto se genera con EEVEE normal, `cycles_qa_count=0`, una sola instancia
  de Blender y reserva mínima de 4 GB de RAM. No se autoriza otro lote de 640
  imágenes ni entrenamientos nuevos hasta aprobar el piloto.
- El piloto semilla 16000 termina íntegro con 60 imágenes y 151 cajas, pero se
  rechaza para escalado. Cumplen la composición media (1,899 pp), luminancia,
  invariantes físicos y revisión del capacho. Fallan la brecha máxima de área
  (7,384 pp), energía de borde contextual (14,815) y dispersión contextual de
  luminancia (27,449).
- El próximo paso no será otro lote de 60: se requiere primero una matriz
  pequeña con las tres cámaras y un micropiloto de fondo. El resultado v2
  demuestra que añadir más geometría procedural no garantiza mayor frecuencia
  espacial si sus hebras quedan subpíxel o sus siluetas continúan lisas.
