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
                    message_text=f"🎵 Men @{bot_username} orqali musiqa qidiryapman!\nSiz ham sinab ko'ring!"
                )
            )
        )
        await inline_query.answer(results, cache_time=10, is_personal=True)
        return

    # Qidiruvni amalga oshiramiz (barcha taronalar va konsertlar)
    search_res = await music_service.search(query, limit=25)

    for i, item in enumerate(search_res):
        video_id = item.get('id')
        title = item.get('title', 'Musiqa')
        artist = item.get('artist', "Noma'lum")
        duration_str = item.get('duration_str', '00:00')
        thumb_url = item.get('thumbnail')
        is_concert = item.get('is_concert', False)

        display_title = f"🎬 [Konsert] {title}" if is_concert else f"🎵 {title}"

        # Agar qo'shiq avval yuklangan bo'lsa, to'g'ridan-to'g'ri audio yuboramiz!
        cached = await db.get_cached_music(video_id)
        if cached and cached.get('file_id'):
            audio_result = InlineQueryResultCachedAudio(
                id=str(video_id),
                audio_file_id=cached['file_id'],
                caption=f"{display_title}\n👤 <i>@{bot_username}</i>\n\n🤖 @{bot_username}",
                reply_markup=get_audio_keyboard(video_id, cached['title'])
            )
            results.append(audio_result)
        else:
            # Agar hali yuklanmagan bo'lsa, maqola ko'rinishida chiqarib bot orqali yuklab olish tugmasini beramiz
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📥 Yuklab olish",
                        url=f"https://t.me/{bot_username}?start=dl_{video_id}"
                    )
                ]
            ])

            article = InlineQueryResultArticle(
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
            results.append(article)

    await inline_query.answer(results, cache_time=60, is_personal=False)

