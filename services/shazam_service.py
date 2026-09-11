import os
import logging
from typing import Optional, Dict, Any
from shazamio import Shazam

logger = logging.getLogger(__name__)

class ShazamService:
    def __init__(self):
        self.shazam = Shazam()

    async def recognize_song(self, audio_path: str) -> Optional[Dict[str, Any]]:
        """
        Ovozli xabar yoki audio fayl orqali qo'shiqni aniqlash
        """
        try:
            if not os.path.exists(audio_path):
                return None

            out = await self.shazam.recognize(audio_path)
            if not out or 'track' not in out:
                logger.info(f"Shazam orqali qo'shiq topilmadi ({audio_path})")
                return None

            track = out['track']
            title = track.get('title', "Noma'lum")
            artist = track.get('subtitle', "Noma'lum ijrochi")
            cover = track.get('images', {}).get('coverart')
            genres = track.get('genres', {}).get('primary')

            return {
                'title': title,
                'artist': artist,
                'query': f"{artist} - {title}".strip(),
                'cover': cover,
                'genre': genres
            }
        except Exception as e:
            logger.error(f"Shazam xizmatida xatolik ({audio_path}): {e}")
            return None

# Yagona xizmat nusxasi
shazam_service = ShazamService()
