import os
import re
import time
import logging
from typing import Optional, Any
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, FSInputFile
from aiogram.enums import ChatAction

from services.story_service import story_service
from database.db import db
from config import ADMINS

logger = logging.getLogger(__name__)
story_router = Router()

USERNAME_REGEX = re.compile(r'^@([a-zA-Z0-9_]{4,32})$')
STORY_URL_REGEX = re.compile(r'(?:https?://)?t\.me/([a-zA-Z0-9_]{4,32})(?:/s/\d+)?', re.IGNORECASE)

async def _process_stories_download(message: Message, target: Any, display_name: str):
    """Istoriyalarni yashirincha yuklab, foydalanuvchiga ketma-ket taqdim etish"""
    # 1. Sessiya ulanganligini tekshirish
    if not story_service.is_configured():
        is_admin = message.from_user.id in ADMINS
        admin_hint = (
            "\n\n👑 <b>Administrator uchun:</b>\n"
            "Serverda <code>python scripts/generate_session.py</code> buyrug'ini ishga tushiring va "
            "olingan sessiya kalitini <code>.env</code> faylidagi <code>TELEGRAM_SESSION_STRING</code> ga yozing."
        ) if is_admin else ""

        await message.reply(
            "🔒 <b>Yashirin Istoriya Xizmati Sozlanmoqda</b>\n\n"
            "Telegram xavfsizlik qoidalariga ko'ra, rasmiy botlar boshqa shaxslarning profil istoriyalarini to'g'ridan-to'g'ri ko'ra olmaydi.\n\n"
            "Ushbu funksiya to'liq <b>100% yashirin (anonim)</b> ishlashi uchun maxsus MTProto Userbot sessiyasi ulanishi zarur."
            f"{admin_hint}",
            parse_mode="HTML"
        )
        return

    status_msg = await message.reply(
        f"🕵️‍♂️ <b>«{display_name}»</b> ning barcha istoriyalari yashirincha qidirilmoqda...\n"
        "<i>Egasiga hech qanday bildirishnoma bormaydi (100% anonim).</i>",
        parse_mode="HTML"
    )
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    # 2. Istoriyalarni olish (ReadStories chaqirilmaydi!)
    stories = await story_service.fetch_user_stories(target)

    if stories is None:
        await status_msg.edit_text(
            f"❌ <b>«{display_name}»</b> ning istoriyalarini olish imkoni bo'lmadi.\n"
            "<i>Sababi: profil mavjud emas, yopiq (private) yoki bot uni topa olmadi.</i>",
            parse_mode="HTML"
        )
        return

    if not stories:
        await status_msg.edit_text(
            f"😔 <b>«{display_name}»</b> da ayni paytda faol istoriyalar mavjud emas.",
            parse_mode="HTML"
        )
        return

    total = len(stories)
    await status_msg.edit_text(
        f"🎉 <b>«{display_name}»</b> profilida <b>{total} ta</b> istoriya topildi!\n"
        f"⚡️ Boshidan oxirigacha yuklab yuborilmoqda...",
        parse_mode="HTML"
    )

    # 3. Har bir istoriyani tartib bilan yuklab yuborish
    for i, s in enumerate(stories, start=1):
        await message.bot.send_chat_action(
            message.chat.id,
            ChatAction.UPLOAD_VIDEO if s['is_video'] else ChatAction.UPLOAD_PHOTO
        )

        ext = "mp4" if s['is_video'] else "jpg"
        temp_filename = f"story_{message.from_user.id}_{s['id']}_{int(time.time())}.{ext}"

        file_path = await story_service.download_story_media(s['story_obj'], temp_filename)
        if not file_path or not os.path.exists(file_path):
            continue

        caption_text = f"\n📝 <i>{s['caption']}</i>" if s.get('caption') else ""
        date_str = s['date'].strftime("%Y-%m-%d %H:%M") if s.get('date') else ""

        caption = (
            f"📸 <b>Istoriya: {i}/{total}</b>\n"
            f"👤 Profil: <b>{display_name}</b>\n"
            f"⏱ Joylangan: <b>{date_str}</b>"
            f"{caption_text}\n\n"
            f"🕵️‍♂️ <i>Yashirincha yuklandi (ko'rildi belgisi bormadi)</i>\n"
            f"🤖 @ChiroqchiMuzbot"
        )

        try:
            input_file = FSInputFile(file_path)
            if s['is_video']:
                await message.answer_video(
                    video=input_file,
                    caption=caption,
                    parse_mode="HTML"
                )
            else:
                await message.answer_photo(
                    photo=input_file,
                    caption=caption,
                    parse_mode="HTML"
                )
        except Exception as send_err:
            logger.error(f"Istoriyani yuborishda xatolik: {send_err}")
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass

    await status_msg.delete()

@story_router.message(F.text == "📸 Istoriya yuklash")
async def msg_story_prompt(message: Message):
    """Istoriya yuklash tugmasi bosilganda qulay qo'llanma"""
    await message.answer(
        "📸 <b>Telegram Istoriyalarini Yashirincha Yuklab Olish:</b>\n\n"
        "Istalgan odamning profilidagi barcha faol istoriyalarni <b>egasiga bildirmasdan (100% anonim)</b> boshidan oxirigacha yuklab olishingiz mumkin.\n\n"
        "👇 <b>Quyidagilardan birini yuboring:</b>\n"
        "1️⃣ Istalgan <b>Kontakt</b> (Telegram kontakt ulashish kartasi)\n"
        "2️⃣ Profil <b>@username</b>i (masalan: <code>@durov</code>)\n"
        "3️⃣ Yoki istoriya havolasi (<code>https://t.me/username/s/1</code>)\n\n"
        "<i>💡 Eslatma: Istoriya egasining «Ko'rganlar» ro'yxatida sizning profilingiz umuman ko'rinmaydi!</i>",
        parse_mode="HTML"
    )

@story_router.message(Command(commands=["story", "istoriya", "stories"]))
async def cmd_story(message: Message, command: CommandObject):
    """Buyruq orqali istoriya yuklash: /story @username"""
    query = command.args
    if not query:
        await message.reply(
            "📸 <b>Foydalanuvchi @username yoki kontaktini yuboring:</b>\n"
            "<i>Masalan: <code>/story @durov</code></i>",
            parse_mode="HTML"
        )
        return

    clean_u = query.strip().lstrip("@")
    await _process_stories_download(message, clean_u, f"@{clean_u}")

@story_router.message(F.contact)
async def handle_contact_story(message: Message):
    """Foydalanuvchi kontakt kartasi yuborganda uning barcha istoriyalarini olish"""
    contact = message.contact
    display_name = contact.first_name
    if contact.last_name:
        display_name += f" {contact.last_name}"

    # Target sifatida user_id yoki phone_number beriladi
    target = contact.user_id if contact.user_id else contact.phone_number
    await _process_stories_download(message, target, display_name)

@story_router.message(F.text.regexp(r'^@[a-zA-Z0-9_]{4,32}$'))
async def handle_username_story(message: Message):
    """Foydalanuvchi to'g'ridan-to'g'ri @username yuborganda uning istoriyalarini tekshirish"""
    username = message.text.strip().lstrip("@")
    await _process_stories_download(message, username, f"@{username}")
