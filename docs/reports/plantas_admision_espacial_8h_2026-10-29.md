# Plantas con admisión espacial y dataset: cierre

Se verificaron **20 plantas admitidas**, de las cuales 17 proceden de semillas nuevas y 3 de posturas antes rechazadas. Se registraron 20 intentos. Tiempo efectivo: 15.4910 h. Motivo de parada: `insufficient_time_for_next_complete_scene`. Se generaron 144 pares completos de imágenes y anotaciones tras alcanzar veinte plantas. No hubo entrenamiento. El usuario autorizó después hasta ocho horas efectivas adicionales, con parada anticipada en mil imágenes. Se preservan el presupuesto original y el reloj acumulado mediante una revisión por hash.

Cada admisión reconstruida presenta cero cruces duros auditados, suelo plano válido a 1 mm, orientación/unión de cálices válida y morfología sin errores. Se comprobaron los hashes, el original, el árbol final y los límites acumulados. La pérdida es estrictamente menor del 5 % para frutos y hojas por separado; se controla también el proxy nominal foliar largo*ancho, sin confundirlo con superficie medida.

| Semilla | Origen | Hojas retenidas/originales | Frutos retenidos/originales | Pérdida hojas | Pérdida frutos | Proximidades |
|---|---|---:|---:|---:|---:|---:|
| 2026102702 | previously_unadmitted_pose_continuation | 1045/1045 | 370/385 | 0.000% | 3.896% | 337 |
| 2026102703 | previously_unadmitted_pose_continuation | 1055/1062 | 371/390 | 0.659% | 4.872% | 284 |
| 2026102708 | previously_unadmitted_pose_continuation | 808/827 | 286/296 | 2.297% | 3.378% | 262 |
| 2026102860 | fresh_seed | 496/498 | 175/181 | 0.402% | 3.315% | 128 |
| 2026102827 | fresh_seed | 639/653 | 232/238 | 2.144% | 2.521% | 176 |
| 2026102836 | fresh_seed | 634/644 | 239/243 | 1.553% | 1.646% | 171 |
| 2026102805 | fresh_seed | 739/739 | 266/278 | 0.000% | 4.317% | 215 |
| 2026102863 | fresh_seed | 740/744 | 273/279 | 0.538% | 2.151% | 217 |
| 2026102835 | fresh_seed | 729/739 | 274/281 | 1.353% | 2.491% | 206 |
| 2026102813 | fresh_seed | 756/764 | 270/276 | 1.047% | 2.174% | 193 |
| 2026102849 | fresh_seed | 839/850 | 303/310 | 1.294% | 2.258% | 228 |
| 2026102843 | fresh_seed | 833/845 | 303/312 | 1.420% | 2.885% | 265 |
| 2026102842 | fresh_seed | 834/834 | 303/317 | 0.000% | 4.416% | 272 |
| 2026102808 | fresh_seed | 827/838 | 307/318 | 1.313% | 3.459% | 223 |
| 2026102834 | fresh_seed | 827/846 | 304/318 | 2.246% | 4.403% | 241 |
| 2026102809 | fresh_seed | 875/902 | 292/301 | 2.993% | 2.990% | 317 |
| 2026102837 | fresh_seed | 872/878 | 324/327 | 0.683% | 0.917% | 255 |
| 2026102815 | fresh_seed | 870/911 | 306/321 | 4.501% | 4.673% | 238 |
| 2026102844 | fresh_seed | 906/909 | 315/327 | 0.330% | 3.670% | 301 |
| 2026102829 | fresh_seed | 851/886 | 322/336 | 3.950% | 4.167% | 233 |

La admisión es una heurística de ingeniería con realimentación de mallas, no un modelo medido de abscisión o aborto. Se conservan dimensiones y posturas de los órganos supervivientes. Hoja–hoja sigue como ocupación blanda y las proximidades como advertencias; no se certifican exhaustivamente flores ni contexto, mecánica, realismo fotométrico o utilidad para un detector. Revisión visual humana pendiente.

La cola adaptativa priorizó tres recuperaciones y después semillas nuevas por coste anatómico original. No se podaron los originales para esa prioridad. El inventario puro no cuenta como admisión y esta selección no permite estimar una tasa de éxito uniforme de la población. Las tres plantas ya válidas históricamente quedan excluidas del contador nuevo.

[Galería de plantas](../../outputs/spatial_plant_pool_20261028/review.html), [todos los intentos](../../outputs/spatial_plant_pool_20261028/results.json), [verificación independiente](../../outputs/spatial_plant_pool_20261028/review_summary.json) y [presupuesto](../../outputs/spatial_plant_pool_20261028/budget.json). Los rechazos y parciales permanecen en cada carpeta; no se mezclan con las admisiones.

El contrato está documentado en [la guía](../guides/plantas_admision_espacial_8h.md). Las comprobaciones del grafo deben distinguir los diez errores preexistentes de localizadores de cualquier regresión nueva.
