# Configuración del brazo robótico de 5 GDL

**Documento de referencia técnica**\
**Fecha de consolidación:** 25 de noviembre de 2026\
**Estado:** configuración documentada; pendiente de validar contra el
hardware instalado.

## 1. Descripción general

El brazo está documentado con cinco grados de libertad (GDL), más un
actuador independiente para el gripper. La cadena cinemática se organiza
desde la base hasta el efector final en el siguiente orden:

1.  **J1 -- Yaw:** giro de la base.
2.  **J2 -- Pitch:** articulación del hombro.
3.  **J3 -- Pitch:** articulación del codo.
4.  **J4 -- Roll:** giro de muñeca.
5.  **J5 -- Pitch:** inclinación de muñeca.
6.  **Gripper:** apertura y cierre de la pinza; no se cuenta como GDL de
    posicionamiento del brazo.

## 2. Actuadores del brazo

  -------------------------------------------------------------------------
  Eje              Función           Referencia            Torque anunciado
                                     documentada      
  ---------------- ----------------- ---------------- ---------------------
  J1               Giro de la base   RDS3235-270                  35 kgf·cm
                   (Yaw)                              

  J2               Hombro (Pitch)    ASME-03B                    380 kgf·cm

  J3               Codo (Pitch)      ASME-MRA-110KG              110 kgf·cm

  J4               Muñeca (Roll)     TD-8135MG-180                35 kgf·cm

  J5               Muñeca (Pitch)    TD-8135MG-180                35 kgf·cm

  Gripper          Apertura/cierre   TD-8135MG-180      35 kgf·cm anunciado
                                     (opcional; por   
                                     confirmar)       
  -------------------------------------------------------------------------

**Nota:** los valores son los torques anunciados asociados a las
referencias documentadas. No deben asumirse como torque continuo
disponible ni como torque efectivo en la articulación sin verificar
ficha técnica, tensión de alimentación, condiciones térmicas, geometría
y relación mecánica.

## 3. Descripción funcional por articulación

### J1 -- Base (Yaw)

Permite la rotación horizontal del conjunto del brazo y orienta el área
de trabajo alrededor de la base.

-   Actuador documentado: RDS3235-270.
-   Torque anunciado: 35 kgf·cm.

### J2 -- Hombro (Pitch)

Eleva y desciende el conjunto del brazo. Es una articulación crítica
porque soporta el peso de los eslabones posteriores y la carga útil.

-   Actuador documentado: ASME-03B.
-   Torque anunciado: 380 kgf·cm.

### J3 -- Codo (Pitch)

Modifica la extensión del brazo y la distancia del efector final
respecto a la base.

-   Actuador documentado: ASME-MRA-110KG.
-   Torque anunciado: 110 kgf·cm.

### J4 -- Muñeca (Roll)

Proporciona giro alrededor del eje longitudinal de la muñeca o
herramienta, según la orientación mecánica final.

-   Actuador documentado: TD-8135MG-180.
-   Torque anunciado: 35 kgf·cm.

### J5 -- Muñeca (Pitch)

Permite inclinar el efector final para ajustar la orientación de
aproximación o manipulación.

-   Actuador documentado: TD-8135MG-180.
-   Torque anunciado: 35 kgf·cm.

### Gripper

Actuador separado destinado a abrir y cerrar la pinza. La referencia
TD-8135MG-180 aparece como opción documentada, pero su instalación debe
confirmarse.

## 4. Sensores de posición y realimentación

En la configuración técnica se contempló el uso de encoders magnéticos
**AS5600** para la realimentación angular de las articulaciones.

Antes de cerrar el diseño electrónico, se debe verificar:

-   Cantidad real de sensores instalados.
-   Correspondencia entre cada sensor y su articulación.
-   Montaje del imán y alineación con el sensor.
-   Rango angular útil y posibles vueltas completas.
-   Dirección de lectura, offset y calibración de cero.
-   Interfaz eléctrica, alimentación y compatibilidad del bus I²C.
-   Estrategia para detectar pérdida de lectura o desconexión.

La mención de AS5600 representa una solución prevista/documentada, no
una confirmación de que todos los sensores estén instalados y
calibrados.

## 5. Orden cinemático

La secuencia de ejes documentada es:

``` text
Base
 └── J1: Yaw
      └── J2: Pitch (hombro)
           └── J3: Pitch (codo)
                └── J4: Roll (muñeca)
                     └── J5: Pitch (muñeca)
                          └── Efector final / Gripper
```

Este orden sirve como referencia para estructurar el modelo cinemático,
la asignación de articulaciones en el CAD y la interfaz de control. Los
sentidos positivos, límites angulares, ceros mecánicos y dimensiones de
los eslabones deben tomarse del CAD y de la validación física; no están
especificados en este documento.

## 6. Consideraciones de control

Para implementar el control del brazo se recomienda documentar, por cada
eje:

-   Posición objetivo y posición medida.
-   Límites mecánicos mínimo y máximo.
-   Offset de calibración.
-   Velocidad y aceleración máximas permitidas.
-   Sentido positivo de giro.
-   Estado de habilitación y estado de fallo.
-   Comportamiento ante pérdida de alimentación o realimentación.

No se incluyen aquí pines, controlador, protocolo de comunicación,
frecuencias PWM ni parámetros PID porque no están confirmados en la
configuración disponible.

## 7. Validaciones pendientes

  -----------------------------------------------------------------------
  Elemento                            Estado / acción requerida
  ----------------------------------- -----------------------------------
  Referencias de servomotores J1--J5  Confirmar contra etiquetas y
                                      facturas del hardware instalado

  Torque de cada actuador             Verificar ficha técnica y
                                      condiciones de medición

  Actuador del gripper                Confirmar si se instaló el
                                      TD-8135MG-180

  Encoders AS5600                     Confirmar cantidad, montaje y
                                      calibración

  Límites articulares                 Obtener del CAD y comprobar
                                      físicamente

  Ceros y sentido de giro             Calibrar eje por eje

  Alimentación                        Verificar tensión, corriente pico y
                                      capacidad de la fuente

  Controlador y cableado              Documentar referencias, pines y
                                      protocolo reales

  Carga útil                          Definir y validar mediante análisis
                                      de torque y pruebas controladas
  -----------------------------------------------------------------------

## 8. Advertencias técnicas

1.  No dimensionar la fuente únicamente sumando corrientes nominales sin
    considerar picos de arranque y bloqueo de los servomotores.
2.  No operar las articulaciones cerca de sus límites mecánicos sin
    topes, límites de software y procedimiento de parada.
3.  No asumir que el torque anunciado equivale al torque continuo o al
    torque disponible en el efector final.
4.  Verificar calentamiento, vibración, holgura y caída de tensión
    durante pruebas progresivas.
5.  Realizar las primeras pruebas sin carga útil y con el brazo
    asegurado para evitar movimientos inesperados.

## 9. Resumen de configuración

-   **Arquitectura:** brazo de 5 GDL más gripper.
-   **Cadena cinemática:** Yaw -- Pitch -- Pitch -- Roll -- Pitch.
-   **Actuadores documentados:** RDS3235-270, ASME-03B, ASME-MRA-110KG y
    TD-8135MG-180.
-   **Realimentación prevista:** encoders magnéticos AS5600.
-   **Estado documental:** referencias y torques anunciados
    consolidados; hardware instalado, cableado, límites y calibración
    pendientes de verificación.

------------------------------------------------------------------------

**Control de cambios:** este documento consolida la configuración
previamente documentada. Cualquier cambio de referencia, cantidad de
actuadores, arquitectura o sensor debe registrarse aquí una vez
confirmado.
