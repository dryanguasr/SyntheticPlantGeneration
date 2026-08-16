# Entrega estudiantil: entrenamiento YOLO11n multisemilla

## Procedencia

- Grupo: estudiantes del proyecto encabezados por Diego Amaya.
- Entrega local de origen: `Dataset Original/Dataset + Aumentacion clasica/ENTRENAMIENTO MULTI-SEED UCHUVA/ENTREGA_CODIGO_PROFESOR_YOLO11N_30_SEMILLAS/`.
- Snapshot del lanzador: SHA-256 `44F6EAEA0A893F4BEDB60BE2CEDF0D0622648F67C60C1868BE33A9BE57FC9828`.
- README de entrega: SHA-256 `43620470B97C54AFB779C61E316E21CD3A69157EBF9118D998581D2958A8DE0C`.

## Contenido preservado

Se conserva el lanzador que valida, entrena y reanuda las condiciones E0, E1 y
E2 con 30 semillas. Tambien se conservan sus configuraciones y dependencias.
No se incluyen los datasets, pesos ni resultados de entrenamiento.

## Limitacion importante

La entrega disponible no contiene codigo para materializar las transformaciones
offline de E1 y E2. Por tanto, esas condiciones se consideran datasets
precalculados reproducibles solo si se dispone de sus archivos y manifiestos;
no se afirmara que sus recetas son reproducibles hasta recuperarlas o
reimplementarlas y validarlas.

## Uso en el repositorio

Esta es una referencia atribuida. La interfaz vigente de aumentacion clasica
vive en `src/uchuva_classical_augmentation/`; la infraestructura compartida de
experimentos se mantendra separada del modelo morfologico.
