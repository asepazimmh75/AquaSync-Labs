// 1. DATA WARNA DAN TIPS UNTUK GRAFIK
const metricConfig = {
    feed: {
        color: "rgba(59, 130, 246, 1)", // Blue
        bgGradient: "rgba(59, 130, 246, 0.2)",
        tips: "Tren pakan menunjukkan ikan lebih aktif makan di sore hari. Pastikan wadah penyimpanan (hopper) tetap kering agar pelet tidak menggumpal dan menyumbat servo."
    },
    temp: {
        color: "rgba(239, 68, 68, 1)", // Red
        bgGradient: "rgba(239, 68, 68, 0.2)",
        tips: "Suhu optimal untuk kebanyakan ikan tropis adalah 24-28°C. Hindari meletakkan akuarium di dekat jendela yang terkena sinar matahari langsung untuk mencegah lonjakan suhu mendadak."
    },
    water: {
        color: "rgba(14, 165, 233, 1)", // Sky blue
        bgGradient: "rgba(14, 165, 233, 0.2)",
        tips: "Penurunan level air sebesar 1-2% per hari adalah normal akibat penguapan. Jika turun drastis, periksa segera silikon kaca akuarium untuk mendeteksi kebocoran."
    },
    health: {
        color: "rgba(34, 197, 94, 1)", // Green
        bgGradient: "rgba(34, 197, 94, 0.2)",
        tips: "Skor dihitung dari uptime ESP32 dan latensi jaringan. Jika skor turun di bawah 80%, coba restart router Wi-Fi atau cek daya adaptor ESP32."
    }
};

// 2. INISIALISASI CHART.JS
const ctx = document.getElementById('mainChart').getContext('2d');
let currentChart;

function renderChartWithRealData(metricKey) {
    const config = metricConfig[metricKey];

    // --- MENGAMBIL DATA ASLI DARI FLASK API ---
    fetch(`/api/chart-data/${metricKey}`)
        .then(response => response.json())
        .then(data => {
            
            // Atur Judul berdasarkan tipe yang di-klik
            let judul = "";
            let deskripsi = "";
            
            if(metricKey === 'temp') {
                judul = "Water Temperature Trends";
                deskripsi = "Suhu air dalam 2 jam terakhir (°C)";
            } else if(metricKey === 'water') {
                judul = "Water Level Trends";
                deskripsi = "Ketinggian air dalam 2 jam terakhir (%)";
            } else if(metricKey === 'feed') {
                judul = "Feeding Trends";
                deskripsi = "Sisa pakan dalam 2 jam terakhir (%)";
            } else if(metricKey === 'health') {
                judul = "System Health Score";
                deskripsi = "Kestabilan koneksi dan sensor (%)";
            }

            // Update Teks HTML
            document.getElementById('chartTitle').innerText = judul;
            document.getElementById('chartDesc').innerText = deskripsi;
            document.getElementById('chartTips').innerText = config.tips;

            // Buat Gradien Warna
            const gradient = ctx.createLinearGradient(0, 0, 0, 400);
            gradient.addColorStop(0, config.bgGradient);
            gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');

            // Hancurkan chart lama jika ada
            if(currentChart) {
                currentChart.destroy();
            }

            // Buat Chart Baru Pakai Data Asli
            currentChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels, // <--- Ini jam asli dari Database
                    datasets: [{
                        label: judul,
                        data: data.values, // <--- Ini angka asli dari Sensor
                        borderColor: config.color,
                        backgroundColor: gradient,
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointBackgroundColor: '#fff',
                        pointBorderColor: config.color,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: false, grid: { borderDash: [5, 5] } },
                        x: { grid: { display: false } }
                    }
                }
            });
        })
        .catch(error => {
            console.error("Gagal ngambil data chart:", error);
            document.getElementById('chartDesc').innerText = "Gagal memuat data dari server. Pastikan sistem online.";
        });
}

// Fungsi global biar bisa dipanggil dari HTML onclick
window.changeChart = function(metricKey) {
    renderChartWithRealData(metricKey);
};

// Tampilkan grafik suhu (atau feed) sebagai default saat halaman dimuat
renderChartWithRealData('temp');


// 3. LOGIKA SMART ALERTS (Notifikasi Dinamis)
function checkAlerts() {
    // Ambil data dari jembatan yang udah disiapin di HTML
    const currentTemp = window.aquaSyncData.temp;
    const currentWater = window.aquaSyncData.water;
    const isOnline = window.aquaSyncData.isOnline;
    
    const alertContainer = document.getElementById('smartAlertsContainer');
    if(!alertContainer) return; 

    alertContainer.innerHTML = ''; 

    function createAlert(type, message, solution) {
        const colors = type === 'danger' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-yellow-50 border-yellow-200 text-yellow-700';
        const icon = type === 'danger' ? 'fa-triangle-exclamation' : 'fa-circle-exclamation';
        
        const alertHTML = `
            <div class="p-4 rounded-xl border flex items-start gap-3 ${colors} shadow-sm animate-fade-in">
                <div class="mt-0.5"><i class="fa-solid ${icon} text-lg"></i></div>
                <div>
                    <h4 class="font-bold">${message}</h4>
                    <p class="text-sm mt-1 opacity-90"><b>Solusi:</b> ${solution}</p>
                </div>
            </div>
        `;
        alertContainer.insertAdjacentHTML('beforeend', alertHTML);
    }

    // Rule 1: Suhu Panas/Dingin
    if (currentTemp > 31.0) {
        createAlert('danger', `Suhu Air Kritis (${currentTemp}°C)`, 'Nyalakan kipas pendingin atau turunkan suhu ruangan segera agar ikan tidak stres.');
    } else if (currentTemp < 23.0 && currentTemp > 0) { // Tambah proteksi > 0 biar ga spam kalau sensor error
        createAlert('warning', `Suhu Air Terlalu Dingin (${currentTemp}°C)`, 'Nyalakan heater (pemanas air) untuk mengembalikan suhu ke batas optimal (26°C).');
    }

    // Rule 2: Air Surut
    if (currentWater < 50 && currentWater > 0) {
        createAlert('danger', `Level Air Rendah (${currentWater}%)`, 'Segera tambahkan air ke dalam akuarium dan periksa indikasi kebocoran pada kaca.');
    }

    // Rule 3: Device Mati
    if (!isOnline) {
        createAlert('danger', 'Koneksi Alat Terputus (Offline)', 'Sistem tidak menerima data dari ESP32. Periksa colokan listrik dan pastikan Wi-Fi alat terhubung.');
    }
}

// Jalankan pengecekan alert setiap kali autoRefresh (data baru masuk)
// Kita panggil ini dari dalem setInterval yang ada di dashboard.html
window.checkAlertsGlobal = checkAlerts;