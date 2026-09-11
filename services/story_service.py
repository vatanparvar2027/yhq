import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.stories import GetPeerStoriesRequest
from telethon.tl.types import StoryItem, MessageMediaPhoto, MessageMediaDocument
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING, DOWNLOADS_DIR

logger = logging.getLogger(__name__)

class StoryDownloaderService:
    def __init__(self):
        self.api_id = TELEGRAM_API_ID
        self.api_hash = TELEGRAM_API_HASH
        self.session_str = TELEGRAM_SESSION_STRING
        self._client: Optional[TelegramClient] = None
        self._is_connected = False
        self._lock = asyncio.Lock()

    def is_configured(self) -> bool:
        """Sessiya kaliti o'rnatilganligini tekshirish"""
        return bool(self.session_str and len(self.session_str) > 20)

    async def get_client(self) -> Optional[TelegramClient]:
        """Telethon mijozini olish va ulash"""
        if not self.is_configured():
            return None

        async with self._lock:
            if self._client is None or not self._is_connected:
                try:
                    self._client = TelegramClient(
                        StringSession(self.session_str),
                        self.api_id,
                        self.api_hash,
                        timeout=15
                    )
                    await self._client.connect()
                    if await self._client.is_user_authorized():
                        self._is_connected = True
                        logger.info("✅ Telethon Userbot sessiyasi muvaffaqiyatli ulandi!")
                    else:
                        logger.warning("⚠️ Telethon Userbot sessiyasi avtorizatsiyadan o'tmagan yoki muddati tugagan.")
                        self._is_connected = False
                        return None
                except Exception as e:
                    logger.error(f"Telethon ulanishida xatolik: {e}")
                    self._is_connected = False
                    return None

        return self._client

    async def fetch_user_stories(self, target: Any) -> Optional[List[Dict[str, Any]]]:
        """
        Foydalanuvchi yoki kontaktning barcha faol istoriyalarini yashirincha (ReadStories yubormasdan) olish.
        target: username (str), phone (str), user_id (int)
        """
        client = await self.get_client()
        if not client:
            return None

        try:
            # 1. Foydalanuvchini aniqlaymiz
            entity = await client.get_input_entity(target)
            # 2. Istoriyalarni so'raymiz (ReadStories chaqirilmaydi — 100% yashirincha / anonim!)
            result = await client(GetPeerStoriesRequest(peer=entity))
            if not result or not hasattr(result, 'stories') or not result.stories:
                return []

            peer_stories = result.stories
            story_items = getattr(peer_stories, 'stories', [])

            stories_data = []
            for s in story_items:
                if not isinstance(s, StoryItem):
                    continue

                story_id = s.id
                caption = s.caption or ""
                date = s.date
                is_video = False

                # Mediani aniqlash
                if s.media:
                    if isinstance(s.media, MessageMediaDocument):
                        is_video = True

                    stories_data.append({
                        'id': story_id,
                        'caption': caption,
                        'date': date,
                        'is_video': is_video,
                        'story_obj': s
                    })

            # Boshidan oxirigacha (eski tarixdan yangisiga qarab yoki tartib bilan)
            stories_data.sort(key=lambda x: x['id'])
            return stories_data
        except Exception as e:
            logger.error(f"Istoriyalarni olishda xatolik ({target}): {e}")
            return None

    async def download_story_media(self, story_item: Any, output_filename: str) -> Optional[str]:
        """Istoriya faylini (rasm yoki video) yuklab olish"""
        client = await self.get_client()
        if not client:
            return None

        try:
            file_path = str(DOWNLOADS_DIR / output_filename)
            path = await client.download_media(story_item.media, file=file_path)
            return path
        except Exception as e:
            logger.error(f"Istoriya mediasini yuklab olishda xatolik: {e}")
            return None

# Yagona xizmat nusxasi
story_service = StoryDownloaderService()
