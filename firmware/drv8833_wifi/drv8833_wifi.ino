// Transporte WiFi/TCP para el firmware DRV8833_ROS_V5 de PhysalisHarvest.
//
// El protocolo, el armado, el interbloqueo y el watchdog de 250 ms son los del
// sketch original, que se incluye sin modificar desde drv8833_core.h. Ese
// archivo lo genera scripts/prepare_drv8833_wifi.py tras verificar su SHA-256
// contra contributions/physalisharvest.provenance.json; no se versiona.
//
// Este envoltorio solo cambia el canal: un cliente TCP autenticado ocupa el
// lugar del puerto USB. Al desconectarse el cliente, los motores se paran.

#include <Arduino.h>
#include <WiFi.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "wifi_config.h"

constexpr bool sameText(const char* a, const char* b) {
  return *a == *b && (*a == '\0' || sameText(a + 1, b + 1));
}

static_assert(sizeof(BRIDGE_TOKEN) > 16, "BRIDGE_TOKEN necesita al menos 16 caracteres");
static_assert(!sameText(BRIDGE_TOKEN, "cambia-este-token"), "Cambia BRIDGE_TOKEN en wifi_config.h");
static_assert(sizeof(WIFI_SSID) > 1 ||
                  (sizeof(AP_PASSWORD) > 8 && !sameText(AP_PASSWORD, "cambia-esta-clave")),
              "Define una clave WPA2 propia de al menos 8 caracteres en AP_PASSWORD");

constexpr size_t authLimit = 64;
constexpr uint32_t authTimeoutMs = 2000;  // cliente sin AUTH
constexpr uint32_t idleTimeoutMs = 3000;  // cliente autenticado sin tráfico

WiFiServer server(BRIDGE_PORT);
WiFiClient client;
bool hasClient = false;
bool authenticated = false;
uint32_t lastActivity = 0;
char authBuffer[authLimit];
size_t authLength = 0;

// Sustituye a Serial dentro del sketch original: solo habla con el cliente
// autenticado. Sin cliente, available() es 0 y lo escrito se descarta.
class NetSerial {
 public:
  void begin(unsigned long) {}

  int available() { return authenticated ? client.available() : 0; }

  int read() {
    if (!authenticated) return -1;
    lastActivity = millis();
    return client.read();
  }

  size_t println(const char* text) {
    if (!authenticated) return 0;
    const size_t count = strlen(text);
    client.write(reinterpret_cast<const uint8_t*>(text), count);
    client.write(reinterpret_cast<const uint8_t*>("\n"), 1);
    return count + 1;
  }

  int printf(const char* format, ...) {
    char text[64];
    va_list args;
    va_start(args, format);
    const int count = vsnprintf(text, sizeof(text), format, args);
    va_end(args);
    if (!authenticated || count <= 0) return 0;
    const size_t sent = count < static_cast<int>(sizeof(text)) ? count : sizeof(text) - 1;
    client.write(reinterpret_cast<const uint8_t*>(text), sent);
    return static_cast<int>(sent);
  }
};

NetSerial netSerial;

#define Serial netSerial
#define setup drv8833_setup
#define loop drv8833_loop
#include "drv8833_core.h"
#undef loop
#undef setup
#undef Serial

void sendLine(WiFiClient& target, const char* text) {
  target.write(reinterpret_cast<const uint8_t*>(text), strlen(text));
  target.write(reinterpret_cast<const uint8_t*>("\n"), 1);
}

// Cualquier pérdida del cliente para los motores y descarta órdenes a medias.
void dropClient() {
  disarm(millis());
  hasClient = false;
  authenticated = false;
  authLength = 0;
  length = 0;
  overflow = false;
  client.stop();
}

void acceptClient() {
  WiFiClient incoming = server.accept();
  if (!incoming) return;
  if (hasClient) {
    sendLine(incoming, "ERR BUSY");
    incoming.stop();
    return;
  }
  client = incoming;
  client.setNoDelay(true);
  hasClient = true;
  authenticated = false;
  authLength = 0;
  lastActivity = millis();
}

// Primera línea del cliente: "AUTH <token>". Hasta entonces nada llega al sketch.
void authenticate() {
  while (!authenticated && client.available()) {
    const int byte = client.read();
    lastActivity = millis();
    if (byte == '\r') continue;
    if (byte != '\n') {
      if (authLength >= authLimit - 1) {
        sendLine(client, "AUTH ERR");
        dropClient();
        return;
      }
      authBuffer[authLength++] = static_cast<char>(byte);
      continue;
    }
    authBuffer[authLength] = '\0';
    if (strncmp(authBuffer, "AUTH ", 5) == 0 && strcmp(authBuffer + 5, BRIDGE_TOKEN) == 0) {
      authenticated = true;
      sendLine(client, "AUTH OK");
    } else {
      sendLine(client, "AUTH ERR");
      dropClient();
    }
    return;
  }
}

void serviceNetwork(uint32_t now) {
  if (hasClient && !client.connected()) dropClient();
  if (hasClient && now - lastActivity >= (authenticated ? idleTimeoutMs : authTimeoutMs)) {
    dropClient();
  }
  acceptClient();
  if (hasClient && !authenticated) authenticate();
}

void startWifi() {
  if (sizeof(WIFI_SSID) > 1) {
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  } else {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
  }
  server.begin();
  server.setNoDelay(true);
}

void setup() {
  drv8833_setup();  // GPIO en bajo y PWM antes de abrir la red
  Serial.begin(115200);
  startWifi();
}

void loop() {
  static bool reported = false;
  const bool station = sizeof(WIFI_SSID) > 1;
  if (!reported && (!station || WiFi.status() == WL_CONNECTED)) {
    // Por USB: indica la dirección a usar en el puente.
    const String ip = station ? WiFi.localIP().toString() : WiFi.softAPIP().toString();
    Serial.printf("DRV8833_WIFI %s:%d\n", ip.c_str(), BRIDGE_PORT);
    reported = true;
  }
  serviceNetwork(millis());
  drv8833_loop();
}
