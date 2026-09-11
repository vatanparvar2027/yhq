import os
import time
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatAction

from config import DOWNLOADS_DIR
from services.shazam_service import shazam_service
from services.music_search import music_service
from keyboards.inline_kb import build_search_keyboard
from handlers.start import check_user_subscription
from keyboards.inline_kb import get_channel_sub_keyboard
from config import CHANNELS

logger = logging.getLogger(__name__)
shazam_router = Router()

@shazam_router.message(F.text == "🎙 Shazam (Ovozdan topish)")
async def msg_shazam_info(message: Message):
    text = (
        "🎙 <b>Shazam orqali musiqani topish:</b>\n\n"
        "Menga quyidagilardan birini yuboring:\n"
        "• 🗣 <b>Ovozli xabar</b> (kamida 5-10 soniya musiqani yozib oling);\n"
        "• 🎵 <b>Audio yoki qo'shiq parchasi</b>;\n"
        "• 📹 <b>Video yoki yumaloq video (video-xabar)</b>.\n\n"
        "<i>Guruhlarda esa ovozli xabarga <b>reply (javob)</b> qilib <code>/shazam</code> deb yozishingiz mumkin!</i>"
    )
    await message.answer(text, parse_mode="HTML")

async def process_recognition(message: Message, target_msg: Message):
    """Media faylni yuklab olib, Shazam orqali musiqani aniqlash"""
    user = message.from_user

    # Majburiy obunani faqat shaxsiy chatda tekshiramiz
    if message.chat.type == "private":
        is_subscribed = await check_user_subscription(message.bot, user.id)
        if not is_subscribed:
            await message.answer(
                "Botdan foydalanish uchun kanallarga a'zo bo'ling:",
                reply_markup=get_channel_sub_keyboard(CHANNELS)
            )
            return

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    status_msg = await message.reply("🎧 <i>Musiqa eshitilmoqda va Shazam orqali aniqlanmoqda...</i>", parse_mode="HTML")

    file_obj = target_msg.voice or target_msg.audio or target_msg.video or target_msg.video_note
    if not file_obj:
        await status_msg.edit_text("❌ Aniqlash uchun audio, video yoki ovozli xabar topilmadi.")
        return

    ext = ".ogg" if target_msg.voice else (".mp3" if target_msg.audio else ".mp4")
    temp_input = str(DOWNLOADS_DIR / f"shazam_{user.id}_{int(time.time())}{ext}")

    try:
        # Faylni yuklab olish
        await message.bot.download(file_obj, destination=temp_input)

        # Shazam orqali aniqlash
        result = await shazam_service.recognize_song(temp_input)
        if not result:
            await status_msg.edit_text(
                "😔 <b>Afsuski, ushbu ovozdan musiqa topilmadi.</b>\n\n"
                "💡 <i>Maslahat: Ovozni musiqa baland va shovqin kam bo'lgan joyda kamida 5-10 soniya yozib yuboring.</i>",
                parse_mode="HTML"
            )
            return

        title = result['title']
        artist = result['artist']
        query = result['query']

        await status_msg.edit_text(
            f"🎉 <b>Musiqa topildi!</b>\n\n"
            f"🎵 <b>Nomi:</b> {title}\n"
            f"👤 <b>Ijrochi:</b> {artist}\n\n"
            f"⏳ <i>Yuklab olish variantlari tayyorlanmoqda...</i>",
            parse_mode="HTML"
        )

        # Topilgan nom bo'yicha qidiruv natijalarini olib kelish
        search_results = await music_service.search(query, limit=6)
        if not search_results:
            search_results = await music_service.search(f"{title}", limit=6)

        if search_results:
            await status_msg.edit_text(
                f"🎉 <b>Musiqa topildi!</b>\n\n"
                f"🎵 <b>Nomi:</b> {title}\n"
                f"👤 <b>Ijrochi:</b> {artist}\n\n"
                "Yuklab olish uchun quyidagi tugmani bosing 👇",
                reply_markup=build_search_keyboard(search_results, page=0),
                parse_mode="HTML"
            )
        else:
            await status_msg.edit_text(
                f"🎉 <b>Musiqa topildi:</b> {artist} - {title}\n"
                f"Lekin yuklab olish uchun variantlar topilmadi.",
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Shazam tekshiruvida xatolik: {e}")
        await status_msg.edit_text("❌ Musiqani aniqlashda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
    finally:
        # Fayllarni tozalash
        if os.path.exists(temp_input):
            try:
                os.remove(temp_input)
            except Exception:
                pass

@shazam_router.message(Command(commands=["shazam", "top", "find"]))
async def cmd_shazam(message: Message):
    """Guruhlarda yoki shaxsiy chatda /shazam buyrug'i orqali aniqlash"""
    reply = message.reply_to_message
    if not reply or not (reply.voice or reply.audio or reply.video or reply.video_note):
        await message.reply(
            "🎙 <b>Shazam orqali musiqani aniqlash:</b>\n\n"
            "Ovozli xabar, audio yoki videoga <b>reply (javob)</b> qilib <code>/shazam</code> deb yozing!",
            parse_mode="HTML"
        )
        return
    await process_recognition(message, reply)

@shazam_router.message(F.voice | F.audio | F.video | F.video_note)
async def handle_audio_recognition(message: Message):
    # Agar guruhda bo'lsa, xabarda bot tilga olingan yoki /shazam bo'lsa ishlaydi (spamni oldini olish uchun)
    if message.chat.type in ["group", "supergroup"]:
        caption = (message.caption or "").lower()
        bot_info = await message.bot.get_me()
        bot_mention = f"@{bot_info.username}".lower()
        if "/shazam" not in caption and bot_mention not in caption:
            return

    await process_recognition(message, message)

