# 🎵 CHIROQCHIMUZ - Telegram Musiqa Boti

Har qanday musiqani nomi, ijrochisi, ovozli xabari (Shazam) yoki havolasi orqali topib beruvchi zamonaviy va tezkor Telegram bot.

---

## 🚀 Asosiy Imkoniyatlar

- **🔍 Matn orqali qidiruv**: Istalgan qo'shiq nomi yoki ijrochisini yozing (masalan: `Janob Rasul`, `Konsta O'zbekiston`, `Eminem`) va bot eng yaxshi 10 ta variantni taqdim etadi.
- **🎙 Shazam (Ovozdan topish)**: Botga ovozli xabar (voice), qo'shiq parchasi yoki video yuboring — bot 1-2 soniyada musiqani aniqlaydi va yuklab beradi.
- **🔗 Havolalardan yuklash**: YouTube, YouTube Shorts, SoundCloud, Instagram Reels havolasini yuboring va darhol MP3 formatda oling.
- **⚡️ Kesh tizimi (Instant Caching)**: Bir marta yuklangan qo'shiq keyingi safar 0.1 soniyada darhol Telegramdan yetkazib beriladi.
- **🌐 Inline rejim**: Istalgan guruh yoki chatda `@bot_username qo'shiq_nomi` deb yozib, to'g'ridan-to'g'ri musiqa yuborishingiz mumkin.
- **👑 Admin Panel**: `/admin` buyrug'i orqali statistika (foydalanuvchilar soni, keshdagi qo'shiqlar) va barcha foydalanuvchilarga xabar tarqatish (broadcast).
- **📢 Majburiy obuna**: Botdan foydalanish uchun homiy kanallarni sozlash imkoniyati.

---

## 🛠 O'rnatish va Sozlash

### 1. Bot Token olish
1. Telegramda [@BotFather](https://t.me/BotFather) botiga kiring.
2. `/newbot` buyrug'ini yuboring va ko'rsatmalarga amal qilib bot yarating.
3. Bot yaratilgach, sizga berilgan **API Token**ni nusxalab oling.
4. [@BotFather](https://t.me/BotFather) da `/setinline` buyrug'ini yuboring va botingizni tanlab, unga inline rejimini yoqing (placeholder matn: `Musiqa qidirish...`).

### 2. Sozlamalarni kiritish
Loyiha papkasidagi `.env` faylini oching va tokenni yozing:
```env
BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxx
ADMINS=123456789
FFMPEG_PATH=E:\Botlarim\ffmpeg-2026-06-01-git-bf608f16fd-essentials_build\bin
CHANNELS=
```

### 3. Ishga tushirish
Windowsda botni ishga tushirish uchun shunchaki **`run_bot.bat`** faylini sichqoncha bilan ikki marta bosing!
Yoki terminalda:
```powershell
python main.py
```

---

## 📂 Loyiha Tuzilmasi

- `main.py` — Botni ishga tushiruvchi markaziy fayl
- `config.py` — Konfiguratsiya va tizim sozlamalari
- `database/` — Asinxron SQLite ma'lumotlar bazasi (foydalanuvchilar va musiqa keshi)
- `services/`
  - `music_search.py` — `yt-dlp` orqali tezkor qidiruv va yuklab olish
  - `shazam_service.py` — `shazamio` orqali musiqani aniqlash
  - `audio_tagger.py` — `mutagen` orqali MP3 teglarini sozlash
- `handlers/`
  - `start.py` — `/start`, `/help` va chuqur havolalar
  - `search.py` — Matnli qidiruv va yuklash
  - `shazam.py` — Voice, audio va videodan musiqani topish
  - `inline.py` — Inline rejim
  - `admin.py` — Admin panel va statistika
- `keyboards/` — Chiroyli inline va reply menyular
