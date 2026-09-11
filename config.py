import os
from pathlib import Path
from dotenv import load_dotenv

# .env faylini yuklash (lokal development uchun)
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Asosiy parametrlar
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Adminlar ID ro'yxati
ADMINS_RAW = os.getenv("ADMINS", "").strip()
ADMINS = [int(admin_id.strip()) for admin_id in ADMINS_RAW.split(",") if admin_id.strip().isdigit()]

# Majburiy obuna kanallari ro'yxati
CHANNELS_RAW = os.getenv("CHANNELS", "").strip()
CHANNELS = [ch.strip() for ch in CHANNELS_RAW.split(",") if ch.strip()]

# FFmpeg — serverda (Docker) ffmpeg sistem yo'lida bo'ladi, lokal uchun yo'l aniqlanadi
_default_ffmpeg_local = r"E:\Botlarim\ffmpeg-2026-06-01-git-bf608f16fd-essentials_build\bin"
FFMPEG_PATH = os.getenv("FFMPEG_PATH", _default_ffmpeg_local).strip()

# Agar ko'rsatilgan lokal ffmpeg mavjud bo'lsa PATH ga qo'shamiz, aks holda sistem ffmpeg ishlatiladi
if os.path.isdir(FFMPEG_PATH) and FFMPEG_PATH not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_PATH + os.pathsep + os.environ.get("PATH", "")

# Ma'lumotlar bazasi va vaqtinchalik fayllar papkasi
DATABASE_PATH = BASE_DIR / "bot.db"
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Telegram MTProto (Userbot) sessiyasi — Istoriyalarni yashirincha yuklash uchun
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "2040").strip()) if os.getenv("TELEGRAM_API_ID", "2040").strip().isdigit() else 2040
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "b18441a1ff607e10a989891a5462e627").strip()
TELEGRAM_SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", "").strip()
