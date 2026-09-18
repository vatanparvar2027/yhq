import os
import time
import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.enums import ChatAction

from config import ADMINS, CHANNELS
from database.db import db
from keyboards.reply_kb import get_main_menu
from keyboards.inline_kb import get_channel_sub_keyboard, get_audio_keyboard
from services.music_search import music_service

logger = logging.getLogger(__name__)
start_router = Router()

async def get_all_active_channels() -> list:
    """Barcha faol majburiy obuna kanallarini to'liq formatda olish (.env + baza)"""
    full_db_channels = await db.get_db_channels_full()
    result = []
    seen = set()

    for ch in full_db_channels:
        key = ch.get('username') or ch.get('chat_id')
        if key and key not in seen:
            seen.add(key)
            result.append(ch)

    for env_ch in CHANNELS:
        env_ch = env_ch.strip()
        if env_ch and env_ch not in seen:
            seen.add(env_ch)
            result.append({
                'username': env_ch,
                'chat_id': None,
                'title': None,
                'invite_link': None
            })
    return result

async def check_user_subscription(bot, user_id: int) -> bool:
    """Foydalanuvchi barcha majburiy kanallarga a'zo bo'lganligini aniq va xatosiz tekshirish"""
    all_channels = await get_all_active_channels()
    if not all_channels:
        return True

    for ch in all_channels:
        chat_target = None
        if isinstance(ch, dict):
            chat_target = ch.get('chat_id') or ch.get('username')
        else:
            chat_target = str(ch).strip()

        if not chat_target:
            continue

        # Agar username yoki havola bo'lsa, tozalaymiz
        if isinstance(chat_target, str):
            chat_target = chat_target.strip()
            if "t.me/" in chat_target:
                part = chat_target.split("t.me/", 1)[1].strip("/")
                if not part.startswith("+") and not part.startswith("joinchat/"):
                    chat_target = "@" + part
            if not chat_target.startswith("@") and not chat_target.startswith("-") and not chat_target.startswith("http"):
                chat_target = "@" + chat_target

        try:
            member = await bot.get_chat_member(chat_id=chat_target, user_id=user_id)
            if member.status not in ["creator", "administrator", "member", "restricted"]:
                logger.info(f"Foydalanuvchi {user_id} kanalda a'zo emas: {chat_target} (status: {member.status})")
                return False
        except Exception as e:
            err_str = str(e).lower()
            logger.warning(f"Kanal obunasi tekshiruvida xatolik ({chat_target}, user={user_id}): {e}")
            if "chat not found" in err_str or "bot is not a member" in err_str:
                # Agar bot kanalda yo'q bo'lsa yoki private link chat_id siz bo'lsa, xatoni o'tkazib yubormaslik
                continue
            elif "user not found" in err_str:
                return False
            else:
                return False
    return True

@start_router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    user = message.from_user
    # Orqa fonda foydalanuvchini bazaga yozish (tezlikni tushirmaslik uchun)
    asyncio.create_task(db.add_or_update_user(user.id, user.full_name, user.username))

    is_subscribed = await check_user_subscription(message.bot, user.id)
    if not is_subscribed:
        all_channels = await get_all_active_channels()
        await message.answer(
            f"👋 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
            "Botdan to'liq foydalanish uchun quyidagi kanallarga a'zo bo'ling:",
            reply_markup=get_channel_sub_keyboard(all_channels),
            parse_mode="HTML"
        )
        return

    # Deep linking: agar /start dl_VIDEOID ko'rinishida kelgan bo'lsa
    args = command.args
    if args and args.startswith("dl_"):
        video_id = args[3:]
        # Avvalo keshdan tekshiramiz (0ms)
        cached = await db.get_cached_music(video_id)
        bot_logo = "bot_avatar.jpg" if os.path.exists("bot_avatar.jpg") else None
        thumb_file = FSInputFile(bot_logo) if bot_logo else None

        if cached:
            from handlers.search import format_audio_caption
            dur = cached.get('duration') or 0
            is_conc = dur >= 1200 or "konsert" in (cached.get('title') or "").lower()
            caption = format_audio_caption(
                title=cached.get('title', 'Musiqa'),
                artist=cached.get('performer', '@ChiroqchiMuzbot'),
                duration_str=format_duration(dur),
                is_concert=is_conc
            )
            await message.answer_audio(
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

        # Keshda bo'lmasa yuklab beramiz
        load_msg = await message.answer("⚡️ <i>Musiqa yuklanmoqda...</i>", parse_mode="HTML")
        await message.bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)
        audio_data = await music_service.download(video_id, video_id)
        if audio_data:
            try:
                from handlers.search import format_audio_caption
                audio_file = FSInputFile(audio_data['file_path'])
                bot_cover = bot_logo if bot_logo else audio_data.get('cover_path')
                thumb_f = FSInputFile(bot_cover) if bot_cover and os.path.exists(bot_cover) else None

                file_size = os.path.getsize(audio_data['file_path']) if os.path.exists(audio_data['file_path']) else None
                caption = format_audio_caption(
                    title=audio_data['title'],
                    artist=audio_data['artist'],
                    duration_str=format_duration(audio_data['duration']),
                    is_concert=(audio_data['duration'] >= 1200),
                    file_size=file_size
                )

                sent = await message.answer_audio(
                    audio=audio_file,
                    title=audio_data['title'],
                    performer="@ChiroqchiMuzbot",
                    duration=audio_data['duration'],
                    thumbnail=thumb_f,
                    caption=caption,
                    reply_markup=get_audio_keyboard(video_id, audio_data['title']),
                    parse_mode="HTML"
                )
                await db.save_music_cache(
                    video_id=video_id,
                    file_id=sent.audio.file_id,
                    title=audio_data['title'],
                    performer="@ChiroqchiMuzbot",
                    duration=audio_data['duration']
                )
                await load_msg.delete()
            except Exception as e:
                logger.error(f"Audio yuborishda xatolik: {e}")
                await load_msg.edit_text("❌ Musiqani yuborishda xatolik yuz berdi.")
            finally:
                if os.path.exists(audio_data['file_path']):
                    try:
                        os.remove(audio_data['file_path'])
                    except Exception:
                        pass
                if audio_data.get('cover_path') and os.path.exists(audio_data['cover_path']):
                    try:
                        os.remove(audio_data['cover_path'])
                    except Exception:
                        pass
            return
        else:
            await load_msg.edit_text("❌ Musiqani yuklab olish imkoni bo'lmadi.")
            return

    is_admin = user.id in ADMINS
    text = (
        f"👋 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
        "🎵 <b>CHIROQCHIMUZ — Musiqa va Media Botiga xush kelibsiz!</b>\n\n"
        "Men har qanday musiqani va mediani topib bera olaman:\n"
        "• ✍️ <b>Qo'shiq nomi</b> yoki <b>ijrochi</b>sini yozing (konsert dasturlari bilan birga);\n"
        "• 🎙 <b>Ovozli xabar</b> (voice) yuboring — qo'shiqni darhol aniqlayman (Shazam);\n"
        "• 📸 <b>Yashirin Istoriya:</b> Kontakt yoki @username yuborsangiz, barcha istoriyalarini egasiga bildirmasdan (anonim) yuklab beraman;\n"
        "• 🔗 <b>YouTube / TikTok / Instagram</b> havolasidan MP3 yoki 4K video yuklash;\n"
        "• 🔍 Guruhlarda <code>@ChiroqchiMuzbot musiqa nomi</code> orqali inline qidiruv.\n\n"
        "<i>Musiqa nomini, kontakt yoki @username yozib ko'ring...</i>"
    )
    banner_path = "bot_banner.jpg"
    if os.path.exists(banner_path):
        await message.answer_photo(
            photo=FSInputFile(banner_path),
            caption=text,
            reply_markup=get_main_menu(is_admin),
            parse_mode="HTML"
        )
    else:
        await message.answer(text, reply_markup=get_main_menu(is_admin), parse_mode="HTML")

@start_router.message(Command("help"))
@start_router.message(F.text == "ℹ️ Bot haqida / Yordam")
async def cmd_help(message: Message):
    text = (
        "📖 <b>Botdan foydalanish bo'yicha qo'llanma:</b>\n\n"
        "1️⃣ <b>Musiqa va Konsertlar qidiruvi:</b>\n"
        "Qo'shiq yoki ijrochi nomini yozing (masalan: <i>Benom</i>) — barcha taronalar va konsert dasturlari ro'yxat bo'lib chiqadi.\n\n"
        "2️⃣ <b>Shazam (Ovozdan topish):</b>\n"
        "Ovozli xabar yuborsangiz, bot darhol musiqani topib beradi.\n\n"
        "3️⃣ <b>Telegram Istoriyalarini Yashirincha Yuklash:</b>\n"
        "Istalgan profilning kontaktini yoki <code>@username</code>ini yuboring. Bot uning barcha faol istoriyalarini egasiga bildirmasdan yuklab beradi.\n\n"
        "4️⃣ <b>Video va MP3 Yuklash:</b>\n"
        "YouTube, Instagram yoki TikTok havolasini yuboring — MP3 yoki 4K gacha bo'lgan sifatda yuklab oling!"
    )
    avatar_path = "bot_avatar.jpg"
    if os.path.exists(avatar_path):
        await message.answer_photo(photo=FSInputFile(avatar_path), caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")

@start_router.callback_query(F.data == "check_subscription")
async def cb_check_sub(call: CallbackQuery):
    is_subscribed = await check_user_subscription(call.bot, call.from_user.id)
    if not is_subscribed:
        await call.answer("❌ Siz hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)
        return

    # Obuna tasdiqlandi
    await call.answer("✅ Rahmat! Obuna tasdiqlandi!")
    await call.message.delete()

    user = call.from_user
    is_adm = user.id in ADMINS

    # Foydalanuvchining eslab qolingan so'rovini tekshiramiz
    from handlers.search import PENDING_REQUESTS, execute_search, URL_CACHE, clean_old_url_cache, _get_all_channels
    from services.music_search import is_url, extract_url, clean_url
    from keyboards.inline_kb import get_media_choice_keyboard

    pending = PENDING_REQUESTS.pop(user.id, None)

    if pending and (time.time() - pending.get("time", 0)) < 1800:
        # Pending so'rov topildi — bajaramiz
        req_type = pending.get("type")
        query = pending.get("query", "")

        if req_type == "url" and query:
            # URL so'rovini qayta ishlaymiz
            clean_old_url_cache()
            status_msg = await call.message.answer(
                f"🔍 <b>Havola tekshirilmoqda...</b>",
                parse_mode="HTML"
            )
            await call.bot.send_chat_action(call.message.chat.id, ChatAction.TYPING)

            from services.music_search import music_service
            target_clean_url = clean_url(query)
            info = await music_service.get_media_info(target_clean_url)
            if not info:
                await status_msg.edit_text("❌ Ushbu havola orqali media topilmadi yoki havola yopiq.")
                return

            import time as _time
            url_key = f"u_{user.id}_{int(_time.time() * 1000) % 10000000}"
            URL_CACHE[url_key] = {"url": target_clean_url, "info": info, "time": _time.time()}

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
                    await call.message.answer_photo(
                        photo=info['thumbnail'],
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                    sent = True
                    await status_msg.delete()
                except Exception:
                    pass

            if not sent:
                await status_msg.edit_text(caption, reply_markup=reply_markup, parse_mode="HTML")

        elif req_type == "search" and query:
            # Matn qidiruvi so'rovini qayta ishlaymiz
            await call.message.answer(
                f"✅ <b>A'zolik tasdiqlandi!</b>\n"
                f"⚡️ <i>«{query[:40]}» qidirish davom etmoqda...</i>",
                reply_markup=get_main_menu(is_adm),
                parse_mode="HTML"
            )

            # Fake message yaratib execute_search ga uzatamiz
            class _FakeMessage:
                from_user = user
                chat = call.message.chat
                bot = call.bot
                async def answer(self, *a, **kw): return await call.message.answer(*a, **kw)
                async def reply(self, *a, **kw): return await call.message.answer(*a, **kw)
                async def reply_photo(self, *a, **kw): return await call.message.answer_photo(*a, **kw)

            await execute_search(_FakeMessage(), query)

    else:
        # Pending so'rov yo'q — oddiy xush kelibsiz xabari
        await call.message.answer(
            f"✅ <b>Obuna tasdiqlandi, {user.first_name}!</b>\n\n"
            "🎵 Endi istalgan qo'shiq nomini yozing yoki havola yuboring!",
            reply_markup=get_main_menu(is_adm),
            parse_mode="HTML"
        )


