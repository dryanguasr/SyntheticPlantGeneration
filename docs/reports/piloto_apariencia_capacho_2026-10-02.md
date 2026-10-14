# Piloto de apariencia del capacho: tres categorías

Se ejecutaron diez capturas Blender de una misma planta, sin crear un dataset
ni entrenar. El usuario confirmó que **pintona, madura y sobremadura se asignan
por apariencia del capacho**. La correspondencia de materiales propuesta aquí
requiere revisión humana; no representa madurez agronómica medida del fruto.

## Entrada y contraste

Se reutilizó `plant_13` de `individual_bouquet_crown_v4`, semilla 23092613,
con su árbol morfológico y escena existente. Se trabajó en la rama de
intervención `codex/reconstruction-pilot-20261001`, sobre HEAD
`8cf9c4e33437c84fb5bacaacf02c8a60096ad3df`, preservando los cambios locales
anteriores. No se modificaron módulos del modelo ni el contrato histórico de
cuatro clases del piloto de cultivo.

Se inspeccionaron las ilustraciones 01, 02 y 06 de
`docs/reports/assets/nuevo_dataset_2026-09-23/`, todas de train. La galería
incluye 02 y 06; no se adjudicaron clases a esas fotografías. Son imágenes
reducidas para revisión, no nuevas mediciones calibradas ni una muestra
representativa de las tres clases. No se consultaron nuevas imágenes de test.

Las referencias muestran nervaduras oscuras, variación de orientación,
arrugamiento foliar, solapamiento y tutorado abundante. La escena reciente
usaba materiales planos `calyx_ntc_*`; se ensayó su sustitución por los mapas
procedurales ya existentes. **No se estimaron parámetros de clase a partir
de etiquetas reales terminadas**, porque aún están en preparación.

## Ejecuciones nuevas

- `outputs/appearance_pilot_20261002_v1/`: siete RGB de 960 × 720; dos cámaras
  con material base y texturizado, más tres estados de apariencia del capacho
  focal. Tiempo interno total registrado: 50,0 s.
- `outputs/appearance_pilot_20261002_v2/`: tres primeros planos con mayor luz
  ambiental y relleno frontal. Misma geometría y encuadre; entre estas tres
  imágenes solo cambia el material del capacho focal.
- `outputs/appearance_pilot_20261002_v2/review/index.html`: galería comparativa,
  lámina `comparacion.jpg` y verificación de los diez archivos.

Cada ejecución conserva árbol JSON, validación morfológica, copia de auditoría
de malla de origen, escena editable con texturas empacadas, cámaras, tiempos,
hashes y copia exacta del runner. La segunda verifica por hash que las
coordenadas, caras y transformaciones de las mallas semánticas se conservaron.
La validación morfológica nueva informa `valid_with_warnings`. La auditoría
de mallas es **recuperada**, no una nueva ejecución: sus conflictos previos
continúan pendientes (565 pares según el informe de tutorado). No se midió
oclusión ni se generaron máscaras o etiquetas YOLO.

La memoria disponible observada fue 13.409 MiB antes y 12.741 MiB durante
la primera ejecución; se observó un solo proceso Blender, con 977 MiB RSS
en ese sondeo. No son mediciones de pico. Ambas ejecuciones terminaron
correctamente. El informe verifica hashes, dimensiones y decodificación de
10/10 PNG, además de la correspondencia del código archivado.

## Hipótesis de apariencia, pendientes de aprobación

| Categoría prevista | Material inicial |
|---|---|
| Pintona | `calyx_transition_v0` |
| Madura | `calyx_straw_v1` |
| Sobremadura | `calyx_dry_v1` |

Esta tabla es `manual_initial_guess`, no equivalencia validada. Los capachos
de contexto reciben una mezcla determinista por identidad para conservar
heterogeneidad visual; no se cambia su historia fenológica. El archivo
`appearance_review.json` separa hipótesis visual, revisión humana pendiente
y madurez del fruto desconocida. No debe usarse como ground truth de entrenamiento.

## Lectura visual y siguiente iteración

La luz revisada facilita inspeccionar el órgano, pero no prueba mayor realismo.
Los mapas recuperan nervaduras que faltaban en el material plano, aunque
siguen mucho menos contrastadas que en la fotografía real. Las hojas se ven
demasiado planas y ordenadas; también deben revisarse proporción del capacho,
relieve, ápice y distribución de orientaciones. El fondo es diagnóstico y
simple: falta reintroducir tutorado, suelo y plantas vecinas antes de evaluar
capturas contextuales.

Primero revisar los tres capachos focales con los estudiantes y ajustar sus
fronteras visuales usando ejemplos reales de desarrollo adjudicados. Después
ensayar nervaduras y relieve sobre estas mismas cámaras y semilla, conservando
el control anterior. El beneficio de aumento sintético queda sin evaluar;
no se justifica todavía ampliar la generación.

## Reproducción

Usar una carpeta nueva para no sobrescribir evidencia. El runner admite:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' --background --factory-startup --python-exit-code 1 --python scripts/render_appearance_pilot.py -- --source outputs/bouquet_crowns_v4/review/plant_13_dense.blend --morphology outputs/bouquet_crowns_v4/plants/plant_13.json --audit outputs/bouquet_crowns_v4/review/plant_13_mesh_contacts.json --output outputs/appearance_pilot_nueva_revision --focus-only --frontal-fill
```

Sin las dos últimas opciones produce siete comparaciones. El ensamblador
`scripts/report_appearance_pilot.py` corresponde específicamente a las dos
ejecuciones del 2 de octubre y rechaza sobrescribir su galería.
