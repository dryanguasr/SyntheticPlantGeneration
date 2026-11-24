#include <Arduino.h>
#include <driver/gpio.h>

constexpr gpio_num_t motorInputs[] = {GPIO_NUM_25, GPIO_NUM_26, GPIO_NUM_27, GPIO_NUM_14};

void report() {
  Serial.print("GPIO");
  for (const gpio_num_t pin : motorInputs) {
    Serial.printf(" %d=%d", static_cast<int>(pin), gpio_get_level(pin));
  }
  Serial.println();
}

void setup() {
  for (const gpio_num_t pin : motorInputs) {
    gpio_set_level(pin, 0);
  }
  gpio_config_t config{};
  for (const gpio_num_t pin : motorInputs) {
    config.pin_bit_mask |= 1ULL << pin;
  }
  config.mode = GPIO_MODE_INPUT_OUTPUT;
  config.pull_down_en = GPIO_PULLDOWN_ENABLE;
  config.intr_type = GPIO_INTR_DISABLE;
  esp_err_t status = gpio_config(&config);
  Serial.begin(115200);
  Serial.println(status == ESP_OK ? "READY GPIO CHECK" : "ERR GPIO CONFIG");
  report();
}

void loop() {
  while (Serial.available()) {
    if (Serial.read() == '?') {
      report();
    }
  }
  delay(10);
}
