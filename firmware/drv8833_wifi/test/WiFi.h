#pragma once

// MOCK nativo de la red del ESP32: conexiones TCP en memoria, sin radio.
#include <cstddef>
#include <cstdint>
#include <deque>
#include <memory>
#include <string>

using String = std::string;

constexpr int WL_CONNECTED = 3;
constexpr int WIFI_STA = 1;
constexpr int WIFI_AP = 2;

struct IPAddress {
  String text;
  String toString() const { return text; }
};

struct MockConnection {
  std::deque<char> toEsp;  // lo que envía el computador
  std::string fromEsp;     // lo que responde el ESP32
  bool open = true;
  bool noDelay = false;

  void send(const std::string& text) {
    for (char value : text) toEsp.push_back(value);
  }

  std::string take() {
    std::string text;
    text.swap(fromEsp);
    return text;
  }
};

class WiFiClient {
 public:
  WiFiClient() = default;
  explicit WiFiClient(std::shared_ptr<MockConnection> connection) : connection_(connection) {}

  explicit operator bool() const { return connected(); }  // como en el núcleo ESP32
  bool connected() const { return connection_ && connection_->open; }
  int available() { return connected() ? static_cast<int>(connection_->toEsp.size()) : 0; }

  int read() {
    if (!available()) return -1;
    const char value = connection_->toEsp.front();
    connection_->toEsp.pop_front();
    return static_cast<unsigned char>(value);
  }

  size_t write(const uint8_t* data, size_t size) {
    if (!connected()) return 0;
    connection_->fromEsp.append(reinterpret_cast<const char*>(data), size);
    return size;
  }

  void setNoDelay(bool value) {
    if (connection_) connection_->noDelay = value;
  }

  void stop() {
    if (connection_) connection_->open = false;
    connection_.reset();
  }

 private:
  std::shared_ptr<MockConnection> connection_;
};

inline std::deque<std::shared_ptr<MockConnection>> pendingConnections;

inline std::shared_ptr<MockConnection> connectClient() {
  auto connection = std::make_shared<MockConnection>();
  pendingConnections.push_back(connection);
  return connection;
}

class WiFiServer {
 public:
  explicit WiFiServer(uint16_t port) : port(port) {}
  void begin() { started = true; }
  void setNoDelay(bool) {}

  WiFiClient accept() {
    if (!started || pendingConnections.empty()) return WiFiClient();
    auto connection = pendingConnections.front();
    pendingConnections.pop_front();
    return WiFiClient(connection);
  }

  uint16_t port;
  bool started = false;
};

struct MockWiFi {
  int currentMode = 0;
  int currentStatus = 0;
  String ssid;
  void mode(int value) { currentMode = value; }
  void setAutoReconnect(bool) {}
  void begin(const char* name, const char*) { ssid = name; currentStatus = WL_CONNECTED; }
  bool softAP(const char* name, const char*) { ssid = name; return true; }
  int status() const { return currentStatus; }
  IPAddress localIP() const { return {"10.0.0.42"}; }
  IPAddress softAPIP() const { return {"192.168.4.1"}; }
};

inline MockWiFi WiFi;
