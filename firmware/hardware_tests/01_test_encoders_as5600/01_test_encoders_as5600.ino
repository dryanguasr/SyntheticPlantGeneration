/*
 * PRUEBA INDEPENDIENTE 01: Encoders Magnéticos AS5600 (1 directo o hasta 5 con TCA9548A)
 *
 * Librerías necesarias en Arduino IDE:
 *   - Wire.h   -> Incluida por defecto en el paquete ESP32.
 *   - AS5600.h -> Instalar desde Gestor de Bibliotecas: buscar "AS5600" de Rob Tillaart.
 *
 * Conexión ESP32 clásica:
 *   - SDA -> GPIO 21
 *   - SCL -> GPIO 22
 *   - VCC -> 3.3V (IMPORTANTE: usar 3.3V, no 5V, para no dañar pines del ESP32)
 *   - GND -> GND
 *   - Multiplexor HiLetgo TCA9548A: A0, A1, A2 sin conectar / a GND -> Dirección 0x70
 *   - Encoders AS5600 #0..#4 -> Canales SD0/SC0 .. SD4/SC4 del TCA9548A
 *     (Si aún no tienes el multiplexor, puedes conectar 1 solo AS5600 directo a GPIO 21/22
 *      y este test también lo detectará automáticamente).
 *
 * Cómo detectar qué falla (Monitor Serial a 115200 bps, ajuste "Nueva línea / NL"):
 *   - No detecta nada en I2C    -> Cables SDA/SCL cruzados, falta GND común o falta 3.3V.
 *   - Detecta otra dir != 0x70  -> Pines A0/A1/A2 del TCA9548A están en HIGH o es otro chip.
 *   - "NO DETECTADO" en imán    -> El imán está muy lejos, ausente o NO es diametralmente magnetizado.
 *   - "MUY CERCA (MH)"          -> Alejar un poco el imán (ideal: 0.5 mm a 2.5 mm del chip).
 *   - "MUY LEJOS (ML)"          -> Acercar más el imán al centro del chip AS5600.
 *
 * Comandos Serial:
 *   scan       -> Re-escanea todo el bus I2C y canales 0..4 del TCA9548A
 *   read       -> Lee una sola vez
 *   stream on  -> Lectura continua cada 200 ms
 *   stream off -> Detiene lectura continua
 */

#include <Wire.h>
#include <AS5600.h>

const uint8_t PIN_SDA       = 21;
const uint8_t PIN_SCL       = 22;
const uint8_t TCA9548A_ADDR = 0x70;
const uint8_t NUM_CANALES   = 5; // Ejes 0..4 (la pinza J6 no lleva encoder)

AS5600 encoders[NUM_CANALES];
AS5600 encoderDirecto;

bool modoMuxDetectado = false;
bool modoDirectoDetectado = false;
bool streamActivo = true;
unsigned long ultimoStreamMs = 0;

bool seleccionarCanalTCA(uint8_t canal) {
  if (canal > 7) return false;
  Wire.beginTransmission(TCA9548A_ADDR);
  Wire.write(1 << canal);
  return (Wire.endTransmission() == 0);
}

void desactivarCanalesTCA() {
  Wire.beginTransmission(TCA9548A_ADDR);
  Wire.write(0x00);
  Wire.endTransmission();
}

void escanearTodo() {
  Serial.println("\n================ ESCANEO I2C ================");
  modoMuxDetectado = false;
  modoDirectoDetectado = false;

  int dispositivos = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("[I2C] Dispositivo encontrado en 0x");
      if (addr < 16) Serial.print("0");
      Serial.println(addr, HEX);
      dispositivos++;
      if (addr == TCA9548A_ADDR) modoMuxDetectado = true;
      if (addr == 0x36) modoDirectoDetectado = true;
    }
  }

  if (dispositivos == 0) {
    Serial.println("[FALLO] Bus I2C vacio. Revisa alimentacion 3.3V, GND, SDA(21) y SCL(22).");
    return;
  }

  if (modoMuxDetectado) {
    Serial.println("\n[MODO MULTIPLEXOR] TCA9548A detectado en 0x70. Probando canales 0..4:");
    for (uint8_t ch = 0; ch < NUM_CANALES; ch++) {
      seleccionarCanalTCA(ch);
      encoders[ch].begin();
      encoders[ch].setDirection(AS5600_CLOCK_WISE);

      Serial.print("  Canal ");
      Serial.print(ch);
      Serial.print(" (Eje J");
      Serial.print(ch + 1);
      Serial.print("): ");

      if (!encoders[ch].isConnected()) {
        Serial.println("SIN SENSOR (no responde 0x36)");
        continue;
      }

      Serial.print("AS5600 OK | Iman: ");
      if (encoders[ch].magnetDetected())         Serial.print("OK");
      else if (encoders[ch].magnetTooStrong())   Serial.print("MUY CERCA (MH)");
      else if (encoders[ch].magnetTooWeak())     Serial.print("MUY LEJOS (ML)");
      else                                       Serial.print("NO DETECTADO");

      uint16_t raw = encoders[ch].rawAngle();
      Serial.print(" | Raw=");
      Serial.print(raw);
      Serial.print(" | Deg=");
      Serial.println(raw * AS5600_RAW_TO_DEGREES, 2);
    }
    desactivarCanalesTCA();
  } else if (modoDirectoDetectado) {
    Serial.println("\n[MODO DIRECTO] AS5600 unico detectado en 0x36 (sin multiplexor).");
    encoderDirecto.begin();
    encoderDirecto.setDirection(AS5600_CLOCK_WISE);
    Serial.print("  Iman: ");
    if (encoderDirecto.magnetDetected())         Serial.println("OK");
    else if (encoderDirecto.magnetTooStrong())   Serial.println("MUY CERCA (MH)");
    else if (encoderDirecto.magnetTooWeak())     Serial.println("MUY LEJOS (ML)");
    else                                         Serial.println("NO DETECTADO");
  }
  Serial.println("=============================================\n");
}

void leerUnaVez() {
  if (modoMuxDetectado) {
    Serial.print("[MUX] ");
    for (uint8_t ch = 0; ch < NUM_CANALES; ch++) {
      Serial.print("E");
      Serial.print(ch);
      Serial.print(":");
      if (seleccionarCanalTCA(ch) && encoders[ch].isConnected()) {
        uint16_t raw = encoders[ch].rawAngle();
        Serial.print(raw * AS5600_RAW_TO_DEGREES, 1);
        Serial.print("deg");
      } else {
        Serial.print("ERR");
      }
      if (ch < NUM_CANALES - 1) Serial.print(" | ");
    }
    Serial.println();
  } else if (modoDirectoDetectado) {
    if (encoderDirecto.isConnected()) {
      uint16_t raw = encoderDirecto.rawAngle();
      Serial.print("[DIRECTO] Raw: ");
      Serial.print(raw);
      Serial.print(" | Grados: ");
      Serial.print(raw * AS5600_RAW_TO_DEGREES, 2);
      Serial.print(" | Iman: ");
      Serial.println(encoderDirecto.magnetDetected() ? "OK" : "FALLO");
    } else {
      Serial.println("[DIRECTO] Sensor desconectado.");
    }
  } else {
    Serial.println("[INFO] Nada detectado. Envia 'scan' cuando conectes el hardware.");
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(100000); // 100 kHz es mas robusto para cables de prueba

  Serial.println("=== TEST 01: ENCODERS AS5600 ===");
  Serial.println("Comandos: scan | read | stream on | stream off");
  escanearTodo();
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.equalsIgnoreCase("scan")) {
      escanearTodo();
    } else if (cmd.equalsIgnoreCase("read")) {
      leerUnaVez();
    } else if (cmd.equalsIgnoreCase("stream on")) {
      streamActivo = true;
      Serial.println("Stream activado.");
    } else if (cmd.equalsIgnoreCase("stream off")) {
      streamActivo = false;
      Serial.println("Stream detenido.");
    }
  }

  if (streamActivo && (millis() - ultimoStreamMs >= 200)) {
    ultimoStreamMs = millis();
    leerUnaVez();
  }
}
