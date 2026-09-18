import asyncio
import logging
from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedAudio,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from services.music_search import music_service
from database.db import db
from keyboards.inline_kb import get_audio_keyboard

logger = logging.getLogger(__name__)
inline_router = Router()

@inline_router.inline_query()
async def inline_search_handler(inline_query: InlineQuery):
    query = inline_query.query.strip()
    results = []

    bot_info = await inline_query.bot.get_me()
    bot_username = bot_info.username

    if not query:
        results.append(
            InlineQueryResultArticle(
                id="hint",
                title="🔍 Musiqa qidirish",
                description=f"@{bot_username} orqali musiqa qidirish uchun nomini yozing...",
                input_message_content=InputTextMessageContent(
                    message_text=f"🎵 Men @{bot_username} orqali musiqa tinglayapman!\nSiz ham sinab ko'ring: @{bot_username}"
                )
            )
        )
        await inline_query.answer(results, cache_time=10, is_personal=True)
        return

    # 1. Avval RAM keshidan 0ms da qidiramiz (avval yuklangan musiqalar darhol chiqadi!)
    cached_ids_added = set()
    q_lower = query.lower()

    # Agar so'rov video_id yoki start parametri bo'lsa (masalan dl_xyz yoki xyz)
    clean_vid = query.replace("dl_", "").replace("id_", "").strip()
    if clean_vid in db._ram_cache:
        item = db._ram_cache[clean_vid]
        cached_ids_added.add(clean_vid)
        results.append(
            InlineQueryResultCachedAudio(
                id=f"c_{clean_vid}",
                audio_file_id=item['file_id'],
                caption=f"🎧 <b>{item['title']}</b>\n👤 <i>{item['performer']}</i>\n\n🤖 @{bot_username}",
                reply_markup=get_audio_keyboard(clean_vid, item['title'])
            )
        )

    # Nomi bo'yicha RAM keshidan mos tushgan qo'shiqlarni chiqaramiz
    for vid, item in list(db._ram_cache.items()):
        if vid in cached_ids_added:
            continue
        title_l = (item.get('title') or '').lower()
        perf_l = (item.get('performer') or '').lower()
        if q_lower in title_l or q_lower in perf_l:
            cached_ids_added.add(vid)
            results.append(
                InlineQueryResultCachedAudio(
                    id=f"c_{vid}",
                    audio_file_id=item['file_id'],
                    caption=f"🎧 <b>{item['title']}</b>\n👤 <i>{item['performer']}</i>\n\n🤖 @{bot_username}",
                    reply_markup=get_audio_keyboard(vid, item['title'])
                )
            )
            if len(results) >= 15:
                break

    # 2. Agar keshda 5 tadan kam natija bo'lsa, tezkor onlayn qidiruv (Telegram timeout bo'lmasligi uchun 2.5s limit)
    if len(results) < 5:
        try:
            search_res = await asyncio.wait_for(music_service.search(query, limit=15), timeout=2.5)
            for item in search_res:
                video_id = item.get('id')
                if video_id in cached_ids_added:
                    continue

                title = item.get('title', 'Musiqa')
                artist = item.get('artist', "Noma'lum")
                duration_str = item.get('duration_str', '00:00')
                thumb_url = item.get('thumbnail')
                is_concert = item.get('is_concert', False)

                display_title = f"🎬 [Konsert] {title}" if is_concert else f"🎵 {title}"

                cached = await db.get_cached_music(video_id)
                if cached and cached.get('file_id'):
                    results.append(
                        InlineQueryResultCachedAudio(
                            id=f"c_{video_id}",
                            audio_file_id=cached['file_id'],
                            caption=f"{display_title}\n👤 <i>@{bot_username}</i>\n\n🤖 @{bot_username}",
                            reply_markup=get_audio_keyboard(video_id, cached['title'])
                        )
                    )
                else:
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📥 Yuklab olish",
                                url=f"https://t.me/{bot_username}?start=dl_{video_id}"
                            )
                        ]
                    ])

                    results.append(
                        InlineQueryResultArticle(
                            id=str(video_id),
                            title=display_title,
                            description=f"👤 {artist} | ⏱ {duration_str}",
                            thumbnail_url=thumb_url,
                            input_message_content=InputTextMessageContent(
                                message_text=(
                                    f"{display_title}\n"
                                    f"👤 <i>{artist}</i>\n"
                                    f"⏱ <b>Davomiyligi:</b> {duration_str}\n\n"
                                    f"🤖 @{bot_username} orqali yuklab oling!"
                                ),
                                parse_mode="HTML"
                            ),
                            reply_markup=kb
                        )
                    )
                cached_ids_added.add(video_id)
                if len(results) >= 20:
                    break
        except Exception as e:
            logger.warning(f"Inline qidiruvda vaqt o'tishi yoki xatolik: {e}")

    await inline_query.answer(results, cache_time=30, is_personal=False)

