import os
import time
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from shazamio import Shazam

from config import FFMPEG_PATH, DOWNLOADS_DIR

logger = logging.getLogger(__name__)

class ShazamService:
    def __init__(self):
        self.shazam = Shazam()
        self.ffmpeg_bin = self._find_ffmpeg()

    def _find_ffmpeg(self) -> str:
        """FFmpeg dasturining to'liq yo'lini aniqlash"""
        if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
            exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            direct_candidate = os.path.join(FFMPEG_PATH, exe_name)
            if os.path.exists(direct_candidate):
                return direct_candidate
            if os.path.isfile(FFMPEG_PATH):
                return FFMPEG_PATH

        import shutil
        system_ffmpeg = shutil.which("ffmpeg")
        return system_ffmpeg or "ffmpeg"

    def _prepare_audio_snippet(self, input_path: str, output_path: str, start_sec: int = 0, duration: int = 15) -> bool:
        """
        FFmpeg yordamida audio/video/ogg fayldan 15 soniyalik 44100Hz mono audio parcha tayyorlash.
        Bu Shazam uchun eng maqbul, tezkor va aniq format hisoblanadi.
        """
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-ss", str(start_sec),
            "-i", input_path,
            "-t", str(duration),
            "-vn",
            "-acodec", "libmp3lame" if input_path.endswith(".mp3") else "pcm_s16le",
            "-ar", "44100",
            "-ac", "1",
            output_path
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            return res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000
        except Exception as e:
            logger.warning(f"FFmpeg snippet tayyorlashda xatolik: {e}")
            return False

    async def recognize_song(self, audio_path: str) -> Optional[Dict[str, Any]]:
        """
        Ovozli xabar, video yoki audio fayl orqali qo'shiqni aniqlash (FFmpeg optimallashtirish bilan)
        """
        if not os.path.exists(audio_path):
            return None

        # 1. FFmpeg orqali audio parchalarini tayyorlaymiz (boshidan va o'rtasidan)
        snippet_ext = ".wav"
        snippet_path = str(DOWNLOADS_DIR / f"snippet_{os.path.basename(audio_path).split('.')[0]}{snippet_ext}")
        snippet_mid_path = str(DOWNLOADS_DIR / f"snippet_mid_{os.path.basename(audio_path).split('.')[0]}{snippet_ext}")

        prep_success = await asyncio.to_thread(self._prepare_audio_snippet, audio_path, snippet_path, 0, 15)
        target_to_shazam = snippet_path if prep_success else audio_path

        out = None
        try:
            # 1-urinish: boshlang'ich 15 soniya yoki original fayl
            out = await self.shazam.recognize(target_to_shazam)

            # Agar topilmasa va fayl uzun bo'lsa, 5-soniyadan keyingi qismini tekshiramiz
            if (not out or 'track' not in out) and prep_success:
                prep_mid = await asyncio.to_thread(self._prepare_audio_snippet, audio_path, snippet_mid_path, 5, 15)
                if prep_mid:
                    out = await self.shazam.recognize(snippet_mid_path)

            # Agar hali ham topilmasa va original fayl bilan urinilmagan bo'lsa
            if (not out or 'track' not in out) and target_to_shazam != audio_path:
                out = await self.shazam.recognize(audio_path)

        except Exception as e:
            logger.error(f"Shazam recognize jarayonida xatolik: {e}")
        finally:
            # Vaqtinchalik snippetlarni tozalash
            for sp in [snippet_path, snippet_mid_path]:
                if os.path.exists(sp):
                    try:
                        os.remove(sp)
                    except Exception:
                        pass

        if not out or 'track' not in out:
            logger.info(f"Shazam orqali qo'shiq topilmadi ({audio_path})")
            return None

        track = out['track']
        title = track.get('title', "Noma'lum")
        artist = track.get('subtitle', "Noma'lum ijrochi")
        
        # Eng yuqori sifatli rasmni (cover) olish
        images = track.get('images', {})
        cover = images.get('coverarthq') or images.get('coverart') or images.get('background')
        
        genres = track.get('genres', {}).get('primary', 'Musiqa')

        # Apple music yoki Shazam link
        share_url = track.get('url') or track.get('share', {}).get('href')

        return {
            'title': title,
            'artist': artist,
            'query': f"{artist} - {title}".strip(),
            'cover': cover,
            'genre': genres,
            'share_url': share_url
        }

# Yagona xizmat nusxasi
shazam_service = ShazamService()
