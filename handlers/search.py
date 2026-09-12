import os
import time
import asyncio
import logging
from typing import Dict, List, Any, Optional
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.enums import ChatAction

from database.db import db
from services.music_search import music_service, is_url, format_duration
from keyboards.inline_kb import build_search_keyboard, get_audio_keyboard, get_media_choice_keyboard
from handlers.start import check_user_subscription
from keyboards.inline_kb import get_channel_sub_keyboard
from config import CHANNELS

logger = logging.getLogger(__name__)
search_router = Router()

# Foydalanuvchilarning so'nggi qidiruv natijalarini vaqtincha xotirada saqlash
USER_SEARCH_CACHE: Dict[int, Dict[str, Any]] = {}

# Havola orqali media tanlovlari uchun kesh
URL_CACHE: Dict[str, Dict[str, Any]] = {}

# Obunadan oldin kelgan so'rovni eslab qolish (obunadan keyin avtomatik bajarish uchun)
# {user_id: {"type": "search"|"url", "query": str, "time": float}}
PENDING_REQUESTS: Dict[int, Dict[str, Any]] = {}

def clean_old_url_cache():
    """1 soatdan eski kesh yozuvlarini tozalash"""
    now = time.time()
    expired = [k for k, v in URL_CACHE.items() if now - v.get("time", 0) > 3600]
    for k in expired:
        URL_CACHE.pop(k, None)
    # Pending so'rovlarni ham tozalaymiz (30 daqiqadan eski)
    expired_p = [k for k, v in PENDING_REQUESTS.items() if now - v.get("time", 0) > 1800]
    for k in expired_p:
        PENDING_REQUESTS.pop(k, None)

async def _get_all_channels(bot) -> list:
    """Barcha faol kanallarni olish (.env + baza)"""
    from handlers.start import get_all_active_channels
    return await get_all_active_channels()

def format_search_message(query: str, results: List[Dict[str, Any]], page: int = 0, per_page: int = 6) -> str:
    """Qidiruv natijalarini ro'yxatma-ro'yxat, chiroyli va tartibli matn ko'rinishida formatlash"""
    total = len(results)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total)
    current_items = results[start_idx:end_idx]

    lines = [
        f"🎧 <b>«{query}»</b> bo'yicha barcha taronalar va konsertlar:",
        f"📊 Jami: <b>{total} ta</b> natija topildi | Sahifa: <b>{page + 1}/{total_pages}</b>\n"
    ]

    for i, item in enumerate(current_items, start=start_idx + 1):
        title = item.get('title', 'Musiqa')
        artist = item.get('artist', '')
        duration_str = item.get('duration_str', '00:00')
        is_concert = item.get('is_concert', False)

        tag = "🎬 [Konsert]" if is_concert else "🎵"

        if artist and artist != "Noma'lum" and artist.lower() not in title.lower():
            display_name = f"{title} — <i>{artist}</i>"
        else:
            display_name = title

        lines.append(f"{i}. {tag} <b>{display_name}</b> <code>({duration_str})</code>")

    lines.append("\n👇 <i>Yuklab olish uchun pastdagi tegishli tugmani bosing:</i>")
    return "\n".join(lines)

def format_audio_caption(title: str, artist: str, duration_str: str, is_concert: bool = False, file_size: Optional[int] = None) -> str:
    """Musiqa yuborilganda chiroyli va estetik xabar matni"""
    size_str = f"💾 <b>Hajmi:</b> {round(file_size / (1024 * 1024), 1)} MB | " if file_size else ""
    if is_concert:
        return (
            f"🎬 <b>{title}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎭 <b>Dastur:</b> Jonli Konsert / Mix To'plam\n"
            f"⏱ <b>Davomiyligi:</b> {duration_str}\n"
            f"{size_str}🎵 <b>Format:</b> To'liq MP3 (HQ Audio)\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Kanal / Bot:</b> @ChiroqchiMuzbot\n"
            f"🌟 <i>Yuqori sifatli jonli ijro dasturi!</i>"
        )
    return (
        f"🎧 <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Ijrochi:</b> {artist}\n"
        f"⏱ <b>Davomiyligi:</b> {duration_str}\n"
        f"{size_str}🎵 <b>Format:</b> MP3 Audio (HQ)\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Kanal / Bot:</b> @ChiroqchiMuzbot\n"
        f"⚡️ <i>Eng sara musiqalar va yangi taronalar!</i>"
    )

def format_video_caption(title: str, quality_label: str, duration_str: str, file_size: Optional[int] = None) -> str:
    """Video yuborilganda chiroyli va estetik xabar matni"""
    size_str = f"💾 <b>Fayl hajmi:</b> {round(file_size / (1024 * 1024), 1)} MB\n" if file_size else ""
    return (
        f"🎬 <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📺 <b>Video sifati:</b> {quality_label}\n"
        f"⏱ <b>Davomiyligi:</b> {duration_str}\n"
        f"{size_str}"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Kanal / Bot:</b> @ChiroqchiMuzbot\n"
        f"🚀 <i>Eng yuqori sifatda yuklab berildi!</i>"
    )

@search_router.message(F.text == "🔍 Musiqa qidirish")
async def msg_search_prompt(message: Message):
    await message.answer(
        "🔎 <b>Qidirmoqchi bo'lgan musiqangiz nomini yoki ijrochisini yozing:</b>\n"
        "<i>Masalan: Benom, Konsta, Janob Rasul, Eminem, Sevara Nazrxon...</i>\n\n"
        "💡 <i>Bot barcha qo'shiqlar, albomlar va to'liq konsert dasturlarini ro'yxat qilib topib beradi!</i>",
        parse_mode="HTML"
    )

@search_router.message(F.text == "🔝 Trend musiqalar")
async def msg_trending(message: Message):
    # Orqa fonda foydalanuvchini qayd etish
    asyncio.create_task(db.add_or_update_user(message.from_user.id, message.from_user.full_name, message.from_user.username))

    # 0ms da RAM keshidan trend musiqalarni olamiz
    results = await music_service.get_trending()
    if not results:
        await message.answer("❌ Trend musiqalarni yuklashda xatolik yuz berdi.")
        return

    USER_SEARCH_CACHE[message.from_user.id] = {
        "query": "Trend musiqalar",
        "results": results,
        "time": time.time()
    }
    cached_ids = db.get_cached_ids()
    text = format_search_message("Trend musiqalar", results, page=0, per_page=6)
    await message.answer(
        text,
        reply_markup=build_search_keyboard(results, page=0, per_page=6, cached_ids=cached_ids),
        parse_mode="HTML"
    )

async def execute_search(message: Message, query: str):
    """Musiqa qidiruvini amalga oshirib, barcha taronalar va konsertlarni ro'yxatma-ro'yxat qaytarish"""
    user = message.from_user
    clean_q = query.strip()
    if not clean_q:
        return

    # Orqa fonda foydalanuvchini yangilash va qidiruvni log qilish
    asyncio.create_task(db.add_or_update_user(user.id, user.full_name, user.username))
    asyncio.create_task(db.log_search(user.id, clean_q))

    # Majburiy obunani faqat shaxsiy chatda tekshiramiz
    if message.chat.type == "private":
        is_subscribed = await check_user_subscription(message.bot, user.id)
        if not is_subscribed:
            # Foydalanuvchining so'rovini eslab qolamiz
            PENDING_REQUESTS[user.id] = {
                "type": "search",
                "query": clean_q,
                "time": time.time()
            }
            all_channels = await _get_all_channels(message.bot)
            await message.answer(
                f"🔒 <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling!</b>\n\n"
                f"✅ A'zo bo'lgach, <b>«{clean_q[:40]}»</b> so'rovingiz avtomatik bajariladi.",
                reply_markup=get_channel_sub_keyboard(all_channels),
                parse_mode="HTML"
            )
            return

    # Typing holatini yoqamiz
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    # Agar so'rov RAM keshida bo'lsa darhol yuboramiz (0.01 soniyada!)
    norm_query = clean_q.lower()
    if norm_query in music_service._search_cache:
        cache_time, cached_res = music_service._search_cache[norm_query]
        if time.time() - cache_time < music_service._cache_ttl and len(cached_res) > 0:
            USER_SEARCH_CACHE[user.id] = {
                "query": clean_q,
                "results": cached_res,
                "time": time.time()
            }
            cached_ids = db.get_cached_ids()
            text = format_search_message(clean_q, cached_res, page=0, per_page=6)
            await message.reply(
                text,
                reply_markup=build_search_keyboard(cached_res, page=0, per_page=6, cached_ids=cached_ids),
                parse_mode="HTML"
            )
            return

    # Yangi qidiruv: 50 tagacha barcha taronalar va konsert dasturlari olinadi
    status_msg = await message.reply(f"⚡️ <i>«{clean_q}» bo'yicha barcha taronalar va konsertlar qidirilmoqda...</i>", parse_mode="HTML")
    results = await music_service.search(clean_q, limit=50)
    if not results:
        await status_msg.edit_text(f"😔 <b>«{clean_q}»</b> bo'yicha hech qanday musiqa yoki konsert topilmadi.\nIltimos, nomni to'g'riroq yozib ko'ring.", parse_mode="HTML")
        return

    USER_SEARCH_CACHE[user.id] = {
        "query": clean_q,
        "results": results,
        "time": time.time()
    }
    cached_ids = db.get_cached_ids()
    text = format_search_message(clean_q, results, page=0, per_page=6)
    await status_msg.edit_text(
        text,
        reply_markup=build_search_keyboard(results, page=0, per_page=6, cached_ids=cached_ids),
        parse_mode="HTML"
    )

@search_router.message(Command(commands=["music", "musiqa", "song"]))
async def cmd_music_search(message: Message, command: CommandObject):
    """Guruhlarda va shaxsiy chatda /music, /musiqa buyrug'i orqali qidirish"""
    query = command.args
    if not query:
        await message.reply(
            "🔎 <b>Musiqa nomini yozing:</b>\n"
            "<i>Masalan: <code>/music Konsta</code> yoki <code>/musiqa Janob Rasul</code></i>",
            parse_mode="HTML"
        )
        return
    await execute_search(message, query)

@search_router.message(F.new_chat_members)
async def handle_new_chat_members(message: Message):
    """Bot guruhga qo'shilganda qisqa va qulay qo'llanma yuborish"""
    bot_info = await message.bot.get_me()
    for member in message.new_chat_members:
        if member.id == bot_info.id:
            await message.answer(
                f"👋 <b>Assalomu alaykum! Men @{bot_info.username} — musiqiy yordamchingizman!</b>\n\n"
                "🎵 <b>Guruhda musiqa qidirish usullari:</b>\n"
                "• <code>/music musiqa nomi</code> (masalan: <code>/music Konsta</code>)\n"
                "• Yoki istalgan chatda <code>@{bot_info.username} nom</code> deb yozing\n"
                "• Guruhga <b>YouTube, TikTok, Instagram</b> havolasini yuborsangiz, MP3 yoki 4K video yuklab beraman!\n"
                "• Ovozli xabarga javob qilib (reply) <code>/shazam</code> yozsangiz, qo'shiqni aniqlab beraman.\n\n"
                "<i>Maroqli hordiq tilayman! 🎧</i>",
                parse_mode="HTML"
            )
            break

@search_router.message(F.text & ~F.text.startswith("/"))
async def handle_text_search(message: Message):
    user = message.from_user
    text = message.text.strip()
    is_group = message.chat.type in ["group", "supergroup"]

    # 1. Agar havola (URL) yuborilgan bo'lsa (ham guruhda, ham shaxsiy chatda ishlaydi)
    if is_url(text):
        # Avval obunani tekshiramiz (shaxsiy chatda)
        if not is_group:
            is_subscribed = await check_user_subscription(message.bot, user.id)
            if not is_subscribed:
                # URL so'rovini eslab qolamiz
                PENDING_REQUESTS[user.id] = {
                    "type": "url",
                    "query": text,
                    "time": time.time()
                }
                all_channels = await _get_all_channels(message.bot)
                await message.reply(
                    f"🔒 <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling!</b>\n\n"
                    f"✅ A'zo bo'lgach, <b>havola yuklab berish</b> avtomatik davom etadi.",
                    reply_markup=get_channel_sub_keyboard(all_channels),
                    parse_mode="HTML"
                )
                return

        clean_old_url_cache()
        status_msg = await message.reply("🔍 <b>Havola tekshirilmoqda...</b>", parse_mode="HTML")
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        info = await music_service.get_media_info(text)
        if not info:
            await status_msg.edit_text("❌ Ushbu havola orqali media topilmadi yoki havola noto'g'ri/yopiq.")
            return

        url_key = f"u_{user.id}_{int(time.time() * 1000) % 10000000}"
        URL_CACHE[url_key] = {
            "url": text,
            "info": info,
            "time": time.time()
        }

        caption = (
            f"🎬 <b>{info['title']}</b>\n"
            f"👤 Kanal / Ijrochi: <b>{info['artist']}</b>\n"
            f"⏱ Davomiyligi: <b>{info['duration_str']}</b>\n\n"
            f"👇 <b>Qaysi formatda yuklab olmoqchisiz?</b>\n"
            f"<i>🎵 MP3 yoki 4K gacha bo'lgan video sifatini tanlang:</i>"
        )
        reply_markup = get_media_choice_keyboard(url_key, info.get('available_heights'))

        sent = False
        if info.get('thumbnail'):
            try:
                await message.reply_photo(
                    photo=info['thumbnail'],
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                sent = True
                await status_msg.delete()
            except Exception as e:
                logger.warning(f"Rasm bilan yuborishda ogohlantirish: {e}")
                sent = False

        if not sent:
            await status_msg.edit_text(
                caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        return

    # 2. Agar guruhda bo'lsa:
    if is_group:
        bot_info = await message.bot.get_me()
        bot_mention = f"@{bot_info.username}".lower()
        # Agar bot nomini yozib qidirishsa (masalan: @ChiroqchiMuzbot Konsta)
        if text.lower().startswith(bot_mention):
            query = text[len(bot_mention):].strip()
            if query:
                await execute_search(message, query)
            return
        # Agar botning xabariga javoban (reply) yozilgan bo'lsa
        elif message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot_info.id:
            await execute_search(message, text)
            return
        else:
            # Guruhdagi boshqa oddiy suhbatlarga bot xalaqit bermaydi
            return

    # 3. Shaxsiy chatda har qanday matn orqali to'g'ridan-to'g'ri qidiruv
    await execute_search(message, text)

@search_router.callback_query(F.data.startswith("dl:"))
async def handle_download_callback(call: CallbackQuery):
    video_id = call.data.split(":", 1)[1]
    user_id = call.from_user.id

    # 1. ENG MUHIM: Tugma bosilgan zahoti call.answer() yuboriladi (Tugma aylanib qotmasligi uchun)
    await call.answer("⚡️ Musiqa tayyorlanmoqda...", cache_time=1)

    # 2. RAM va bazadagi keshdan tekshiramiz (0ms tezlik)
    cached = await db.get_cached_music(video_id)
    if cached:
        dur = cached.get('duration') or 0
        dur_str = format_duration(dur)
        is_conc = dur >= 1200 or "konsert" in (cached.get('title') or "").lower()
        caption = format_audio_caption(
            title=cached.get('title', 'Musiqa'),
            artist=cached.get('performer', '@ChiroqchiMuzbot'),
            duration_str=dur_str,
            is_concert=is_conc
        )
        bot_logo = "bot_avatar.jpg" if os.path.exists("bot_avatar.jpg") else None
        thumb_file = FSInputFile(bot_logo) if bot_logo else None

        await call.bot.send_audio(
            chat_id=call.message.chat.id,
            audio=cached['file_id'],
            title=cached.get('title'),
            performer="@ChiroqchiMuzbot",
            duration=dur,
            thumbnail=thumb_file,
            caption=caption,
            reply_markup=get_audio_keyboard(video_id, cached.get('title', 'Musiqa')),
            parse_mode="HTML"
        )
        return

    # 3. Agar keshda bo'lmasa, yuklab olamiz
    # Qidiruv keshida muqova rasmi va konsert holati bormi
    thumb_hint = None
    is_concert = False
    cached_search = USER_SEARCH_CACHE.get(user_id, {})
    for item in cached_search.get("results", []):
        if item.get("id") == video_id:
            thumb_hint = item.get("thumbnail")
            is_concert = item.get("is_concert", False)
            break

    loading_text = "⚡️ <i>[1/2] Konsert dasturi yuklab olinmoqda va tayyorlanmoqda...</i>" if is_concert else "⚡️ <i>[1/2] Musiqa yuklab olinmoqda va tayyorlanmoqda...</i>"
    progress_msg = await call.message.answer(loading_text, parse_mode="HTML")
    await call.bot.send_chat_action(call.message.chat.id, ChatAction.RECORD_VOICE)

    audio_data = await music_service.download(video_id, video_id, thumb_url_hint=thumb_hint)
    if not audio_data:
        await progress_msg.edit_text("❌ Musiqani yuklab olishda xatolik yuz berdi. Boshqa variantni tanlab ko'ring.")
        return

    await progress_msg.edit_text("🚀 <i>[2/2] Telegramga yuklanmoqda...</i>", parse_mode="HTML")
    try:
        audio_file = FSInputFile(audio_data['file_path'])
        bot_logo = "bot_avatar.jpg" if os.path.exists("bot_avatar.jpg") else audio_data.get('cover_path')
        thumb_file = FSInputFile(bot_logo) if bot_logo and os.path.exists(bot_logo) else None

        file_size = os.path.getsize(audio_data['file_path']) if os.path.exists(audio_data['file_path']) else None
        caption = format_audio_caption(
            title=audio_data['title'],
            artist=audio_data['artist'],
            duration_str=format_duration(audio_data['duration']),
            is_concert=is_concert or audio_data['duration'] >= 1200,
            file_size=file_size
        )

        sent_msg = await call.bot.send_audio(
            chat_id=call.message.chat.id,
            audio=audio_file,
            title=audio_data['title'],
            performer="@ChiroqchiMuzbot",
            duration=audio_data['duration'],
            thumbnail=thumb_file,
            caption=caption,
            reply_markup=get_audio_keyboard(video_id, audio_data['title']),
            parse_mode="HTML"
        )

        # Bazaga va RAM ga saqlaymiz
        await db.save_music_cache(
            video_id=video_id,
            file_id=sent_msg.audio.file_id,
            title=audio_data['title'],
            performer="@ChiroqchiMuzbot",
            duration=audio_data['duration']
        )
        await progress_msg.delete()
    except Exception as e:
        logger.error(f"Musiqa yuborishda xatolik: {e}")
        await progress_msg.edit_text("❌ Musiqani yuborishda xatolik yuz berdi.")
    finally:
        try:
            if audio_data and audio_data.get('file_path') and os.path.exists(audio_data['file_path']):
                os.remove(audio_data['file_path'])
            if audio_data and audio_data.get('cover_path') and "bot_avatar" not in str(audio_data['cover_path']) and os.path.exists(audio_data['cover_path']):
                os.remove(audio_data['cover_path'])
        except Exception:
            pass

@search_router.callback_query(F.data.startswith("page:"))
async def handle_pagination(call: CallbackQuery):
    # Birinchi bo'lib call.answer() - spinner darhol o'chadi
    await call.answer()
    page = int(call.data.split(":", 1)[1])
    user_id = call.from_user.id

    cached = USER_SEARCH_CACHE.get(user_id)
    if not cached or not cached.get("results"):
        await call.answer("Qidiruv muddati o'tgan, iltimos qayta qidiring.", show_alert=True)
        return

    results = cached["results"]
    query = cached.get("query", "Musiqa")
    cached_ids = db.get_cached_ids()

    new_text = format_search_message(query, results, page=page, per_page=6)
    new_kb = build_search_keyboard(results, page=page, per_page=6, cached_ids=cached_ids)

    try:
        await call.message.edit_text(
            text=new_text,
            reply_markup=new_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        try:
            await call.message.edit_reply_markup(reply_markup=new_kb)
        except Exception:
            pass

@search_router.callback_query(F.data.startswith("dl_as_video:"))
async def handle_dl_as_video(call: CallbackQuery):
    """Musiqa ostidagi Video yuklash tugmasi bosilganda sifatlarni taklif qilish"""
    video_id = call.data.split(":", 1)[1]
    url = f"https://www.youtube.com/watch?v={video_id}"
    await call.answer("🎬 Video ma'lumotlari tekshirilmoqda...")

    status_msg = await call.message.reply("🔍 <i>Video sifati va formatlari aniqlanmoqda...</i>", parse_mode="HTML")
    info = await music_service.get_media_info(url)
    if not info:
        await status_msg.edit_text("❌ Ushbu videoni yuklab olish imkoni bo'lmadi.")
        return

    clean_old_url_cache()
    url_key = f"v_{call.from_user.id}_{int(time.time() * 1000) % 10000000}"
    URL_CACHE[url_key] = {
        "url": url,
        "info": info,
        "time": time.time()
    }

    caption = (
        f"🎬 <b>{info['title']}</b>\n"
        f"👤 Ijrochi / Kanal: <b>{info['artist']}</b>\n"
        f"⏱ Davomiyligi: <b>{info['duration_str']}</b>\n\n"
        f"👇 <b>Qaysi video sifatini tanlaysiz?</b>"
    )
    reply_markup = get_media_choice_keyboard(url_key, info.get('available_heights'))
    await status_msg.edit_text(caption, reply_markup=reply_markup, parse_mode="HTML")

@search_router.callback_query(F.data == "close_search")
async def handle_close_search(call: CallbackQuery):
    await call.answer("Yopildi")
    await call.message.delete()

@search_router.callback_query(F.data == "noop")
async def handle_noop(call: CallbackQuery):
    await call.answer()


@search_router.callback_query(F.data.startswith("dl_url_audio:"))
async def handle_url_audio_download(call: CallbackQuery):
    await call.answer("⚡️ MP3 yuklanmoqda...")
    url_key = call.data.split(":", 1)[1]
    cached = URL_CACHE.get(url_key)
    if not cached:
        await call.answer("⚠️ Havola muddati o'tgan, iltimos havolani qayta yuboring.", show_alert=True)
        return

    url = cached["url"]
    info = cached["info"]

    progress_msg = await call.message.reply(
        "⏳ <b>[1/2] MP3 yuklab olinmoqda...</b>\n<i>Iltimos kuting, yuqori sifatda tayyorlanmoqda...</i>",
        parse_mode="HTML"
    )
    await call.bot.send_chat_action(call.message.chat.id, ChatAction.RECORD_VOICE)

    unique_id = f"url_aud_{call.from_user.id}_{int(time.time())}"
    audio_data = await music_service.download(url, unique_id, thumb_url_hint=info.get('thumbnail'))

    if not audio_data:
        await progress_msg.edit_text("❌ Ushbu havoladan MP3 yuklab olishda xatolik yuz berdi.")
        return

    await progress_msg.edit_text("🚀 <b>[2/2] Telegramga yuklanmoqda...</b>", parse_mode="HTML")
    try:
        audio_file = FSInputFile(audio_data['file_path'])
        bot_logo = "bot_avatar.jpg" if os.path.exists("bot_avatar.jpg") else audio_data.get('cover_path')
        thumb_file = FSInputFile(bot_logo) if bot_logo and os.path.exists(bot_logo) else None

        file_size = os.path.getsize(audio_data['file_path']) if os.path.exists(audio_data['file_path']) else None
        caption = format_audio_caption(
            title=audio_data['title'],
            artist=audio_data['artist'],
            duration_str=format_duration(audio_data['duration']),
            is_concert=audio_data['duration'] >= 1200,
            file_size=file_size
        )

        sent_audio = await call.message.reply_audio(
            audio=audio_file,
            title=audio_data['title'],
            performer="@ChiroqchiMuzbot",
            duration=audio_data['duration'],
            thumbnail=thumb_file,
            caption=caption,
            reply_markup=get_audio_keyboard(audio_data['id'], audio_data['title']),
            parse_mode="HTML"
        )

        # Keshga saqlash
        await db.save_music_cache(
            video_id=audio_data['id'],
            file_id=sent_audio.audio.file_id,
            title=audio_data['title'],
            performer="@ChiroqchiMuzbot",
            duration=audio_data['duration']
        )
        await progress_msg.delete()
    except Exception as e:
        logger.error(f"Telegramga audio yuborishda xatolik: {e}")
        await progress_msg.edit_text("❌ Telegramga audio yuborishda xatolik yuz berdi.")
    finally:
        try:
            if audio_data and audio_data.get('file_path') and os.path.exists(audio_data['file_path']):
                os.remove(audio_data['file_path'])
            if audio_data and audio_data.get('cover_path') and "bot_avatar" not in str(audio_data['cover_path']) and os.path.exists(audio_data['cover_path']):
                os.remove(audio_data['cover_path'])
        except Exception:
            pass


@search_router.callback_query(F.data.startswith("dl_url_video:"))
async def handle_url_video_download(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Xatolik yuz berdi.", show_alert=True)
        return

    url_key = parts[1]
    quality = int(parts[2])

    quality_title = "4K Ultra HD" if quality >= 2160 else f"{quality}p HD"
    await call.answer(f"⚡️ {quality_title} video yuklanmoqda...")

    cached = URL_CACHE.get(url_key)
    if not cached:
        await call.answer("⚠️ Havola muddati o'tgan, iltimos havolani qayta yuboring.", show_alert=True)
        return

    url = cached["url"]

    progress_msg = await call.message.reply(
        f"⏳ <b>[1/2] {quality_title} video yuklab olinmoqda...</b>\n"
        f"<i>Video va audio eng yuqori sifatda birlashtirilmoqda, iltimos kuting...</i>",
        parse_mode="HTML"
    )
    await call.bot.send_chat_action(call.message.chat.id, ChatAction.UPLOAD_VIDEO)

    unique_id = f"url_vid_{call.from_user.id}_{quality}_{int(time.time())}"
    video_data = await music_service.download_video(url, unique_id, max_height=quality)

    if not video_data:
        # Platformaga mos xato xabar
        url_lower = url.lower()
        if "instagram.com" in url_lower:
            platform_note = (
                "\n\n<i>💡 Instagram yopiq postlar uchun login talab qiladi. "
                "Ochiq (ommaviy) postlarni yuklab ko'ring yoki <b>🎵 MP3</b> formatini tanlang.</i>"
            )
        elif "tiktok.com" in url_lower:
            platform_note = (
                "\n\n<i>💡 TikTokdan video yuklab olishda muammo yuzaga keldi. "
                "<b>🎵 MP3</b> formatini tanlab ko'ring.</i>"
            )
        else:
            platform_note = "\n\n<i>💡 Boshqa sifatni tanlab ko'ring yoki <b>🎵 MP3</b> variantini sinab ko'ring.</i>"

        await progress_msg.edit_text(
            f"❌ <b>{quality_title} videoni yuklab olishda xatolik yuz berdi.</b>{platform_note}",
            parse_mode="HTML"
        )
        return

    file_size = video_data.get('file_size', 0)
    MAX_BOT_SIZE = 49.5 * 1024 * 1024  # 50MB Telegram Bot API cheklovi

    if file_size > MAX_BOT_SIZE:
        size_mb = round(file_size / (1024 * 1024), 1)
        await progress_msg.edit_text(
            f"⚠️ <b>Video hajmi Telegram me'yoridan katta ({size_mb} MB)!</b>\n\n"
            f"Telegram Bot API faqat <b>50 MB</b> gacha hajmdagi fayllarni yuborishga imkon beradi.\n"
            f"Iltimos, videoni <b>1080p, 720p yoki 480p</b> sifatda yoki <b>🎵 MP3</b> variantida yuklab oling.",
            parse_mode="HTML"
        )
        try:
            if os.path.exists(video_data['file_path']):
                os.remove(video_data['file_path'])
            if video_data.get('cover_path') and os.path.exists(video_data['cover_path']):
                os.remove(video_data['cover_path'])
        except Exception:
            pass
        return

    # Haqiqiy yuklangan sifatni ko'rsatish
    actual_height = video_data.get('height', 0)
    if actual_height >= 2000:
        actual_quality_label = "4K Ultra HD (2160p)"
    elif actual_height >= 1080:
        actual_quality_label = f"Full HD ({actual_height}p)"
    elif actual_height >= 720:
        actual_quality_label = f"HD ({actual_height}p)"
    elif actual_height > 0:
        actual_quality_label = f"{actual_height}p"
    else:
        actual_quality_label = quality_title

    await progress_msg.edit_text("🚀 <b>[2/2] Video Telegramga yuklanmoqda...</b>", parse_mode="HTML")
    try:
        video_file = FSInputFile(video_data['file_path'])
        thumb_file = FSInputFile(video_data['cover_path']) if video_data.get('cover_path') and os.path.exists(video_data['cover_path']) else None

        caption = format_video_caption(
            title=video_data['title'],
            quality_label=actual_quality_label,
            duration_str=format_duration(video_data.get('duration', 0)),
            file_size=file_size
        )

        await call.message.reply_video(
            video=video_file,
            caption=caption,
            duration=video_data.get('duration', 0),
            width=video_data.get('width'),
            height=video_data.get('height'),
            thumbnail=thumb_file,
            supports_streaming=True,
            parse_mode="HTML"
        )
        await progress_msg.delete()
    except Exception as e:
        logger.error(f"Telegramga video yuborishda xatolik: {e}")
        await progress_msg.edit_text("❌ Telegramga videoni yuborishda xatolik yuz berdi.")
    finally:
        try:
            if os.path.exists(video_data['file_path']):
                os.remove(video_data['file_path'])
            if video_data.get('cover_path') and os.path.exists(video_data['cover_path']):
                os.remove(video_data['cover_path'])
        except Exception:
            pass



