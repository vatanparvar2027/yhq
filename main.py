import os
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database.db import db
from handlers.start import start_router
from handlers.admin import admin_router
from handlers.shazam import shazam_router
from handlers.inline import inline_router
from handlers.story import story_router
from handlers.search import search_router

# Windows konsolida Unicode/Emoji xatoliklarini oldini olish
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Logging sozlamasi
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    if not BOT_TOKEN or "YOUR_BOT_TOKEN_HERE" in BOT_TOKEN or "ExampleToken" in BOT_TOKEN:
        logger.error(
            "\n" + "="*60 + "\n"
            "❌ DIQQAT: .env faylida BOT_TOKEN ko'rsatilmagan!\n"
            "Iltimos, .env faylini oching va @BotFather dan olgan tokenni yozing.\n"
            "Misol: BOT_TOKEN=7123456789:AAH... \n" + "="*60
        )
        return

    logger.info("Bot ishga tushirilmoqda...")

    # Ma'lumotlar bazasini ishga tushirish
    await db.init_db()
    logger.info("Ma'lumotlar bazasi (SQLite) tayyorlandi.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Handler routerlarini ro'yxatdan o'tkazish
    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(shazam_router)
    dp.include_router(inline_router)
    dp.include_router(story_router)
    dp.include_router(search_router)

    # Render / Koyeb Web Service port listener (Health Check)
    port = int(os.environ.get("PORT", 0))
    if port > 0:
        try:
            from aiohttp import web
            async def health_check(request):
                return web.Response(text="OK - @ChiroqchiMuzbot is active!")
            app = web.Application()
            app.router.add_get("/", health_check)
            app.router.add_get("/health", health_check)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            logger.info(f"Render/Koyeb web server port {port} da ishga tushirildi.")
        except Exception as e:
            logger.warning(f"Web server ishga tushirishda xatolik: {e}")

    # Eski kutilmagan xabarlarni tozalash va polling boshlash
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot muvaffaqiyatli ishga tushdi: @{bot_info.username} ({bot_info.first_name})")

        # Telegram profil bio va tavsifini avtomatik chiroyli qilib sozlash
        try:
            await bot.set_my_description(
                description=(
                    "🎵 CHIROQCHIMUZ — Har qanday musiqani yashin tezligida topuvchi bot!\n\n"
                    "⚡️ Imkoniyatlar:\n"
                    "• 🔍 Musiqa nomi yoki ijrochisi bo'yicha qidiruv\n"
                    "• 🎙 Ovozli xabar (voice) orqali musiqani topish (Shazam)\n"
                    "• 🔗 YouTube, TikTok, Instagram havolalaridan yuklash\n"
                    "• 🔝 Eng sara trend va xit musiqalar\n"
                    "• ⚡️ 0.1 soniyada tezkor keshdan yuborish!\n\n"
                    "👇 Boshlash uchun Start tugmasini bosing!"
                )
            )
            await bot.set_my_short_description(
                short_description="🎵 Har qanday musiqani yashin tezligida topuvchi bot! 🎙 Shazam | 🔍 Qidiruv | ⚡️ 0.1s"
            )
            logger.info("Bot bio va tavsifi muvaffaqiyatli o'rnatildi.")
        except Exception as e:
            logger.warning(f"Bio o'rnatishda xatolik: {e}")

        print("\n" + "="*50)
        print(f"🎵 Bot faol: @{bot_info.username}")
        print("Musiqa qidirish, Shazam va yuklash tizimlari tayyor!")
        print("="*50 + "\n")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
