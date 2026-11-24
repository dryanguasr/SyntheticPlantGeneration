# Piloto privado de máscaras de capachos

La campaña mide el efecto de aumentar la cantidad de fotografías reales
anotadas por el asistente. Usa tamaños acumulativos de 20, 40, 80, 160, 320 y
461 fotografías. Cada tamaño tiene tres semillas, 4.000 actualizaciones AdamW
y 8.000 exposiciones. Las 88 fotos de validación se mantienen fijas. Las 94 de
desarrollo histórico se evalúan tras sellar los 18 pesos.

Las clases describen el aspecto visible del capacho. El detector real congelado
propone localizaciones y clases a partir de RGB. Ese detector ya vio el conjunto
de entrenamiento. MobileSAM produce las máscaras candidatas y el asistente las
verifica sobre el RGB, ajusta la clase y registra incertidumbre o rechazo. Los
polígonos históricos de train no se entregan al anotador. Las propuestas del
detector y las superposiciones sin revisar quedan como borradores.

Los archivos se guardan en una raíz `outputs/private_mask_ladder_*` independiente
de la ronda estudiantil. Los lotes estudiantiles, las etiquetas originales y
el archivo histórico de GrabCut conservan sus propias fuentes. Las 50 fotografías
de la revisión cruzada forman parte del inventario de train, sin usar las
entregas de los estudiantes en esta campaña.

## Ejecución y recuperación

Usar el entorno del proyecto con Ultralytics 8.4.114. El comando `init` verifica
y fija el inventario, las referencias y los pesos locales. `run` sella cada
prefijo antes de entrenar, espera memoria de GPU suficiente y ejecuta una sola
corrida a la vez.

```powershell
& .venv-training/Scripts/python.exe scripts/run_private_mask_ladder.py init
& .venv-training/Scripts/python.exe scripts/run_private_mask_ladder.py run
```

`visual_review` contiene el RGB, la superposición numerada y los recortes de
los borradores. El asistente registra una decisión explícita por candidato y
sella la tanda con `annotate_private_mask_ladder.py --root RAIZ seal DECISIONES`.
Sólo las decisiones selladas son insumos del entrenador. La exclusión de regiones
inciertas conserva los positivos verificados. Las imágenes totalmente inciertas
se registran como exposiciones sin supervisión y nunca forman un lote entero sin
gradientes.

Para recuperar una interrupción, verificar `controller_identity.json`,
`active_child.json` y `state.json`, y ejecutar `run` con la misma raíz. Los pesos,
manifiestos y fuentes se comprueban por hash. Las corridas incompletas se retoman
desde el último grupo de 500 actualizaciones sellado. El controlador registra
los bloqueos de GPU y mantiene los resultados parciales.

La campaña del 21 de noviembre selló una revisión de entrada después de las
tres corridas de 20 fotos. La caché guarda el RGB y las máscaras proyectadas
de forma reversible. En cuatro fotos reales se compararon los cinco arreglos
de entrada y ocho muestras aumentadas byte a byte. La lectura caliente por
foto tardó entre 6 y 11 ms. Repetir la proyección tardó entre 46 y 2.704 ms.
Estos tiempos corresponden a la preparación de datos.

La primera semilla de 40 fotos retomó las 1.500 actualizaciones ya guardadas.
Su punto de control original y las fuentes anteriores quedan archivados en
la revisión. El manifiesto de caché liga los seis prefijos al mismo protocolo
de entrada. La proyección, las semillas, el orden de exposición, la tasa de
aprendizaje y la evaluación conservan sus parámetros sellados.

El primer intento de la fase de 461 encontró un lote de dos fotos sin capachos
con clase. Ultralytics devolvió la máscara de asignación vacía como tensor
numérico. La corrección convierte esa máscara a booleana. La prueba verifica
gradiente cero en las regiones inciertas y gradiente de fondo en las zonas
con supervisión. Con objetos presentes, los cinco resultados del asignador
coinciden con los de la implementación anterior.

El intento falló antes del primer checkpoint. Su evidencia quedó archivada
y la misma semilla volvió a partir de los pesos iniciales. Los 15 pesos y
resultados previos conservan sus hashes y procedencia.

## Lectura de resultados

`val_summary.md` informa el desempeño de cada fase terminada. `test_summary.md`
se publica progresivamente tras el cierre del entrenamiento. Los JSON de cada
corrida contienen AP de máscara por clase, tamaño y grupo, localización sin
distinguir clase y errores de Sobremadura. Las galerías comparan las máscaras
predichas con las referencias históricas. Las 94 fotos se consultaron antes,
por lo que los resultados son exploratorios. La comparación con entregas humanas
adjudicadas pertenece a una ejecución posterior.

La curva se genera desde el resumen de la partición con fases completas.
Muestra cada semilla, la media y la desviación estándar. Las clases sin
soporte en la referencia quedan sin punto.

```powershell
& .venv-training/Scripts/python.exe scripts/plot_private_mask_ladder.py --root outputs/private_mask_ladder_20261121 --split val
```

Tras el cierre, `--split test` utiliza el resumen de desarrollo histórico.

El cierre técnico comprueba los hashes de pesos, referencias y predicciones,
la cobertura de las particiones y las 4.000 actualizaciones de cada semilla.
El suplemento calcula AP de máscaras por clase y tamaño de instancia desde
las predicciones guardadas.

```powershell
& .venv-training/Scripts/python.exe scripts/audit_private_mask_ladder_release.py supplement --root outputs/private_mask_ladder_20261121
```
