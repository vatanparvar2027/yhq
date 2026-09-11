"""
Telegram Stories uchun Userbot sessiya kalitini (SESSION_STRING) yaratish skripti.
Ishga tushirish: python scripts/generate_session.py
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# Standart Telegram API ma'lumotlari (yoki my.telegram.org dan olingan)
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

async def main():
    print("=" * 60)
    print("📸 Telegram Yashirin Istoriya Yuklovchi (Session Generator)")
    print("=" * 60)
    print("Ushbu skript yordamchi hisobingiz uchun SESSION_STRING yaratadi.")
    print("Telefon raqamingizni xalqaro formatda kiriting (masalan: +998901234567)\n")

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start()

    session_str = client.session.save()
    print("\n" + "=" * 60)
    print("✅ MUVAFFAQITYATLI YARATILDI!")
    print("=" * 60)
    print("\nQuyidagi qatorni nusxalab oling va .env faylingizga qo'ying:\n")
    print(f"TELEGRAM_SESSION_STRING={session_str}")
    print("\n" + "=" * 60)
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
