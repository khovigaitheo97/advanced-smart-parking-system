#include <WiFi.h>
#include <WebServer.h>
#include <Arduino.h>
#include <ESP32Servo.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <LittleFS.h>

// ===================== WIFI =====================
const char* ssid = "Andrew Nguyen";
const char* pass = "chienhd123";

// ===================== OLED =====================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_ADDRESS 0x3C

Adafruit_SSD1306 displayOled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
bool oledOK = false;

// ===================== SERVER =====================
WebServer server(80);

// ===================== HARDWARE =====================
Servo sg90;

int ledPins[6] = {16, 17, 18, 19, 25, 26};
const int servo_pinout = 23;

// ===================== ULTRASONIC =====================
const int trigPin = 27;
const int echoPin = 14;

volatile bool carDetected = false;
unsigned long lastTriggerTime = 0;

// ===================== PARKING =====================
String spotStatus[6] = {"unknown","unknown","unknown","unknown","unknown","unknown"};
String lastMessage = "No message yet";

String oledSpaceMsg = "";
int freeCounter = 0;
const int TOTAL_SPACE = 6;

// ===================== PLATE =====================
String allowedPlates[] = {"A6", "V3", "C1"};
const int ALLOWED_COUNT = sizeof(allowedPlates) / sizeof(allowedPlates[0]);

String lastPlate = "";
bool lastPlateOk = false;
String plateMsg = "";

bool gateOpenedByValidPlate = false;
int servoAngle = 0;

// ===================== TIME =====================
unsigned long lastValidPlateTime = 0;
unsigned long lastPlateSeenTime = 0;
unsigned long lastWebVisitTime = 0;

const unsigned long PLATE_SEEN_TIMEOUT = 4000;
const unsigned long WEB_GRACE_MS = 6000;

// ===================== ISR =====================
void IRAM_ATTR echoISR() {
  carDetected = true;
}

// ===================== HELPERS =====================
bool plateAllowed(const String &n) {
  for (int i = 0; i < ALLOWED_COUNT; i++) {
    if (n == allowedPlates[i]) return true;
  }
  return false;
}

void updatePlateMsg() {
  plateMsg = "PLATE:";

  if (lastPlate.length() == 0) {
    plateMsg += "NO DETECTION";
    return;
  }

  plateMsg += lastPlate;

  if (lastPlateOk)
    plateMsg += " ALLOWED!";
  else
    plateMsg += " DENIED";
}

// ===================== HANDLERS =====================

// ---- PLATE ----
void handlePlate() {
  if (!server.hasArg("n")) {
    server.send(200, "text/plain", "Plate page");
    return;
  }

  String n = server.arg("n");
  n.trim();

  lastPlateSeenTime = millis();

  if (n == "NONE") {
    lastPlate = "";
    lastPlateOk = false;
    updatePlateMsg();
    server.send(200, "text/plain", "NO DETECTION");
    return;
  }

  lastPlate = n;
  bool ok = plateAllowed(n);

  Serial.printf("Plate: %s -> %s\n", n.c_str(), ok ? "ALLOWED" : "DENIED");

  // ✅ ONLY OPEN WHEN: valid plate + car detected
  if (ok && carDetected) {

    if (freeCounter == 0) {
      sg90.write(0);
      servoAngle = 0;
    } else {
      sg90.write(90);
      servoAngle = 90;
    }

    carDetected = false;   // reset after use
    lastValidPlateTime = millis();
    gateOpenedByValidPlate = true;
    lastPlateOk = true;

  } else {
    lastPlateOk = false;
  }

  updatePlateMsg();
  server.send(200, "text/plain", ok ? "ALLOWED" : "DENIED");
}

// ---- LED ----
void handleLed() {
  if (!server.hasArg("s")) {
    server.send(400, "text/plain", "Missing s");
    return;
  }

  String s = server.arg("s");

  if (s.length() != 6) {
    server.send(400, "text/plain", "Need 6 chars");
    return;
  }

  for (int i = 0; i < 6; i++) {
    digitalWrite(ledPins[i], (s[i] == '1') ? HIGH : LOW);
  }

  server.send(200, "text/plain", "OK");
}

// ---- MSG ----
void handleMsg() {
  if (!(server.hasArg("spot") && server.hasArg("status"))) {
    server.send(400, "text/plain", "Missing spot/status");
    return;
  }

  int spot = server.arg("spot").toInt();
  String status = server.arg("status");
  status.toLowerCase();

  if (spot >= 1 && spot <= 6) {
    spotStatus[spot - 1] = status;
  }

  freeCounter = 0;
  oledSpaceMsg = "";
  bool freeFlag = false;
  String html = "";

  for (int i = 0; i < 6; i++) {
    if (spotStatus[i] == "free") {
      freeCounter++;
      freeFlag = true;

      html += "Spot " + String(i + 1) + " is FREE<br>";
      oledSpaceMsg += String(i + 1) + ",";
    }
  }

  if (oledSpaceMsg.endsWith(",")) {
    oledSpaceMsg.remove(oledSpaceMsg.length() - 1);
  }

  if (!freeFlag) {
    html = "No free spots";
  }

  lastMessage = html;
  server.send(200, "text/plain", "OK");
}

// ---- ROOT ----
void handleRoot() {
  updatePlateMsg();

  String html = R"rawliteral(
<!DOCTYPE html>
<html>
<body>
<h1>Smart Parking</h1>
<p>{{plate}}</p>
<div>{{parking}}</div>
</body>
</html>
)rawliteral";

  html.replace("{{plate}}", plateMsg);
  html.replace("{{parking}}", lastMessage);

  lastWebVisitTime = millis();
  server.send(200, "text/html", html);
}

// ===================== SETUP =====================
void setup() {
  Serial.begin(115200);

  LittleFS.begin(true);

  // LED
  for (int i = 0; i < 6; i++) {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
  }

  // SERVO
  sg90.setPeriodHertz(50);
  sg90.attach(servo_pinout, 500, 2400);
  sg90.write(0);

  // ULTRASONIC
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  attachInterrupt(digitalPinToInterrupt(echoPin), echoISR, RISING);

  // WIFI
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  Serial.println("\nConnected: " + WiFi.localIP().toString());

  // SERVER
  server.on("/", handleRoot);
  server.on("/led", handleLed);
  server.on("/msg", handleMsg);
  server.on("/plate", handlePlate);
  server.begin();

  // OLED
  Wire.begin(21, 22);
  oledOK = displayOled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS);
}

// ===================== LOOP =====================
void loop() {
  server.handleClient();

  // trigger ultrasonic pulse
  if (millis() - lastTriggerTime > 100) {
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);

    lastTriggerTime = millis();
  }

  // reset detection if no plate comes
  if (carDetected && (millis() - lastPlateSeenTime > 3000)) {
    carDetected = false;
  }

  // OLED
  if (oledOK) {
    displayOled.clearDisplay();
    displayOled.setCursor(0, 0);

    displayOled.printf("FREE: %d/%d\n", freeCounter, TOTAL_SPACE);
    displayOled.printf("SPOT: %s\n", oledSpaceMsg.c_str());
    displayOled.println(plateMsg);

    if (freeCounter == 0)
      displayOled.println("FULL PARKING!");
    else if (servoAngle == 90)
      displayOled.println("GATE OPEN!");
    else
      displayOled.println("GATE CLOSE!");

    displayOled.display();
  }

  // auto close gate
  if (gateOpenedByValidPlate &&
      millis() - lastValidPlateTime > PLATE_SEEN_TIMEOUT) {

    sg90.write(0);
    servoAngle = 0;

    gateOpenedByValidPlate = false;
    lastPlate = "";
    lastPlateOk = false;

    updatePlateMsg();
    Serial.println("Auto close gate");
  }

  delay(50);
}