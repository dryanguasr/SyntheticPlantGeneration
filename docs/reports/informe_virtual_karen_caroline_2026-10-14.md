# Componente virtual y resultados experimentales para la tesis

Dirigido a Karen y Caroline. Corte de información: 14 de octubre de 2026, Colombia.

El componente virtual permite estudiar la percepción de uchuvas en imágenes y recorridos simulados, medir sus errores y preparar una futura evaluación en cultivo real. Ya se ejecutaron ensayos de detección, segmentación, reconstrucción y localización espacial. La infraestructura funciona como plataforma experimental, pero los resultados aún no demuestran una mejora general en imágenes reales ni un sistema de cosecha autónoma validado.

Las cifras siguientes proceden de los informes y cierres conservados del proyecto. Esta síntesis no corresponde a nuevos entrenamientos ni a una repetición de los experimentos. La campaña de vídeo continuo quedó cerrada el 12 de octubre; los trabajos abiertos se distinguen de las ejecuciones terminadas.

## En qué consiste la parte virtual

Se trabaja con escenas de cultivo, cámaras virtuales y recorridos en Gazebo, un entorno de simulación robótica. El sistema produce imágenes sobre las que se ensayan métodos de percepción. La información de referencia disponible en la simulación permite comprobar si las predicciones corresponden al objeto correcto y cuánto se desvía su posición estimada.

**Las escenas sintéticas se generaron de forma procedimental, tomando como referencia literatura afín sobre representación virtual de plantas y datos sintéticos agrícolas** [1, 2]. La descripción del procedimiento de generación se reserva para una publicación posterior. El contexto de la especie se apoya en literatura sobre *Physalis peruviana* [3]. Estas referencias contextualizan el trabajo; no validan por sí mismas la fidelidad de las escenas ni sus resultados.

Conviene distinguir cuatro tareas. La detección indica dónde aparece un objeto mediante una caja. La segmentación por instancia delimita los píxeles de cada capacho. El seguimiento intenta reconocer el mismo capacho en imágenes sucesivas. La localización 3D estima su posición espacial respecto a una referencia, en este caso marcadores visuales ArUco [4]. Una detección correcta en una imagen no implica que se conserve la identidad ni que se obtenga una posición 3D correcta.

La reconstrucción a partir de vídeo real es una línea complementaria: busca recuperar superficies observadas del cultivo mediante múltiples imágenes [5]. Debe describirse separadamente del conjunto sintético procedimental.

## Experimentos ejecutados y significado de sus resultados

### Antecedente de detección con datos reales y sintéticos

El estudio híbrido histórico comparó entrenamiento con datos reales frente a una combinación con datos sintéticos. La auditoría del 8 de septiembre recuperó un incremento medio de **0,001533 en mAP50–95** en tres semillas, con dos de los tres cambios individuales negativos. Es una diferencia de aproximadamente 0,1533 puntos porcentuales en la escala porcentual de AP, no una mejora del 15 %.

Hubo un resultado preliminar favorable de una sola semilla, pero el estudio posterior mostró que esa ventaja no era consistente. Además, las imágenes del test histórico ya habían sido consultadas durante desarrollo. Por tanto, este antecedente es exploratorio y no demuestra superioridad general ni constituye una evaluación externa intacta. Fuente: [auditoría científica](auditoria_cientifica_blender_2026-09-08.md).

La aumentación clásica constituye otro frente, a cargo de las estudiantes. Su campaña v2 registró 40 corridas confirmatorias válidas y ninguna receta alcanzó el criterio predeclarado de mejora integral; el test de esa campaña permaneció sin consultar. Ese estado no debe confundirse con el del test histórico del estudio híbrido. Fuente: [cierre de aumentación clásica](aumento_clasico_v2_confirmatory_2026-08-28.md).

### Reconstrucción desde vídeo real

El piloto del 1 de octubre ensayó reconstrucción fotogramétrica con COLMAP. La continuación mejoró la superficie frontal: pasó de 16 a 51 vistas locales y de 5.131 a 112.433 puntos en el mismo recorte. La superficie se pudo cargar y observar en Gazebo.

Sin embargo, **no se obtuvo una planta completa con base, copa y ambas caras conectadas**. Las superficies del regreso se conservaron separadas porque su correspondencia con la planta frontal no quedó resuelta. La densidad de puntos y el error de reproyección son diagnósticos internos, no una medida de exactitud contra geometría real independiente. Tampoco se demostró escala centimétrica. Los métodos neurales Splatfacto y Nerfacto no se ejecutaron; no existe una comparación experimental entre las tres familias. Fuente: [piloto de reconstrucción](piloto_reconstruccion_uchuva_2026-10-01.md).

### Segmentación por instancia

La campaña cerrada el 4 de octubre incluyó tres ciclos originales y un cuarto experimento de entradas por regiones y recortes. Cada ciclo registró 180 imágenes, con 140 para entrenamiento y 40 para validación, y entrenamientos de 60 épocas. Se separaron los grupos usados en entrenamiento, validación y escenarios de evaluación. En esta campaña no se entrenó con imágenes reales.

El modelo elegido en los tres ciclos originales fue el del ciclo 3. En el escenario final reservado obtuvo **mAP50–95 de máscaras de 0,012271**, frente a **0,001768** del ciclo 1. El resultado mejora respecto a ese control, pero el desempeño absoluto sigue siendo bajo.

El cuarto experimento estudió el efecto de procesar recortes de la imagen. Estos resultados corresponden a escenarios de desarrollo diferentes del cierre reservado anterior:

| Escenario | Imagen completa | Recortes | Lectura |
|---|---:|---:|---|
| Referencia fija | 0,000822 | 0,029894 | Los recortes mejoraron el AP de máscaras |
| Nuevo vuelo cercano | 0,010613 | 0,052503 | La mejora persistió en ese vuelo |

En el vuelo cercano, los recortes alcanzaron precisión de 42,55 % y recall de 22,62 %, con mediana total de 1,787 segundos por imagen. Todavía se omitía la mayoría de los capachos. El recorte automático de una región de vegetación sin subdivisión empeoró el resultado en ese vuelo. No se evaluó un modelo independiente de detección con cajas dentro de esta campaña. Fuente: [cierre de segmentación](cierre_campana_segmentacion_2026-10-04.md).

Las clases se denominaron **pintona —incluye verdes—, madura y sobremadura por apariencia del capacho**. Son categorías visuales operativas del experimento. No certifican madurez fisiológica, calidad comercial ni estado del fruto que permanece oculto.

### Piloto de localización 3D

El piloto cerrado el 5 de octubre evaluó seis plantas reservadas. La variante congelada localizó correctamente **37 de 388 capachos observables**, equivalente a recall 3D de **9,54 %**, con precisión conjunta de **80,43 %**. No alcanzó el objetivo de localizar más de la mitad con al menos 90 % de precisión conjunta.

Una localización correcta exigía identidad respaldada, marcador correcto, error no mayor de 5 cm y ausencia de duplicación. Dos capachos completamente ocultos se registraron aparte. La posición estimada corresponde al centro aproximado del capacho, no al centro del fruto interno. El sistema detectó al menos una vez 361 objetos, pero solo 37 cumplieron todos los criterios de localización: esta diferencia muestra por qué no se deben intercambiar ambas métricas. Fuente: [cierre del piloto 3D](cierre_localizacion_3d_2026-10-05.md).

### Vídeo continuo con cultivo de fondo

El estudio iniciado el 8 de octubre y cerrado el **12 de octubre de 2026** utilizó seis plantas objetivo y doce de contexto. Se capturaron 7.972 pares originales de imágenes y máscaras a 1280 × 720. La hilera objetivo reutilizó plantas previamente inspeccionadas; por ello esta campaña es retrospectiva y no representa generalización a una parcela nueva.

Se compararon tres formas de procesar las mismas capturas:

| Protocolo | Correctos sobre 388 | Recall 3D | Precisión conjunta | Duplicados |
|---|---:|---:|---:|---:|
| Seguimiento histórico con muestreo a 1 Hz | 22 | 5,67 % | 61,11 % | 3 |
| Seguimiento histórico en cada fotograma | 73 | 18,81 % | 36,50 % | 78 |
| Seguimiento y conciliación posterior en cada fotograma | 62 | 15,98 % | 32,98 % | 15 |

La conciliación posterior redujo los duplicados de 78 a 15 frente al seguimiento en cada fotograma, pero también redujo los aciertos de 73 a 62. No corresponde presentarla como una mejora global. Su precisión de asociación fue 48,94 %, distinta de la precisión conjunta de 32,98 %, que exige también exactitud espacial y ausencia de duplicación. No se registraron intrusiones de plantas de fondo en el mapa objetivo.

La campaña no alcanzó el objetivo de localizar más de la mitad de los capachos observables con precisión de asociación de al menos 90 %. Se registraron dificultades de continuidad de identidad, apoyos temporales y geometría. Los diagnósticos que utilizaron información verdadera del simulador se mantuvieron separados del estimador: sirven para investigar errores, no representan desempeño disponible en un robot real.

La inferencia acumulada por fotograma requirió 81.827,2 segundos, aproximadamente 22,73 horas. La captura a 30 Hz no significa inferencia a 30 Hz ni operación en tiempo real. La ejecución tuvo recuperaciones y una revisión computacional durante el estudio; no es una comparación homogénea ejecutada desde cero bajo un único protocolo invariable. Fuente: [evaluación de vídeo continuo](evaluacion_video_continuo_2026-10-08.md). El cierre local `outputs/continuous_row_20261008/study_complete.json` confirma la fecha y el objetivo no alcanzado.

## Trabajo abierto y experimentos pendientes

Al corte de este informe, los registros consultados no acreditan una nueva campaña experimental activa después del cierre del 12 de octubre. La línea de investigación continúa abierta; eso no significa que estos ensayos estén actualmente ejecutándose.

| Trabajo abierto | Estado documentado | Evidencia necesaria para reportarlo como resultado |
|---|---|---|
| Transferencia al cultivo real | Pendiente de confirmación independiente | Nuevas sesiones reales separadas de desarrollo y controles comparables |
| Validación humana de categorías visuales | Pendiente | Anotaciones independientes, acuerdo y resolución de desacuerdos |
| Madurez del fruto oculto | No validada | Observación pareada del capacho y del fruto con criterio agronómico |
| Seguimiento y localización robustos | Objetivos de los pilotos no alcanzados | Ensayo nuevo congelado antes de evaluar, con identidades y posiciones correctas |
| Reconstrucción completa | Piloto parcial | Continuidad de base, copa y caras, y referencia independiente de escala |
| Reconstrucción neural | No ejecutada en el piloto | Ejecución y evaluación comparable antes de atribuir resultados |
| Localización aprendida de arbustos y detector independiente con cajas | Pendientes de la campaña de segmentación | Modelos identificados, entrenamiento y evaluación propios |
| Operación en tiempo real y cosecha física | No demostradas | Medición integral de latencia y validación robótica específica |

Estas necesidades no constituyen una programación de nuevas corridas. Tampoco debe presentarse el conjunto de pilotos como un gemelo digital validado de una planta real.

## Cómo presentar las métricas y las conclusiones en la tesis

El AP resume la relación entre precisión y recall. El mAP50–95 promedia AP a umbrales de solapamiento de 0,50 a 0,95. Las cifras se expresan aquí entre 0 y 1. Hay que especificar si se evalúan cajas o máscaras; sus resultados no son intercambiables. El recall 3D indica qué fracción de los objetos observables se localizó correctamente, mientras la precisión conjunta indica qué fracción de las localizaciones emitidas cumplió los criterios conjuntos.

No deben compararse directamente los 37 aciertos del piloto reservado con los 62 del vídeo continuo como si solo cambiara un algoritmo: cambiaron captura, contexto y protocolo, y se reutilizaron las plantas objetivo. La comparación controlada del vídeo continuo es la tabla de sus tres variantes sobre las mismas capturas. Los errores espaciales de los objetos asociados tampoco representan a los objetos que nunca se localizaron.

Texto que pueden adaptar en la tesis:

> Se desarrolló un componente virtual para evaluar percepción de uchuva en escenarios simulados. Las escenas sintéticas se generaron procedimentalmente con apoyo en referencias afines. Se realizaron experimentos de segmentación por instancia, seguimiento y localización tridimensional, además de un piloto complementario de reconstrucción desde vídeo real. El procesamiento por recortes mejoró la segmentación en los escenarios estudiados, aunque persistió una baja cobertura de objetos. En el estudio retrospectivo de vídeo continuo, la conciliación posterior localizó correctamente 62 de 388 capachos observables y redujo duplicados respecto al seguimiento por fotograma, a costa de menor recall y precisión conjunta. Los resultados describen desempeño en simulación; la transferencia al cultivo real y la correspondencia entre apariencia del capacho y madurez del fruto permanecen pendientes de validación.

Para sustentar los resultados, deben citarse los informes del proyecto junto con la versión de código que se entregue. Los artículos académicos siguientes fundamentan el contexto y las técnicas generales; no son la fuente de las cifras de nuestros experimentos. Los vídeos y mapas ilustran resultados, pero no sustituyen las tablas de evaluación. Los artefactos pesados se conservan localmente y no se incluyen por defecto en Git.

## Referencias académicas

1. Prusinkiewicz, P., y Lindenmayer, A. (1990). *The Algorithmic Beauty of Plants*. Springer-Verlag. [Edición disponible en el sitio de los autores](https://algorithmicbotany.org/papers/#abop). Referencia general de representación virtual de plantas, sin atribuir al proyecto una implementación específica.

2. Fei, Z., Olenskyj, A. G., Bailey, B. N., y Earles, M. (2021). Enlisting 3D Crop Models and GANs for More Data Efficient and Generalizable Fruit Detection. *IEEE/CVF International Conference on Computer Vision Workshops*, 1269–1277. [Publicación](https://openaccess.thecvf.com/content/ICCV2021W/CVPPA/html/Fei_Enlisting_3D_Crop_Models_and_GANs_for_More_Data_Efficient_ICCVW_2021_paper.html), [versión de los autores](https://arxiv.org/abs/2108.13344). Antecedente de datos sintéticos agrícolas; citarlo no implica que aquí se hayan utilizado GANs.

3. Fischer, G., y Melgarejo, L. M. (2020). The ecophysiology of cape gooseberry (*Physalis peruviana* L.) — an Andean fruit crop. A review. *Revista Colombiana de Ciencias Hortícolas, 14*(1), 76–89. [DOI: 10.17584/rcch.2020v14i1.10893](https://doi.org/10.17584/rcch.2020v14i1.10893). Contexto biológico de la especie.

4. Garrido-Jurado, S., Muñoz-Salinas, R., Madrid-Cuevas, F. J., y Marín-Jiménez, M. J. (2014). Automatic generation and detection of highly reliable fiducial markers under occlusion. *Pattern Recognition, 47*(6), 2280–2292. [DOI: 10.1016/j.patcog.2014.01.005](https://doi.org/10.1016/j.patcog.2014.01.005). Fundamento de los marcadores ArUco usados como referencia visual.

5. Schönberger, J. L., y Frahm, J.-M. (2016). Structure-from-Motion Revisited. *IEEE Conference on Computer Vision and Pattern Recognition*, 4104–4113. [Publicación](https://openaccess.thecvf.com/content_cvpr_2016/html/Schonberger_Structure-From-Motion_Revisited_CVPR_2016_paper.html), [bibliografía oficial de COLMAP](https://colmap.github.io/). Fundamento de la reconstrucción desde múltiples imágenes ensayada en el piloto.
