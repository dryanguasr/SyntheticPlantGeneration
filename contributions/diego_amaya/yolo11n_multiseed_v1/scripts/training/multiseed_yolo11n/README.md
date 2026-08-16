# Estudio YOLO11n con 30 semillas

Paquete portable para repetir E0, E1 y E2 en un computador con GPU.
Son 30 semillas por experimento: 90 entrenamientos.

## Diseno experimental

- Semillas: 1 a 29 y 42. La 42 conecta con la corrida historica.
- Orden emparejado: E0, E1 y E2 para cada semilla.
- Cada corrida comienza desde el mismo yolo11n.pt.
- 50 epocas, 640 px, batch 8, AdamW y aumentaciones internas desactivadas.
- deterministic=True y amp=False por defecto.
- last.pt se actualiza cada epoca; epochN.pt adicional cada 5 epocas.
- El mismo comando omite corridas terminadas y reanuda la incompleta.

## Datos descargados

Copie bajo la raiz:
    data/semifield_v1/
    data/working/dataset_E1_occ_light_strong/
    data/working/dataset_E2_occ_light_soft/
    models/pretrained/yolo11n.pt

E0: 1062 train, 109 val, 109 test; 3.27 GB.
E1: 2124 train, 109 val, 109 test; 5.64 GB.
E2: 2124 train, 109 val, 109 test; 5.72 GB.
Total aproximado: 14.63 GB. Comprima cada dataset por separado.
Los datasets y pesos estan excluidos de Git.
