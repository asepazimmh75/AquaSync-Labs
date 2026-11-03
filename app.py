# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets
import time  # <-- Penting untuk ngitung device online/offline
from bson.objectid import ObjectId
from dotenv import load_dotenv

# --- IMPORT DARI FILE LUAR (Pastikan models.py dan utils.py sudah ada) ---
from models import users_collection, schedules_collection, settings_collection, sensor_history_collection, User
from utils import generate_otp, send_email_general

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kuncirahasia123'

# --- SETUP FLASK LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    try:
        user_data = users_collection.find_one({"_id": ObjectId(user_id)})
        if user_data:
            return User(user_data)
    except:
        return None
    return None

# --- VARIABEL GLOBAL SENSOR ---
suhu_terakhir = 0.0
persen_pelet_terakhir = 0    # <--- Ubah ini
persen_air_terakhir = 0      # <--- Ubah ini
sinyal_terakhir = 0          # <--- Pastiin ini ada
waktu_terakhir_ping = 0.0
status_alat = True
perintah_pakan_web = "IDLE"
perintah_lampu_web = "IDLE" # <--- TAMBAHIN INI BOS
status_lampu = "MATI"  # <--- JAGOAN BARU KITA, SIMPEN STATUS LAMPU SAAT INI
waktu_simpan_db_terakhir = 0 # <--- Jagoan baru buat ngerem database
waktu_cek_db_terakhir = 0.0 # Rem biar ga nge-spam MongoDB
menit_pakan_terakhir = ""   # Biar pakan ga tumpah berkali-kali di menit yang sama
# --- TAMBAHAN BARU BUAT ANIMASI & ANOMALI ---
waktu_terakhir_pakan = 0.0 
pelet_sebelumnya = -1       
pesan_anomali = None

# ==========================================
# ROUTES AUTENTIKASI
# ==========================================

@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        otp_input = request.form.get('otp_code')

        user_data = users_collection.find_one({"email": email})

        if user_data and check_password_hash(user_data['password'], password):
            if not user_data.get('is_verified'):
                flash('Akun belum diverifikasi. Cek email Anda.', 'warning')
                return render_template('login.html')

            if not otp_input:
                flash('Silakan minta dan masukkan kode OTP terlebih dahulu.', 'warning')
                return render_template('login.html')

            otp_expiry = user_data.get('otp_expiry')
            if not otp_expiry or datetime.now() > otp_expiry:
                flash('Kode OTP kadaluarsa. Silakan minta ulang.', 'error')
                return render_template('login.html')

            if user_data.get('otp_hash') and check_password_hash(user_data['otp_hash'], otp_input):
                users_collection.update_one(
                    {"_id": user_data['_id']},
                    {"$set": {
                        "otp_hash": None, 
                        "otp_expiry": None, 
                        "otp_verified": True,
                        "otp_request_count": 0  
                    }}
                )
                
                user_obj = User(user_data)
                login_user(user_obj)
                return redirect(url_for('dashboard'))
            else:
                flash('Kode OTP salah!', 'error')
        else:
            flash('Email atau password salah!', 'error')

    return render_template('login.html')

@app.route('/ajax-send-otp', methods=['POST'])
def ajax_send_otp():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user_data = users_collection.find_one({"email": email})

    if not user_data or not check_password_hash(user_data['password'], password):
        return jsonify({'status': 'error', 'message': 'Email atau Password salah!'}), 401

    current_time = datetime.now()
    last_request = user_data.get('last_otp_request')
    request_count = user_data.get('otp_request_count', 0)

    if last_request:
        time_diff = (current_time - last_request).total_seconds()
        if time_diff < 60:
            remaining = int(60 - time_diff)
            return jsonify({'status': 'error', 'message': f'Tunggu {remaining} detik lagi.'}), 429

    if last_request and (current_time - last_request).total_seconds() > 3600:
        request_count = 0

    if request_count >= 5:
        return jsonify({'status': 'error', 'message': 'Limit OTP tercapai (5x). Coba lagi nanti.'}), 429

    otp_code = generate_otp()
    otp_hash = generate_password_hash(otp_code)
    otp_expiry = current_time + timedelta(minutes=5)

    users_collection.update_one(
        {"_id": user_data['_id']},
        {"$set": {
            "otp_hash": otp_hash, 
            "otp_expiry": otp_expiry, 
            "otp_verified": False,
            "last_otp_request": current_time,
            "otp_request_count": request_count + 1
        }}
    )

    # --- TEMPLATE EMAIL OTP LOGIN (AQUASYNC THEME) ---
    body = f"""
    <div style="background-color: #0f172a; padding: 40px 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #ffffff;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <div style="background: linear-gradient(135deg, #2563eb, #06b6d4); padding: 30px 20px; text-align: center;">
                <h2 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: bold;">🌊 Kode OTP Login</h2>
            </div>
            <div style="padding: 30px 20px; text-align: center;">
                <p style="margin: 0 0 20px 0; color: #94a3b8; font-size: 15px;">Berikut adalah kode OTP untuk login ke akun AquaSync Anda.</p>
                <div style="background-color: #0f172a; border: 1px dashed #38bdf8; border-radius: 10px; padding: 15px; margin-bottom: 20px;">
                    <h1 style="margin: 0; color: #38bdf8; font-size: 36px; letter-spacing: 8px;">{otp_code}</h1>
                </div>
                <p style="margin: 0; color: #64748b; font-size: 12px;">Kode ini berlaku selama 5 menit. Jangan berikan kode ini kepada siapapun.</p>
            </div>
        </div>
    </div>
    """
    
    if send_email_general(email, "Kode OTP AquaSync", body):
        remaining_quota = 5 - (request_count + 1)
        return jsonify({'status': 'success', 'message': f'OTP Terkirim! Sisa percobaan: {remaining_quota}'})
    else:
        return jsonify({'status': 'error', 'message': 'Gagal mengirim email.'}), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        quiz_answer = request.form.get('quiz_answer')

        if quiz_answer != 'correct':
            flash('Jawaban keamanan salah!', 'error')
            return redirect(url_for('register'))

        if users_collection.find_one({"email": email}):
            flash('Email sudah terdaftar!', 'error')
            return redirect(url_for('register'))

        token = secrets.token_urlsafe(32)
        expiry_time = datetime.now() + timedelta(hours=24)

        new_user = {
            "username": username,
            "email": email,
            "password": generate_password_hash(password, method='scrypt'),
            "is_verified": False,
            "verification_token": token,
            "token_expiry": expiry_time,
            "created_at": datetime.now()
        }
        users_collection.insert_one(new_user)

        verify_url = url_for('verify_email', token=token, _external=True)
        
        # --- TEMPLATE EMAIL VERIFIKASI REGISTER (AQUASYNC THEME) ---
        body = f"""
        <div style="background-color: #0f172a; padding: 40px 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #ffffff;">
            <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                <div style="background: linear-gradient(135deg, #2563eb, #06b6d4); padding: 30px 20px; text-align: center;">
                    <h2 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: bold;">🌊 Verifikasi Akun</h2>
                </div>
                <div style="padding: 30px 20px; text-align: center;">
                    <p style="margin: 0 0 25px 0; color: #94a3b8; font-size: 15px;">Halo <b>{username}</b>, selamat datang di AquaSync! Klik tombol di bawah ini untuk mengaktifkan akun Anda.</p>
                    
                    <a href="{verify_url}" style="display: inline-block; background: linear-gradient(135deg, #2563eb, #06b6d4); color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: bold; font-size: 16px; margin-bottom: 25px;">Verifikasi Sekarang</a>
                    
                    <p style="margin: 0; color: #64748b; font-size: 12px;">Link ini berlaku selama 24 jam. Jika tombol tidak berfungsi, salin URL berikut: <br><span style="color:#38bdf8;">{verify_url}</span></p>
                </div>
            </div>
        </div>
        """
        
        if send_email_general(email, "Verifikasi Akun AquaSync", body):
            flash('Registrasi berhasil! Cek email untuk verifikasi.', 'success')
        else:
            flash('Registrasi berhasil tapi gagal kirim email.', 'warning')

        return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/verify/<token>')
def verify_email(token):
    user_data = users_collection.find_one({"verification_token": token})
    
    if not user_data:
        flash('Token tidak valid.', 'error')
        return redirect(url_for('login'))
    
    if user_data.get('token_expiry') < datetime.now():
        flash('Token kadaluarsa. Daftar ulang.', 'error')
        users_collection.delete_one({"_id": user_data['_id']})
        return redirect(url_for('register'))
    
    users_collection.update_one(
        {"_id": user_data['_id']},
        {"$set": {"is_verified": True, "verification_token": None, "token_expiry": None}}
    )
    
    flash('Email diverifikasi! Silakan login.', 'success')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        user_data = users_collection.find_one({"email": email})

        if user_data:
            otp_code = generate_otp()
            otp_expiry = datetime.now() + timedelta(minutes=5)

            users_collection.update_one(
                {"_id": user_data['_id']},
                {"$set": {"otp_hash": generate_password_hash(otp_code), "otp_expiry": otp_expiry}}
            )

            # --- TEMPLATE EMAIL RESET PASSWORD (AQUASYNC THEME) ---
            body = f"""
            <div style="background-color: #0f172a; padding: 40px 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #ffffff;">
                <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                    <div style="background: linear-gradient(135deg, #2563eb, #06b6d4); padding: 30px 20px; text-align: center;">
                        <h2 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: bold;">🌊 Reset Password</h2>
                    </div>
                    <div style="padding: 30px 20px; text-align: center;">
                        <p style="margin: 0 0 20px 0; color: #94a3b8; font-size: 15px;">Kami menerima permintaan untuk mereset password akun Anda. Berikut adalah kode OTP Anda:</p>
                        <div style="background-color: #0f172a; border: 1px dashed #ef4444; border-radius: 10px; padding: 15px; margin-bottom: 20px;">
                            <h1 style="margin: 0; color: #ef4444; font-size: 36px; letter-spacing: 8px;">{otp_code}</h1>
                        </div>
                        <p style="margin: 0; color: #64748b; font-size: 12px;">Kode ini berlaku selama 5 menit. Jika Anda tidak merasa meminta reset password, abaikan email ini dan pastikan akun Anda aman.</p>
                    </div>
                </div>
            </div>
            """
            
            if send_email_general(email, "Reset Password AquaSync", body):
                session['reset_email'] = email
                flash('Kode OTP dikirim.', 'info')
                return redirect(url_for('verify_reset_otp'))
        else:
            flash('Email tidak ditemukan.', 'error')

    return render_template('forgot_password.html')

@app.route('/reset-verify', methods=['GET', 'POST'])
def verify_reset_otp():
    if 'reset_email' not in session:
        return redirect(url_for('forgot_password'))

    email = session['reset_email']
    user_data = users_collection.find_one({"email": email})

    if request.method == 'POST':
        otp_input = request.form.get('otp_code')

        if not user_data or datetime.now() > user_data.get('otp_expiry'):
            flash('Kode OTP kadaluarsa.', 'error')
            return redirect(url_for('forgot_password'))

        if check_password_hash(user_data.get('otp_hash'), otp_input):
            session['is_reset_verified'] = True
            return redirect(url_for('update_password'))
        else:
            flash('Kode OTP salah!', 'error')

    return render_template('verify_reset_otp.html', email=email)

@app.route('/reset-update', methods=['GET', 'POST'])
def update_password():
    if 'reset_email' not in session or 'is_reset_verified' not in session:
        return redirect(url_for('forgot_password'))

    email = session['reset_email']

    if request.method == 'POST':
        new_pass = request.form.get('new_password')
        confirm_pass = request.form.get('confirm_password')

        if new_pass != confirm_pass:
            flash('Password tidak sama.', 'error')
        else:
            users_collection.update_one(
                {"email": email},
                {"$set": {
                    "password": generate_password_hash(new_pass, method='scrypt'),
                    "otp_hash": None,
                    "otp_expiry": None
                }}
            )
            session.pop('reset_email', None)
            session.pop('is_reset_verified', None)
            flash('Password berhasil diubah. Silakan login.', 'success')
            return redirect(url_for('login'))

    return render_template('update_password.html', email=email)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ==========================================
# ROUTES APLIKASI (DASHBOARD DLL)
# ==========================================

@app.route('/dashboard')
@login_required 
def dashboard():
    global suhu_terakhir, persen_pelet_terakhir, persen_air_terakhir, sinyal_terakhir, waktu_terakhir_ping
    
    # 1. Cek Status Online
    is_online = False
    waktu_sekarang = time.time()
    if waktu_terakhir_ping > 0 and (waktu_sekarang - waktu_terakhir_ping) < 300:
        is_online = True

    # ==========================================
    # LOGIKA PERHITUNGAN SYSTEM HEALTH
    # ==========================================
    health_score = 100
    
    if not is_online:
        health_score = 0  # Kalau alat mati/putus koneksi, sistem 0%
    else:
        # Cek Kualitas Sinyal Wi-Fi
        if sinyal_terakhir < -85:
            health_score -= 30  # Sinyal sangat buruk
        elif sinyal_terakhir < -70:
            health_score -= 15  # Sinyal lemah
            
        # Cek Error Sensor Suhu (DS18B20 ngirim -127 jika kabel putus)
        if suhu_terakhir <= -100:
            health_score -= 40
            
    # Kunci nilai biar nggak tembus batas (0-100)
    health_score = max(0, min(100, health_score))

    # ==========================================

    data_sensor = {
        'temp': round(suhu_terakhir, 1),
        'feed': persen_pelet_terakhir,   
        'feed_trend': -12, 
        'water_level': persen_air_terakhir, 
        'system_health': health_score, # <--- SEKARANG PAKAI HASIL HITUNGAN
        'is_online': is_online,
        'signal': sinyal_terakhir  
    }
    return render_template('dashboard.html', user=current_user, data=data_sensor, page='dashboard')

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    global status_alat

    if request.method == 'POST':
        time_input = request.form.get('feed_time')
        if time_input:
            schedules_collection.insert_one({
                "time": time_input,
                "user_id": ObjectId(current_user.id),
                "is_active": True
            })
            flash('Jadwal ditambahkan!', 'success')
        return redirect(url_for('settings'))

    schedules_cursor = schedules_collection.find({"user_id": ObjectId(current_user.id)}).sort("time", 1)
    schedules = list(schedules_cursor)
    
    # --- TAMBAHAN BUAT AMBIL DATA LAMPU ---
    # Cek config lampu di database
    config_lampu = settings_collection.find_one({"_id": "config_lampu"})
    
    # Kalau datanya udah ada, pakai data itu. Kalau belum ada (baru pertama kali buka), pakai default.
    if config_lampu:
        lamp_mode = config_lampu.get("mode", "manual")
        lamp_on_time = config_lampu.get("on_time", "08:00")
        lamp_off_time = config_lampu.get("off_time", "16:00")
    else:
        lamp_mode = "manual"
        lamp_on_time = "08:00"
        lamp_off_time = "16:00"

    # Kirim status_alat dan variabel lampu ke template
    return render_template('settings.html', 
                           user=current_user, 
                           schedules=schedules, 
                           page='settings', 
                           status_alat=status_alat,
                           lamp_mode=lamp_mode,
                           lamp_on_time=lamp_on_time,
                           lamp_off_time=lamp_off_time)

@app.route('/delete_schedule/<id>')
@login_required
def delete_schedule(id):
    schedules_collection.delete_one({"_id": ObjectId(id), "user_id": ObjectId(current_user.id)})
    flash('Jadwal dihapus.', 'success')
    return redirect(url_for('settings'))

@app.route('/edit_schedule/<id>', methods=['POST'])
@login_required
def edit_schedule(id):
    new_time = request.form.get('edit_time')
    if new_time:
        # [MONGO] Update data berdasarkan ID dan user yang login
        schedules_collection.update_one(
            {"_id": ObjectId(id), "user_id": ObjectId(current_user.id)},
            {"$set": {"time": new_time}}
        )
        flash('Jadwal berhasil diperbarui!', 'success')
    return redirect(url_for('settings'))

@app.route('/guide')
@login_required
def guide():
    return render_template('guide.html', user=current_user, page='guide')

@app.route('/about')
@login_required
def about():
    return render_template('about.html', user=current_user, page='about')

@app.route('/contact', methods=['GET', 'POST'])
@login_required
def contact():
    user_data = users_collection.find_one({"_id": ObjectId(current_user.id)})

    current_time = datetime.now()
    last_msg_time = user_data.get('last_contact_time')
    msg_count = user_data.get('contact_msg_count', 0)

    if last_msg_time and (current_time - last_msg_time).total_seconds() > 86400:
        msg_count = 0

    cooldown_seconds = 0
    if last_msg_time:
        time_diff = (current_time - last_msg_time).total_seconds()
        if time_diff < 180: 
            cooldown_seconds = int(180 - time_diff)

    if request.method == 'POST':
        subject_input = request.form.get('subject')
        message_input = request.form.get('message')

        if cooldown_seconds > 0:
            flash(f'Harap tunggu {cooldown_seconds} detik lagi.', 'warning')
            return redirect(url_for('contact'))

        if msg_count >= 3:
            flash('Batas harian (3 pesan) tercapai. Coba lagi besok.', 'error')
            return redirect(url_for('contact'))

        developer_email = "asepazizmiftahulhuda75@gmail.com"
        
        # --- TEMPLATE EMAIL AQUASYNC THEME (BIRU GRADASI) ---
        email_body = f"""
        <div style="background-color: #0f172a; padding: 40px 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #ffffff;">
            <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                
                <div style="background: linear-gradient(135deg, #2563eb, #06b6d4); padding: 30px 20px; text-align: center;">
                    <h2 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: bold;">🌊 New AquaSync Message</h2>
                </div>
                
                <div style="padding: 30px 20px;">
                    
                    <div style="background-color: #0f172a; border-radius: 10px; padding: 15px; margin-bottom: 20px; border: 1px solid #334155;">
                        <p style="margin: 0 0 8px 0; color: #94a3b8; font-size: 14px;">
                            <b>Name:</b> <span style="color: #f8fafc;">{current_user.username}</span>
                        </p>
                        <p style="margin: 0; color: #94a3b8; font-size: 14px;">
                            <b>Email:</b> <a href="mailto:{current_user.email}" style="color: #38bdf8; text-decoration: none;">{current_user.email}</a>
                        </p>
                    </div>

                    <div style="background-color: #0f172a; border-radius: 10px; padding: 15px; margin-bottom: 20px; border: 1px solid #334155;">
                        <p style="margin: 0; color: #94a3b8; font-size: 14px;">
                            <b>Subject:</b> <span style="color: #f8fafc;">{subject_input}</span>
                        </p>
                    </div>

                    <div style="background-color: #0f172a; border-radius: 10px; padding: 15px; margin-bottom: 20px; border: 1px solid #334155;">
                        <p style="margin: 0 0 10px 0; color: #94a3b8; font-size: 14px;"><b>Message:</b></p>
                        <p style="margin: 0; color: #e2e8f0; font-size: 15px; line-height: 1.6;">
                            {message_input}
                        </p>
                    </div>

                    <p style="margin: 30px 0 0 0; color: #64748b; font-size: 12px; text-align: center;">
                        This message was sent securely from AquaSync Contact Form. 🐟
                    </p>
                    
                </div>
            </div>
        </div>
        """
        
        if send_email_general(developer_email, f"Contact: {subject_input}", email_body):
            users_collection.update_one(
                {"_id": ObjectId(current_user.id)},
                {"$set": {
                    "last_contact_time": current_time,
                    "contact_msg_count": msg_count + 1
                }}
            )
            flash('Pesan berhasil dikirim ke Developer! Kami akan segera merespons.', 'success')
        else:
            flash('Gagal mengirim pesan. Silakan coba lagi nanti.', 'error')
            
        return redirect(url_for('contact'))

    return render_template('contact.html', user=current_user, page='contact', cooldown=cooldown_seconds)

# ==========================================
# API UNTUK MENERIMA DATA DARI ALAT (ESP32)
# ==========================================

API_TOKEN_RAHASIA = "AquaSync_Skripsi_2026_TopSecret"

@app.route('/api/sensor', methods=['POST'])
def terima_sensor():
    global suhu_terakhir, persen_pelet_terakhir, persen_air_terakhir, sinyal_terakhir, waktu_terakhir_ping
    global perintah_pakan_web, perintah_lampu_web, status_lampu
    global status_alat, waktu_simpan_db_terakhir
    global waktu_cek_db_terakhir, menit_pakan_terakhir
    global waktu_terakhir_pakan, pelet_sebelumnya, pesan_anomali # <--- Panggil Global

    token_masuk = request.headers.get('x-api-key')
    if token_masuk != API_TOKEN_RAHASIA:
        return jsonify({"status": "error", "pesan": "Akses Ditolak!"}), 401

    data = request.get_json()
    if data:
        suhu_terakhir = data.get('suhu', 0)
        persen_air_terakhir = data.get('persen_air', 0)     
        sinyal_terakhir = data.get('sinyal', 0) 
        
        status_lampu_esp = data.get('status_lampu', 'MATI') 
        status_lampu = "NYALA" if status_lampu_esp.upper() == 'NYALA' else "MATI"
        waktu_terakhir_ping = time.time()  

        # ==========================================
        # LOGIKA ANOMALI PAKAN (SKENARIO B)
        # ==========================================
        pelet_sekarang = data.get('persen_pelet', 0)
        
        if pelet_sebelumnya != -1: # Abaikan pembacaan pertama kali alat nyala
            selisih = pelet_sekarang - pelet_sebelumnya
            # Cek apakah sistem baru ngasih makan dalam 1 menit terakhir
            baru_dikasih_makan = (waktu_terakhir_ping - waktu_terakhir_pakan) < 60
            
            if selisih >= 15:
                pesan_anomali = {"tipe": "success", "teks": "Wadah pakan berhasil diisi ulang manual!"}
            elif selisih <= -10 and not baru_dikasih_makan:
                pesan_anomali = {"tipe": "warning", "teks": "Terdeteksi pemberian pakan manual di luar sistem!"}

        pelet_sebelumnya = pelet_sekarang
        persen_pelet_terakhir = pelet_sekarang
        # ==========================================

        # --- PENCATAT SEJARAH UNTUK GRAFIK (TIAP 10 MENIT) ---
        if (waktu_terakhir_ping - waktu_simpan_db_terakhir) > 600: 
            sensor_history_collection.insert_one({
                "suhu": suhu_terakhir, 
                "persen_pelet": persen_pelet_terakhir,
                "persen_air": persen_air_terakhir, 
                "sinyal": sinyal_terakhir, # <--- TAMBAHIN INI BIAR HISTORI SINYAL KESIMPEN
                "timestamp": datetime.now()
            })
            waktu_simpan_db_terakhir = waktu_terakhir_ping

        # =============================================================
        # OTAK EKSEKUSI JADWAL (DENGAN REM 10 DETIK)
        # =============================================================
        if (waktu_terakhir_ping - waktu_cek_db_terakhir) > 10:
            waktu_cek_db_terakhir = waktu_terakhir_ping
            sekarang_menit = datetime.now().strftime("%H:%M")

            if status_alat: 
                # 1. CEK JADWAL LAMPU
                config_lampu = settings_collection.find_one({"_id": "config_lampu"})
                if config_lampu and config_lampu.get("mode", "manual") != "manual":
                    lamp_mode = config_lampu.get("mode")
                    on_time = "18:00" if lamp_mode == "auto_night" else config_lampu.get("on_time", "08:00")
                    off_time = "06:00" if lamp_mode == "auto_night" else config_lampu.get("off_time", "16:00")
                    
                    is_on = (on_time <= sekarang_menit < off_time) if on_time < off_time else (sekarang_menit >= on_time or sekarang_menit < off_time)
                    perintah_lampu_web = "NYALAKAN_LAMPU" if is_on else "MATIKAN_LAMPU"

                # 2. CEK JADWAL PAKAN
                if sekarang_menit != menit_pakan_terakhir:
                    jadwal_pakan = schedules_collection.find_one({"time": sekarang_menit, "is_active": True})
                    if jadwal_pakan:
                        perintah_pakan_web = "BERI_PAKAN"
                        menit_pakan_terakhir = sekarang_menit
                        waktu_terakhir_pakan = waktu_terakhir_ping # Trigger animasi Web

        # --- SATPAM PENYAMBUNG WEB KE ALAT ---
        if not status_alat:
            perintah_dikirim = "IDLE"
            perintah_lampu_dikirim = "IDLE"
            perintah_pakan_web = "IDLE" 
            perintah_lampu_web = "IDLE"
        else:
            perintah_dikirim = perintah_pakan_web
            perintah_lampu_dikirim = perintah_lampu_web 
            perintah_pakan_web = "IDLE" 
            
            config_lampu_temp = settings_collection.find_one({"_id": "config_lampu"})
            if config_lampu_temp and config_lampu_temp.get("mode", "manual") == "manual":
                perintah_lampu_web = "IDLE" 

        return jsonify({"status": "berhasil", "perintah_alat": perintah_dikirim, "perintah_lampu": perintah_lampu_dikirim}), 200

# ==========================================
# API UNTUK MENERIMA PERINTAH MANUAL DARI WEB
# ==========================================

@app.route('/api/kontrol-pakan', methods=['POST'])
@login_required
def kontrol_pakan():
    global perintah_pakan_web, waktu_terakhir_pakan

    data = request.get_json()
    if data and data.get('aksi') == 'BERI_PAKAN':
        perintah_pakan_web = "BERI_PAKAN" 
        waktu_terakhir_pakan = time.time() # Biar gak dianggep pencurian!
        return jsonify({"status": "sukses", "pesan": "Perintah pakan diterima server"})
    return jsonify({"status": "gagal"}), 400

# ==========================================
# API UNTUK KONTROL LAMPU MANUAL DARI WEB
# ==========================================
@app.route('/api/kontrol-lampu', methods=['POST'])
@login_required
def kontrol_lampu():
    global perintah_lampu_web

    data = request.get_json()
    if data:
        aksi = data.get('aksi')
        if aksi == 'NYALAKAN_LAMPU':
            perintah_lampu_web = "NYALAKAN_LAMPU"
            print("💡 PERINTAH DITERIMA: NYALAKAN LAMPU!")
            return jsonify({"status": "sukses"})
        elif aksi == 'MATIKAN_LAMPU':
            perintah_lampu_web = "MATIKAN_LAMPU"
            print("💡 PERINTAH DITERIMA: MATIKAN LAMPU!")
            return jsonify({"status": "sukses"})
    
    return jsonify({"status": "gagal"}), 400

# ==========================================
# API UNTUK SIMPAN PENGATURAN LAMPU
# ==========================================
@app.route('/settings/lampu', methods=['POST'])
@login_required
def simpan_pengaturan_lampu():
    lamp_mode = request.form.get('lamp_mode')
    lamp_on_time = request.form.get('lamp_on_time', '08:00')
    lamp_off_time = request.form.get('lamp_off_time', '16:00')

    # Asumsi lu punya collection khusus buat setting, misal 'settings_collection'
    # Kalau belum ada, MongoDB bakal otomatis bikin. Kita pakai ID 'config_lampu'
    settings_collection.update_one(
        {"_id": "config_lampu"},
        {"$set": {
            "mode": lamp_mode,
            "on_time": lamp_on_time,
            "off_time": lamp_off_time,
            "updated_at": datetime.now()
        }},
        upsert=True # Kalau datanya belum ada, bikin baru
    )

    flash('Pengaturan lampu berhasil disimpan!', 'success')
    return redirect(url_for('settings'))

# ==========================================
# API UNTUK AUTO-REFRESH DASHBOARD (AJAX)
# ==========================================

@app.route('/api/get-latest-data')
@login_required
def get_latest_data():
    global suhu_terakhir, persen_pelet_terakhir, persen_air_terakhir, sinyal_terakhir, waktu_terakhir_ping, status_lampu
    global waktu_terakhir_pakan, pesan_anomali # Panggil

    is_online = (time.time() - waktu_terakhir_ping) < 300 if waktu_terakhir_ping > 0 else False
    
    health_score = 100
    if not is_online: health_score = 0
    else:
        if sinyal_terakhir < -85: health_score -= 30
        elif sinyal_terakhir < -70: health_score -= 15
        if suhu_terakhir <= -100: health_score -= 40
    health_score = max(0, min(100, health_score))

    config_lampu = settings_collection.find_one({"_id": "config_lampu"})
    lamp_mode = config_lampu.get("mode", "manual") if config_lampu else "manual"

    # Kirim pesan anomali ke web, lalu HAPUS dari server biar gak spam
    anomali_kirim = pesan_anomali
    pesan_anomali = None 

    return jsonify({
        'temp': round(suhu_terakhir, 1),
        'feed': persen_pelet_terakhir,
        'water_level': persen_air_terakhir,
        'system_health': health_score,
        'is_online': is_online,
        'signal': sinyal_terakhir,
        'status_lampu': status_lampu, 
        'lamp_mode': lamp_mode,
        'is_feeding': (time.time() - waktu_terakhir_pakan) < 5, # Animasi
        'anomali': anomali_kirim # Ngirim anomali
    })

# ==========================================
# API UNTUK MENGAMBIL DATA GRAFIK
# ==========================================
@app.route('/api/chart-data/<tipe>')
@login_required
def get_chart_data(tipe):
    # Ambil 12 data terakhir (kalau 1 data tiap 10 menit, berarti ini data 2 jam terakhir)
    records = list(sensor_history_collection.find().sort("timestamp", -1).limit(12))
    records.reverse() # Balik urutannya biar dari kiri (lama) ke kanan (baru)

    labels = []
    values = []

    for r in records:
        # Format jam jadi "HH:MM" buat label bawah grafik
        labels.append(r['timestamp'].strftime("%H:%M"))
        
        if tipe == 'temp':
            values.append(r.get('suhu', 0))
        elif tipe == 'water':
            values.append(r.get('persen_air', 0))
        elif tipe == 'feed':
            values.append(r.get('persen_pelet', 0))
        elif tipe == 'health': 
            # --- LOGIKA SYSTEM HEALTH UNTUK GRAFIK REAL ---
            health_score = 100
            
            histori_suhu = r.get('suhu', 0)
            # Pakai nilai default -50 (sinyal bagus) agar data lama yang belum punya field 'sinyal' di DB tidak error
            histori_sinyal = r.get('sinyal', -50) 
            
            # Cek Kualitas Sinyal Wi-Fi Historis
            if histori_sinyal < -85:
                health_score -= 30
            elif histori_sinyal < -70:
                health_score -= 15
                
            # Cek Error Sensor Suhu Historis
            if histori_suhu <= -100:
                health_score -= 40
                
            # Kunci nilai biar nggak tembus batas (0-100)
            health_score = max(0, min(100, health_score))
            
            values.append(health_score)

    return jsonify({"labels": labels, "values": values})

# ==========================================
# API UNTUK KONTROL ALAT UTAMA (MASTER SWITCH)
# ==========================================
@app.route('/api/toggle_device', methods=['POST'])
@login_required
def toggle_device():
    global status_alat # Pastikan lu udah deklarasiin variabel ini di atas (status_alat = True)

    data = request.get_json()
    if data is not None and 'is_on' in data:
        status_alat = data['is_on']
        status_text = "MENYALA" if status_alat else "DIMATIKAN"
        print(f"🛑 MASTER SWITCH DIUBAH: Sistem sekarang {status_text}!")
        return jsonify({"status": "success", "is_on": status_alat})
    
    return jsonify({"status": "error"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)