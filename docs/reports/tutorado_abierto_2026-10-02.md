# Tutorado que abre y sube: variante v4

Se implementó `individual_bouquet_crown_v4` sobre los árboles densos v3,
sin regenerar nodos ni unidades reproductivas. Las ramas tienen direcciones
locales explícitas, compartidas por los intérpretes Blender y Gazebo.
La variante anterior sigue disponible y sus archivos no se modificaron.

## Forma y escala

El eje principal se acorta al 82 % de v3. Las ramas primarias se abren entre
32 y 58 grados respecto a la vertical, con apertura creciente según la altura
del nodo de inserción. Su longitud se multiplica por 0,90–1,35; las ramas
descendientes mantienen un sector exterior y una componente vertical positiva.
Son heurísticas de pose de tutorado, no parámetros botánicos medidos ni una
simulación de fuerzas de las cuerdas. Las cuerdas se reconectan a los nodos
finales; no se desplazan postes ni cables.

La observación del usuario es que los arbustos reales suelen estar por debajo
de 1,8 m. No se interpreta como un límite biológico universal.
El campo existente tiene **1,4 m entre plantas, 1,8 m entre hileras y postes de
2,5 m**, no 3 m entre plantas. Se conserva la distribución solicitada; la
separación real aproximada de 3 m sigue siendo una observación pendiente de
recalibración del campo.

Comparación nominal de malla, con igual cámara ortográfica y escala, incluyendo
hojas y capachos (altura superior respecto a la base, no extensión bajo tierra):

| Planta | Altura v3 | Altura v4 | Ancho X v3 | Ancho X v4 |
|---|---:|---:|---:|---:|
| plant_13 | 1,317 m | 1,187 m | 0,989 m | 1,020 m |
| plant_03 | 1,552 m | 1,296 m | 1,007 m | 1,158 m |
| plant_27 | 1,456 m | 1,211 m | 0,933 m | 1,014 m |

La cobertura foliar frontal aumenta respectivamente 23,4 %, 13,5 % y 14,9 %
frente a v3. No es una medición de oclusión. El cambio principal es la
distribución ascendente de la copa, no aumentar órganos ni su tamaño.
El máximo de altura de proxies del campo de 36 plantas es 1,3705 m, incluyendo
la escala individual de cada instancia. Los proxies no sustituyen la medición
de malla de las 36 plantas. El Blender combinado tiene unidades métricas,
con ocho unidades internas por metro; sus desplazamientos son de presentación.

## Verificación y límites

- 4.503 ejes, 23.385 hojas y 2.340 capachos: sin cambios frente a v3.
- Comparación exacta de todos los nodos serializados: órganos e identidades
  conservados, con conexiones nodales y radios intactos.
- Posiciones, escalas de las instancias, postes y cables sin cambios.
- Dos pruebas específicas de entrenamiento y cuatro regresiones de densidad
  pasan; prueban determinismo, serialización, conservación y apertura progresiva.
- Auditoría de malla estricta: 565 / 960 / 620 pares de intersección física
  pendientes para plant_13 / plant_03 / plant_27. Frente a v3 (622 / 988 / 515),
  dos mejoran y uno empeora. No se declara válida físicamente esta variante.
  Hay además 168 / 314 / 184 intersecciones hoja/hoja toleradas.
- Algunas hojas basales continúan bajo el plano de suelo; la revisión aislada
  conserva esta limitación y no la oculta moviendo el terreno.
- No se ejecutó otro vuelo, exportación completa a Gazebo ni detección.
  El paquete Gazebo y los videos anteriores siguen representando v3. Las
  nuevas direcciones están en la morfología exportable por el pipeline común.
  La auditoría de trayectoria de v3 no certifica el recorrido para v4.

## Reproducción y artefactos locales

```powershell
.venv-training/Scripts/python.exe scripts/prepare_bouquet_crowns.py --source outputs/dense_crowns_v3_final/input.json --output outputs/bouquet_crowns_v4
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b --python scripts/review_dense_crowns.py -- --source outputs/dense_crowns_v3_final/input.json --new outputs/bouquet_crowns_v4 --output outputs/bouquet_crowns_v4/review --plants plant_13 plant_03 plant_27
.venv-training/Scripts/python.exe scripts/report_bouquet_crowns.py --review outputs/bouquet_crowns_v4/review
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b --python scripts/package_dense_review.py -- outputs/bouquet_crowns_v4/review
```

Los directorios de salida deben ser nuevos para preservar evidencia previa.
`outputs/bouquet_crowns_v4/` contiene el campo morfológico completo, hash de
entrada, comprobación de integridad y 36 archivos de plantas. `review/`
contiene comparativas `bouquet_front.jpg` / `bouquet_back.jpg`, medidas,
auditorías y `arbustos_frondosos.blend`. Revisión visual humana pendiente.
