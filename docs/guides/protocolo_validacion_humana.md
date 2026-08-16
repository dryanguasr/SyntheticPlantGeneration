# Protocolo de validación humana y render estándar

## Propósito

Después de un cambio significativo se revisan diez casos lógicos estables,
cada uno bajo condiciones de cultivo, fenología, iluminación, cámara y entorno
predeclaradas. La suite candidata se compara con la última suite aceptada; no
se seleccionan semillas por apariencia.

Se considera significativo un cambio en morfología, crecimiento, contacto,
soporte, geometría, materiales, iluminación, cámara, render o anotaciones. La
ejecución es manual para evitar iniciar renderizados costosos de forma
accidental.

## Matriz de casos

| Caso | Plantas | Fenología | Luz | Cámara | Foco |
|---|---:|---|---|---|---|
| 01 | 20 | balanced | mediodía | context wide | arquitectura global |
| 02 | 20 | balanced | nublado | oblicua media | oclusión y clearance |
| 03 | 12 | early | mañana | robot close | trellis y amarres |
| 04 | 12 | early | mañana | robot close | ablación del soporte |
| 05 | 8 | early | nublado | real close | unión axilar |
| 06 | 8 | late | tarde | real close | condición seca |
| 07 | 1 | balanced | mañana | real close | hoja y material |
| 08 | 4 | late | mediodía | robot close | forma del capacho |
| 09 | 12 | balanced | tarde | oblicua media | contraluz y ruido |
| 10 | 20 | late | nublado | context wide | entorno y regresión |

Los problemas activos deben estar cubiertos por al menos tres casos y los
problemas históricos con severidad `blocker` por al menos uno. Esta cobertura
se valida antes de abrir Blender.

## Perfiles de render

- `diagnostic_eevee`: 64 muestras, salida económica; no sirve como evidencia
  de aceptación.
- `standard_eevee`: EEVEE, 128 muestras y salida de 8 bits. Es el perfil
  predeterminado para una suite completa de aceptación mientras el detalle
  adicional de Cycles no produzca una ventaja significativa.
- `photoreal_review`: Cycles, 256 muestras máximas, adaptive sampling y
  OpenImageDenoise; solo se usa por selección explícita.
- `photoreal_final`: Cycles, 512 muestras máximas, mínimo 64, umbral `0.005`,
  PNG de 16 bits y AgX; se conserva como opción explícita para una etapa futura
  en la que el detalle vuelva a ser crítico.

Si se selecciona Cycles, intenta OptiX, luego CUDA y finalmente CPU. El
dispositivo real, los fallbacks, tiempo y memoria disponible se registran por
caso.

El costo no se estima con una cifra fija: `elapsed_seconds` registra el tiempo
real total de cada caso y `beauty.elapsed_seconds` separa el render candidato.
En un bootstrap se contabilizan además el render y la escena post hoc de
referencia. El reporte Markdown resume estos valores; así un cambio de GPU,
fallback o complejidad geométrica no queda oculto detrás de una estimación.

El preflight renderiza 320×180 y mide mediana, percentiles 5/95 y clipping.
Solo puede modificar exposición en pasos de 0,25 EV; nunca mueve luces ni
cambia materiales. Después de aceptar un baseline, el EV se bloquea para que
el par antes/después mantenga el mismo procesamiento.

Los casos 07–09 también guardan:

- `material_override.png`, que elimina las texturas para separar problemas de
  geometría y sombreado.

`diagnostic_passes.exr` y el conteo de muestras se generan únicamente cuando
se selecciona un perfil Cycles. El perfil estándar no cambia de motor a
escondidas para producir pases auxiliares.

Las normales usan fortalezas heurísticas conservadoras: `0.30` en hojas,
`0.40` en capachos verdes, `0.45` en pajizos y `0.50` en secos. Los mapas usan
interpolación cúbica. Estos valores no son mediciones botánicas.

## Primer baseline

La inicialización produce los dos lados. El lado de referencia usa el modelo
post hoc retenido (`A_baseline_independent`) y el candidato usa la variante
declarada por el caso. Ambos se renderizan con el mismo perfil solicitado,
materiales, luz, entorno, cámara y exposición. Un bootstrap usa
`standard_eevee` salvo que se solicite Cycles explícitamente. Un baseline y su
candidato deben usar el mismo perfil.

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background `
  --python scripts\generate_human_validation_suite.py -- `
  --change-id standard_render_protocol_v1 `
  --change-category render `
  --change-category materials `
  --bootstrap
```

El comando completo usa auditoría `full_mesh` y `standard_eevee`. Para probar
la integración de un caso sin convertirlo en evidencia:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background `
  --python scripts\generate_human_validation_suite.py -- `
  --change-id smoke_case_07 `
  --change-category render `
  --bootstrap `
  --smoke `
  --case-id case_07
```

El runner reutiliza por defecto los activos CC0 empaquetados en el piloto
histórico y registra el archivo portador. Puede sustituirse con
`--environment-asset-dir` o `--environment-asset-blend`.

## Cambios posteriores

Una suite nueva debe apuntar al manifest aceptado:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background `
  --python scripts\generate_human_validation_suite.py -- `
  --change-id growth_clearance_v2 `
  --change-category growth `
  --change-category contacts `
  --baseline-manifest outputs\human_validation\standard_render_protocol_v1\accepted_baseline_manifest.json
```

Las semillas y condiciones se toman del baseline. Si la matriz cambia, el
comando rechaza la comparación y exige incrementar la versión del protocolo y
crear un bootstrap.

## Artefactos

Cada caso contiene:

- `candidate.blend`;
- `candidate.png` y su preflight;
- `scene.json`, `morphologies.json`, `metrics.json` y validación;
- `comparison_before_after.png`;
- diagnóstico auxiliar cuando corresponde.

Durante el bootstrap también se conservan `baseline_bootstrap.blend`,
`baseline_bootstrap.png`, su morfología, métricas y validación.

La raíz contiene `suite_manifest.json`, `contact_sheet_10_cases.png`,
`report.md`, `human_review.csv` y `suite_manifest.json.sha256`. El manifest y
su sidecar SHA-256 se actualizan después de cada caso para conservar progreso
ante un fallo.

## Revisión y promoción

El revisor completa las diez filas de `human_review.csv`. La suite requiere:

- al menos ocho decisiones `pass`;
- máximo dos `minor`;
- cero `major`, `blocker` o `pending`;
- cero interpenetraciones no intencionales y cero violaciones de clearance.

En cambios posteriores al bootstrap, la columna `problem_outcomes` también se
completa con `improved`, `unchanged` o `worse` para cada problema activo
prellenado. Cada problema debe mejorar en la mayoría de sus casos expuestos y
no puede empeorar en ninguno. Solo un manifest con estado
`accepted_baseline`, producido por la promoción manual, puede reutilizarse.

La promoción es explícita y nunca sobrescribe el manifest fuente:

```powershell
$env:PYTHONPATH='C:\dev\SyntheticPlantGeneration\src'
python scripts\promote_human_validation_suite.py `
  outputs\human_validation\standard_render_protocol_v1\suite_manifest.json
```

El resultado es `accepted_baseline_manifest.json`, que será la referencia de
la siguiente iteración. Antes de evaluar el CSV, el promotor verifica
`suite_manifest.json.sha256`; una modificación del manifest después de la
generación bloquea la promoción.

## Límites

- Una configuración Cycles no demuestra por sí sola fotorrealismo; la
  decisión final sigue siendo humana y queda registrada.
- Los smoke tests, auditorías proxy y perfiles Eevee nunca son aceptables como
  baseline.
- No se modifica `Dataset Original/`, el fruto continúa oculto y el contrato
  YOLO permanece `{"calyx": 0}`.
