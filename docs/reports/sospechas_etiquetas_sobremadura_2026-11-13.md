# Casos sospechosos de etiquetas Sobremadura en evaluación

Se cribaron visualmente las 94 fotos reales solicitadas y 144 regiones
propuestas por las doce cachés existentes (cuatro familias, tres semillas).
Se documentan **17 candidatos para adjudicación humana**, no 17 errores
confirmados: seis etiquetados Pintona, seis Madura y cinco regiones sin caja
sobre el candidato. Siete discrepancias de clase tienen prioridad visual;
cinco son ambiguas. La generación y el piloto permanecen pausados.

## Criterio y límites

Se revisaron la foto contextual con las cajas originales y el recorte limpio:
pigmentación proximal y de venas, extensión entre venas, aspecto gris/pardo,
textura seca, pliegues y conservación de volumen. Oscuridad, sombra o una
predicción Sobremadura no determinan la clase. La apariencia del capacho no
valida madurez interna ni reabsorción fisiológica. Estos atributos no se
convirtieron en una regla automática ni se cambiaron etiquetas.

Las propuestas automáticas fueron 80 cajas de otra clase con candidato Sobre
a IoU >=0,5 y 64 agrupaciones con IoU <0,1 frente a cualquier GT. Estas últimas
incluyen hojas, manos, flores, oclusiones y otros falsos positivos. Para las
cinco regiones sin caja seleccionadas se comprobó también la fracción del
candidato cubierta por cualquier GT: 0 a 0,00591. No son cajas pequeñas
simplemente contenidas dentro de otra anotación. La política de visibilidad,
tamaño y órganos admisibles todavía debe adjudicarse antes de llamarlas
omisiones erróneas.

El cribado no garantiza encontrar todos los órganos diminutos u ocultos.
No estima prevalencia de errores. Los modelos sólo proponen regiones; sus
confianzas y acuerdos no son votos independientes ni verdad terreno.
Las referencias históricas usan otro banco/dosis. El test es de desarrollo,
ya consultado históricamente: no se recalcularon métricas con labels supuestos
ni se ajustó el modelo a estas observaciones.

## Lista para revisar

Índices GT de base cero, según el orden original de las líneas YOLO.

| Caso | Foto / GT | Etiqueta actual | Motivo de revisión | Prioridad |
|---|---|---|---|---|
| P1 | 153 / 11 | Pintona | Muy oscuro, contorno estrecho y plegado | Alta |
| P2 | 153 / 6 | Pintona | Pardo/gris entre venas y aspecto seco | Alta |
| P3 | 364 / 1 | Pintona | Pigmentación extensa y pliegues | Alta |
| P4 | 548 / 5 | Pintona | Estrecho y seco; comprobar vista parcial | Alta |
| P5 | 579 / 5 | Pintona | Pigmentado, pero conserva volumen | Ambigua |
| P6 | 44 / 1 | Pintona | Oscuro y de baja resolución | Ambigua |
| M1 | 153 / 1 | Madura | Pardo, alargado y plegado | Alta |
| M2 | 599 / 2 | Madura | Tejido pardo, pliegues y apertura aparente | Alta |
| M3 | 548 / 2 | Madura | Pardo y seco, detalle limitado | Alta |
| M4 | 282 / 1 | Madura | Pajizo, pliegues y zona proximal oscura | Ambigua |
| M5 | 101 / 0 | Madura | Papeloso y mancha proximal, aún inflado | Ambigua |
| M6 | 579 / 0 | Madura | Gris/pardo entre venas, conserva volumen | Ambigua |
| U1 | 113 / sin caja | Sin anotación sobre el candidato | Capacho oscuro visible fuera de la única GT | Revisar instancia y después clase |
| U3 | 8 / sin caja | Sin anotación sobre el candidato | Estructura parda/papelosa; confirmar órgano | Identidad y clase pendientes |
| U4 | 384 / sin caja | Sin anotación sobre el candidato | Compatible con capacho seco o tejido foliar | Identidad y clase pendientes |
| U5 | 584 / sin caja | Sin anotación sobre el candidato | Posible repetición de U4 | No contar como órgano independiente |
| U6 | 661 / sin caja | Sin anotación sobre el candidato | Capacho a contraluz | Posible omisión; clase incierta |

U2 (588, región propuesta sin caja) se conserva **fuera del listado**: al
ampliar parece tejido foliar enrollado con una nervadura central, sin base
suficiente para presentarlo como Sobremadura omitida. Otras propuestas
correspondían claramente a hojas amarillas/secas o a una mano. Se evita
convertir esos falsos positivos en supuestas omisiones.

U4/U5 muestran una escena muy similar y pueden repetir el mismo órgano.
También hay fotogramas relacionados entre otras filas; los conteos son
registros de revisión y no individuos botánicos independientes.

## Entrega y preservación

En `outputs/suspected_sobremadura_labels_20261113`:

- `galeria_P.png`, `galeria_M.png`, `galeria_U.png`: recortes sin superposición
  para inspeccionar textura y forma.
- `cases/`: 17 fichas seleccionadas con foto contextual, todas las GT
  originales, región propuesta en amarillo y recorte limpio. U2 se preserva
  como ejemplo descartado y no entra en el ZIP de candidatos.
- `casos_sospechosos_para_revisar.zip`: tres galerías, las 17 fichas, índice y
  registros con coordenadas, rutas y hashes; sin JavaScript ni HTML necesario.
- `candidates.json`, `reviewed_cases.json`, `selected_cases.json`: separación
  entre propuesta de modelo, inspección de Codex y selección para revisión
  humana. Ninguna equivale a adjudicación humana.
- `input_lock.json`, `state.json`, `delivery_manifest.json`: fuentes y hashes,
  pausa y ausencia de nuevas inferencias/entrenamientos/renders. Se verificaron
  2.142 entradas del lock de entrenamiento y las entradas de revisión.

Se inspeccionaron los 16 mosaicos de fotos, los 12 de propuestas, las fichas
individuales y las tres galerías finales. Los RGB, labels y pesos originales
no cambiaron. El controlador histórico propio se comprobó por PID y creation
tick sin tocarlo; no estaba vivo. El validador del grafo conserva diez errores
de localizadores preexistentes, sin nuevos errores de esta intervención.

El siguiente paso es adjudicar los casos según un criterio de clase acordado,
incluyendo qué hacer con un capacho seco cuyo fruto no se ve y con los órganos
parcialmente ocultos. No se propone cambiar las etiquetas para favorecer a
ningún modelo ni reanudar la campaña con esta lista.
