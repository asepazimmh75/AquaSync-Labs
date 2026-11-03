#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "RTClib.h" 
#include <ESP32Servo.h> 

// ==========================================
// 1. KONFIGURASI WIFI & SERVER FLASK
// ==========================================
const char* ssid = "********";        
const char* password = "**********"; 
const char* serverUrl = "*********"; // <-- Pastikan IP bener
const char* apiToken = "*************"; 

// ==========================================
// 2. DEKLARASI PIN (100% SESUAI TABEL LU TERBARU)
// ==========================================
#define SDA_PIN 21      
#define SCL_PIN 22      
#define ONE_WIRE_BUS 19 // <--- SUDAH UPDATE KE D19 (Suhu DS18B20)
#define SERVO_PIN 23    // <-- D23 (Motor Servo)
#define TRIG_PELET 4
#define ECHO_PELET 16   
#define TRIG_AIR 5
#define ECHO_AIR 17     

// --- UPDATE RELAY LAMPU ---
#define RELAY_LAMPU 2   // <-- Cuma pakai 1 Relay di D2

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
LiquidCrystal_I2C lcd(0x27, 16, 2); 
RTC_DS3231 rtc;
Servo servoPakan; 

unsigned long lastUpdateLCD = 0;
int lcdPage = 0; 
bool isLampuNyala = false; // <-- Variabel penyimpan status lampu saat ini

float bacaJarak(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW); delayMicroseconds(2);
  digitalWrite(trigPin, HIGH); delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH);
  return duration * 0.034 / 2.0;
}

// --- FUNGSI SERVO ---
void beriPakan() {
  Serial.println("MENGELUARKAN PAKAN...");
  servoPakan.write(90); // Muter 90 derajat buat buka katup pakan
  delay(1000);          // Biarin buka selama 1 detik
  servoPakan.write(0);  // Muter balik ke 0 derajat buat nutup katup
}

void setup() {
  Serial.begin(115200);

  pinMode(TRIG_PELET, OUTPUT); pinMode(ECHO_PELET, INPUT); 
  pinMode(TRIG_AIR, OUTPUT); pinMode(ECHO_AIR, INPUT); 
  
  // --- SETUP RELAY LAMPU ---
  pinMode(RELAY_LAMPU, OUTPUT);
  digitalWrite(RELAY_LAMPU, HIGH); // Default Mati (Asumsi Relay Active LOW)

  // --- SETUP SERVO ---
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
  servoPakan.setPeriodHertz(50);    
  servoPakan.attach(SERVO_PIN, 500, 2400); 
  servoPakan.write(0); // Posisi awal nutup

  Wire.begin(SDA_PIN, SCL_PIN);
  lcd.init(); lcd.backlight();
  
  // --- SETUP JAM (RTC) OTOMATIS ---
  if (!rtc.begin()) {
    Serial.println("RTC Tidak Ditemukan!");
  }
  
  if (rtc.lostPower()) {
    Serial.println("RTC kehilangan daya, menyetel ulang waktu...");
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  }

  sensors.begin();
  WiFi.begin(ssid, password);
  
  lcd.setCursor(0, 0); lcd.print("Booting WiFi...");
  while(WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  lcd.clear(); lcd.print("WiFi Connected!"); delay(2000);
}

void loop() {
  if(WiFi.status() == WL_CONNECTED){
    
    sensors.requestTemperatures(); 
    float suhuCelcius = sensors.getTempCByIndex(0);
    float jPelet = bacaJarak(TRIG_PELET, ECHO_PELET);
    float jAir = bacaJarak(TRIG_AIR, ECHO_AIR);
    int sinyalWiFi = WiFi.RSSI(); 
    DateTime now = rtc.now();

    int persenPelet = map(jPelet, 1, 10, 100, 0);
    persenPelet = constrain(persenPelet, 0, 100);

    int persenAir = map(jAir, 1, 15, 100, 0); 
    persenAir = constrain(persenAir, 0, 100);

    // --- TAMPILAN LCD BERGANTIAN ---
    if (millis() - lastUpdateLCD > 1000) { 
      lastUpdateLCD = millis();
      lcd.clear();
      if (lcdPage == 0) {
        lcd.setCursor(0, 0);
        lcd.print("Jam: "); 
        if(now.hour() < 10) lcd.print('0');
        lcd.print(now.hour()); lcd.print(":"); 
        if(now.minute() < 10) lcd.print('0');
        lcd.print(now.minute());
        
        lcd.setCursor(0, 1);
        lcd.print("Suhu: "); lcd.print(suhuCelcius, 1); lcd.print(" C");
        lcdPage = 1;
      } else {
        lcd.setCursor(0, 0);
        lcd.print("Pakan: "); lcd.print(persenPelet); lcd.print("%");
        lcd.setCursor(0, 1);
        lcd.print("Air  : "); lcd.print(persenAir); lcd.print("%");
        lcdPage = 0;
      }
    }

    // --- KIRIM DAN TERIMA DATA WEB ---
    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("x-api-key", apiToken);

    // (Update size document biar muat lebih banyak data)
    StaticJsonDocument<512> docKirim; 
    docKirim["suhu"] = suhuCelcius;
    docKirim["persen_pelet"] = persenPelet; 
    docKirim["persen_air"] = persenAir;     
    docKirim["sinyal"] = sinyalWiFi; 
    
    // --- NGIRIM LAPORAN STATUS LAMPU SAAT INI KE WEB ---
    docKirim["status_lampu"] = isLampuNyala ? "NYALA" : "MATI";
    
    String requestBody;
    serializeJson(docKirim, requestBody);

    int httpResponseCode = http.POST(requestBody);

    if (httpResponseCode > 0) {
      String payload = http.getString();
      StaticJsonDocument<512> docTerima;
      deserializeJson(docTerima, payload);
      
      // --- BACA PERINTAH PAKAN ---
      String perintahPakanWeb = docTerima["perintah_alat"]; 
      if (perintahPakanWeb == "BERI_PAKAN") {
        beriPakan();
      }
      
      // --- BACA PERINTAH LAMPU ---
      String perintahLampuWeb = docTerima["perintah_lampu"];
      if (perintahLampuWeb == "NYALAKAN_LAMPU" && !isLampuNyala) {
        isLampuNyala = true;
        digitalWrite(RELAY_LAMPU, LOW); // Relay ON
        Serial.println("💡 LAMPU DINYALAKAN DARI WEB/JADWAL!");
      } 
      else if (perintahLampuWeb == "MATIKAN_LAMPU" && isLampuNyala) {
        isLampuNyala = false;
        digitalWrite(RELAY_LAMPU, HIGH); // Relay OFF
        Serial.println("💡 LAMPU DIMATIKAN DARI WEB/JADWAL!");
      }
    }

    http.end(); 
  } else {
    // --- FITUR FAIL-SAFE RTC (SAAT WIFI MATI) ---
    DateTime now = rtc.now();
    static int menitOfflineTerakhir = -1; // Mencegah pakan tumpah berkali-kali di menit yang sama

    // [KONFIRMASI] Dibungkus timer millis agar LCD tidak kedap-kedip parah tiap 500ms
    if (millis() - lastUpdateLCD > 1000) { 
      lastUpdateLCD = millis();
      lcd.clear(); 
      lcd.setCursor(0, 0);
      lcd.print("WiFi Offline!");
      lcd.setCursor(0, 1);
      
      // Nampilin jam RTC di LCD biar keliatan alat masih hidup
      lcd.print("Jam RTC: ");
      if(now.hour() < 10) lcd.print('0');
      lcd.print(now.hour());
      lcd.print(":");
      if(now.minute() < 10) lcd.print('0');
      lcd.print(now.minute());
    }

    // Jadwal Darurat Darat (08:00 Pagi dan 17:00 Sore)
    if ((now.hour() == 8 && now.minute() == 0) || (now.hour() == 17 && now.minute() == 0)) {
        if (now.minute() != menitOfflineTerakhir) {
            Serial.println("FAIL-SAFE RTC AKTIF: Memberi Pakan Luring!");
            beriPakan(); // Panggil fungsi putar servo
            menitOfflineTerakhir = now.minute();
        }
    }
  }
  
  delay(500); 
}