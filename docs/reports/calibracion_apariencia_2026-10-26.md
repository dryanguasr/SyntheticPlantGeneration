# Correcciones y primera calibración del piloto de apariencia

Estado: **galería de 50 imágenes terminada, revisión humana pendiente, cero
entrenamientos nuevos**. Campaña `outputs/appearance_factorial_20261026`.
El [protocolo implementado](../guides/piloto_apariencia_factorial.md) conserva la
matriz de 26 screenings y 36 confirmaciones; esos resultados aún no existen.

## Cambios implementados

- Preset `trained_trellis_audit_v2`, carga `architecture_driven`, cohortes sin
  creación de órganos por cuota y parámetros de cámara separados de la planta.
- Parámetros efectivos y hash en árboles nuevos; conteos por etapa; rango radial
  de orden 3 explícito y heurístico; continuidad respecto al padre en la inserción.
- Validación de integridad, plausibilidad y geometría por etapa; procedencia de
  overrides y alias históricos; ficha de campo sin atribuir mediciones inexistentes.
- Contrato común de deformación para geometría/proxies y auditoría de envolventes
  finales. Las intersecciones físicas siguen siendo una comprobación independiente.
- Perfiles explícitos de luz/material, color y exposición efectivas registradas,
  órganos sin emisión y desgaste separado de la clase. Sobremadura usa una
  hipótesis pajiza, sin imponer manchas marrones como definición.
- Lanzadores, snapshots, presupuesto activo, banco común, adaptador de
  entrenamiento emparejado y evaluador nuevos. Los controles reales se reentrenarán.

Las cuatro plantas de calibración tienen respectivamente 9/16/18/4 unidades
reproductivas, 1/2/2/1 flores y **8/14/16/3 frutos**. Superar diez frutos no causa
rechazo. Estas cantidades surgen de los sitios nodales; no son límites ni
distribuciones botánicas medidas. Tampoco son el número de anotaciones por imagen.

## Evidencia visual ejecutada

Se midieron 4.723 instancias poligonales de las 461 imágenes de entrenamiento.
No se usó validación ni test para colores o selección de referencias. Los recortes
reales muestran ejemplos oscuros, centrales, claros y de bajo contraste con sus
etiquetas originales. No hay relabelado automático ni una declaración de que
la ambigüedad visual ya esté resuelta. `Nuevo Dataset/Norma.webp` se incluye solo
como referencia cualitativa aportada.

Galería local:
`outputs/appearance_factorial_20261026/calibration/round_01/review/index.html`.
Paneles `referencias_reales.jpg`, `comparacion_clases.jpg` y cuatro
`encuadres_planta_N.jpg`. Contiene 18 focales y 32 contextuales. En los 17 grupos
emparejados se verificaron hashes iguales de máscara, geometría y cámara.
Las focales cambian la hipótesis de clase superficial sobre el mismo órgano;
sus metadatos de desarrollo latente no se reinterpretan como clase observada.

Se conserva `smoke_01` con dos renders previos, que revelaron sobreiluminación.
Su corrección produjo el candidato `candidate_01_after_photometric_smoke`.
Ambos trabajos sumaron aproximadamente 252 segundos activos del ledger; no es
un tiempo total de desarrollo ni una estimación del entrenamiento.

## Observaciones y límites detectados

1. **El candidato aún no está aprobado.** En la luz difusa, las medianas de
   luminancia codificada de los materiales candidatos son 0,352/0,468/0,407 para
   Pintona/Madura/Sobremadura; las medianas por instancia reales son
   aproximadamente 0,429/0,579/0,516. No son reflectancias comparables bajo luz
   controlada; muestran que subir o bajar luz globalmente no resuelve por sí solo
   la apariencia. Madura y Sobremadura siguen próximas visualmente.
2. **La luz candidata oscurece el contexto.** Sobre ocho encuadres, la mediana de
   las medianas del contexto es 0,470 en B/T y 0,341 en L/LT. Las correspondientes
   del objetivo son B 0,582; L 0,436; T 0,526; LT 0,382. Esto es una medición del
   render, no una mejora de transferencia. Conviene recalibrar fondo y órgano por
   separado en la segunda ronda.
3. **El fondo todavía es simplificado.** Se usaron malezas procedurales, pero
   faltaron los assets externos de suelo y HDRI, según los manifiestos. El cielo
   efectivo es procedural y está registrado; no se afirma que el horizonte abierto
   represente los nuevos videos. El banco deberá conservar un contexto explícito
   y revisado, con diversidad entre escenas y constancia dentro de cada pareja.
4. **Ninguna de estas cuatro escenas está admitida al entrenamiento.** La auditoría
   de mallas detectó 12/3/10/1 intersecciones físicas y 8/6/12/0 violaciones de
   separación. Son diagnósticos, no oclusión inferida por máscaras. No se relajan
   esos controles ni se borran frutos para aprobar. Las auditorías y los rechazos
   se conservan; el banco tiene reintentos acotados y puede bloquearse si no obtiene
   escenas válidas.
   Su contrato permite explícitamente ocupación blanda hoja–hoja y no cubre todos
   los contactos con maleza/residuos; esa excepción no se extenderá a los demás
   órganos ni se confundirá con oclusión visual.
5. **Correcciones posteriores registradas.** `round_01/audit_review.json` documenta
   que la primera envolvente guardó escala 1 antes de configurar 0,125 m/BU; las
   coordenadas BU se conservan y se corrige su interpretación sin reescribirlas.
   El renderer futuro configura unidades antes de auditar y conserva la visibilidad
   original de frutos internos. La galería inicial activó su visibilidad en vistas
   contextuales: otra razón por la que esas imágenes no se usarán para entrenar.
   La máscara diagnóstica conserva el filtro histórico de componentes menores de
   tres píxeles; el banco nuevo lo desactiva para mantener todos los fragmentos
   visibles válidos. Estas máscaras diagnósticas no se reutilizarán como etiquetas.
   El digest futuro cubre además curvas, y el cambio de material conserva el estado
   foliar sano/senescente. Las capturas y su snapshot original permanecen intactos.

## Revisión necesaria y continuación

Se solicita la revisión acordada de las tres clases: correspondencia con las
referencias, separación Madura/Sobremadura, tono y fuerza de nervaduras, brillo de
capacho frente al fondo. La propuesta técnica es una segunda ronda con Madura más
cercana a amarillo verdoso, Sobremadura pajiza con variación independiente de
desgaste y luz de contexto menos oscura. Son hipótesis para revisar, no un dictamen
normativo ni evidencia de mejora de AP.

Antes del banco deben resolverse las escenas inválidas con arquitectura nodal,
parámetros efectivos y auditoría final; ni la revisión humana de color ni un buen
hash certifican la geometría física. Solo después se congelarán los perfiles
aprobados y se generará el banco común. No se ha escrito un lock de aprobación.
No hay resultados nuevos de entrenamiento, pesos seleccionados ni promoción.

La ejecución conjunta final pasó **66 pruebas CPU**, incluida integración real
del DataLoader, transformación de cajas, decisiones emparejadas y rechazo de una
actualización AMP omitida. La prueba de render produjo las 50 imágenes sobre su
snapshot original; los cambios posteriores de metadatos/visibilidad se verificaron
por revisión y sintaxis, y deberán comprobarse en la siguiente ronda. No equivalen
a haber ejecutado 26 entrenamientos ni 36 confirmaciones.

`verification_pre_review.json` registra hashes, aislamiento por imágenes y grupos
de las 643 imágenes reales, los 17 grupos visuales y el snapshot de 145 archivos.
El validador del grafo conserva exactamente sus diez errores de evidencia
preexistentes, sin nuevas regresiones; no se presenta como un validador sin fallos.
El informe del piloto cerrado y las trece fuentes congeladas coinciden por hash.
Los 15 archivos modificados previamente y ajenos a esta intervención permanecen
idénticos; los otros cuatro modificados durante esta intervención conservaron
copia previa en `preservation/local_changes`. No se retiraron cambios locales.
