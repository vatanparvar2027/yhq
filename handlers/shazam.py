import os
import time
import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatAction
from urllib.parse import quote

from config import DOWNLOADS_DIR
from database.db import db
from services.shazam_service import shazam_service
from services.music_search import music_service, format_duration
from keyboards.inline_kb import build_search_keyboard, get_channel_sub_keyboard
from handlers.start import check_user_subscription, get_all_active_channels

logger = logging.getLogger(__name__)
shazam_router = Router()

# Shazam topgan qidiruv variantlari keshi (boshqa variantlarni ko'rish uchun)
SHAZAM_SEARCH_CACHE = {}

def get_shazam_audio_keyboard(video_id: str, title: str, query: str) -> InlineKeyboardMarkup:
    """Shazam orqali yuborilgan audio ostidagi qulay tugmalar"""
    clean_t = title.replace("\n", " ").strip()[:60]
    share_text = quote(f"🎧 {clean_t}\n\n🤖 @ChiroqchiMuzbot — Har qanday musiqani Shazam orqali tezkor topuvchi bot!")
    share_url = quote(f"https://t.me/ChiroqchiMuzbot?start=dl_{video_id}")
    share_link = f"https://t.me/share/url?url={share_url}&text={share_text}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔀 Boshqa variantlar", callback_data=f"shazam_more:{video_id}"),
            InlineKeyboardButton(text="🎬 Video klip", callback_data=f"dl_as_video:{video_id}")
        ],
        [
            InlineKeyboardButton(text="📤 Do'stlarga ulashish", url=share_link),
            InlineKeyboardButton(text="❤️ Sevimlilar", callback_data=f"fav:{video_id}")
        ]
    ])

@shazam_router.message(F.text == "🎙 Shazam (Ovozdan topish)")
async def msg_shazam_info(message: Message):
    text = (
        "🎙 <b>Shazam orqali musiqani yashin tezligida topish:</b>\n\n"
        "Menga quyidagilardan birini yuboring:\n"
        "• 🗣 <b>Ovozli xabar</b> (musiqani 5-10 soniya yozib yuboring);\n"
        "• 🎵 <b>Audio yoki qo'shiq parchasi</b>;\n"
        "• 📹 <b>Video yoki yumaloq video (video-xabar)</b>.\n\n"
        "<i>⚡️ Bot musiqani darhol aniqlab, to'liq MP3 qo'shiqni va muqovasini tayyorlab beradi!</i>\n"
        "<i>👥 Guruhlarda esa ovozli xabarga <b>reply (javob)</b> qilib <code>/shazam</code> deb yozishingiz mumkin!</i>"
    )
    await message.answer(text, parse_mode="HTML")

async def process_recognition(message: Message, target_msg: Message):
    """Media faylni yuklab olib, Shazam orqali aniqlash va darhol to'liq MP3 yuborish"""
    user = message.from_user

    # Majburiy obunani faqat shaxsiy chatda tekshiramiz
    if message.chat.type == "private":
        is_subscribed = await check_user_subscription(message.bot, user.id)
        if not is_subscribed:
            all_channels = await get_all_active_channels()
            await message.answer(
                f"👋 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
                "Musiqani Shazam orqali aniqlash va yuklab olish uchun quyidagi kanallarga a'zo bo'ling:",
                reply_markup=get_channel_sub_keyboard(all_channels),
                parse_mode="HTML"
            )
            return

    await message.bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)
    status_msg = await message.reply("🎧 <i>Musiqa eshitilmoqda va Shazam orqali aniqlanmoqda...</i>", parse_mode="HTML")

    file_obj = target_msg.voice or target_msg.audio or target_msg.video or target_msg.video_note
    if not file_obj:
        await status_msg.edit_text("❌ Aniqlash uchun audio, video yoki ovozli xabar topilmadi.")
        return

    ext = ".ogg" if target_msg.voice else (".mp3" if target_msg.audio else ".mp4")
    temp_input = str(DOWNLOADS_DIR / f"shazam_raw_{user.id}_{int(time.time() * 1000)}{ext}")

    try:
        # Faylni yuklab olish
        await message.bot.download(file_obj, destination=temp_input)

        # Shazam orqali aniqlash
        result = await shazam_service.recognize_song(temp_input)
        if not result:
            await status_msg.edit_text(
                "😔 <b>Afsuski, ushbu ovozdan musiqa topilmadi.</b>\n\n"
                "💡 <i>Maslahat: Musiqani shovqinsizroq joyda yoki ovoz balandroq qilib kamida 5-10 soniya yozib yuboring.</i>",
                parse_mode="HTML"
            )
            return

        title = result['title']
        artist = result['artist']
        query = result['query']
        cover_url = result.get('cover')
        genre = result.get('genre', 'Musiqa')

        await status_msg.edit_text(
            f"🎉 <b>Musiqa topildi!</b>\n\n"
            f"🎵 <b>Nomi:</b> {title}\n"
            f"👤 <b>Ijrochi:</b> {artist}\n"
            f"🎭 <b>Janr:</b> {genre}\n\n"
            f"⚡️ <i>To'liq MP3 musiqa yuklab olinmoqda va tayyorlanmoqda...</i>",
            parse_mode="HTML"
        )
        await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VOICE)

        # Topilgan nom bo'yicha qidiruv natijalarini olib kelamiz
        search_results = await music_service.search(query, limit=10)
        if not search_results:
            search_results = await music_service.search(f"{artist} {title}", limit=10)

        # Keshga saqlab qo'yamiz (keyinchalik foydalanuvchi "Boshqa variantlar"ni bossa)
        target_video_id = search_results[0]['id'] if search_results else f"yt_{int(time.time())}"
        SHAZAM_SEARCH_CACHE[target_video_id] = {
            "query": query,
            "results": search_results,
            "time": time.time()
        }

        # 1. Avval bazadagi keshdan tekshiramiz (agar oldin yuklangan bo'lsa - 0ms da beradi)
        cached = await db.get_cached_music(target_video_id)
        if cached:
            dur = cached.get('duration') or 0
            caption = (
                f"🎧 <b>{cached.get('title', title)}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Ijrochi:</b> {artist}\n"
                f"⏱ <b>Davomiyligi:</b> {format_duration(dur)}\n"
                f"🎙 <b>Topildi:</b> Shazam orqali\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 <b>Kanal / Bot:</b> @ChiroqchiMuzbot"
            )
            bot_logo = "bot_avatar.jpg" if os.path.exists("bot_avatar.jpg") else None
            thumb_file = FSInputFile(bot_logo) if bot_logo else None

            await message.bot.send_audio(
                chat_id=message.chat.id,
                audio=cached['file_id'],
                title=cached.get('title'),
                performer=artist,
                duration=dur,
                thumbnail=thumb_file,
                caption=caption,
                reply_markup=get_shazam_audio_keyboard(target_video_id, cached.get('title', title), query),
                parse_mode="HTML"
            )
            await status_msg.delete()
            return

        # 2. Keshda bo'lmasa, DARHOL MP3 ni eng yuqori sifatda yuklab olamiz
        output_name = f"shazam_dl_{user.id}_{int(time.time())}"
        audio_data = await music_service.download_by_query(
            query=f"{artist} - {title}",
            output_id=output_name,
            cover_url=cover_url
        )

        if not audio_data:
            # Agar query bo'yicha bo'lmasa, faqat title bilan urinib ko'ramiz
            audio_data = await music_service.download_by_query(
                query=title,
                output_id=output_name,
                cover_url=cover_url
            )

        if audio_data and os.path.exists(audio_data['file_path']):
            audio_file = FSInputFile(audio_data['file_path'])
            cover_file = FSInputFile(audio_data['cover_path']) if audio_data.get('cover_path') and os.path.exists(audio_data['cover_path']) else None
            actual_dur = audio_data.get('duration') or 0

            caption = (
                f"🎧 <b>{audio_data['title']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Ijrochi:</b> {artist}\n"
                f"⏱ <b>Davomiyligi:</b> {format_duration(actual_dur)}\n"
                f"🎵 <b>Sifati:</b> 320/192 kbps (HQ Audio)\n"
                f"🎙 <b>Topildi:</b> Shazam orqali\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 <b>Kanal / Bot:</b> @ChiroqchiMuzbot"
            )

            sent_msg = await message.bot.send_audio(
                chat_id=message.chat.id,
                audio=audio_file,
                title=audio_data['title'],
                performer=artist,
                duration=actual_dur,
                thumbnail=cover_file,
                caption=caption,
                reply_markup=get_shazam_audio_keyboard(audio_data.get('id', target_video_id), audio_data['title'], query),
                parse_mode="HTML"
            )

            # Bazaga saqlaymiz
            await db.save_music_cache(
                video_id=audio_data.get('id', target_video_id),
                file_id=sent_msg.audio.file_id,
                title=audio_data['title'],
                performer=artist,
                duration=actual_dur
            )

            await status_msg.delete()
        else:
            # Agar avtomatik yuklashda xatolik bo'lsa, qidiruv variantlari tugmasini chiqaramiz
            if search_results:
                await status_msg.edit_text(
                    f"🎉 <b>Musiqa topildi!</b>\n\n"
                    f"🎵 <b>Nomi:</b> {title}\n"
                    f"👤 <b>Ijrochi:</b> {artist}\n\n"
                    "Yuklab olish uchun quyidagi variantlardan birini tanlang 👇",
                    reply_markup=build_search_keyboard(search_results, page=0),
                    parse_mode="HTML"
                )
            else:
                await status_msg.edit_text(
                    f"🎉 <b>Musiqa topildi:</b> {artist} — {title}\n"
                    f"Lekin yuklab olish uchun variant topilmadi.",
                    parse_mode="HTML"
                )

    except Exception as e:
        logger.error(f"Shazam jarayonida xatolik: {e}")
        await status_msg.edit_text("❌ Musiqani aniqlash yoki yuklashda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
    finally:
        # Vaqtinchalik fayllarni tozalash
        if os.path.exists(temp_input):
            try:
                os.remove(temp_input)
            except Exception:
                pass

@shazam_router.callback_query(F.data.startswith("shazam_more:"))
async def cb_shazam_more(call: CallbackQuery):
    """Shazam topgan musiqaning boshqa ijro/remiks variantlarini ko'rsatish"""
    video_id = call.data.split(":", 1)[1]
    cached_item = SHAZAM_SEARCH_CACHE.get(video_id)
    if not cached_item or not cached_item.get("results"):
        await call.answer("🔍 Boshqa variantlar qidirilmoqda...", show_alert=False)
        return

    await call.answer()
    from handlers.search import format_search_message, USER_SEARCH_CACHE
    USER_SEARCH_CACHE[call.from_user.id] = {
        "query": cached_item["query"],
        "results": cached_item["results"],
        "time": time.time()
    }
    cached_ids = db.get_cached_ids()
    text = format_search_message(cached_item["query"], cached_item["results"], page=0, per_page=6)
    await call.message.answer(
        text,
        reply_markup=build_search_keyboard(cached_item["results"], page=0, per_page=6, cached_ids=cached_ids),
        parse_mode="HTML"
    )

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
    # Guruhda bo'lsa, xabarda bot tilga olingan yoki /shazam bo'lsa ishlaydi
    if message.chat.type in ["group", "supergroup"]:
        caption = (message.caption or "").lower()
        bot_info = await message.bot.get_me()
        bot_mention = f"@{bot_info.username}".lower()
        if "/shazam" not in caption and bot_mention not in caption:
            return

    await process_recognition(message, message)
