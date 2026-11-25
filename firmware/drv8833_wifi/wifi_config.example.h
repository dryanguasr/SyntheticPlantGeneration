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

// ---- Servos por PCA9685 (I2C) ----
// Valores genéricos (estimated): mide el rango real de cada articulación antes
// de mover el brazo. Una orden fuera de rango se rechaza, no se recorta.
#define SERVO_ENABLED 1
#define PCA9685_ADDRESS 0x40   // A0-A5 sin puentear
#define PCA9685_SDA 21         // pines I2C por defecto del ESP32 Dev Module
#define PCA9685_SCL 22
#define SERVO_FREQUENCY_HZ 50
#define SERVO_SLEW_US_PER_S 500  // velocidad máxima del pulso: 500 us/s

// Rango común para los canales 0..SERVO_CHANNELS-1.
#define SERVO_CHANNELS 16
#define SERVO_MIN_US 1000
#define SERVO_MAX_US 2000

// O bien un rango por canal, empezando en el canal 0 (sustituye a los tres
// anteriores). Ejemplo para tres articulaciones:
// #define SERVO_LIMITS {{1100, 1900}, {1000, 1700}, {1200, 1800}}

// Al perder el puente: 0 corta el pulso (servos sin par); 1 mantiene la última
// posición. Si el brazo cae por gravedad sin par, evalúa 1 con el corte físico
// de alimentación de servos al alcance.
#define SERVO_HOLD_ON_DISCONNECT 0
