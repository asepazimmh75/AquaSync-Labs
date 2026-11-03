# 🐟 AquaSync Labs: Smart Aquarium Monitoring & Automation System

AquaSync Labs adalah sistem *Internet of Things (IoT)* berbasis web yang dirancang untuk membantu pengguna memantau kondisi akuarium secara *real-time* sekaligus mengontrol perangkat keras (pemberi pakan otomatis dan lampu) dari jarak jauh. Project ini dikembangkan sebagai bagian dari Skripsi.

---

## 🚀 Fitur Utama
* **Monitoring Real-Time:** Memantau suhu air (sensor DS18B20), persentase sisa pakan, dan ketinggian air secara langsung melalui web dashboard.
* **Smart Feeder (Pemberi Pakan Otomatis):** Mengontrol motor servo untuk memberi pakan ikan secara otomatis lewat web atau jadwal darurat.
* **Lighting Control:** Menyalakan/mematikan lampu akuarium menggunakan modul Relay.
* **Fail-Safe RTC (DS3231):** Sistem tetap dapat menjalankan jadwal pakan otomatis secara luring (*offline*) meskipun koneksi WiFi atau server sedang mati.

---

## 🛠️ Teknologi yang Digunakan
* **Backend:** Python (Flask), PyMongo
* **Database:** MongoDB Atlas
* **Frontend:** HTML5, CSS3, JavaScript, Bootstrap / Tailwind
* **Firmware / Hardware:** C++ (Arduino IDE), ESP32 NodeMCU, Sensor DS18B20, Sensor Ultrasonik (HC-SR04), RTC DS3231, Motor Servo, Relay 1-Channel.

---

## 📁 Struktur Repository
```text
aquasync_project/
├── firmware/              # Kode program ESP32 (Arduino IDE)
│   └── aquasync_esp32.ino
├── static/                # Aset frontend (CSS, JS, Gambar/Logo)
├── templates/             # Halaman HTML Web Dashboard (Flask)
├── app.py                 # Server utama backend Flask
├── models.py              # Konfigurasi database MongoDB
├── utils.py               # Fungsi pendukung / helper
├── requirements.txt       # Daftar library Python
└── README.md              # Dokumentasi project