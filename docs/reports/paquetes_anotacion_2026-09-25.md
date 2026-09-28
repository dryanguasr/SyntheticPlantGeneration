# Cinco paquetes de anotación — 25 de septiembre de 2026

El usuario autorizó ejecutar el documento de cinco paquetes y regenerar unas
4.500 imágenes tras borrar la entrega grande anterior. La inspección encontró
los **7.615 candidatos trazables** en el caché de v6, además de sus 488
representantes. Se forma un banco nuevo desde ese caché; no se limita a los
representantes ni se confunde con las antiguas 4.501 imágenes de train.

Entrada original: `Nuevo Dataset/Recolección de datos 12-09-2026`, 667 fotos y
26 videos. Padre: `outputs/new_real_dataset/captura_20260912_v6/manifest.jsonl`.
Salida: `outputs/annotation_packages/captura_20260925_v1/`.
Rama: `codex/annotation-packages-20260925`, preservando cambios locales previos.

## Reparto

| Paquete | Candidatos | Fotos | Frames | Grupos presentes |
|---|---:|---:|---:|---:|
| P01 | 900 | 244 | 656 | 7 |
| P02 | 900 | 188 | 712 | 7 |
| P03 | 899 | 90 | 809 | 9 |
| P04 | 898 | 73 | 825 | 7 |
| P05 | 903 | 72 | 831 | 8 |
| Total | 4.500 | 667 | 3.833 | 37 únicos |

Un grupo grande se comparte por bloques de revisión, conservando group_id y
split; por ello los grupos por paquete no suman los únicos. Se mantienen
**3.108 train, 661 val y 731 test**. Todas las fotografías entran al banco,
incluidas 13 exclusiones históricas como NO USAR; las demás decisiones quedan
pendientes. El presupuesto temporal de frames no impone cuotas de aprobación
ni de etiquetado: los estudiantes harán la selección visual.

Los paquetes tienen copias independientes de los originales orientados, vistas
PNG640 con relleno gris114, galería paginada, procedencia automática, selección
de dos columnas, devolución y copia intacta de la guía breve. Las cinco imágenes
de calibración se repiten intencionalmente con la misma identidad y no se suman
como nuevas muestras. El piloto sugerido propone 40 train únicos (incluidas las
cinco) y diez val de grupos separados, pendientes de revisión visual.

## Ejecución y comprobaciones

**Generación y verificación completas.** Registro:
`outputs/annotation_packages_20260925.log`. Los cinco ZIP ocupan 10.899.672.913
bytes (10,90 GB decimales). Se comprobaron los 4.500 originales y sus vistas:
hashes, dimensiones, orientación, píxeles exactos del letterbox y gris114.
La unión de responsables coincide exactamente con el banco, sin pérdidas ni
repeticiones accidentales. Cada miembro de los ZIP coincide por hash con su
archivo de entrega; las cinco copias de calibración conservan su identidad.

La comprobación adicional `portability` extrajo **los cinco ZIP completos** en
carpetas temporales fuera del proyecto, resolvió todos los enlaces de las
galerías y comprobó concordancia CSV/JSONL y procedencia por paquete.
`verification.json` registra la auditoría de imágenes y bytes; la ampliación
completa de portabilidad está en `verification_portability.json`, que también
incluye SHA-256 de cada ZIP. `closeout.json` vincula ambas verificaciones con el
manifiesto final. No se confunde integridad con aprobación científica/humana.

Pasaron doce pruebas nuevas de paquetes y doce de curación existente. Cubren
determinismo, cobertura, grupos con varios revisores, conflictos entre fuentes
de distintos dispositivos, duplicados, letterbox, ZIP y calibración. Las pruebas
de importación usan máscaras de ejemplo: preservan DUDOSAS y madurez desconocida,
rechazan nombres/clases incompatibles y no inventan negativos ni duplican
muestras por revisor. También pasaron cuatro pruebas del grafo de contexto:
28 pruebas en conjunto. El grafo fue actualizado y su validador aprobó.
Se conserva una devolución ficticia de demostración, separada de las capturas,
en `outputs/annotation_import_smoke_20260925`: RLE con madurez desconocida y
decisión DUDOSA, preservado íntegro sin aprobarlo para entrenamiento.

No se ejecutaron entrenamiento, inferencia, autolabeling, instalaciones ni subidas.
El validador es un ingreso de devoluciones pendientes, no un exportador listo
para entrenar. Conserva toda la recepción y valida un contrato JSON normalizado;
el formato concreto del editor necesitará un adaptador explícito. No se afirma
compatibilidad automática con exportaciones arbitrarias.

## Pendientes del coordinador

- Asignar P01–P05 y revisar las propuestas de calibración y piloto: no hay
  garantía automática de cobertura de clases, escala ni primer plano.
- Confirmar los 37 grupos provisionales por planta/área/recorrido y relaciones
  entre dispositivos. Las relaciones ya registradas no presentan cruces, pero
  esto no prueba independencia visual. Mantener test reservado.
- Adjudicar calibración y revisión cruzada (primeras 5–10 por persona, luego
  alrededor de 10 % y todas las DUDOSAS). Conservar todas las máscaras.
- Conciliar las devoluciones por ID, confirmar representación y exhaustividad,
  resolver madurez pendiente y congelar grupos antes de liberar una ronda.

## Entrega y reproducción

ZIP: `zips/P01.zip` a `zips/P05.zip`. Maestro: `manifest.csv` y equivalente
JSONL. `groups.csv`, `relations.csv`, `partition_audit.json`,
`bank_selection.csv` y `campaign.json` registran vínculos, presupuesto, hashes
del padre y versión de código. `verification.json` registra la verificación.

Los comandos reales y el contrato de importación están en
[la guía técnica](../guides/paquetes_anotacion_trazables.md).
Para reproducir, elegir otra carpeta de versión; nunca sobrescribir la entrega.
