#pragma once

// MOCK nativo del bus I2C: un PCA9685 en el bus principal, un multiplexor
// TCA9548A y encoders AS5600 detrás de él (o uno directo), con sus registros.
#include <cstddef>
#include <cstdint>
#include <deque>
#include <vector>

struct MockPca9685 {
  bool present = true;
  bool failWrites = false;
  uint8_t address = 0x40;
  uint8_t registers[256] = {};
  int writes = 0;

  // Cuentas OFF de 12 bits de un canal; -1 si el canal está en apagado total.
  int offTicks(int channel) const {
    const int base = 0x06 + 4 * channel;
    if (registers[base + 3] & 0x10) return -1;
    return registers[base + 2] | ((registers[base + 3] & 0x0F) << 8);
  }
};

struct MockAs5600 {
  bool present = false;
  uint8_t registers[256] = {};
  uint8_t pointer = 0;

  void set(uint16_t raw, uint8_t status) {
    present = true;
    registers[0x0B] = status;
    registers[0x0C] = static_cast<uint8_t>(raw >> 8);
    registers[0x0D] = static_cast<uint8_t>(raw & 0xFF);
  }
};

inline MockPca9685 pca;
inline bool muxPresent = false;
inline uint8_t muxSelection = 0;  // máscara de canales abiertos
inline MockAs5600 muxEncoders[8];
inline MockAs5600 directEncoder;  // AS5600 en el bus principal

// AS5600 que responde en 0x36 ahora mismo, o nullptr (ninguno o choque).
inline MockAs5600* reachableEncoder() {
  MockAs5600* found = directEncoder.present ? &directEncoder : nullptr;
  if (muxPresent) {
    for (int channel = 0; channel < 8; ++channel) {
      if ((muxSelection & (1 << channel)) && muxEncoders[channel].present) {
        if (found) return nullptr;  // dos AS5600 a la vez: misma dirección
        found = &muxEncoders[channel];
      }
    }
  }
  return found;
}

class TwoWire {
 public:
  bool begin(int sda, int scl) {
    sdaPin = sda;
    sclPin = scl;
    return true;
  }
  void setClock(uint32_t hz) { clock = hz; }
  void beginTransmission(uint8_t address) {
    target = address;
    data.clear();
  }
  size_t write(const uint8_t* bytes, size_t size) {
    data.insert(data.end(), bytes, bytes + size);
    return size;
  }
  uint8_t endTransmission() {
    if (target == 0x70 && muxPresent) {
      if (!data.empty()) muxSelection = data.back();
      return 0;
    }
    if (target == 0x36) {
      MockAs5600* encoder = reachableEncoder();
      if (!encoder) return 2;
      if (!data.empty()) encoder->pointer = data[0];
      return 0;
    }
    if (!pca.present || target != pca.address) return 2;  // NACK de dirección
    if (pca.failWrites) return 4;
    if (data.empty()) return 0;
    // Con auto-incremento, los bytes siguientes van a registros consecutivos.
    uint8_t reg = data[0];
    for (size_t i = 1; i < data.size(); ++i, ++reg) {
      if (reg >= 0xFA && reg <= 0xFD) {
        // ALL_LED_*: escritura simultánea en los 16 canales.
        for (int channel = 0; channel < 16; ++channel) {
          pca.registers[0x06 + 4 * channel + (reg - 0xFA)] = data[i];
        }
      } else {
        pca.registers[reg] = data[i];
      }
    }
    ++pca.writes;
    return 0;
  }
  uint8_t requestFrom(uint8_t address, uint8_t count) {
    incoming.clear();
    MockAs5600* encoder = address == 0x36 ? reachableEncoder() : nullptr;
    if (!encoder) return 0;
    for (uint8_t i = 0; i < count; ++i) incoming.push_back(encoder->registers[encoder->pointer++]);
    return count;
  }
  int available() { return static_cast<int>(incoming.size()); }
  int read() {
    if (incoming.empty()) return -1;
    const uint8_t value = incoming.front();
    incoming.pop_front();
    return value;
  }

  int sdaPin = -1;
  int sclPin = -1;
  uint32_t clock = 0;

 private:
  uint8_t target = 0;
  std::vector<uint8_t> data;
  std::deque<uint8_t> incoming;
};

inline TwoWire Wire;
