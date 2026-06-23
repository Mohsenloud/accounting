"""
ماژول رمزنگاری دیتابیس SQLite با استفاده از AES-GCM
"""
import os
import hashlib
import shutil
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# پسوند فایل رمزنگاری شده
ENCRYPTED_EXT = '.enc'
DB_FILE = 'accounting.db'
ENCRYPTED_FILE = DB_FILE + ENCRYPTED_EXT


def _derive_key(password: str) -> bytes:
    """تولید کلید 32 بایتی از رمز عبور"""
    return hashlib.sha256(password.encode('utf-8')).digest()


def encrypt_file(filepath: str, password: str) -> bool:
    """
    رمزنگاری یک فایل با AES-GCM
    فایل خروجی: filepath.enc
    """
    try:
        if not os.path.exists(filepath):
            return False
        
        with open(filepath, 'rb') as f:
            plaintext = f.read()
        
        key = _derive_key(password)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # 96-bit nonce
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        # ذخیره: nonce (12 بایت) + ciphertext
        enc_path = filepath + ENCRYPTED_EXT
        with open(enc_path, 'wb') as f:
            f.write(nonce + ciphertext)
        
        return True
    except Exception as e:
        print(f"خطا در رمزنگاری: {e}")
        return False


def decrypt_file(enc_filepath: str, password: str) -> bool:
    """
    رمزگشایی یک فایل رمزنگاری شده
    خروجی: فایل اصلی (بدون .enc)
    """
    try:
        if not os.path.exists(enc_filepath):
            return False
        
        with open(enc_filepath, 'rb') as f:
            data = f.read()
        
        key = _derive_key(password)
        nonce = data[:12]
        ciphertext = data[12:]
        
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        
        # ذخیره فایل رمزگشایی شده
        out_path = enc_filepath.replace(ENCRYPTED_EXT, '')
        with open(out_path, 'wb') as f:
            f.write(plaintext)
        
        return True
    except Exception as e:
        print(f"خطا در رمزگشایی: {e}")
        return False


def setup_encrypted_db(password: str):
    """
    تنظیم دیتابیس رمزنگاری شده.
    اگر فایل رمزنگاری شده وجود داشته باشد، رمزگشایی می‌شود.
    اگر فایل عادی وجود داشته باشد، رمزنگاری می‌شود.
    """
    enc_exists = os.path.exists(ENCRYPTED_FILE)
    db_exists = os.path.exists(DB_FILE)
    
    if enc_exists:
        # رمزگشایی فایل رمزنگاری شده
        if not decrypt_file(ENCRYPTED_FILE, password):
            raise Exception("خطا در رمزگشایی دیتابیس. رمز عبور اشتباه است.")
    
    # رمزگشایی دیتابیس فعلی
    re_encrypt_on_exit = True


def save_encrypted_db(password: str):
    """رمزنگاری و ذخیره دیتابیس"""
    if os.path.exists(DB_FILE):
        encrypt_file(DB_FILE, password)


class EncryptedDBManager:
    """مدیریت رمزنگاری دیتابیس"""
    
    def __init__(self, password: str):
        self.password = password
        self.original_db = DB_FILE
        self.encrypted_db = ENCRYPTED_FILE
    
    def decrypt(self) -> bool:
        """رمزگشایی دیتابیس هنگام شروع برنامه"""
        if os.path.exists(self.encrypted_db):
            return decrypt_file(self.encrypted_db, self.password)
        return True
    
    def encrypt(self) -> bool:
        """رمزنگاری دیتابیس هنگام تغییرات"""
        if os.path.exists(self.original_db):
            return encrypt_file(self.original_db, self.password)
        return False
    
    def get_db_path(self) -> str:
        """مسیر فایل دیتابیس"""
        return self.original_db