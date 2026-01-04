from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import secrets
import smtplib
import os

load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = 'kuncirahasia123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///aquasync.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def send_verification_email(user_email, token):
    sender_email = os.getenv("GMAIL_EMAIL")  # GANTI DENGAN EMAIL KAMU
    sender_password = os.getenv("GMAIL_APP_PASSWORD") # GANTI DENGAN APP PASSWORD GMAIL (16 digit)
    
    # Membuat Link Verifikasi (Sesuaikan port jika bukan 5000)
    verify_url = url_for('verify_email', token=token, _external=True)
    
    subject = "Verifikasi Akun AquaSync"
    body = f"""
    <h2>Halo!</h2>
    <p>Terima kasih telah mendaftar di AquaSync.</p>
    <p>Silakan klik link di bawah ini untuk mengaktifkan akun Anda:</p>
    <a href="{verify_url}" style="background-color: #3B82F6; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Verifikasi Email Saya</a>
    <p>Link ini akan kadaluarsa dalam 24 jam.</p>
    <br>
    <p>Jika Anda tidak merasa mendaftar, abaikan email ini.</p>
    """

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = user_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))

    try:
        # Setup Server SMTP Gmail
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() # Enkripsi koneksi
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, user_email, msg.as_string())
        server.quit()
        print(f"Email verifikasi dikirim ke {user_email}")
        return True
    except Exception as e:
        print(f"Gagal kirim email: {e}")
        return False

# --- MODEL USER (Tetap) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# --- KOLOM TAMBAHAN UNTUK VERIFIKASI ---
    is_verified = db.Column(db.Boolean, default=False) # Status akun
    verification_token = db.Column(db.String(100), unique=True, nullable=True) # Token unik
    token_expiry = db.Column(db.DateTime, nullable=True) # Batas waktu token

# --- MODEL BARU: SCHEDULE (Jadwal Pakan) ---
class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    time = db.Column(db.String(10), nullable=False) # Format "HH:MM"
    is_active = db.Column(db.Boolean, default=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id')) # Relasi ke User

# Buat tabel baru (jalankan sekali saja nanti)
with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTES LAMA (Login/Register) Tetap Sama... --- 
# (Copy paste route login/register yang sebelumnya di sini, saya skip biar tidak kepanjangan)
# ...

@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):

            # --- CEK STATUS VERIFIKASI EMAIL ---
            if not user.is_verified:
                flash('Akun belum diverifikasi. Cek inbox email Anda.', 'warning')
                return render_template('login.html')
            # ----------------------------------

            login_user(user)
            return redirect(url_for('dashboard'))

        else:
            flash('Email atau password salah!', 'error')

    return render_template('login.html')


# Di dalam file app.py, cari route @app.route('/register' ...)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        quiz_answer = request.form.get('quiz_answer')

        # --- VALIDASI QUIZ ---
        if quiz_answer != 'correct':
            flash('Jawaban keamanan salah! Anda tidak dapat mendaftar.', 'error')
            return redirect(url_for('register'))

        # --- CEK EMAIL ---
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('Email sudah terdaftar!', 'error')
            return redirect(url_for('register'))

        # --- GENERATE TOKEN & EXPIRY ---
        token = secrets.token_urlsafe(32)
        expiry_time = datetime.now() + timedelta(hours=24)

        # --- BUAT USER (BELUM TERVERIFIKASI) ---
        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password, method='scrypt'),
            is_verified=False,
            verification_token=token,
            token_expiry=expiry_time
        )

        db.session.add(new_user)
        db.session.commit()

        # --- KIRIM EMAIL VERIFIKASI ---
        if send_verification_email(email, token):
            flash('Registrasi berhasil! Cek email untuk verifikasi akun.', 'success')
        else:
            flash('Registrasi berhasil, tapi email verifikasi gagal dikirim.', 'warning')

        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/verify/<token>')
def verify_email(token):
    # 1. Cari user berdasarkan token
    user = User.query.filter_by(verification_token=token).first()
    
    # 2. Validasi: Apakah user ada?
    if not user:
        flash('Token verifikasi tidak valid atau sudah digunakan.', 'error')
        return redirect(url_for('login'))
    
    # 3. Validasi: Apakah token sudah kadaluarsa?
    if user.token_expiry < datetime.now():
        flash('Token verifikasi sudah kadaluarsa. Silakan daftar ulang.', 'error')
        # Opsional: Hapus user agar bisa daftar lagi dengan email sama
        db.session.delete(user) 
        db.session.commit()
        return redirect(url_for('register'))
    
    # 4. SUKSES: Aktifkan akun
    user.is_verified = True
    user.verification_token = None # Hapus token agar tidak bisa dipakai 2x
    user.token_expiry = None
    db.session.commit()
    
    flash('Email berhasil diverifikasi! Silakan login.', 'success')
    return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- ROUTES UTAMA ---

@app.route('/dashboard')
@login_required
def dashboard():
    # Data dummy (nanti diganti data sensor asli)
    data_sensor = {'temp': 26.5, 'feed': 145, 'feed_trend': -12, 'water_level': 85, 'system_health': 98}
    return render_template('dashboard.html', user=current_user, data=data_sensor, page='dashboard')

# --- ROUTES BARU: SETTINGS & GUIDE ---

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        time_input = request.form.get('feed_time')
        if time_input:
            # Simpan jadwal baru ke database
            new_schedule = Schedule(time=time_input, user_id=current_user.id)
            db.session.add(new_schedule)
            db.session.commit()
            flash('Jadwal pakan berhasil ditambahkan!', 'success')
        else:
            flash('Waktu tidak boleh kosong', 'error')
        return redirect(url_for('settings'))

    # Ambil semua jadwal milik user ini
    schedules = Schedule.query.filter_by(user_id=current_user.id).order_by(Schedule.time).all()
    return render_template('settings.html', user=current_user, schedules=schedules, page='settings')

@app.route('/delete_schedule/<int:id>')
@login_required
def delete_schedule(id):
    schedule = Schedule.query.get_or_404(id)
    if schedule.user_id == current_user.id:
        db.session.delete(schedule)
        db.session.commit()
        flash('Jadwal dihapus.', 'success')
    return redirect(url_for('settings'))

@app.route('/guide')
@login_required
def guide():
    return render_template('guide.html', user=current_user, page='guide')

if __name__ == '__main__':
    app.run(debug=True)