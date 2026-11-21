# Índice de documentación

La documentación producida por el proyecto se versiona y se organiza por
función, no por orden de creación. La única excepción deliberada es
`docs/drafts/`, que contiene borradores locales y permanece fuera de Git.

## Arquitectura vigente

- `architecture/modelo_morfologico_uchuva.md`: entidades y supuestos botánicos.
- `architecture/adaptacion_morfologica_del_cultivo.md`: adaptación de cultivo.
- `architecture/crecimiento_multi_planta_sincronizado.md`: coordinación,
  soporte, contacto y variantes A–F.
- `architecture/competencia_luminica_tutorado_y_cobertura.md`: estratos,
  postura foliar, guía, vegetación acompañante y política de render.
- `architecture/integracion_augmentacion_sintetica_gazebo.md`: contratos entre
  aumentación clásica, generación sintética y Gazebo.

## Guías operativas

- [Video del DJI Neo en Android y PC](guides/video_dron_pc_rtmp.md): recepción
  RTMP, servidor local, red del teléfono emisor y exportación de videos y datos.

- [Aplicación móvil con ArUco](guides/aplicacion_movil_aruco.md): compilación,
  requisitos de un clon nuevo, instalación, medidas aproximadas, capturas y
  protocolo de prueba en teléfono; APK y pesos permanecen fuera de Git.
- [Revisión de resultados de aumento clásico v2](guides/revision_resultados_aumento_clasico_v2.md):
  acceso al paquete publicado con resultados, manifiestos, predicciones y previews.
- `guides/biblioteca_texturas_uchuva.md`: generación, calibración y uso de
  texturas.
- `guides/protocolo_validacion_humana.md`: matriz de validación, perfiles de
  render y promoción manual del baseline.

## Gobernanza y evidencia

- [Auditoría independiente de generación sintética y Gazebo (25-10-2026)](reports/auditoria_generacion_sintetica_2026-10-25.md):
  defectos reproducidos de morfología, validación y procedencia; límites de la
  exportación física, prioridades para estudiantes y piloto flexible secundario.
- [Informe del componente virtual para Karen y Caroline](reports/informe_virtual_karen_caroline_2026-10-14.md):
  experimentos, resultados, pendientes y referencias para la tesis, sin detalles del generador.
- [Auditoría científica de Blender y maduración](reports/auditoria_cientifica_blender_2026-09-08.md):
  resultados históricos contrastados, límites de las etiquetas y ruta científica elegida.
- [Plan de continuidad en Codex](plan_auditoria_cientifica_blender_2026-09-08.md):
  primera intervención ejecutada, hitos, criterios, costes y texto exacto de arranque.
- `governance/decisiones_tecnicas.md`: decisiones cronológicas.
- `governance/registro_evidencia.md`: procedencia, incertidumbre y estado
  epistemológico de parámetros y resultados.
- `repository_context_graph.json`: mapa descriptivo validable del repositorio.

## Frentes de trabajo

- `workstreams/classical_augmentation.md`: baseline convencional y procedencia
  de la entrega estudiantil.
- `workstreams/synthetic_generation.md`: implementación vigente del generador.
- `workstreams/gazebo_bridge.md`: plan de exportación semántica por LOD.
- `plan_reestructuracion_augmentacion_sintetica_gazebo.md`: especificación de
  la reorganización inicial y los spikes posteriores.

## Referencias científicas

La carpeta `references/` conserva **metadatos, bibliografía y guías de lectura,
no copias de artículos**.

Los artículos de referencia utilizados por el proyecto son de acceso libre o
cuentan con una versión pública disponible en sus ubicaciones originales,
repositorios institucionales o servicios públicos de preprints. Para evitar
duplicar material de terceros, los PDFs descargados localmente no se versionan.
Use los DOI y URL registrados para localizar cada trabajo en su fuente pública.

Consulte:

- `references/README.md`: política y forma de localizar las fuentes;
- `references/referencias_uchuva_lsystem.bib`: bibliografía estructurada;
- `references/README_articulos_recomendados.md`: selección comentada de lecturas.

## Reportes con fecha de corte

- [RTMP Android y aplicación PC](reports/video_rtmp_android_pc_2026-09-11.md):
  pruebas de transmisión local, referencias multipunto y paquetes 0.3.0.

- [Aplicación Android con ArUco](reports/aplicacion_android_aruco_2026-09-02.md):
  APK local, equivalencia del detector, verificación en emulador y límites de campo.
- [Confirmación de aumento clásico v2](reports/aumento_clasico_v2_confirmatory_2026-08-28.md):
  cierre de 40 corridas sin receta promovida, decisión operacional y tiempos.
- `reports/estado_proyecto_2026-07-23.md`.
- `reports/comparacion_multi_planta_2026-07-23.md`.
- `reports/resultado_dataset_hibrido_2026-08-01.md`: dataset sintético,
  calibración espacial, matriz de proporciones y resultado híbrido preliminar.
- `reports/mejoras_virtuales_prioritarias_2026-08-14.md`: cohortes
  fenológicas, maduración conjunta, fondo, composición, diagnóstico del
  detector y decisión de escalado del piloto v2.

Los reportes fechados son históricos. Para rutas y comandos vigentes, use el
`README.md` de la raíz.

## Borradores

`docs/drafts/` es una carpeta local deliberadamente excluida del control de
versiones. Un documento debe moverse fuera de `drafts/` solo cuando se considere
suficientemente estable para formar parte de la evidencia o documentación
reproducible del proyecto.
