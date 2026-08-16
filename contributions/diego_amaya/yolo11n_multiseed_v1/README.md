# Código para 90 entrenamientos YOLO11n — E0, E1 y E2

Este archivo acompaña el código de los experimentos confirmatorios de
`Physalis peruviana`. Las imágenes no están incluidas en este ZIP porque los
datasets se comparten por Google Drive.

El estudio ejecuta:

- E0: dataset real sin aumentación offline.
- E1: oclusión y cambios fuertes de iluminación.
- E2: oclusión e iluminación moderadas.
- 30 semillas por experimento: `1–29` y `42`.
- 90 entrenamientos en total.
- Orden emparejado: E0 → E1 → E2 para cada semilla.

Todos los comandos se ejecutan desde la carpeta que contiene este README.

## 1. Colocar los datasets descargados de Drive

Después de extraer el ZIP de código, descargar los tres datasets y conservar
exactamente esta estructura:

```text
ENTREGA_CODIGO_PROFESOR_YOLO11N_30_SEMILLAS/
├── data/
│   ├── semifield_v1/
│   │   ├── images/train, images/val, images/test
│   │   └── labels/train, labels/val, labels/test
│   └── working/
│       ├── dataset_E1_occ_light_strong/
│       │   ├── images/train, images/val, images/test
│       │   └── labels/train, labels/val, labels/test
│       └── dataset_E2_occ_light_soft/
│           ├── images/train, images/val, images/test
│           └── labels/train, labels/val, labels/test
├── models/pretrained/yolo11n.pt
├── configs/datasets/
└── scripts/training/multiseed_yolo11n/
```

Cantidades esperadas:

| Experimento | Train | Validation | Test |
|---|---:|---:|---:|
| E0 | 1062 | 109 | 109 |
| E1 | 2124 | 109 | 109 |
| E2 | 2124 | 109 | 109 |

No renombrar las carpetas. El script valida automáticamente estas cantidades,
los pares imagen–label y el formato YOLO antes de entrenar.

## 2. Protocolo congelado

```text
Arquitectura: YOLO11n
Peso inicial: models/pretrained/yolo11n.pt
Épocas: 50
imgsz: 640
batch: 8
workers: 4
Optimizador: AdamW
lr0: 0.001
lrf: 0.01
weight_decay: 0.0005
patience: 50
deterministic: True
AMP: False
rect: True
cache: False
Validación y gráficos: activados
Checkpoint adicional: cada 5 épocas
```

Las aumentaciones online de Ultralytics están explícitamente desactivadas:

```text
hsv_h=0.0, hsv_s=0.0, hsv_v=0.0
degrees=0.0, translate=0.0, scale=0.0, shear=0.0, perspective=0.0
flipud=0.0, fliplr=0.0, bgr=0.0
mosaic=0.0, mixup=0.0, cutmix=0.0, copy_paste=0.0
close_mosaic=0
```

Cada corrida comienza desde el mismo `yolo11n.pt`; nunca se encadenan pesos
entre experimentos.

## 3. Crear el entorno virtual

Se recomienda Python 3.11 de 64 bits y una GPU NVIDIA compatible con CUDA.

Abrir PowerShell en esta carpeta:

```powershell
nvidia-smi
py -3.11 -m venv .venv_gpu
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv_gpu\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## 4. Instalar PyTorch con CUDA

Instalar primero la versión de PyTorch con CUDA apropiada para la GPU y el
controlador del computador, utilizando el selector oficial:

<https://pytorch.org/get-started/locally/>

Después verificar CUDA:

```powershell
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO DETECTADA'); print('PyTorch:', torch.__version__); print('CUDA PyTorch:', torch.version.cuda)"
```

Debe aparecer `CUDA: True`. No iniciar el estudio si aparece `False`.

## 5. Instalar las demás dependencias

```powershell
python -m pip install -r scripts/training/multiseed_yolo11n/requirements.txt
```

Comprobar Ultralytics:

```powershell
python -c "import ultralytics; print(ultralytics.__version__)"
```

## 6. Validar todo sin entrenar

```powershell
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0 --dry-run
```

La salida final correcta es:

```text
Plan: 30 semillas x 3 experimentos = 90 corridas
Orden emparejado: E0 -> E1 -> E2 por cada semilla
DRY RUN correcto; no se entreno ningun modelo.
```

El `dry-run` comprueba los datasets, labels, peso inicial, GPU, semillas y
rutas, pero no entrena.

## 7. Prueba corta de GPU y VRAM

Antes de lanzar las 90 corridas, ejecutar una época en una carpeta separada:

```powershell
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0 --epochs 1 --seeds 1 --project runs/detect/experiments/training/yolo11n_preflight_batch8
```

Si batch 8 no cabe en la VRAM, probar batch 4 sin mezclarlo con el anterior:

```powershell
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0 --epochs 1 --batch 4 --seeds 1 --project runs/detect/experiments/training/yolo11n_preflight_batch4
```

Si se cambia el batch, debe utilizarse el mismo valor en las 90 corridas.

## 8. Ejecutar los 90 entrenamientos

Con la configuración original batch 8:

```powershell
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0
```

El programa realiza automáticamente:

```text
Semilla 1:  E0 -> E1 -> E2
Semilla 2:  E0 -> E1 -> E2
...
Semilla 29: E0 -> E1 -> E2
Semilla 42: E0 -> E1 -> E2
```

## 9. Reanudar después de una interrupción

Volver a abrir PowerShell, activar el entorno y ejecutar exactamente el mismo
comando:

```powershell
.\.venv_gpu\Scripts\Activate.ps1
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0
```

El lanzador omite las corridas completas, reanuda la corrida interrumpida
desde `weights/last.pt` y continúa con las semillas pendientes.

## 10. Ejecutar bloques de semillas

Si es necesario dividir el trabajo:

```powershell
# Semillas 1 a 10
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0 --seeds 1-10

# Semillas 11 a 20
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0 --seeds 11-20

# Semillas 21 a 29 y 42
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0 --seeds 21-29,42
```

Para preservar el emparejamiento, cada bloque debe conservar E0, E1 y E2.

## 11. Resultados

Las corridas se guardan separadamente en:

```text
runs/detect/experiments/training/yolo11n_multiseed_v1/
```

El seguimiento general se guarda en:

```text
execution_state.csv
execution_environment.json
```

Cada corrida contiene, entre otros:

```text
results.csv
args.yaml
results.png
weights/best.pt
weights/last.pt
weights/epochN.pt
```

## 12. Archivos que deben devolverse

Preferiblemente devolver completa la carpeta:

```text
runs/detect/experiments/training/yolo11n_multiseed_v1/
```

Si resulta demasiado grande, devolver como mínimo por cada corrida:

```text
results.csv
args.yaml
weights/best.pt
```

Además devolver `execution_state.csv` y `execution_environment.json`.

## 13. Integridad del peso inicial

El lanzador comprueba automáticamente este SHA-256 de `yolo11n.pt`:

```text
0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1
```

## 14. Comando principal resumido

```powershell
# Validar
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0 --dry-run

# Entrenar o reanudar
python scripts/training/multiseed_yolo11n/train_multiseed.py --device 0
```
