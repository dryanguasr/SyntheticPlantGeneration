# Integración de aumentación clásica, generación sintética y Gazebo

## Propósito

Este documento resume la dirección propuesta para reestructurar el repositorio de trabajo de aumentación de datos y abrir una nueva línea de integración con Gazebo para el robot cosechador virtual.

La intención es que el repositorio deje de crecer como una colección de scripts independientes y pase a organizarse alrededor de **tres líneas claramente diferenciadas pero interoperables**:

1. **Aumentación clásica de datos**: códigos desarrollados por los estudiantes.
2. **Generación sintética de plantas**: pipeline `SyntheticPlantGeneration`, actualmente centrado en *Physalis peruviana*.
3. **Importación / generación de plantas para Gazebo**: nueva rama orientada a simulación robótica, interacción física y entrenamiento del cosechador.

La reestructuración debe conservar la trazabilidad de lo ya desarrollado, evitar mezclar prototipos históricos con implementaciones vigentes y preparar el repositorio para experimentos reproducibles.

---

## 1. Línea A — Aumentación clásica

Agrupar aquí los códigos de los estudiantes relacionados con transformaciones de imagen convencionales, por ejemplo:

- rotación;
- traslación;
- escalado;
- recorte;
- flip;
- cambios fotométricos;
- ruido;
- blur;
- transformaciones de color;
- combinaciones de técnicas;
- generación de datasets aumentados;
- evaluación del efecto de estas técnicas sobre modelos de visión.

Esta línea debe quedar conceptualmente separada de la generación procedural 3D.

Su función principal es servir como **baseline de aumentación tradicional** frente a:

- datos naturales sin aumentar;
- datos naturales + aumentación clásica;
- datos naturales + datos sintéticos;
- estrategias híbridas futuras.

---

## 2. Línea B — Generación sintética de uchuva

El código actual de `SyntheticPlantGeneration` debe conservarse como la implementación vigente del generador procedural.

La arquitectura conceptual que debe preservarse es:

```text
parámetros con procedencia
    ↓
morfología serializable
    ↓
fenología / gramática
    ↓
crecimiento multi-planta sincronizado
    ↓
competencia / soporte / política de contacto
    ↓
validación morfológica y geométrica
    ↓
interpretación Blender
    ↓
anotaciones y dataset
    ↓
experimentos ML
```

Principios que deben mantenerse:

- la **morfología es la fuente de verdad**, no la geometría Blender;
- Blender es un intérprete de esa morfología;
- los módulos puros no deben depender de `bpy`;
- las plantas deben seguir siendo reproducibles por semilla;
- los parámetros deben conservar su procedencia epistemológica;
- deben distinguirse hipótesis de ingeniería, mediciones reales y literatura;
- no debe mezclarse el código vigente con prototipos `legacy`;
- el contrato actual de detección sigue siendo, por ahora, una única clase `calyx`.

Esta línea sigue siendo responsable de:

- morfología;
- fenología;
- escenas multi-planta;
- texturas;
- Blender;
- generación de imágenes sintéticas;
- anotaciones;
- calibración de dominio;
- entrenamiento híbrido;
- evaluación.

---

## 3. Línea C — Nueva integración con Gazebo

### Idea central

No se propone importar simplemente el `.blend` completo a Gazebo y convertir toda la planta en un objeto físico detallado.

La propuesta es reutilizar el **mismo árbol morfológico** y crear un nuevo intérprete:

```text
                         ┌──→ Blender
morfología serializable ─┤
                         └──→ Gazebo
```

Blender y Gazebo deben cumplir funciones diferentes.

### Blender

Mantenerlo como entorno principal para:

- alta fidelidad visual;
- texturas;
- iluminación;
- render sintético;
- generación de datasets de visión;
- inspección visual.

### Gazebo

Usarlo para:

- navegación entre cultivos;
- percepción RGB / RGB-D;
- planeación del manipulador;
- reaching;
- interacción robot-planta;
- agarre;
- desprendimiento;
- entrenamiento del robot cosechador virtual;
- futuros experimentos Sim2Real.

---

## 4. Representación dual de la planta en Gazebo

La planta debe tener dos representaciones distintas.

### Representación visual

Puede provenir de Blender o de una geometría simplificada del generador.

Debe conservar:

- hojas;
- ramas;
- tallos;
- capachos;
- tutorado;
- apariencia general suficiente para percepción.

No todos estos elementos deben tener física.

### Representación física

Debe generarse directamente desde la estructura morfológica.

Propuesta inicial:

```text
Axis / Internode
    ↓
cilindro o cápsula
    ↓
joint
    ↓
siguiente internode

Node
 ├── Leaf
 │     └── inicialmente visual-only
 │
 ├── Branch
 │     └── cadena simplificada de links
 │
 └── ReproductiveUnit
       └── pedicel
             ↓
       unidad desprendible
```

Posibles aproximaciones:

- tallos y ramas: cilindros o cápsulas;
- hojas: visuales sin colisión en las primeras versiones;
- capachos: mesh visual + collider simple;
- frutos/capachos objetivo: modelos independientes;
- pedicelos: puntos naturales para implementar el desprendimiento;
- ramas: cadenas cortas de links con resortes y damping.

---

## 5. Reutilización de la política de contacto actual

La taxonomía existente puede mapearse a Gazebo:

| Política actual | Interpretación propuesta en Gazebo |
|---|---|
| `hard_occupancy` | collider físico |
| `soft_occupancy` | collider simplificado o contacto suave |
| `visual_occlusion` | visual sin collider |
| `intentional_support` | unión/restricción con trellis |
| `near_contact` | diagnóstico sin contacto físico |

Esto permitiría mantener coherencia entre el generador morfológico, Blender y Gazebo.

---

## 6. Niveles de detalle recomendados

No todas las plantas deben simularse con la misma física.

### LOD 0 — Fondo

Para plantas lejanas:

- geometría visual ligera;
- sin física;
- posibilidad de agrupar varias plantas.

Uso:

- ambientación;
- oclusión;
- fondo visual.

### LOD 1 — Navegación y percepción

Para plantas cercanas al robot:

- mesh individual simplificada;
- colisiones básicas de tallos;
- capachos visibles;
- hojas inicialmente sin collider.

Uso:

- navegación;
- RGB-D;
- percepción;
- acercamiento del brazo.

### LOD 2 — Planta objetivo de cosecha

Solo una o pocas plantas cercanas al manipulador:

- tallos articulados;
- ramas flexibles simplificadas;
- capachos independientes;
- pedicelos;
- unidades reproductivas desprendibles;
- sensores/contactos.

Uso:

- reaching;
- grasping;
- harvesting;
- RL;
- penalizaciones por daño.

---

## 7. Estrategia inicial de interacción física

No implementar de entrada modelos biomecánicos complejos.

La primera aproximación puede usar cuerpos rígidos articulados:

```text
stem_0
  ↓ joint elástico
stem_1
  ↓ joint elástico
stem_2
```

Cada joint puede incluir:

- stiffness;
- damping;
- límites;
- pequeñas variaciones procedurales.

Para el desprendimiento:

```text
rama
  ↓
pedicelo
  ↓
joint desprendible
  ↓
capacho / fruto
```

Un plugin o controlador debe decidir el desprendimiento cuando se cumpla una condición, por ejemplo:

- fuerza;
- desplazamiento;
- tensión;
- agarre válido;
- combinación de criterios.

Los parámetros físicos deben ser inicialmente `engineering_heuristic` o `to_be_measured`, no hechos botánicos.

---

## 8. Ground truth y percepción en Gazebo

La nueva rama debe explorar el uso de sensores simulados para producir:

- RGB;
- depth;
- segmentación semántica;
- bounding boxes;
- pose 3D exacta;
- estado privilegiado del objetivo.

Idealmente, cada unidad reproductiva debe conservar identidad semántica.

Ejemplo conceptual:

```text
leaf      → background
stem      → background
trellis   → background
calyx     → target
```

Esto permitiría usar Gazebo tanto para entrenamiento del robot como para evaluar pipelines de percepción.

---

## 9. Entrenamiento progresivo del robot

Evitar entrenar desde el inicio percepción, control y física simultáneamente.

### Etapa 1 — Estado privilegiado

Entrenar o validar:

```text
pose capacho
pose efector
pose ramas
    ↓
reaching
    ↓
grasp
    ↓
detach
```

Objetivo: aislar el problema de control.

### Etapa 2 — Percepción simulada ideal

Usar:

- segmentación;
- depth;
- ground truth de Gazebo.

### Etapa 3 — Percepción RGB simulada

Introducir:

- iluminación;
- ruido;
- variación morfológica;
- oclusión;
- textura;
- fondo;
- cámara.

### Etapa 4 — Integración Sim2Real

Sustituir progresivamente la percepción privilegiada por:

- detector entrenado con datos reales;
- detector entrenado con datos aumentados;
- detector híbrido real + sintético.

---

## 10. Domain randomization reutilizando el generador procedural

El generador actual puede convertirse en una fuente natural de randomización por episodio.

Cada episodio puede variar:

```text
seed
altura
ramificación
posición de capachos
fenología
densidad
oclusión
arquitectura
```

Y posteriormente:

```text
stiffness
damping
masa
fricción
fuerza de desprendimiento
```

Además de parámetros del sensor:

```text
camera pose
FOV
noise
lighting
exposure
```

La meta a largo plazo es que la misma semilla pueda producir:

- representación visual Blender;
- representación física Gazebo;
- metadata común;
- ground truth;
- configuración reproducible.

---

## 11. Separación entre repositorios / módulos

### SyntheticPlantGeneration

Debe seguir siendo responsable del modelo de planta.

Posibles módulos futuros:

```text
src/uchuva_lsystem/
    gazebo_export.py
    gazebo_physics.py
```

Posibles scripts:

```text
scripts/
    export_gazebo_plant.py
    export_gazebo_crop.py
```

Posible salida:

```text
exports/gazebo/
    seed_0001/
        model.config
        model.sdf
        meshes/
        materials/
        semantic_manifest.json
```

### Robot-Cosechador

Debe consumir los activos exportados, sin asumir cómo fueron generados.

Posible estructura:

```text
robot_cosechador_gazebo/
├── worlds/
├── models/
├── plugins/
├── launch/
└── config/
```

Responsabilidades:

- robot;
- ROS 2;
- control;
- sensores;
- mundos;
- plugins;
- entrenamiento;
- evaluación de tareas.

---

## 12. Spike técnico recomendado antes de diseñar toda la infraestructura

No implementar aún todo el exportador.

Primero realizar tres pruebas pequeñas.

### Spike A — Importación visual

Tomar una sola planta existente.

```text
seed conocida
    ↓
morfología
    ↓
mesh simplificada
    ↓
SDF
    ↓
Gazebo
```

Verificar:

- escala;
- pose;
- materiales;
- texturas;
- tiempo de carga;
- FPS;
- integración con el robot.

### Spike B — Semántica y sensores

Añadir:

- cámara RGB-D;
- segmentación;
- bounding boxes.

Verificar que los capachos puedan conservar identidad individual.

### Spike C — Interacción mínima

Construir solo:

- un tallo;
- una rama;
- un pedicelo;
- un capacho.

Demostrar:

```text
brazo toca rama
    ↓
rama se deforma
    ↓
gripper alcanza / agarra
    ↓
se cumple criterio
    ↓
unidad reproductiva se desprende
```

Si estos tres spikes funcionan, diseñar entonces el exportador formal `morphology → Gazebo`.

---

## 13. Arquitectura objetivo

```text
                   ┌──────────────────────────────┐
                   │ SyntheticPlantGeneration     │
                   │ morphology / phenology       │
                   └──────────────┬───────────────┘
                                  │
                       seed + parámetros
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │ Morphology Tree / JSON       │
                   └───────────┬───────────┬──────┘
                               │           │
                    ┌──────────┘           └───────────┐
                    ▼                                  ▼
             Blender interpreter                Gazebo interpreter
             ───────────────────                ──────────────────
             detailed meshes                    collision proxies
             PBR textures                       links / joints
             EEVEE                              flexible branches
             synthetic images                   detachable calyx
                    │                                  │
                    ▼                                  ▼
             perception training                robot training
                    │                                  │
                    └──────────────┬───────────────────┘
                                   ▼
                           Robot cosechador
                              Sim2Real
```

---

## 14. Alcance de esta reestructuración

Durante la reorganización inicial del repositorio:

### Sí hacer

- separar claramente aumentación clásica, generación sintética y Gazebo;
- conservar el historial y los prototipos relevantes;
- identificar implementaciones vigentes y `legacy`;
- definir interfaces entre subsistemas;
- mover código sin cambiar comportamiento cuando sea posible;
- añadir documentación de arquitectura;
- preparar puntos de extensión para Gazebo;
- mantener scripts existentes reproducibles;
- conservar seeds, manifests y trazabilidad.

### No hacer todavía

- reescribir el generador completo;
- implementar Cosserat rods;
- generar grandes datasets de Gazebo;
- diseñar toda la física de la planta;
- cambiar la clase de detección;
- fusionar Blender y Gazebo en una única implementación;
- introducir dependencias pesadas sin necesidad;
- eliminar resultados o prototipos antes de clasificarlos.

---

## 15. Resultado esperado de la reestructuración

El repositorio debe quedar preparado para estudiar sistemáticamente:

```text
Datos reales
    │
    ├── sin aumento
    │
    ├── + aumentación clásica
    │
    └── + datos sintéticos
              │
              ├── Blender → percepción
              │
              └── Gazebo → robótica / interacción
```

La idea de largo plazo es que **la generación sintética deje de limitarse a imágenes** y se convierta en una infraestructura común para:

- percepción;
- experimentación controlada;
- generación procedural de cultivos;
- entrenamiento del robot;
- Sim2Real.

---

## 16. Criterio rector para Codex

Durante la reestructuración, priorizar:

> **separación de responsabilidades, trazabilidad y compatibilidad antes que refactorización agresiva.**

El objetivo inmediato es que quede claro:

1. qué pertenece a aumentación clásica;
2. qué pertenece al modelo procedural de plantas;
3. qué pertenece al puente hacia Gazebo;
4. qué código es vigente;
5. qué código es histórico;
6. qué interfaces deben permanecer estables.

La integración con Gazebo debe tratarse inicialmente como una **nueva salida del modelo morfológico**, no como una modificación del núcleo del generador.
