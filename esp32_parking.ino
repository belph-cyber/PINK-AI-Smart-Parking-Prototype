/*
  =============================================================================
  Smart AI Parking - ESP32 Firmware
  (SG92R Servo + Traffic Light LED + HC-SR04 Ultrasonic Slot Sensor x3)
  =============================================================================
  บอร์ด    : ESP32 Dev Module (Core v2.x / v3.x Compatible)
  Broker   : broker.emqx.io:1883

  การต่อสายฮาร์ดแวร์ (Pin Mapping):
  ─────────────────────────────────────────────────────────────────────────────
  1. มอเตอร์เซอร์โว SG92R (ไม้กั้นทางเข้า):
       - สายสีส้ม/เหลือง (PWM Signal) → ขา D15 (GPIO 15)
       - สายสีแดง       (VCC 5V)      → ขา VIN หรือ 5V ของ ESP32
       - สายสีน้ำตาล/ดำ  (GND)         → ขา GND ของ ESP32

  1.1 มอเตอร์เซอร์โว SG92R #2 (ไม้กั้นทางออก): สัญญาณ → GPIO 13, VCC → 5V, GND → GND
  2. โมดูลไฟจราจรทางเข้า (Traffic Light Module 3 สี):
       - ขา GND   → GND ของ ESP32
       - ขา R     → ขา D33 (GPIO 33) [ไฟแดง]
       - ขา G     → ขา D25 (GPIO 25, 26, 27) [ไฟเขียว]

  3. เซนเซอร์วัดระยะทาง HC-SR04 #1 (ช่องจอดรถที่ 1):
       - ขา VCC   → ขา VIN หรือ 5V ของ ESP32
       - ขา Trig  → ขา D5  (GPIO 5)
       - ขา Echo  → ขา D18 (GPIO 18)
       - ขา GND   → ขา GND ของ ESP32

  4. เซนเซอร์วัดระยะทาง HC-SR04 #2 (ช่องจอดรถที่ 2):
       - ขา VCC   → ขา VIN หรือ 5V ของ ESP32
       - ขา Trig  → ขา D19 (GPIO 19)
       - ขา Echo  → ขา D21 (GPIO 21)
       - ขา GND   → ขา GND ของ ESP32

  5. เซนเซอร์วัดระยะทาง HC-SR04 #3 (ช่อง "ห้ามจอด" - แจ้งเตือนรปภ. ทันที):
       - ขา VCC   → ขา VIN หรือ 5V ของ ESP32
       - ขา Trig  → ขา D22 (GPIO 22)
       - ขา Echo  → ขา D23 (GPIO 23)
       - ขา GND   → ขา GND ของ ESP32
  =============================================================================
*/

#include <WiFi.h>
#include <PubSubClient.h>

// ─────────────────────────────────────────────────────────────────────────────
// กำหนดขาเชื่อมต่อ (Pin Definitions)
// ─────────────────────────────────────────────────────────────────────────────
// 1. Servo SG92R (ไม้กั้น)
const int PIN_SERVO            = 15;  // ขา D15 (GPIO 15)
const int PIN_SERVO_EXIT       = 13;  // ขา D13 (GPIO 13) ไม้กั้นทางออก

// 2. หลอดไฟ LED ทางเข้า
const int PIN_LED_ENTRY_RED    = 33;  // ขา D33 (ไฟแดง)
const int PIN_LED_GREEN_1      = 25;  // ขา D25 (ไฟเขียว)
const int PIN_LED_GREEN_2      = 26;  // ขา D26 (ไฟเขียว สำรอง)
const int PIN_LED_GREEN_3      = 27;  // ขา D27 (ไฟเขียว สำรอง)

// 3. เซนเซอร์วัดระยะทาง HC-SR04 #1 (ช่องจอดรถที่ 1)
const int PIN_TRIG             = 5;   // ขา D5  (Trig)
const int PIN_ECHO             = 18;  // ขา D18 (Echo)

// 4. เซนเซอร์วัดระยะทาง HC-SR04 #2 (ช่องจอดรถที่ 2)
const int PIN_TRIG2            = 19;  // ขา D19 (Trig)
const int PIN_ECHO2            = 21;  // ขา D21 (Echo)

// 5. เซนเซอร์วัดระยะทาง HC-SR04 #3 (ช่อง "ห้ามจอด" - แจ้งเตือนรปภ.)
const int PIN_TRIG3            = 22;  // ขา D22 (Trig)
const int PIN_ECHO3            = 23;  // ขา D23 (Echo)

// ─────────────────────────────────────────────────────────────────────────────
// การตั้งค่าระบบ (Configuration)
// ─────────────────────────────────────────────────────────────────────────────
// Servo Angles
const int SERVO_ANGLE_OPEN   = 90;   // องศาเปิด
const int SERVO_ANGLE_CLOSED = 0;    // องศาปิด
const int SERVO_PWM_FREQ     = 50;   // 50 Hz
const int SERVO_PWM_RES      = 14;   // 14-bit
const int SERVO_PWM_CHANNEL  = 0;
const int SERVO_EXIT_PWM_CHANNEL = 1;

// ระยะเวลาเปิดไม้กั้นค้างไว้ (5 วินาที)
const unsigned long GATE_HOLD_MS = 5000;

// เกณฑ์ระยะทางของเซนเซอร์ HC-SR04 (ซม.)
// หากตรวจพบวัตถุต่ำกว่า 20 ซม. ถือว่ามีรถจอดอยู่ในช่อง
const float DISTANCE_THRESHOLD_CM = 20.0;
const unsigned long SONAR_INTERVAL_MS = 1500; // ตรวจวัดระยะทุกๆ 1.5 วินาที

// WiFi & MQTT
const char* WIFI_SSID     = "Kc";
const char* WIFI_PASSWORD = "987654321";
const char* MQTT_SERVER   = "broker.emqx.io";
const int   MQTT_PORT     = 1883;

// MQTT Topics
const char* TOPIC_GATE              = "parking/esp/gate";
const char* TOPIC_GATE_EXIT         = "parking/esp/gate/exit"; // ไม้กั้นทางออก
const char* TOPIC_LED_ENTRY         = "parking/esp/led/entry";
const char* TOPIC_LED_WILD          = "parking/esp/led/#";
const char* TOPIC_SLOTS_STATUS      = "parking/sensors/slots"; // ข้อมูลเซนเซอร์ (service.py รวมกับผลกล้องที่ parking/slots/status)
const char* TOPIC_ESP_STATUS        = "parking/esp/status";
const char* TOPIC_NO_PARK_ALERT     = "parking/alert/no_parking"; // แจ้งเตือนช่องห้ามจอด

// ตัวแปรสถานะ
WiFiClient   espClient;
PubSubClient client(espClient);

bool          isGateOpen        = false;
unsigned long gateOpenTime      = 0;
bool          isExitGateOpen    = false;
unsigned long exitGateOpenTime  = 0;
unsigned long lastMqttRetry     = 0;
unsigned long lastSonarCheck    = 0;
bool          lastSlotOccupied  = false;

// สถานะเซนเซอร์ #3 (ช่องห้ามจอด)
bool          lastNoParkOccupied = false;
unsigned long noParkAlertCooldown = 0;
const unsigned long NO_PARK_ALERT_INTERVAL_MS = 30000; // แจ้งเตือนซ้ำทุก 30 วินาที ถ้ายังจอดอยู่

// ─────────────────────────────────────────────────────────────────────────────
// ฟังก์ชันควบคุม Servo SG92R
// ─────────────────────────────────────────────────────────────────────────────
void initServo() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcAttach(PIN_SERVO, SERVO_PWM_FREQ, SERVO_PWM_RES);
#else
  ledcSetup(SERVO_PWM_CHANNEL, SERVO_PWM_FREQ, SERVO_PWM_RES);
  ledcAttachPin(PIN_SERVO, SERVO_PWM_CHANNEL);
#endif
}

void initExitServo() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcAttach(PIN_SERVO_EXIT, SERVO_PWM_FREQ, SERVO_PWM_RES);
#else
  ledcSetup(SERVO_EXIT_PWM_CHANNEL, SERVO_PWM_FREQ, SERVO_PWM_RES);
  ledcAttachPin(PIN_SERVO_EXIT, SERVO_EXIT_PWM_CHANNEL);
#endif
}

void setExitServoAngle(int angle) {
  angle = constrain(angle, 0, 180);
  long pulse_us = map(angle, 0, 180, 500, 2400);
  uint32_t duty = (uint32_t)(pulse_us * 16383UL / 20000UL);
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcWrite(PIN_SERVO_EXIT, duty);
#else
  ledcWrite(SERVO_EXIT_PWM_CHANNEL, duty);
#endif
}

void setServoAngle(int angle) {
  angle = constrain(angle, 0, 180);
  long pulse_us = map(angle, 0, 180, 500, 2400);
  uint32_t duty = (uint32_t)(pulse_us * 16383UL / 20000UL);
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcWrite(PIN_SERVO, duty);
#else
  ledcWrite(SERVO_PWM_CHANNEL, duty);
#endif
}

// ─────────────────────────────────────────────────────────────────────────────
// ฟังก์ชันควบคุมไฟ LED ทางเข้า
// ─────────────────────────────────────────────────────────────────────────────
void setEntryLed(const char* color) {
  if (strcmp(color, "GREEN") == 0) {
    digitalWrite(PIN_LED_ENTRY_RED, LOW);
    digitalWrite(PIN_LED_GREEN_1,   HIGH);
    digitalWrite(PIN_LED_GREEN_2,   HIGH);
    digitalWrite(PIN_LED_GREEN_3,   HIGH);
    Serial.println("[LED] >>> GREEN ON (GPIO 25, 26, 27 = HIGH, GPIO 33 = LOW)");
  } else if (strcmp(color, "RED") == 0) {
    digitalWrite(PIN_LED_ENTRY_RED, HIGH);
    digitalWrite(PIN_LED_GREEN_1,   LOW);
    digitalWrite(PIN_LED_GREEN_2,   LOW);
    digitalWrite(PIN_LED_GREEN_3,   LOW);
    Serial.println("[LED] <<< RED ON (GPIO 33 = HIGH, GREEN = LOW)");
  } else {
    digitalWrite(PIN_LED_ENTRY_RED, LOW);
    digitalWrite(PIN_LED_GREEN_1,   LOW);
    digitalWrite(PIN_LED_GREEN_2,   LOW);
    digitalWrite(PIN_LED_GREEN_3,   LOW);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ฟังก์ชันควบคุมไม้กั้น
// ─────────────────────────────────────────────────────────────────────────────
void openGate(const char* source) {
  isGateOpen   = true;
  gateOpenTime = millis();

  setServoAngle(SERVO_ANGLE_OPEN);
  setEntryLed("GREEN");

  Serial.println("==================================================");
  Serial.printf("[GATE] >>> OPEN (Servo -> %d deg)  Source: %s\n", SERVO_ANGLE_OPEN, source);
  Serial.printf("[GATE] Will auto-close in %lu seconds...\n", GATE_HOLD_MS / 1000);
  Serial.println("==================================================");

  if (client.connected()) {
    client.publish(TOPIC_ESP_STATUS, "GATE OPEN");
  }
}

void closeGate(const char* source) {
  isGateOpen   = false;
  gateOpenTime = 0;

  setServoAngle(SERVO_ANGLE_CLOSED);
  setEntryLed("RED");

  Serial.println("--------------------------------------------------");
  Serial.printf("[GATE] <<< CLOSE (Servo -> %d deg)  Source: %s\n", SERVO_ANGLE_CLOSED, source);
  Serial.println("--------------------------------------------------");

  if (client.connected()) {
    client.publish(TOPIC_ESP_STATUS, "GATE CLOSED");
  }
}

void openExitGate(const char* source) {
  isExitGateOpen   = true;
  exitGateOpenTime = millis();
  setExitServoAngle(SERVO_ANGLE_OPEN);
  Serial.printf("[EXIT GATE] >>> OPEN (Servo GPIO %d -> %d deg)  Source: %s\n", PIN_SERVO_EXIT, SERVO_ANGLE_OPEN, source);
  if (client.connected()) client.publish(TOPIC_ESP_STATUS, "EXIT GATE OPEN");
}

void closeExitGate(const char* source) {
  isExitGateOpen   = false;
  exitGateOpenTime = 0;
  setExitServoAngle(SERVO_ANGLE_CLOSED);
  Serial.printf("[EXIT GATE] <<< CLOSE (Servo -> %d deg)  Source: %s\n", SERVO_ANGLE_CLOSED, source);
  if (client.connected()) client.publish(TOPIC_ESP_STATUS, "EXIT GATE CLOSED");
}

// ─────────────────────────────────────────────────────────────────────────────
// ฟังก์ชันวัดระยะทางด้วย HC-SR04 Ultrasonic Sensor (หน่วย: ซม.)
// รับพารามิเตอร์ขา trigPin และ echoPin เพื่อใช้กับเซนเซอร์ได้หลายตัว
// ─────────────────────────────────────────────────────────────────────────────
float readUltrasonicDistanceCM(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // รอรับสัญญาณสะท้อนกลับ (Timeout 25,000 us = ประมาณ 4 เมตร)
  long duration = pulseIn(echoPin, HIGH, 25000);
  if (duration == 0) return -1.0;

  // คำนวณระยะทาง: ระยะ = (เวลา * ความเร็วเสียง 0.0343) / 2
  return (duration * 0.0343) / 2.0;
}

// ─────────────────────────────────────────────────────────────────────────────
// MQTT Callback เมื่อได้รับข้อความ
// ─────────────────────────────────────────────────────────────────────────────
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  char msg[64] = {0};
  unsigned int len = min((unsigned int)(sizeof(msg) - 1), length);
  memcpy(msg, payload, len);
  while (len > 0 && (msg[len-1] == ' ' || msg[len-1] == '\r' || msg[len-1] == '\n')) {
    msg[--len] = '\0';
  }

  Serial.printf("\n[MQTT IN] Topic: %s | Msg: %s\n", topic, msg);

  // 1. คำสั่งเปิด-ปิดไม้กั้น
  if (strcmp(topic, TOPIC_GATE) == 0) {
    if      (strcmp(msg, "OPEN")  == 0) openGate("MQTT");
    else if (strcmp(msg, "CLOSE") == 0) closeGate("MQTT");
  // 1.1 คำสั่งเปิด-ปิดไม้กั้นทางออก
  } else if (strcmp(topic, TOPIC_GATE_EXIT) == 0) {
    if      (strcmp(msg, "OPEN")  == 0) openExitGate("MQTT");
    else if (strcmp(msg, "CLOSE") == 0) closeExitGate("MQTT");
  // 2. คำสั่งไฟทางเข้า
  } else if (strcmp(topic, TOPIC_LED_ENTRY) == 0) {
    setEntryLed(msg);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// เชื่อมต่อ MQTT Broker
// ─────────────────────────────────────────────────────────────────────────────
void reconnectMqtt() {
  if (client.connected()) return;

  unsigned long now = millis();
  if (now - lastMqttRetry < 5000) return;
  lastMqttRetry = now;

  char clientId[32];
  snprintf(clientId, sizeof(clientId), "ESP32Gate-%04X", (unsigned)random(0xFFFF));
  Serial.printf("[MQTT] Connecting to %s as %s ...", MQTT_SERVER, clientId);

  if (client.connect(clientId)) {
    Serial.println(" OK!");
    client.subscribe(TOPIC_GATE);
    client.subscribe(TOPIC_GATE_EXIT);
    client.subscribe(TOPIC_LED_WILD);
    client.publish(TOPIC_ESP_STATUS, "ESP32 ONLINE (SG92R + HC-SR04 Active)");
    Serial.println("[MQTT] Ready! Subscribed to gate and led topics");
  } else {
    Serial.printf(" FAILED rc=%d (retry in 5s)\n", client.state());
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// setup()
// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println("\n=================================================");
  Serial.println("  Smart AI Parking - ESP32 Controller Starting");
  Serial.printf("  - Servo Gate Pin    : GPIO %d\n", PIN_SERVO);
  Serial.printf("  - LED Red Pin       : GPIO %d\n", PIN_LED_ENTRY_RED);
  Serial.printf("  - LED Green Pins    : GPIO %d, %d, %d\n", PIN_LED_GREEN_1, PIN_LED_GREEN_2, PIN_LED_GREEN_3);
  Serial.printf("  - Sensor#1 Trig/Echo: GPIO %d / %d  [ช่องจอด 1]\n", PIN_TRIG,  PIN_ECHO);
  Serial.printf("  - Sensor#2 Trig/Echo: GPIO %d / %d  [ช่องจอด 2]\n", PIN_TRIG2, PIN_ECHO2);
  Serial.printf("  - Sensor#3 Trig/Echo: GPIO %d / %d  [ห้ามจอด - Alert]\n", PIN_TRIG3, PIN_ECHO3);
  Serial.printf("  - MQTT Broker       : %s:%d\n", MQTT_SERVER, MQTT_PORT);
  Serial.println("=================================================");

  // ตั้งค่า Pin Mode สำหรับ LED
  pinMode(PIN_LED_ENTRY_RED, OUTPUT);
  pinMode(PIN_LED_GREEN_1,   OUTPUT);
  pinMode(PIN_LED_GREEN_2,   OUTPUT);
  pinMode(PIN_LED_GREEN_3,   OUTPUT);

  // ตั้งค่า Pin Mode สำหรับเซนเซอร์วัดระยะ HC-SR04 ทั้ง 3 ตัว
  // ตัวที่ 1 (ช่องจอดที่ 1)
  pinMode(PIN_TRIG,  OUTPUT);
  pinMode(PIN_ECHO,  INPUT);
  digitalWrite(PIN_TRIG, LOW);

  // ตัวที่ 2 (ช่องจอดที่ 2)
  pinMode(PIN_TRIG2, OUTPUT);
  pinMode(PIN_ECHO2, INPUT);
  digitalWrite(PIN_TRIG2, LOW);

  // ตัวที่ 3 (ช่องห้ามจอด - แจ้งเตือนรปภ.)
  pinMode(PIN_TRIG3, OUTPUT);
  pinMode(PIN_ECHO3, INPUT);
  digitalWrite(PIN_TRIG3, LOW);

  // ตั้งค่าเริ่มต้น Servo และสถานะปิด
  initServo();
  initExitServo();
  closeGate("INIT");
  closeExitGate("INIT");

  // เชื่อมต่อ WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WIFI] Connecting to '%s'", WIFI_SSID);

  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 20) {
    delay(400);
    Serial.print(".");
    retry++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
  }

  client.setServer(MQTT_SERVER, MQTT_PORT);
  client.setCallback(mqttCallback);
  client.setKeepAlive(60);
}

// ─────────────────────────────────────────────────────────────────────────────
// loop()
// ─────────────────────────────────────────────────────────────────────────────
void loop() {
  // 1. ตรวจสอบการเชื่อมต่อ MQTT
  if (!client.connected()) {
    reconnectMqtt();
  } else {
    client.loop();
  }

  unsigned long currentMillis = millis();

  // 2. ระบบ Auto-Close ไม้กั้น (เปิดครบ 5 วินาทีแล้วปิดลงอัตโนมัติ)
  if (isGateOpen && (currentMillis - gateOpenTime >= GATE_HOLD_MS)) {
    Serial.printf("\n[TIMER] %lu s elapsed -> Auto-closing gate\n", GATE_HOLD_MS / 1000);
    closeGate("AUTO_TIMER");
  }

  // 2.1 Auto-Close ไม้กั้นทางออก
  if (isExitGateOpen && (currentMillis - exitGateOpenTime >= GATE_HOLD_MS)) {
    closeExitGate("AUTO_TIMER");
  }

  // 3. เซนเซอร์วัดระยะทาง HC-SR04 ตรวจจับช่องจอดรถ (ตรวจวัดทุก 1.5 วินาที)
  if (currentMillis - lastSonarCheck >= SONAR_INTERVAL_MS) {
    lastSonarCheck = currentMillis;

    // ─── เซนเซอร์ #1 (ช่องจอดที่ 1) ───────────────────────────────────────
    float dist1 = readUltrasonicDistanceCM(PIN_TRIG, PIN_ECHO);
    bool  occ1  = (dist1 > 0 && dist1 < DISTANCE_THRESHOLD_CM);

    // ─── เซนเซอร์ #2 (ช่องจอดที่ 2) ───────────────────────────────────────
    delay(25); // เว้น 25ms ป้องกันคลื่นเสียงสะท้อนรบกวนกันข้ามโมดูล
    float dist2 = readUltrasonicDistanceCM(PIN_TRIG2, PIN_ECHO2);
    bool  occ2  = (dist2 > 0 && dist2 < DISTANCE_THRESHOLD_CM);

    // ─── เซนเซอร์ #3 (ช่องห้ามจอด) ────────────────────────────────────────
    delay(25);
    float dist3 = readUltrasonicDistanceCM(PIN_TRIG3, PIN_ECHO3);
    bool  occ3  = (dist3 > 0 && dist3 < DISTANCE_THRESHOLD_CM);

    // ส่งข้อมูล JSON รวมช่องจอด 1 และ 2 ขึ้น MQTT
    if (client.connected()) {
      int occupiedCount = (occ1 ? 1 : 0) + (occ2 ? 1 : 0);
      int freeCount     = 2 - occupiedCount;

      char slotJson[512];
      snprintf(slotJson, sizeof(slotJson),
        "{\"total\":2,\"occupied\":%d,\"free\":%d,\"closed\":0,"
        "\"slots\":["
          "{\"id\":1,\"status\":\"%s\",\"reason\":\"%s (%.1f cm)\"},"
          "{\"id\":2,\"status\":\"%s\",\"reason\":\"%s (%.1f cm)\"}"
        "]}",
        occupiedCount,
        freeCount,
        occ1 ? "occupied" : "free",
        occ1 ? "มีรถจอด"  : "ว่าง",   dist1 > 0 ? dist1 : 999.0,
        occ2 ? "occupied" : "free",
        occ2 ? "มีรถจอด"  : "ว่าง",   dist2 > 0 ? dist2 : 999.0
      );
      client.publish(TOPIC_SLOTS_STATUS, slotJson);
    }

    // แสดงผล Serial Monitor (แสดงผลเสมอ แม้เซนเซอร์จะอ่านค่าไม่ได้ เพื่อให้ตรวจสอบสายได้ทันที)
    if (dist1 > 0) {
      Serial.printf("[HC-SR04 #1] ระยะ: %.1f ซม. -> %s\n", dist1, occ1 ? "🛑 มีรถจอด" : "🟢 ว่าง");
    } else {
      Serial.printf("[HC-SR04 #1] ❌ ไม่พบสัญญาณ Echo (Timeout) - ขา Trig:%d, Echo:%d\n", PIN_TRIG, PIN_ECHO);
    }

    if (dist2 > 0) {
      Serial.printf("[HC-SR04 #2] ระยะ: %.1f ซม. -> %s\n", dist2, occ2 ? "🛑 มีรถจอด" : "🟢 ว่าง");
    } else {
      Serial.printf("[HC-SR04 #2] ❌ ไม่พบสัญญาณ Echo (Timeout) - ขา Trig:%d, Echo:%d\n", PIN_TRIG2, PIN_ECHO2);
    }

    // ─── แจ้งเตือน ช่องห้ามจอด (เซนเซอร์ #3) ─────────────────────────────
    if (occ3) {
      Serial.printf("[HC-SR04 #3] ⚠️  ตรวจพบรถในช่องห้ามจอด! ระยะ: %.1f ซม.\n", dist3);

      // ส่งสถานะ active=true ทุกรอบตรวจวัด (รปภ. เห็นทันที)
      if (client.connected()) {
        char alertJson[220];
        snprintf(alertJson, sizeof(alertJson),
          "{\"alert\":\"NO_PARKING_VIOLATION\",\"active\":true,\"message\":\"ตรวจพบรถจอดในช่องห้ามจอด!\","
          "\"distance_cm\":%.1f,\"timestamp\":%lu}",
          dist3, currentMillis / 1000
        );
        client.publish(TOPIC_NO_PARK_ALERT, alertJson);
        if (!lastNoParkOccupied) Serial.println("[ALERT] >> ส่งแจ้งเตือนไปยัง รปภ. ผ่าน MQTT แล้ว!");
      }
    } else {
      if (dist3 > 0)
        Serial.printf("[HC-SR04 #3] ✅ ช่องห้ามจอดว่าง (%.1f ซม.)\n", dist3);

      // ส่งสถานะ active=false เพื่อเคลียร์แจ้งเตือนบนเว็บ
      if (client.connected()) {
        char clearJson[200];
        snprintf(clearJson, sizeof(clearJson),
          "{\"alert\":\"CLEARED\",\"active\":false,\"message\":\"ไม่มีรถจอดในช่องห้ามจอด\","
          "\"distance_cm\":%.1f,\"timestamp\":%lu}",
          dist3 > 0 ? dist3 : 999.0, currentMillis / 1000
        );
        client.publish(TOPIC_NO_PARK_ALERT, clearJson);
      }
    }
    lastNoParkOccupied = occ3;
  }

  delay(20);
}
