# Piloto de reconstrucción de uchuva — 1 de octubre de 2026

## Continuación tras el cierre prematuro

El primer cierre a los 64 minutos fue insuficiente para el objetivo del piloto.
Se retomó el trabajo dentro del presupuesto original de dos horas. Los artefactos
iniciales se conservan intactos en `outputs/reconstruction/pilot_20261001/`;
la continuación está en `outputs/reconstruction/pilot_20261001_improved/`.
Las secciones posteriores que describen parches corresponden al **primer cierre**.

La continuación mejora sustancialmente el frente, pero **no cumple todavía el
mínimo de planta completa con base, copa y ambos lados**. Tampoco ejecutó los
métodos neurales. El cierre y consumo total del presupuesto original quedan
en `pilot_20261001_improved/benchmark.json`; el proceso de sellado verifica las
huellas del primer piloto y guarda una copia del código utilizado.

| Resultado ejecutado | Primer cierre | Continuación |
|---|---:|---:|
| Vistas usadas para MVS local | 16 | 51 |
| Lado mayor de imagen MVS | 640 px | 1280 px |
| Puntos densos completos | 25.920 | 197.490 |
| Puntos del mismo recorte | 5.131 | 112.433 |
| Representación Gazebo | cuadrados orientados | superficie Poisson con textura fotográfica |
| Triángulos visuales | 10.262 | 734.174 |

El recorte mantiene la misma imagen, rectángulo y rango de profundidad. Aumentó
21,91 veces el número de muestras; la separación mediana entre vecinos pasó de
0,02449 a 0,01129 unidades arbitrarias. La distancia mediana de la nube anterior
a la nueva es 0,01496; su percentil 95 es 0,05244. En sentido inverso la mediana
es 0,05440: la nueva nube contiene zonas poco muestreadas anteriormente. Son
diagnósticos de densidad y consistencia, **no exactitud contra verdad externa**.

Poisson produjo 874.872 triángulos crudos. El filtro de soporte conservó 748.472;
se asignó textura a 734.174 mediante acuerdo con la profundidad de una cámara.
Se conservan las caras sin textura en `surface/supported_surface.npz`, junto
con su asignación de cámara. La malla cruda está en `surface/poisson_raw.ply`.
Los umbrales de distancia 0,045 y arista 0,15 son heurísticas en coordenadas
arbitrarias. Poisson interpola: no certifica anatomía ni rellena legítimamente
órganos nunca observados. La nube analítica permanece separada y sin ese mallado.

Gazebo cargó la superficie y las 51 texturas y entregó dos cámaras RGB reales.
La prueba de contacto registró 1.339 contactos sobre la caja, ninguno de la
esfera exterior contra ella. Esto valida el proxy AABB, no contactos foliares
ni navegación entre ramas. La comparación visual está en `comparison_gazebo.png`;
cada recorte se recentra automáticamente, por lo que no es una evaluación
fotométrica con cámaras congeladas.

Se entregan `blender_review_v2/uchuva_observed_surface.blend`, con fotografías
empacadas, y `uchuva_observed_surface.glb`. El primer empaquetado Blender se
conserva marcado como sustituido porque aplicaba la conversión predeterminada
de ejes OBJ. La versión v2 declara explícitamente los ejes del paquete Gazebo.

La recuperación de cobertura utilizó 140 imágenes: 51 del frente y 89 del regreso
340–365 s. Con la calibración local fijada, el componente principal registró 108
cámaras y 27.210 puntos, con error medio de reproyección 0,970 px. También quedaron
componentes de 3 y 36 cámaras, que se conservan separados. La alineación por las
51 cámaras compartidas tuvo error mediano de centro 0,00414, máximo 0,02521 unidades
arbitrarias y diferencia angular mediana 0,179°. Estos residuos no certifican
que dos recortes de follaje correspondan a la misma planta.

La proyección del recorte inicial en la foto de 351,751 s cae a profundidad
mediana 23,06, mientras que el arbusto cercano de esa foto tiene puntos dispersos
principalmente entre 6 y 8. Se conserva esta discrepancia en
`return_identity_check.json` y `return_identity_projection.jpg`. **No se fusionan
ambos recortes como si fueran una sola planta**: identidad diferente o error del
registro entre pasadas siguen siendo explicaciones posibles. El ángulo máximo
de nuevas cámaras respecto a la primera cámara frontal ronda 100,5° alrededor
del centro del recorte inicial; no prueba reconstrucción de la cara opuesta.

Se densificaron por separado 24 vistas del regreso a 1280 píxeles: 291.639 puntos
totales. El recorte de la foto de 343,743 s, rectángulo `(420,170,955,715)` y
profundidad 16–22, retuvo 26.780 puntos. Su malla tiene 163.723 triángulos
fototexturizados y se cargó realmente en Gazebo en
`return_surface_framed/gazebo/`. **La inspección muestra una base fragmentada,
no continuidad suficiente de los tallos**. Se conserva como referencia secundaria
y resultado negativo respecto al requisito de planta completa. No desplaza la
superficie frontal como entrega principal ni se suma a ella para aparentar
completitud. La caja y el suelo de Gazebo son elementos artificiales de prueba.

La mejora local de MVS tardó 886,7 s y el mallado/texturizado 207,8 s supervisados.
La recuperación SfM adicional tardó 557,5 s, parcialmente en paralelo. No sumar
estos tiempos como tiempo de pared total. Las etapas acotadas registran recursos
en `stages/`; la preparación/exportación Blender y las comprobaciones pequeñas
también consumen el presupuesto de pared, aunque no tienen el mismo muestreo.

### Versiones visuales para simulación

La superficie completa sigue siendo la referencia visual. Se probaron dos
simplificaciones en Blender, preservando UV, normales y fotografías:

| Versión | Triángulos | p99 original → simplificada | p99 simplificada → original |
|---|---:|---:|---:|
| Agresiva, 30 % | 220.226 | 0,01012 | 0,01682 |
| Conservadora, 65 % | 477.181 | 0,00117 | 0,00235 |

Las distancias están en unidades arbitrarias y se calcularon sobre 50.000
vértices muestreados determinísticamente por paquete, buscando el triángulo
más próximo en la superficie completa, a través de todos los grupos de textura.
No son una cota máxima global ni exactitud física. Los máximos muestrales
original → simplificada fueron 0,18676 y 0,05640 respectivamente: pueden
perderse fragmentos pequeños aunque la apariencia general se conserve.
La comparación anterior por grupo de cámara, también conservada, sobreestima
la pérdida del conjunto cuando otra cámara representa la misma superficie.

Para inspección geométrica se conserva la malla completa y, prioritariamente,
la nube analítica. Como candidato visual se conserva `gazebo_light_conservative/`,
con 35 % menos triángulos. Su inspección RGB muestra moteado adicional: la cercanía
geométrica por sí sola no preservó toda la calidad de textura. **La entrega
principal sigue siendo `surface/gazebo/`, sin simplificación**. Ambas variantes
reducidas quedan como ensayos de compromiso, no como geometría de medición
ni reemplazo aceptado.
La simplificación no modifica las nubes originales ni valida la colisión AABB.

## Resultado y alcance del primer cierre

Se ejecutó un piloto local de viabilidad con COLMAP y Gazebo, dentro del máximo
de dos horas solicitado. Se obtuvo una reconstrucción **parcial**, no un benchmark
comparativo terminado ni una planta completa con base, copa y ambos lados.
El **primer cierre**, sustituido por la continuación anterior, queda registrado
en `outputs/reconstruction/pilot_20261001/benchmark.json`.
El trabajo se realizó en `codex/reconstruction-pilot-20261001`, sin push.

Resultados nuevos, efectivamente ejecutados:

- COLMAP local: 51 de 51 cámaras, 20.302 puntos dispersos y error medio de
  reproyección de 1,137 px, a 1280 × 720. Mediana: 1,064 px; longitud media
  de pista: 6,81 observaciones. Estos indicadores no certifican exactitud física.
- MVS: 25.920 puntos con normales y color, desde 16 vistas a un máximo de
  640 píxeles. Se conserva la nube completa y un recorte de primer plano de
  5.131 puntos; no hay segmentación certificada de una planta individual.
- Gazebo Harmonic: SDF válido, carga real, dos cámaras RGB recibidas por
  Gazebo Transport y dos pruebas físicas completadas sobre un proxy explícito.
- Recorrido amplio: 172 imágenes, cinco componentes; únicamente uno resulta
  plausible como referencia local. No se verificó alineación de los dos lados.
- Gaussian Splatting y NeRF no se ejecutaron en este piloto. No hay métricas
  visuales, tiempos de entrenamiento ni geometrías atribuidas a esas familias.

La salida de Gazebo es una **visualización de los puntos mediante parches
orientados**, con 10.262 triángulos y 32 materiales. No es una superficie vegetal
continua, una malla cerrada reconstruida, ni una representación de Gaussian Splatting.
No se completaron hojas que la captura no observó.

![RGB real de Gazebo del recorte parcial](../../outputs/reconstruction/pilot_20261001/gazebo/smoke/drone_camera.png)

Las esferas negras son cuerpos de prueba. La esfera superior descansa sobre una
caja invisible de colisión; sus apoyos no representan ramas reales.

## Entrada y captura

El nombre exacto del adjunto no estaba presente. El usuario confirmó expresamente
`dji_fly_20260912_090830_0017_1789409511229_video_beautify-006.mp4`, localizado bajo
`Nuevo Dataset/Recolección de datos 12-09-2026/`. No se sustituyó silenciosamente.

Tamaño: 4.012.627.938 bytes. Video 3840 × 2160, aproximadamente 29,97 fps,
15.135 cuadros y 505,004 s. SHA-256:
`7c2ff7fa2a43865a0e5a03f7e4faa591b675e9514f352591a83233af7f014742`.
Una segunda inspección con el script versionado produjo el mismo hash.

La hoja de contacto distribuida contiene 32 muestras. Se observan plantas,
tutorado, suelo, fondo vegetal, cambios de dirección y personas que ocultan la
escena. La textura fina y los hilos ocupan muchas correspondencias; la nitidez
medida no equivale a evidencia de rigidez. No se demostró una edición por el
sufijo `beautify`, ni se cuantificó movimiento foliar independientemente.

La selección amplia sondeó 329 candidatos entre 32 y 360 s y conservó 172
imágenes a 960 × 540. La decisión combina flujo óptico, seguimiento de ida y
vuelta y continuidad temporal: 115 por movimiento, 32 por separación temporal,
24 por pérdida de seguimiento y la primera vista. Los fotogramas conservados
por continuidad no se presumen buenos; permiten localizar los problemas.

El diagnóstico OpenCV encontró 94 de 171 pares consecutivos débiles bajo un
umbral heurístico de soporte/distribución espacial. Se reforzó el tramo 32–62 s:
121 candidatos cada 0,25 s, 51 seleccionados a 1280 × 720. No hay una partición
de evaluación independiente; PSNR, SSIM y LPIPS quedan sin calcular.

## Geometría local y resultado negativo del recorrido

La reconstrucción local produjo dos componentes. El `sparse/0` contiene solo
tres cámaras y tres puntos: se descarta, pese a su diminuto error residual.
El `sparse/1` contiene las 51 cámaras y los 20.302 puntos útiles para continuar.
El modelo es `SIMPLE_RADIAL`, con focal e intrínsecos refinados por ajuste global;
no procede de una calibración física independiente.

El ensayo amplio usó menos características por imagen y menor resolución que
el local. Es una prueba de conectividad, no una comparación controlada de calidad.

| Componente amplio | Cámaras | Puntos | Diagnóstico |
|---|---:|---:|---|
| 0 | 3 | 0 | Degenerado |
| 1 | 17 | 1.672 | Plausible localmente; 14 vistas del inicio y 3 del regreso |
| 2 | 5 | 418 | Focal de unos 30 px en imágenes de 960 px: no aceptado |
| 3 | 6 | 590 | Focal/distorsión inestables: no aceptado |
| 4 | 7 | 1.755 | Focal/distorsión inestables: no aceptado |

El componente 1 enlaza aproximadamente 32–63 s con 352–354 s. Nueve cámaras
comunes permiten un diagnóstico de concordancia mediante una semejanza rígida
con escala uniforme; no se deformó ni fusionó ningún modelo. El residuo máximo
de los centros comunes fue 0,065 unidades arbitrarias. Las vistas de regreso
cambian aproximadamente 29–39° respecto al inicio alrededor del centro del recorte,
según esa estimación. **Un enlace entre tiempos lejanos no demuestra una vista
del lado opuesto.** No se validó una cadena de postes que conectara ambos lados.

MVS conservó originales y resultados negativos. La primera preparación exportó
16 imágenes pero dejó 51 cámaras como posibles fuentes; se corrigió reduciendo
una copia del modelo. Después se calcularon los mapas densos, pero la escritura
falló porque `txt` significa directorio COLMAP. Se recuperó únicamente la fusión
con `output_type="ply"`, sin repetir PatchMatch. Los mapas y la nube son resultados
reales, no métricas recuperadas de otro experimento.

## Escala, recorte y descriptores

No se identificó un par adyacente de postes utilizable para escalar. El intervalo
informado de 3,15–3,50 m se conserva como referencia pendiente, sin transformarlo
en una distancia medida, un intervalo de confianza ni una escala central aplicada.
Altura física, ancho y profundidad métricos permanecen **desconocidos**.

El recorte usa el fotograma de 49,516 s, rectángulo `[200,85,1100,720]` y profundidad
`[4.3,8.5]` en coordenadas arbitrarias de su cámara. La imagen de evidencia muestra
los puntos seleccionados. Incluye superficies visibles parciales; no garantiza
exclusión de hilos u otros elementos ni recuperación del tronco/base.

![Región y puntos del recorte](../../outputs/reconstruction/pilot_20261001/foreground/crop_evidence.jpg)

Su caja mide 6,664 × 3,763 × 3,792 **unidades arbitrarias**, en ejes derecha,
avance y arriba de la cámara de referencia. No es altura respecto a un suelo
medido. Las relaciones respecto al ancho son 1 : 0,565 : 0,569.
Al cambiar solo el límite lejano de profundidad de 8,5 a 9,0, la extensión de
profundidad sube a 4,520 y la vertical a 4,657. Esto muestra sensibilidad a pocos
puntos adicionales y desaconseja interpretar las cajas extremas como medidas
botánicas estables. Se guardó también la distribución vertical normalizada de
las muestras observadas, afectada por oclusión y muestreo.

No se calculó biomasa, área foliar total ni volumen sólido. Tampoco se realizó
una comparación con una planta sintética completa: el recorte parcial y la
orientación sin gravedad medida no permiten el mismo protocolo. La referencia
sirve por ahora para inspeccionar órganos visibles y preparar vistas comparables;
no autoriza recalibrar la arquitectura del generador a partir de este ejemplar.

## Gazebo: verificaciones y límites

Se reutilizó el ensamblador y el verificador de cámaras del proyecto. Los OBJ
contienen parches de radio 0,045 unidades arbitrarias, orientados por normales
MVS, con colores discretizados. Ese radio es una heurística de visualización.
La nube analítica conserva puntos originales sin esos parches.

La transformación está guardada como rotación, traslación y escala uniforme.
Para diagnosticar la importación se mapea una unidad arbitraria a un metro SDF;
**esto no establece escala física del cultivo**. La orientación usa la cámara,
no una vertical del suelo estimada. El mundo incluye suelo artificial de prueba.

- `gz sdf -k`: válido.
- Servidor Harmonic 8.14.0 y dos cámaras RGB 1280 × 960: ejecutados; se guardó
  el sexto fotograma de cada cámara con su sello temporal de simulación.
- Contacto: 1.320 mensajes contra la caja; esfera a `z=4.09213` frente al apoyo
  configurado de `4.09224` en unidades de simulación.
- Columna exterior libre: esfera a `z=0.09912` sobre el suelo de prueba y cero
  contactos con el proxy de la planta.

El primer ensayo de contacto se suscribió a un tópico que Harmonic no publicó;
las poses indicaban apoyo, pero no se declaró suficiente. El reintento usó el
tópico jerárquico observado en el log y verificó mensajes y poses. Ambos quedan
guardados. La caja rellena todos los huecos del follaje: estas pruebas no validan
contacto con ramas, corredores entre hojas ni seguridad de vuelo.
No se midió rendimiento sostenido o tiempo real; los segundos de arranque y
captura no son un benchmark de tasa de simulación.

## Coste y estado de los métodos

| Etapa supervisada | Tiempo de pared |
|---|---:|
| Selección amplia | 281,8 s |
| Selección local | 113,3 s |
| Diagnóstico de pares | 51,8 s |
| SfM local | 251,1 s |
| MVS, fallo y recuperación de exportación incluidos | 139,2 s |
| SfM amplio | 615,6 s |
| Carga y dos RGB de Gazebo | 8,0 s |
| Dos ensayos de contacto, fallo incluido | 16,1 s |
| Reinspección completa y hash final del original | 37,1 s |

Preparación, instalación, decisiones, edición e inspección también consumieron
el presupuesto global. No se suman las etapas paralelas como si fueran tiempo
de pared consecutivo. La instalación no tuvo un perfil detallado propio; su coste
permanece incluido en el tiempo global, no se presenta como cero.

El pico agregado **muestreado** de árboles supervisados fue aproximadamente
1,13 GiB. El RSS puede contar memoria compartida varias veces y no captura todos
los picos subsegundo; tampoco incluye toda la edición interactiva e instalación.
La GPU disponible fue RTX 4050 Laptop de 6.141 MiB; se observó, entre otras muestras,
1.019 MiB durante SfM local. No es un pico exacto atribuible solo al piloto.

Se aplicaron límites cgroup: 10 GiB en reconstrucciones locales, 8 GiB en el
recorrido y 4 GiB en Gazebo, con `MemorySwapMax=0`. La única concurrencia de
reconstrucción y simulador tuvo límites agregados de 12 GiB. El reporte de
`MemoryPeak` de systemd fue inconsistente en WSL; se conserva pero no se usa como
pico medido. Se verificó además el corte temporal del supervisor con un proceso
de prueba. Los plazos absolutos de los reintentos no ampliaron las dos horas.

COLMAP SfM/MVS queda **parcial**. Splatfacto y Nerfacto quedan **no ejecutados por
el alcance y presupuesto del piloto**: no estaban instalados en WSL y no se abrió
otra preparación neural. No se puede declarar un ganador entre tres familias;
COLMAP es la única ensayada. No hay referencia geométrica independiente ni
afirmación de exactitud centimétrica.

## Artefactos y continuación del principal

La [guía operativa](../guides/reconstruccion_piloto.md) contiene requisitos y
comandos. Todos los artefactos pesados están bajo `outputs/reconstruction/pilot_20261001/`,
ignorados por Git. Se conservan manifiestos, hojas de contacto, selecciones,
bases de correspondencias, modelos COLMAP binarios/texto, PLY, mapas densos,
SDF/OBJ, RGB, contactos, comandos y consumo. `benchmark.json` es la tabla de
resultados legible por máquina; `artifact_manifest.json` enumera archivos y hashes.

Para mañana, la prioridad es recuperar geometría y conexiones antes de entrenar
apariencia:

1. Empezar con un directorio y plazo nuevos, conservando este piloto. Reutilizar
   el entorno autorizado y el manifiesto del video confirmado.
2. Seleccionar una planta/tramo específico, densificar vistas de conexión y
   excluir personas móviles. Revisar la secuencia completa necesaria para ambos
   lados; la selección amplia de este piloto resultó insuficiente.
3. Validar correspondencias de postes/suelo y calibración entre segmentos. No
   unir follaje similar ni aceptar componentes con intrínsecos degenerados.
4. Identificar en imágenes un par de postes y medir su separación real, si es
   posible. Sin esa medición, mantener el intervalo provisional y unidades
   arbitrarias cuando no haya un par defendible. Una captura lenta que muestre
   base, copa y conexión alrededor de la misma planta aportaría mucho valor.
5. Fijar vistas de evaluación separadas; aumentar detalle de MVS solo en el
   segmento coherente. Comparar estabilidad del filtrado y conservar los huecos.
6. Preparar un método neural dentro del presupuesto principal y de la VRAM;
   verificar antes instalación/exportadores y autorizar sus dependencias conforme
   a `AGENTS.md`. Reservar tiempo para las mismas pruebas Gazebo y el cierre.

La comparación con sintéticos deberá aplicar las mismas vistas y observabilidad,
separando forma normalizada de escala física. El principal no queda ejecutándose
ni programado por este informe.

Validación del código: cuatro pruebas nuevas de movimiento/PLY, cuatro del grafo
y el validador del contexto pasaron. No se modificó ni reejecutó la campaña
morfológica, el detector o el entrenamiento de estudiantes.
