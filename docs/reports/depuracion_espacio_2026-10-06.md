# Depuración de espacio — 6 de octubre de 2026

El responsable autorizó reevaluar la migración a Drive y eliminar directamente
material no crítico, conservando versiones actuales e informes generales. También
incluyó campañas consolidadas de septiembre y octubre y sus intermediarios
razonablemente recuperables. Esta autorización sustituye la necesidad de subir
cada imagen histórica antes de retirarla. Los paquetes previamente subidos a
Drive no se modificaron.

## Resultado ejecutado

| Bloque | Archivos retirados | Espacio lógico liberado |
|---|---:|---:|
| Datasets históricos y checkpoints redundantes de julio/agosto | 142 452 | 299,09 GiB |
| Candidatos y geometría/intermediarios de septiembre/octubre | 31 630 | 25,59 GiB |
| Discos e instantánea del emulador Android de pruebas | 8 | 8,60 GiB |
| Fotogramas de vuelos históricos Gazebo v1/v2 | 8 668 | 1,51 GiB |
| Total | 182 758 | 334,78 GiB |

El espacio corresponde a la suma de tamaños de los archivos eliminados; el
espacio libre de la unidad puede variar con otros trabajos y archivos del PC.

## Evidencia conservada

- Código, documentación, informes y contribuciones, incluidas modificaciones
  locales ajenas a esta intervención.
- Métricas, configuraciones, manifiestos, etiquetas y 924 imágenes de muestra
  de datasets históricos. Se verificaron por SHA-256 680 archivos de evidencia,
  incluidos los pesos finales protegidos. Se conserva el checkpoint híbrido
  publicado en el README y los `best.pt` de las campañas.
- Imágenes reales originales: `Dataset Original/` y `Nuevo Dataset/`.
- Las 488 imágenes seleccionadas de septiembre y sus exportaciones actuales,
  junto con los paquetes de anotación y material de revisión humana.
- Pesos, informes, registros, videos y escenas Blender de las campañas recientes:
  3 355 archivos protegidos se comprobaron por SHA-256 después del borrado.
- Escenarios finales de segmentación y localización, la variante Bouquet v4
  y entregables recientes de reconstrucción.

## Material retirado y efecto

Se retiró el grueso de las imágenes bajo `images/train`, `images/val` e
`images/test` de los experimentos históricos y la campaña clásica v2 cerrada.
Se conservaron tres imágenes por carpeta y todos los informes, manifiestos,
configuraciones y etiquetas. Los `last.pt` y `epochN.pt` se retiraron únicamente
cuando existía `best.pt`. Estos datasets quedan **incompletos**: no deben usarse
para entrenar o reevaluar sin reconstruir/restaurar primero sus imágenes.

Se retiraron las imágenes extraídas de `captura_20260912_v6/candidates` tras
comprobar por hash los 693 originales registrados, conservando las imágenes
seleccionadas y los metadatos de selección. Reextraer candidatos desde los
originales antes de ejecutar una nueva selección o exportación que los requiera.

Se retiraron mallas DAE/OBJ/PLY de escenarios intermedios Gazebo (`field_v1`,
`field_v2`, `low_pilot_v1`, `low_pilot_v2`, `dense_crowns_v3` y su LOD) y siete
variantes de campos de desarrollo de segmentación. Se conservaron sus registros
y los escenarios finales/variantes posteriores. Sus mundos antiguos pueden
referenciar mallas ya retiradas y requieren reexportación antes de ejecutarse.

Se retiraron mapas binarios intermedios de estéreo en `mvs/stereo` y
`mvs_return/stereo` de la reconstrucción mejorada, conservando las fuentes,
modelos, superficies y entregables. Una nueva fusión que requiera esos mapas
debe regenerarlos. No se afirma reproducción idéntica por regeneración.

Se retiraron los discos de usuario, caché, cifrado y snapshot de RAM del AVD
`uchuva_api29.avd`, con el emulador detenido. La aplicación de pruebas debe
reinstalarse al recrear ese emulador; su estado interno anterior se descartó.
Se conservaron configuración, SDK, APK, capturas e informes de prueba.

Se retiraron fotogramas RGB/máscara de los vuelos `low_pilot_v1/v2`, conservando
sus videos, registros y pares de muestra al inicio, mitad y final. Se comprobaron
25 archivos protegidos por SHA-256. `low_pilot_v3` permanece completo. Los
fotogramas retirados no permiten repetir íntegramente las evaluaciones antiguas.

## Inventarios locales

Los registros completos de rutas, tamaños y comprobaciones están en:

- `outputs/archive/depuracion_20261006/{plan.json,result.json}`.
- `outputs/archive/depuracion_reciente_20261006/{plan.json,result.json}`.
- `outputs/archive/depuracion_emulador_20261006/{plan.json,result.json}`.
- `outputs/archive/depuracion_vuelos_20261006/{plan.json,result.json}`.

Los archivos eliminados directamente no se enviaron a la Papelera ni se
respaldaron íntegramente en Drive en esta intervención. Las evidencias
consolidadas y originales descritos arriba permanecen disponibles.
