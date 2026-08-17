# Referencias científicas

Esta carpeta registra las fuentes científicas utilizadas para fundamentar el
modelo morfológico, la generación sintética, la evaluación de dominio y las
extensiones de robótica agrícola.

## Política de almacenamiento

Los artículos de referencia **no se almacenan como PDFs en Git**. Los trabajos
seleccionados son de acceso libre o cuentan con una versión pública disponible
en sus ubicaciones de origen, repositorios institucionales o servicios públicos
de preprints.

Para consultar una fuente:

1. busque su entrada en `referencias_uchuva_lsystem.bib` o en
   `README_articulos_recomendados.md`;
2. use el DOI o URL registrado;
3. acceda a la versión pública ofrecida por el editor, repositorio institucional,
   arXiv u otra fuente pública indicada por los metadatos.

Esta política evita duplicar archivos de terceros y mantiene el repositorio
ligero y trazable.

## Contenido versionado

- `referencias_uchuva_lsystem.bib`: bibliografía estructurada con DOI y URL;
- `README_articulos_recomendados.md`: selección comentada de trabajos
  especialmente relevantes;
- este `README.md`: política de referencias.

## Copias locales

Si durante el trabajo se descargan PDFs para lectura, deben mantenerse fuera de
Git. Puede usarse localmente `docs/references/raw/`, que está ignorada mediante
`.gitignore`.

No agregue PDFs de artículos directamente a esta carpeta aunque sean de acceso
abierto: la fuente pública original o el repositorio público correspondiente
debe seguir siendo la referencia canónica.
