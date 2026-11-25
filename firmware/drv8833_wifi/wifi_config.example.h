// Copia este archivo como wifi_config.h y cambia los valores.
// wifi_config.h está en .gitignore: no versiones claves ni tokens.
// El firmware no compila mientras queden los valores de ejemplo.
#pragma once

// Modo estación: el ESP32 se une a una red existente. Deja WIFI_SSID vacío
// ("") para el modo punto de acceso, recomendado en campo.
#define WIFI_SSID ""
#define WIFI_PASSWORD ""

// Modo punto de acceso (WPA2): el computador se conecta a esta red.
// La IP del ESP32 es 192.168.4.1. La clave necesita al menos 8 caracteres.
#define AP_SSID "uchuva-2wd"
#define AP_PASSWORD "cambia-esta-clave"

// Puerto TCP y token (16+ caracteres) que el puente envía como "AUTH <token>".
// Usa un valor aleatorio; viaja en claro dentro de la red WiFi.
#define BRIDGE_PORT 3333
#define BRIDGE_TOKEN "cambia-este-token"
