# Preparación para redactar el artículo

Estado de preparación al **24 de noviembre de 2026**. Este entorno permite
preparar citas, tablas y figuras mientras se recibe el manuscrito. La clase,
el estilo bibliográfico y los requisitos de exportación se ajustarán a la revista.

## Herramientas disponibles

- Tectonic `0.17.0+20260731` y Python `3.12.14`, proporcionados por el runtime de Codex.
- Entorno local `.venv-writing`, creado con `--system-site-packages`, con
  Matplotlib `3.11.2` y bibtexparser `2.1.0` instalados localmente.
- La base del runtime incluye NumPy `2.3.5`, pandas `3.0.1`, Pillow `13.0.0`,
  pypdf `6.21.4`, pdfplumber `0.11.9`, pypdfium2 `5.13.0`, ReportLab `4.4.9`
  y Poppler.

Los requisitos Python se registran en
[`scripts/writing_requirements.txt`](../../scripts/writing_requirements.txt).
Para reproducirlos en un entorno independiente, use un Python válido:

```powershell
python -m venv .venv-writing-repro
.\.venv-writing-repro\Scripts\python.exe -m pip install -r scripts/writing_requirements.txt
```

En Codex, `load_workspace_dependencies` permite localizar las herramientas del
runtime sin fijar rutas internas de WindowsApps. Si `python` apunta a un alias
de Microsoft Store que no ejecuta, utilice la ruta de un intérprete válido.
Tectonic y Poppler son herramientas externas al entorno creado por `venv`.
Para Poppler se comprobaron los ejecutables de `Library/bin` directamente;
los accesos `.cmd` del runtime fallaron. PDFium mediante `pdfplumber` también
permite renderizar las páginas y fue el método usado para la revisión completa.

La prueba técnica está en
[`outputs/writing_setup/latex_smoke/main.tex`](../../outputs/writing_setup/latex_smoke/main.tex).
Incluye español, citas con BibTeX, tablas y una figura vectorial PDF. Desde la
raíz del repositorio, con Tectonic disponible en la sesión:

```powershell
tectonic --untrusted --keep-logs --keep-intermediates outputs/writing_setup/latex_smoke/main.tex
```

El primer uso puede descargar paquetes. La compilación desde terminal y la del
editor de Codex se verifican por separado. Biber no está validado; los paquetes
y el backend bibliográfico definitivos dependen de la plantilla editorial.

La prueba incluye `fontspec`, `babel`, `geometry`, `graphicx`, `caption`,
`subcaption`, `booktabs`, `multirow`, `tabularx`, `longtable`, `amsmath`,
`amssymb`, `siunitx`, `xcolor`, `microtype`, `natbib`, `tikz`, `hyperref` y
`cleveref`. Para reproducirla se especifican Latin Modern mediante archivos
`.otf` (`lmroman10-regular.otf` y variantes) en `\setmainfont`, español en Babel
y `\usetikzlibrary{babel}` para evitar conflictos de caracteres con TikZ.

## Bibliografía que se puede reutilizar

Las bibliografías existentes contienen **32 entradas**, 25 en
[`referencias_uchuva_lsystem.bib`](../references/referencias_uchuva_lsystem.bib)
y 7 en [`auditoria_blender_2026-09-08.bib`](../references/auditoria_blender_2026-09-08.bib).
No se encontraron claves repetidas. Sí hay fuentes repetidas con claves
distintas: Kew para *Physalis peruviana* y las versiones preprint/editorial
de Fei et al. (2021). Conviene elegir qué versión citar antes de componer
la bibliografía final.

Los DOI, URL, metadatos, estatus editorial y adecuación de cada fuente quedan
pendientes de revisión según las afirmaciones del manuscrito y la revista.
La entrada de World Agroforestry carece de año: no debe completarse por
suposición. La [política de referencias](../references/README.md) conserva
DOI/URL y excluye los PDFs de artículos de Git.

## Incorporación de resultados y figuras

El punto de entrada es el
[índice de resultados experimentales](../reports/indice_resultados_experimentales.md),
que enlaza los informes de
[segmentación](../reports/resultados_segmentacion_privada_2026-11-24.md) y
[detección y generación](../reports/resultados_pilotos_deteccion_y_generacion_2026-11-24.md).
Las tablas reproducibles están en
[`datos_segmentacion_2026-11-24/`](../reports/datos_segmentacion_2026-11-24/).

En esos CSV, AP, precisión y sensibilidad son fracciones de 0 a 1; una celda
vacía indica un valor indefinido y no equivale a cero. Las diferencias entre
porcentajes se presentan en puntos porcentuales. Cada tabla o figura debe
identificar su fuente, partición, métrica, unidad y agregación entre semillas.
Para gráficas se prioriza PDF vectorial y se conserva el dato de origen.

La redacción debe mantener explícitos los resultados negativos y los límites
del protocolo: desarrollo histórico exploratorio, referencias provisionales
y revisión humana pendiente cuando corresponda. Las clases describen apariencia
del capacho; no acreditan madurez interna del fruto. Los metadatos sintéticos
y las máscaras asistidas no deben presentarse como verdad de referencia real
validada. Las semillas que comparten fotografías no aportan muestras de campo
independientes. No se completarán datos ni resultados ausentes por suposición.

## Verificación realizada

- El editor de Codex compiló la prueba mediante `compile_latex_document`,
  con las 32 referencias incluidas por `\nocite{*}`.
- Las bibliotecas Python se importaron correctamente; `pip check` devolvió
  `No broken requirements found`.
- BibtexParser leyó las 25 y 7 entradas sin bloques fallidos (`failed_blocks`)
  ni claves repetidas. Esta comprobación sintáctica no verifica las fuentes.
- La figura de prueba, sin datos experimentales, se exportó a PDF y SVG con
  texto y fuentes vectoriales (`pdf.fonttype=42`, `svg.fonttype=none`), además
  de PNG a 300 dpi.

El registro de comprobaciones está en
[`outputs/writing_setup/environment_check.json`](../../outputs/writing_setup/environment_check.json).
Las salidas de prueba permanecen fuera de Git.

- La compilación nativa por terminal terminó correctamente y se repitió con
  `--only-cached`, sin nuevas descargas. El PDF contiene cuatro páginas y 32
  entradas bibliográficas; las citas y referencias cruzadas están resueltas.
- Se renderizaron y revisaron visualmente las cuatro páginas con PDFium:
  español, tabla, curva vectorial, diagrama y bibliografía legibles, sin cortes
  ni superposiciones. `cleveref` usa la opción `spanish`.
- BibTeX conserva un aviso por el año ausente en la entrada de World
  Agroforestry. La composición conserva dos avisos `Underfull \hbox` en la
  bibliografía; no se observaron desbordamientos ni caracteres ausentes.
  Tectonic avisa de una configuración Fontconfig ausente; la carga explícita
  de los archivos `.otf` funcionó y las fuentes se comprobaron en el PDF.

El [PDF de prueba](../../outputs/writing_setup/latex_smoke/main.pdf) comprueba
el entorno editorial; no es un manuscrito ni contiene resultados científicos.
El contenido de las referencias y el formato de la revista siguen pendientes
de la redacción que se va a incorporar.

Documentación de las herramientas: [Tectonic](https://tectonic-typesetting.github.io/book/latest/)
y [BibtexParser](https://bibtexparser.readthedocs.io/en/main/).
