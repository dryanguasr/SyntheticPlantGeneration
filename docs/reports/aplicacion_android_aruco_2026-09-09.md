# Corrección de rejilla y referencia sin escala — Android 0.2.1

## Actualización posterior: 0.2.2

Por solicitud del usuario, se retiran las posiciones en lados del ArUco.
Al detectar un marcador sin medida confirmada, la app pregunta el lado negro
en centímetros (campo inicialmente vacío). Cancelar mantiene las posiciones
nulas. Confirmar una medida válida habilita las estimaciones y guarda el valor
para futuras aperturas; Ajustes permite modificarlo. JSON 1.3 retira
`position_marker_sides`. Se mantiene la rejilla extendida a toda la imagen.

Compilación, pruebas JVM y lint completados; validador del grafo correcto.
No se ejecutaron pruebas de interfaz en emulador o teléfono en esta revisión.
APK actualizado: `outputs/mobile/apk/uchuva-aruco-debug.apk`.
SHA-256: `dbf8e0ae44dd393f4b9ef52ea27bd391f1cc005c37a4b7bdcbc4a84a23735748`.

## Registro histórico 0.2.1

La prueba aportada por el usuario mostraba una rejilla limitada a dos lados
del marcador y coordenadas anuladas por falta de confirmación de escala.
La nueva rejilla intersecta líneas de coordenada constante con los bordes
del fotograma para cada ArUco. Adapta el espaciado si hay más de 80 líneas por
eje y rechaza proyecciones fuera del lado válido del horizonte del plano.

Cada capacho obtiene coordenadas respecto a todos los marcadores válidos.
Sin medida física confirmada, la interfaz muestra unidades de lado del ArUco;
con medida confirmada muestra centímetros. JSON 1.2 añade
`position_marker_sides`, conservando `position_cm` nulo sin escala confirmada.
Los IDs duplicados siguen siendo ambiguos para asignar posiciones.

Compilación de app y APK instrumentado, pruebas JVM y lint completados el
9 de septiembre. El validador del grafo pasa con 130 nodos y 237 aristas.
Esta revisión no ejecutó el emulador ni pruebas físicas. No se atribuye al APK
nuevo la ejecución instrumentada del 3 de septiembre.

APK: `outputs/mobile/apk/uchuva-aruco-debug.apk`, versión 0.2.1.
SHA-256: `4270b2e47b085f13e65720f7af9016bc8de26a6d4393c2a094d16198d51f91c2`.

Las posiciones siguen siendo proyecciones sobre el plano del marcador;
objetos en otras profundidades, como pantallas distintas, introducen error.
