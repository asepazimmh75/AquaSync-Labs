# models.py
import os
import certifi
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from flask_login import UserMixin
from bson.objectid import ObjectId
from dotenv import load_dotenv

# Load env variables untuk database
load_dotenv()

uri = os.getenv("MONGODB_URI")
db_name_env = os.getenv("DB_NAME")

if not uri:
    raise ValueError("❌ MONGODB_URI belum diset di file .env!")

try:
    # Tambahkan parameter tlsCAFile=certifi.where() untuk fix error SSL
    client = MongoClient(uri, server_api=ServerApi('1'), tlsCAFile=certifi.where())
    
    # Test ping
    client.admin.command('ping')
    print("✅ Berhasil terhubung ke MongoDB Atlas!")
except Exception as e:
    print(f"❌ Gagal konek MongoDB: {e}")

# Definisi Database & Collection
db = client[db_name_env]
users_collection = db['users']
schedules_collection = db['schedules']
settings_collection = db['settings'] # <--- NAH INI JAGOAN BARUNYA KITA TARUH SINI
sensor_history_collection = db['sensor_history'] # <--- TAMBAHIN INI BOS

# --- USER CLASS WRAPPER ---
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id']) # ObjectId harus jadi string buat Flask-Login
        self.username = user_data['username']
        self.email = user_data['email']
        self.password = user_data['password']
        self.is_verified = user_data.get('is_verified', False)
        # Data OTP (optional get)
        self.otp_hash = user_data.get('otp_hash')
        self.otp_expiry = user_data.get('otp_expiry')
        self.verification_token = user_data.get('verification_token')
        self.token_expiry = user_data.get('token_expiry')