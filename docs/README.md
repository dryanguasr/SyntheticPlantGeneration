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

- `guides/biblioteca_texturas_uchuva.md`: generación, calibración y uso de
  texturas.
- `guides/protocolo_validacion_humana.md`: matriz de validación, perfiles de
  render y promoción manual del baseline.

## Gobernanza y evidencia

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
