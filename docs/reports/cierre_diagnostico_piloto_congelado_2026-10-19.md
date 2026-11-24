# Cierre diagnóstico y piloto congelado — 19 de octubre de 2026

La campaña integral del 14 de octubre se cierra por instrucción del usuario como diagnóstico documentado. **No se declara alcanzado el objetivo científico global ni se promueve un modelo a producción.** Los artefactos, pesos parciales, registros de errores y resultados negativos permanecen en `outputs/integral_diagnosis_20261014`.

## Resultados retenidos

- V186: piloto cercano completado, 516 actualizaciones reales. En prueba de desarrollo: precisión 77,19 %, recuperación 43,82 %, F1 55,90 %. No es un holdout externo intacto.
- V192: 156 actualizaciones reales, 432 tensores cambiados por época. Sobre los mismos ocho fotogramas diagnósticos, F1 pasó de 47,91 % a 50,70 %; con el filtro predeclarado de tamaño, de 65,32 % a 68,35 %. Confusiones pintona→madura: 58→51. Son resultados de validación, no evidencia de generalización final.
- V189: localización condicional de 35 tracks, mediana 1,36 cm; cobertura global insuficiente para demostrar el objetivo original. No extrapolar el resultado condicional a todos los frutos.
- V193: dos vistas verificadas con vecinos anotados, suelo procedural y cielo; no valida fotorrealismo. Se congela este entorno sin otra búsqueda estética.

## Resultados negativos y pendientes

Se conservan V182 sin detecciones, V185 interrumpido por RAM, el incumplimiento transitorio de RAM de V186 y su repetición segura, omisiones, cambios de identidad y confusiones residuales, así como los fallos de API de cielo de V193. La comparación V190, recorridos extensos y evaluación final reservada quedan diferidos, no aprobados. Las semillas 914140–914145 siguen sin utilizarse.

## Siguiente piloto autorizado

Raíz: `outputs/frozen_field_pilot_20261019`. Copias independientes y SHA256 de generador, materiales, recursos, ocho plantas, pesos V186/V192 y protocolo. Arquitectura V142 y cultivos V181 sin cambios; entorno V193 fijo, sin plántulas geométricas. El marcador físico ArUco8 es un accesorio de medición predeclarado, no una modificación botánica.

Plan: 200 imágenes de entrenamiento, 40 de validación, 40 de prueba de desarrollo; tres recorridos continuos de 120 fotogramas a 2 Hz; 10 épocas, como máximo 1600 parches de entrenamiento. Inicialización V192, referencia V186. Estimación 6–12 horas de ejecución disponible, no garantía de plazo ni autorización para refinar el generador. Un trabajo pesado GPU, admisión de 6,5 GiB y reserva de 2 GiB.

Secuencia: renderizado y controles nativos de máscaras/identidades; exportación y disjunción; entrenamiento con pasos reales y cambios de pesos; comparación sobre vistas completas con máscaras originales; seguimiento y localización. Las poses exactas quedan privadas al evaluador. El estimador usa RGB, marcadores decodificados y sensores relativos ruidosos. No ajustar decisiones con prueba ni convertir apariencia de capacho en madurez interna.

La automatización continúa sobre el nuevo piloto. Si una etapa falla, conservar evidencia y corregir únicamente su implementación técnica, sin modificar las plantas ni el entorno congelados.
