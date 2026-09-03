# Perfil del dominio real — Classical Augmentation v2

Fecha: 2026-08-21  
Perfil local: `outputs/classical_augmentation_v2/domain_profile/real_train_profile.json`  
SHA-256 lógico del perfil: `4b8d620948d25ad00c7727cf2aca55f69d057a9e83466b2fa2d7876ff425c206`

## Fuente y política de splits

La fuente de verdad de v2 es el árbol local `Dataset Original/IMAGENES` y
`Dataset Original/LABELS`. Este split no es el mismo de la campaña histórica,
que utilizó 109 imágenes en validación y 109 en test. No se reconstruyó ni se
mezcló silenciosamente ninguno de los dos.

| Split | Imágenes | Objetos | Fingerprint SHA-256 |
|---|---:|---:|---|
| train | 1.062 | 2.881 | `568ab42f2246d696ee4cd5e2d1ea1fb6d7011c8cdce33ae6d8f3dd204477d952` |
| val | 133 | 459 | `08b18a2f68cad0f6c6dc2ef51d0e67675135ec7ff258e9e30ae9ad1faeb8dd0f` |
| test | 133 | 480 | `a5752614ab12239ae3104ee73331474c7598a589809a36dffdea4e11e68b0a9b` |

`0117.jpg` no posee archivo de label en train. Se registra explícitamente como
imagen natural sin objetos; no se crea una anotación positiva ficticia.

Toda estadística empleada para construir aumentaciones procede exclusivamente
de train. Val y test permanecen congelados. El test no es un holdout virgen,
porque fue consultado en trabajo histórico, pero queda fuera de la selección v2.

## Geometría observada en train

Se midieron 2.881 cajas.

| Estadístico de `bbox_area_ratio` | Valor |
|---|---:|
| mínimo | 0,00061 |
| p01 | 0,00181 |
| p05 | 0,00471 |
| p25 | 0,01728 |
| mediana | 0,03622 |
| p75 | 0,06382 |
| p95 | 0,17969 |
| p99 | 0,28070 |
| máximo | 0,52928 |

Las bandas de tamaño se fijaron después de medir train, mediante terciles:

- `small`: área menor que 0,02423;
- `medium`: 0,02423 a 0,05196;
- `large`: mayor o igual a 0,05196.

El rango robusto inicial aceptado para crop/zoom es p01–p99
([0,00181, 0,28070]). El límite de 5 puntos porcentuales de desviación agregada
por banda es una `engineering_heuristic`, no un hecho científico.

Train contiene una mediana de 2 objetos por imagen, p75 de 4, p95 de 7 y máximo
de 14. El perfil JSON conserva además ancho, alto, relación de aspecto,
distancia al borde y solapamiento entre cajas.

## Fotometría observada en train

Valores normalizados, calculados globalmente y también alrededor de las cajas.

| Métrica global | p01 | Mediana | p99 |
|---|---:|---:|---:|
| luminancia media | 0,4075 | 0,5276 | 0,6471 |
| desviación de luminancia | 0,1589 | 0,2178 | 0,2824 |
| saturación media | 0,1554 | 0,3864 | 0,6492 |
| contraste local | 0,0163 | 0,0545 | 0,1157 |

Las recetas fotométricas generan candidatos moderados y aceptan únicamente los
que permanecen dentro del soporte p01–p99 de luminancia media, saturación y
contraste local. Es un filtro de ingeniería calibrado contra train.

## Metadata de dominio

No se encontró metadata fiable para separar `laboratory` y `semi-field`. La
propiedad se registra como `unknown_not_available`; no se infirió a partir de
nombres de archivo ambiguos.
