// Grid Monitor — ESP32 heartbeat firmware
//
// Sends a POST to /api/heartbeat every HEARTBEAT_INTERVAL_MS while powered.
// If the grid drops, the ESP32 loses power and stops sending — the server
// infers an outage from missing heartbeats.
//
// Configure the three values in the CONFIG block below, then flash.

#include <WiFi.h>
#include <HTTPClient.h>

// ============== CONFIG ==============
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
// Use the server's LAN IP or hostname. Port must match uvicorn.
const char* SERVER_URL    = "http://192.168.1.100:8000/api/heartbeat";
// ====================================

const uint32_t HEARTBEAT_INTERVAL_MS = 5000;
const uint32_t WIFI_RETRY_DELAY_MS   = 2000;
const uint32_t HTTP_TIMEOUT_MS       = 3000;

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print("WiFi connecting");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(" connected, IP=%s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println(" failed");
  }
}

bool sendHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(SERVER_URL)) {
    Serial.println("http.begin failed");
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Id", "esp32-grid-1");
  int code = http.POST("{}");
  bool ok = code > 0 && code < 400;
  Serial.printf("heartbeat code=%d ok=%d\n", code, ok);
  http.end();
  return ok;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nGrid Monitor booting");
  connectWifi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
    delay(WIFI_RETRY_DELAY_MS);
    return;
  }
  sendHeartbeat();
  delay(HEARTBEAT_INTERVAL_MS);
}
