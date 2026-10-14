# Cierre del intento de tres ciclos de segmentación

> **Corrección y reanudación del 3 de octubre:** el usuario aclaró que las
> doce horas corresponden a ejecución efectiva y excluyen suspensión.
> El cierre por fecha absoluta descrito abajo queda superado; se conserva
> como evidencia histórica. `effective_budget.json` aplica el criterio
> corregido sin alterar `run.json` ni `closure.json`. Se reserva una hora
> estimada para el trabajo anterior (incertidumbre de diez minutos); los
> nuevos trabajos exclusivos y las sesiones activas de preparación/análisis
> registran tiempo despierto del sistema sin doble cómputo. La espera del
> usuario fuera de una sesión activa no consume presupuesto. Los bloqueos
> científicos siguen pendientes hasta superar sus pruebas; el trabajo se
> ha reanudado. Véase el [registro posterior](reanudacion_ciclos_segmentacion_2026-10-03.md).

## Resultado

**Cero ciclos completos de tres previstos.** Se implementó y probó parte de la
infraestructura, pero las escenas no superaron la auditoría geométrica y la
prueba técnica de Gazebo terminó sin imágenes. No existen modelo ganador,
comparación entre ciclos, referencia de vuelo congelada ni evaluación final.
No se demuestra transferencia al cultivo real.

El registro local comenzó el 2 de octubre a las 21:12:02 de Colombia y fijó el
límite para el 3 de octubre a las 09:12:02 (14:12:02 UTC). Al recuperar el reloj
durante el cierre eran las 16:11:41 UTC: el límite ya había vencido. No se
reinició el experimento ni se amplió su plazo. Esto no significa que se hayan
ejecutado doce horas continuas de cómputo. La última prueba de Gazebo había
terminado por timeout; al cierre no había procesos Windows de Blender/Python
ni servidor Gazebo de este ensayo activos en la última inspección de WSL.

Los artefactos se conservan bajo `outputs/segmentation_cycles_20261002/`.
`run.json` conserva el plazo original, semillas, HEAD y huellas de cambios
locales anteriores. Los resultados generados no se incorporan a Git.

## Implementado y comprobado

- Contrato separado de los históricos: `pintona` (incluye verdes), `madura`,
  `sobremadura`, por apariencia visible del capacho. La correspondencia con
  grados sintéticos es explícita; no equivale a madurez agronómica validada.
- Grupos de semillas disjuntos declarados para entrenamiento, validación,
  desarrollo y evaluación final. Se generaron 18 morfologías de entrenamiento
  y seis de validación con resolución por proxies. **No están aceptadas por
  auditoría de mallas.**
- Capturas técnicas RGB/máscaras en Blender; exportador YOLO-seg que rechaza la
  imagen completa si algún polígono no alcanza IoU 0,98.
- Exportación alternativa de máscaras uint16 y cargador de entrenamiento
  que conserva huecos y componentes desconectados. La ida y vuelta del PNG
  original alcanza IoU 1; el redimensionamiento para entrenamiento no implica
  esa misma fidelidad a resolución reducida.
- Prueba técnica de YOLO26n-seg con preentrenamiento general, resolución 960,
  batch solicitado 2, AdamW 0,001 y dos épocas. Usó una imagen de entrenamiento
  y otra de validación **de la misma morfología**, únicamente para comprobar
  ejecución. Duración registrada: 58,85 s. mAP de máscaras: 0. No sirve como
  estimación de generalización ni como modelo del ciclo 1.
- Pesos, curvas, configuración y errores de intentos anteriores conservados
  en `technical_training_v4/` y sus carpetas/logs predecesores. La comprobación
  automática de AMP se omitió al no poder descargar su modelo auxiliar; el
  entrenamiento sí ejecutó AMP. No se fijó un presupuesto común de épocas.
- Preparación de recorrido exterior, margen conservador preflight aproximado
  de 0,725 m, RGB y canal panóptico separado para el evaluador. Solo dos caras
  exteriores previstas; diez caras internas se declaran inaccesibles bajo
  esa preparación. **La separación ejecutada y el encuadre de vuelo no están
  comprobados**, porque no hubo vuelo capturado.

## Resultados negativos y bloqueos

| Prueba sobre semilla 420100 | Pares en `physical_collision_count` | Interpretación |
| --- | ---: | --- |
| Escena técnica inicial | 1029 | No aceptada |
| Resolución por proxies | 178 | Insuficiente para certificar mallas |
| Reparación de pedicelos | 130 | Persisten conflictos |
| Reparación adicional de hojas | 94 | Persisten conflictos |
| Ajuste de ejes y reparación de órganos | 49 | No aceptada; no es ciclo completo |

El último informe separa además 243 intersecciones foliares toleradas y 233
violaciones de separación. De los 49 pares pendientes, 33 son tallo/tallo,
14 hoja/tallo y dos capacho/tallo. El contador físico de esta configuración
incluye cruces hoja/tallo clasificados internamente como `soft_occupancy`:
estos números no deben interpretarse como 49 choques rígidos equivalentes.
No se relajó la aceptación para habilitar entrenamiento principal. Reducir
colisiones tampoco demuestra mayor realismo visual.

Las dos imágenes del paquete técnico fallaron el requisito de polígonos.
Las máscaras fragmentadas pequeñas no se representaron con suficiente IoU
al unir sus contornos. El cargador raster es una **desviación experimental del
formato de entrenamiento previsto**, no una exportación YOLO-seg aprobada.
No hay dataset de 180/240 imágenes que satisfaga el protocolo completo.

Gazebo cargó aproximadamente 11 GiB en el proceso observado, dejando menos
de la reserva de 4 GiB del host durante la inspección. Se solicitó detener el
proceso de esta prueba. El controlador registró `Flight wall timeout` a los
498,40 s, cero RGB, cero waypoints y ningún tiempo simulado disponible.
No se produjo un video final. No se ejecutó la reducción de coste propuesta.

El paquete técnico de vuelo reutiliza un campo v4 anterior; **no materializa
el grupo nuevo de semillas de desarrollo declarado en `run.json`**. No hay
referencia común congelada. El grupo final sigue sin generar ni evaluar.
El evaluador de vuelo es un borrador no ejecutado: faltan comprobación del
decodificador panóptico, pruebas de sincronización y aislamiento, clases
colapsadas, confusión de clases, objetivo/fondo y conteo de identidades únicas.
Sus posibles salidas futuras no pueden considerarse métricas validadas.

## Estado de las etapas

| Etapa | Ciclo 1 | Ciclo 2 | Ciclo 3 |
| --- | --- | --- | --- |
| Apariencia: seis vistas comparables con referencias | Pendiente; pruebas técnicas parciales | Pendiente | Pendiente |
| Dataset aceptado y versionado | Bloqueado por mallas y polígonos | Pendiente | Pendiente |
| Entrenamiento comparable | Pendiente; solo prueba de dos épocas | Pendiente | Pendiente |
| Vuelo, referencia y diagnóstico | Bloqueado antes de RGB | Pendiente | Pendiente |

La revisión de cuatro ciclos no aplica. No se seleccionó checkpoint ni umbral
operativo usando datos reales; tampoco se seleccionó un ganador sintético.

## Verificación y continuidad

Las pruebas unitarias del contrato y cargador cubren mapeo de clases, semillas
disjuntas, rechazo de grados inválidos, contornos, conservación de máscaras,
collation e imposibilidad de reiniciar un registro vencido. No sustituyen las
pruebas end-to-end pendientes. El grafo del repositorio se valida por separado.

Para otro intento, primero se debe resolver la aceptación de una morfología
completa y demostrar diez segundos de RGB/máscaras sincronizados dentro del
presupuesto de memoria. Después deben cerrarse los contratos de particiones,
exportación y evaluador antes de congelar una nueva ventana experimental.
No editar el plazo de este registro ni presentar sus pruebas como un ciclo.
Las búsquedas de poses son heurísticas en desarrollo, no parámetros botánicos
medidos; deben reconstruirse y auditarse antes de cualquier uso principal.
