# Informe breve de estado del proyecto

> Informe histórico de corte. La navegación y las rutas vigentes se describen
> en `README.md` y `docs/README.md`.

**Proyecto:** generación procedural de uchuva (*Physalis peruviana*) para datos sintéticos  
**Fecha de corte:** 23 de julio de 2026  
**Propósito:** servir como contexto breve para conversar con Chat sobre decisiones, avances y próximos ajustes.

> Este informe reconstruye el proceso a partir del repositorio, sus decisiones técnicas, pruebas y artefactos. No sustituye un historial completo de conversación. El historial Git local no está disponible porque la carpeta `.git` está vacía.

## Resumen ejecutivo

El proyecto ya no es solamente un prototipo visual de Blender. Actualmente existe un pipeline funcional que sigue la dirección:

```text
parámetros y semilla
→ árbol morfológico
→ adaptación al cultivo y resolución de colisiones
→ validación
→ geometría y escena Blender
→ máscaras y anotaciones YOLO
→ comparación entre dominio real y sintético
```

La arquitectura `morphology-first` está implementada y el proyecto cuenta con generación reproducible, validación sin Blender, escenas de cultivo, anotaciones y un piloto real-matched. El resultado debe considerarse un **prototipo de investigación avanzado**, no un modelo botánico calibrado ni una demostración de utilidad para aprendizaje automático.

## Trabajo realizado hasta el momento

### 1. Migración del prototipo inicial

- El generador geométrico v0.5 se recuperó del Text Block de un archivo `.blend` y se conservó en `legacy/`.
- Se creó la separación modular entre morfología, parámetros, gramática, validación, geometría Blender, escena y exportadores.
- Se estableció el árbol morfológico JSON como fuente estructural anterior a Blender.
- Se adoptaron semillas reproducibles y metadatos de versión, preset y parámetros.

### 2. Modelo morfológico y cultivo

- Se implementaron dataclasses serializables para plantas, ejes, entrenudos, nodos, hojas, yemas y unidades reproductivas.
- Las hojas, ramas y unidades reproductivas se originan en nodos o axilas; no se distribuyen arbitrariamente en coordenadas globales.
- Se separó la planta individual de la escena de cultivo. La densidad visual proviene de múltiples instancias, hileras, tutorado y cámara, no de inflar artificialmente una planta.
- Se añadió adaptación conjunta por vecinas, espacio disponible, tutores y carga reproductiva antes de crear geometría.

### 3. Geometría, materiales y entorno

- Se implementó un capacho compacto tipo `lantern_squash`, cerrado y opaco, con el fruto conservado en la morfología pero oculto en Blender.
- Se reemplazó la venación genérica por texturas vasculares 2D reproducibles para hojas y capachos. Existen versiones v1, v2 y v3.
- Se ajustaron hojas para eliminar ondulación, torsión y rizado artificiales; la caída actual es suave, cuadrática y monotónica.
- Se añadieron terreno, iluminación exterior, cámaras, tutores y amarres. El terreno se amplió para evitar que su borde aparezca en cámara.
- La escena densa actual usa 20 plantas morfológicas reales y 20 tutores, sin completar el fondo con sustitutos de uchuva low-poly.

### 4. Validación y colisiones

- Se distingue entre colisión física, oclusión visual y morfología fuera de rango.
- Las colisiones se resuelven primero con proxies globales y después se auditan sobre mallas evaluadas mediante BVH en Blender.
- Las uniones nodales, el fruto dentro del capacho y los amarres se consideran contactos intencionales; otras interpenetraciones invalidan la escena.
- El piloto denso aceptado con `seed=1` registró 5.068 proxies, 1.258 ajustes, cero conflictos proxy y cero interpenetraciones en 2.025 objetos auditados.

### 5. Anotaciones y dataset

- Se implementaron RGB, máscaras semánticas, máscaras de instancia de planta y de unidad reproductiva, cajas visibles y metadatos de cámara.
- El contrato YOLO vigente es de una sola clase: `0 = calyx`. Los estados verde, pajizo y seco permanecen como metadatos; las flores no generan cajas.
- `Dataset Original/` se usa como referencia inmutable y no como fuente de píxeles o texturas.
- El piloto real-matched almacenado contiene 100 imágenes, 383 cajas, división 80/10/10, 100 previews y 12 controles Cycles. Reporta cero colisiones físicas, cero capachos abiertos y ningún fruto oculto renderizado por error.
- La brecha media de composición frente al dataset real bajó a 1,27 puntos porcentuales. Esto representa alineación estadística básica, no equivalencia fotográfica.

## Observaciones y críticas del usuario incorporadas

Las siguientes directrices han guiado la evolución del proyecto:

- **No seguir refinando una planta genérica.** El prototipo v0.5 sirve para rescatar utilidades de Blender, pero no define la biología.
- **Priorizar morfología sobre decoración.** Primero debe existir una estructura botánica explícita, serializable y validable; la geometría viene después.
- **No confundir individuo con cultivo.** Una planta individual no debe hacerse artificialmente enorme o arbustiva para explicar una escena densa.
- **Mantener relaciones botánicas.** Hojas, ramas, pedicelos y estructuras reproductivas deben estar unidos a nodos o axilas.
- **Corregir la lectura visual del capacho.** No debe parecer una esfera con varillas; debe tener forma inflada compacta, costillas discretas, depresiones intercostales y venación principalmente en textura.
- **Evitar geometría foliar artificial.** Se criticaron la ondulación, torsión y rizado excesivos; la versión actual usa una lámina mucho más plana y controlada.
- **Separar oclusión de interpenetración.** La oclusión es útil para visión robótica, mientras una colisión física imposible debe corregirse o causar rechazo.
- **Evitar falsos sustitutos de cultivo.** En el perfil denso se eliminaron copas genéricas low-poly usadas para aparentar más plantas.
- **No presentar estimaciones como hechos botánicos.** Los parámetros se etiquetan como `literature_reported`, `dataset_inferred`, `manual_initial_guess` o `to_be_measured`.
- **Mantener un alcance de anotación claro.** Por ahora se detecta el capacho como una sola clase; la fenología queda como metadato y el fruto permanece oculto.
- **No afirmar utilidad ML sin medirla.** Aún no se han instalado frameworks de aprendizaje automático ni se ha ejecutado el benchmark real/sintético/mixto.

## Estado verificado al 23 de julio de 2026

- Las **37 pruebas Python** disponibles pasan correctamente con `src/` en la ruta de importación.
- El grafo de contexto del repositorio es válido y conserva la separación entre morfología pura y Blender.
- Existen artefactos recientes de la escena densa, sus morfologías individuales, máscaras, RGB y anotaciones.
- No se volvió a ejecutar Blender durante la elaboración de este informe; las métricas de malla proceden del artefacto y reporte generado el 22 de julio.

## Limitaciones y asuntos abiertos

- Faltan mediciones locales de dimensiones, color con carta de referencia, reflectancia y respuesta multiángulo. Parte importante de los parámetros sigue siendo una estimación inicial.
- La luminancia mediana sintética reportada es 103,83 frente a 124,71 en el dominio real: la brecha tonal se redujo, pero continúa abierta.
- La pubescencia se aproxima mediante shader, la venación secundaria es procedural y la equivalencia fotográfica aún no está demostrada.
- No existe todavía evidencia de que el dataset sintético mejore un detector. El benchmark ML sigue pendiente y requiere aprobación antes de añadir dependencias.
- La apertura de capachos y la visibilidad parcial del fruto están pospuestas.
- En la fecha de corte, la documentación conservaba una inconsistencia de
  transición entre v2 y v3. La reorganización posterior fijó
  `assets/textures/current/` como única ruta activa.
- No hay historial Git utilizable para reconstruir autoría o cambios por commit. Conviene inicializar o recuperar correctamente el repositorio antes de la siguiente etapa.

## Lectura general

El proyecto ya demuestra que la idea completa es técnicamente viable: puede producir una morfología reproducible, adaptarla a una escena de cultivo, validar su estructura, construirla en Blender y obtener anotaciones. El trabajo siguiente debería concentrarse menos en añadir complejidad y más en **calibrar, consolidar y evaluar**: medir órganos reales, cerrar inconsistencias documentales, revisar visualmente el piloto denso y diseñar un benchmark controlado que determine si los datos sintéticos aportan valor.
