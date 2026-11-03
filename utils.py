# utils.py
import random
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def generate_otp():
    return str(random.randint(100000, 999999))

def send_email_general(to_email, subject, body_html):
    sender_email = os.getenv("GMAIL_EMAIL") # Pastikan ada di .env
    sender_password = os.getenv("GMAIL_APP_PASSWORD") # Pastikan ada di .env

    if not sender_email or not sender_password:
        print("⚠️ ENV GMAIL belum di-set!")
        return False

    msg = MIMEMultipart()
    msg['From'] = f"AquaSync Team <{sender_email}>"
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body_html, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Gagal kirim email: {e}")
        return False