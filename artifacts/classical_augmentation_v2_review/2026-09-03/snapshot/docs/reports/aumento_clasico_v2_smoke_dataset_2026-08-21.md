# Gate de datasets smoke — Classical Augmentation v2

Fecha: 2026-08-21  
Semilla de generación: 20260821  
Tamaño: 25 derivadas por receta aditiva; V2-E0 conserva sólo las 1.062 reales.

## Resultado

Los nueve escenarios aprobaron el gate automático final:

- imágenes derivadas decodificables;
- labels YOLO válidos y dentro de `[0,1]`;
- manifiesto completo por derivada;
- hashes de padre y salida verificados;
- padres y donantes exclusivamente de train;
- val/test byte a byte congelados;
- conteos esperados;
- desviación de bandas de tamaño menor que 5 puntos porcentuales;
- previews `original | augmented | bbox overlay` generados.

| Escenario | Derivadas | Rechazos finales | Máx. desviación de banda |
|---|---:|---:|---:|
| V2-E0 | 0 | 0 | 0,00 pp |
| V2-E0R | 25 | 0 | 0,17 pp |
| V2-E2 | 25 | 6 | 0,36 pp |
| V2-E3 | 25 | 0 | 0,12 pp |
| V2-E4 | 25 | 10 | 0,08 pp |
| V2-E5 | 25 | 0 | 0,17 pp |
| V2-E6 | 25 | 1 | 0,43 pp |
| V2-E7 | 25 | 4 | 0,42 pp |
| V2-E8 | 25 | 7 | 0,48 pp |

V2-E0R crea nuevas entradas de muestreo mediante hardlinks/copias byte a byte;
no decodifica ni recomprime la imagen y no transforma las cajas.

## Auditorías específicas

- V2-E2 aplicó fotometría a 20/25 ejemplos del smoke final. La luminancia
  media pasó de 0,5318 a 0,5103 y permaneció dentro del soporte p01–p99 de
  train. Las oclusiones afectadas conservaron al menos 58,7 % de visibilidad.
- V2-E3 registra en el manifiesto fotometría antes/después para cada muestra.
- V2-E4 conservó al menos 64,2 % de la máscara visible en el smoke final.
- V2-E6/V2-E7 registran ventana, factor de resize, áreas antes/después,
  objetos eliminados y contacto con borde.
- V2-E8 añadió exactamente un target por derivada. El IoU con el fruto ancla
  quedó entre 0,076 y 0,344 y la escala relativa entre 0,652 y 0,906.

## Hallazgo de revisión visual y corrección

La primera versión pasó validaciones numéricas, pero fue bloqueada visualmente:

- E2/E4 reescalaban el parche donante sobre toda la fotografía, produciendo
  oclusores visualmente artificiales;
- E8 permitía agrupaciones sobre fondos de laboratorio o posiciones flotantes;
- el overlay de cajas en imágenes verticales no compensaba el letterboxing.

Antes de autorizar el build completo se corrigió:

- muestreo y reescalado local del parche vegetal;
- mínimo de soporte vegetal tanto en el parche como alrededor del target;
- exclusión del propio target al medir el contexto de Copy-Paste;
- fondo vegetal obligatorio para la parte pegada fuera de cajas existentes;
- núcleo opaco con suavizado gaussiano sólo en bordes;
- dibujo de cajas antes del letterboxing del contact sheet.

Los smoke datasets se regeneraron y auditaron nuevamente. La revisión visual
final no observó los casos bloqueantes anteriores. Este gate autoriza la
generación de 532 derivadas por receta, no constituye evidencia de rendimiento
del detector.
