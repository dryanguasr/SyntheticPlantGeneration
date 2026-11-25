#pragma once

// MOCK nativo del bus I2C con un PCA9685 en memoria: guarda sus registros.
#include <cstddef>
#include <cstdint>
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

inline MockPca9685 pca;

class TwoWire {
 public:
  bool begin(int sda, int scl) {
    sdaPin = sda;
    sclPin = scl;
    return true;
  }
  void beginTransmission(uint8_t address) {
    target = address;
    data.clear();
  }
  size_t write(const uint8_t* bytes, size_t size) {
    data.insert(data.end(), bytes, bytes + size);
    return size;
  }
  uint8_t endTransmission() {
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

  int sdaPin = -1;
  int sclPin = -1;

 private:
  uint8_t target = 0;
  std::vector<uint8_t> data;
};

inline TwoWire Wire;
