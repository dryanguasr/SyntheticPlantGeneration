# Reporte comparativo de la evolución multi-planta

Fecha de ejecución: 2026-07-23.

Este reporte separa resultados verificados de una semilla de control de las
campañas estadísticas todavía pendientes. Los resultados no convierten
parámetros heurísticos en evidencia botánica.

## Estado de implementación

Quedaron implementados los contratos serializables, los presets
morfológicos, el trellis previo al crecimiento, la coordinación sincronizada,
la ocupación compartida, la política de contacto, las variantes A–F, las
métricas, los diagnósticos Blender, la auditoría ampliada de malla y el
manifest reproducible de referencia.

La ruta principal es:

```text
parámetros y procedencia
  → morfologías potenciales
  → propuestas sincronizadas
  → decisiones y ocupación compartida
  → morfologías aceptadas
  → geometría y anotaciones
```

El adaptador anterior permanece disponible como `legacy_posthoc`.

## Comparación controlada: semilla 1

El baseline es `dense_staked_crop` con
`initial_migration_manual_guess`. La variante nueva es
`dense_trellis_synchronous` con `trained_trellis` y
`E_plus_contact_policy_clearance`.

| Métrica | Baseline A | Variante E | Cambio observado |
|---|---:|---:|---:|
| Plantas | 20 | 20 | 0 |
| Ejes | 105 | 150 | +42,9 % |
| Ejes por planta | 5,25 | 7,50 | +42,9 % |
| Hojas | 528 | 640 | +21,2 % por más nodos |
| Mediana de longitud foliar | 8,070 cm | 5,107 cm | −36,7 % |
| Unidades reproductivas materializadas | 168 | 112 | −33,3 % |
| Ejes largos sin hijas | 33,3 % | 0,0 % | −100 % |
| Correcciones post hoc | 1.258 | 0 | −100 % |
| Conflictos proxy duros | 0 con tolerancia legado | 0 con política estricta | Criterio separado |
| Violaciones de clearance duro | No separadas | 0 | Criterio explícito |
| Clearance estricto mínimo | −0,00189 legado | +0,021788 | Positivo |

La variante E no compensa densidad mediante hojas mayores: su mediana foliar
es menor y el aumento de hojas procede de más nodos y ejes. Las 171
propuestas se resolvieron como 91 aceptadas, 36 desviadas, 3 acortadas, 10
diferidas y 31 canceladas. De las cancelaciones, 27 corresponden a yemas
reproductivas que no encontraron un camino con clearance duro. Esta pérdida
reproductiva es un riesgo explícito de calibración, no un resultado botánico.

Frente a las medianas correctivas del baseline —hojas 80°, pedicelos 69° y
ejes 107°— la variante E no aplica rotaciones post hoc. Las desviaciones de
crecimiento ocurren antes de incorporar el órgano, se serializan y tienen
mediana global 0° y percentil 95 de 43,3383°.

## Contacto, oclusión y soporte

La auditoría proxy final de la semilla 1 informa:

- 0 conflictos de ocupación dura;
- 0 violaciones de clearance duro;
- 320 solapamientos de ocupación blanda;
- 118 contactos intencionales con soporte;
- 1.249 contactos cercanos;
- 177 oclusiones visuales proxy.

Estos conteos no se agregan en una única puntuación. El trellis tiene postes
extremos, líneas longitudinales y amarres fijos antes del crecimiento. Su
ablación con la misma semilla cambia las decisiones morfológicas y está
cubierta por prueba automática.

## Artefactos reproducibles

El diagnóstico puro de la semilla 1 está en
`outputs/diagnostics/E_final_seed_1/` y contiene JSON, CSV y Markdown. Registró
la huella SHA-256 del árbol fuente en `experiment.json`, además del tiempo de
ejecución y la memoria pico. La huella se conserva en el artefacto para evitar
una referencia autocambiante dentro de un archivo que también forma parte del
árbol medido.

Las siete vistas económicas (`skeleton`, `branch_order`, `plant_id`,
`leaf_scale_correction`, `contacts`, `global` y `close`) se regeneraron para
las semillas 0, 1 y 9 bajo
`outputs/diagnostic_renders/E_plus_contact_policy_clearance/`.

La integración detallada de una planta y su trellis auditó 100 objetos
evaluados, 941 pares de fase amplia y 800 pares de fase estrecha. El resultado
fue válido: 0 intersecciones físicas, 0 violaciones de clearance, 6 contactos
intencionales poste–línea, 2 intersecciones blandas hoja–poste y 5 contactos
cercanos. El artefacto está en
`outputs/diagnostic_renders/E_plus_contact_policy_clearance/seed_1_full_mesh_smoke/`.

El manifest de referencia derivado contiene 1.061 etiquetas de `train` para
calibración y 133 de `val` para evaluación; las 133 de `test` están excluidas.
No se escribió dentro de `Dataset Original/`.

## Aceptación cerrada y aceptación pendiente

Quedaron verificados en esta ejecución:

- conservación exacta del baseline morfológico de la semilla 1;
- round trip JSON aditivo;
- determinismo y invariancia al orden de plantas;
- cambio morfológico causado por la ablación de soporte;
- contrato YOLO `{"calyx": 0}` y fruto oculto;
- cero correcciones post hoc y cero violaciones proxy duras en la semilla 1;
- regresiones Python y validez del grafo de contexto.

No se declara todavía aceptación estadística final. Deben ejecutarse y
revisarse los siguientes cortes costosos:

1. 30 semillas A–F para morfología y métricas puras;
2. 10 semillas para geometría, clearance y evaluación proyectiva contra
   `val`;
3. auditoría BVH de geometría detallada para las escenas densas;
4. decisión de conservar o retirar F según calidad de copa y límite de 2×;
5. confirmación de los criterios “7 de 10” y “60 % de métricas proyectivas”.

Los renders económicos usan geometría proxy para depuración estructural. No
sustituyen los RGB detallados ni la autoridad BVH de mallas evaluadas.
