# Repetir el piloto acotado de 115 imágenes corregidas

Esta ruta conserva el modelo morfológico, árboles admitidos y cámaras del
piloto anterior. Cambia apariencia de cáliz y condiciones de captura con
semillas separadas. No reanuda el generador histórico ni amplía automáticamente.

1. `prepare_daylight_115_bank.py ROOT` congela fuentes, siete disposiciones,
   máscaras originales, asignaciones y exactamente 115 condiciones. Rechaza
   una raíz existente; para continuar se reutiliza el controlador.
2. `run_daylight_115_bank.py ROOT` mantiene un Blender propio, comprueba hashes
   y la pausa histórica, recicla memoria y sella exactamente 115 RGB nuevos.
   Un segundo argumento entero sirve sólo para un benchmark acotado; no cambia
   el plan de 115 ni reinicia relojes. No entrenar a partir de un prefijo.
3. `report_daylight_115_bank.py ROOT --final` coteja fuentes, pares y máscaras,
   genera `bank/review.html`, resumen y muestras por cielo/profundidad. Revisar
   las imágenes reales y los siete controles nativos de máscara antes de crear
   `bank/technical_review.json`, con `passed=true` y SHA de `bank/sealed.json`.
4. `daylight_augmentation_pilot.py prepare --root ROOT/pilot` congela la receta,
   datos y seis configuraciones nuevas; `run --root ROOT/pilot` las ejecuta y
   evalúa. No editar fuentes congeladas durante una corrida. Las identidades
   nativas y locks OS impiden duplicar procesos; verificar PID y FILETIME antes
   de recuperar un intento parcial.
5. Revisar curvas, predicciones y resultados por semilla/clase, especialmente
   Sobremadura y Madura. Entregar al usuario antes de ampliar. El test histórico
   sigue siendo desarrollo y el banco cambia varios factores simultáneamente.
   `report_daylight_exposure.py ROOT/pilot` reconstruye dosis completas y de
   checkpoints seleccionados sin entrenar ni inferir. `diagnose_daylight_pilot.py
   ROOT/pilot --out CARPETA_NUEVA` compara Sobre desde predicciones guardadas;
   conserva el umbral fijado en val y separa ejemplos de la frecuencia global.

Las máscaras reutilizadas sólo se aceptan con igualdad exacta de cámara,
geometría binaria, visibilidad e intrínsecos y una comprobación nativa nueva
por disposición. Los 115 pares mantienen auditoría de píxeles/IDs/cajas/YOLO.
Las etiquetas diminutas permanecen: el consumidor aplica los filtros nativos
de Ultralytics de la receta de detección congelada, sin cortes adicionales.

El secado es apariencia óptica: no se contraen ni podan las plantas admitidas.
La corrección de cromaticidad ambiental es una heurística visual calibrada con
carta neutra; conserva cielo y mapas, sin afirmar radiometría atmosférica validada.
No se necesitan dependencias nuevas. Véase el informe
`docs/reports/piloto_115_cielos_secado_2026-11-12.md` para el alcance y los
resultados reales de esta ejecución.

La ejecución del 12/11 quedó cerrada con 115 pares auditados y seis corridas
completas. Delta macro medio +0,87 pp, Sobremadura −2,54 pp de media y descenso en cada semilla;
el intervalo macro por grupos incluye cero. Se mantiene la generación pausada:
una mejora visual o de AP agregado no activa una nueva ampliación.
