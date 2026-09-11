import os
import re
import time
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import aiohttp
import yt_dlp

from config import DOWNLOADS_DIR, FFMPEG_PATH
from services.audio_tagger import set_mp3_tags

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(
    r'^(?:http|ftp)s?://' # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
    r'localhost|' # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
    r'(?::\d+)?' # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)

def is_url(text: str) -> bool:
    """Matn havola (URL) ekanligini tekshirish"""
    return bool(URL_REGEX.match(text.strip()))

def format_duration(seconds: Optional[int]) -> str:
    """Soniyani MM:SS yoki HH:MM:SS formatiga o'tkazish"""
    if not seconds or not isinstance(seconds, (int, float)):
        return "00:00"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def clean_title(raw_title: str) -> str:
    """Nomi ichidagi ortiqcha so'zlarni tozalash"""
    if not raw_title:
        return "Musiqa"
    cleaned = re.sub(r'[\(\[\{].*?(?:official|video|audio|klip|clip|lyric|hd|hq|4k|remix|premiera).*?[\)\]\}]', '', raw_title, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    return cleaned if cleaned else raw_title

def is_concert_item(title: str, duration: int) -> bool:
    """Konsert dasturi yoki to'liq musiqiy to'plam ekanligini aniqlash"""
    t = (title or "").lower()
    return (
        duration >= 1200 or
        "konsert" in t or
        "concert" in t or
        "to'plam" in t or
        "toplam" in t or
        "albom" in t or
        "album" in t or
        "jonli ijro" in t or
        "full album" in t
    )

class MusicSearchService:
    def __init__(self):
        self.ffmpeg_location = FFMPEG_PATH if os.path.exists(FFMPEG_PATH) else None
        # Tezkor xotira (RAM) qidiruv keshi: {norm_query: (timestamp, results)}
        self._search_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._cache_ttl = 1800 # 30 daqiqa
        # Trend musiqalar keshi
        self._trend_cache: Dict[str, Any] = {"time": 0, "results": []}
        self._trend_ttl = 3600 # 1 soat

    def _sync_search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Sinxron tezkor qidiruv (flat extraction orqali sekundda 50 tagacha natija oladi)"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'default_search': f'ytsearch{limit}',
            'skip_download': True,
            'ignoreerrors': True,
            'nocheckcertificate': True,
            'source_address': '0.0.0.0',
            'socket_timeout': 10,
        }
        if self.ffmpeg_location:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_location

        results = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                if not info or 'entries' not in info:
                    return []

                for entry in info['entries']:
                    if not entry:
                        continue
                    video_id = entry.get('id')
                    raw_title = entry.get('title') or "Noma'lum"
                    artist = entry.get('uploader') or entry.get('channel') or "Noma'lum ijrochi"
                    duration = int(entry.get('duration') or 0)
                    
                    duration_str = format_duration(duration)
                    url = entry.get('url') or f"https://www.youtube.com/watch?v={video_id}"
                    
                    # Muqova rasmi
                    thumbnails = entry.get('thumbnails')
                    thumb_url = thumbnails[-1]['url'] if thumbnails else None

                    # Konsert yoki to'liq dastur ekanligini aniqlash
                    is_concert = is_concert_item(raw_title, duration)

                    results.append({
                        'id': video_id,
                        'title': clean_title(raw_title),
                        'raw_title': raw_title,
                        'artist': artist.replace(" - Topic", "").strip(),
                        'duration': duration,
                        'duration_str': duration_str,
                        'url': url,
                        'thumbnail': thumb_url,
                        'is_concert': is_concert
                    })
        except Exception as e:
            logger.error(f"Musiqa qidirishda xatolik ({query}): {e}")

        return results

    async def search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Asinxron qidiruv (avval tezkor RAM keshidan tekshiradi - 0ms)"""
        norm_query = query.strip().lower()
        now = time.time()

        # 1. RAM keshida bormi?
        if norm_query in self._search_cache:
            cache_time, cached_res = self._search_cache[norm_query]
            if now - cache_time < self._cache_ttl and len(cached_res) >= min(limit, len(cached_res)):
                return cached_res[:limit]

        # 2. Yangi qidiruv (barcha taronalar va konsertlar olinadi)
        results = await asyncio.to_thread(self._sync_search, query, limit)
        if results:
            self._search_cache[norm_query] = (now, results)
        return results

    async def get_trending(self) -> List[Dict[str, Any]]:
        """Trend musiqalarni bir zumda olish (1 soatlik kesh orqali 0ms da beradi)"""
        now = time.time()
        if self._trend_cache["results"] and (now - self._trend_cache["time"] < self._trend_ttl):
            return self._trend_cache["results"]

        results = await self.search("Top Uzbek Music Hit 2026", limit=10)
        if not results:
            results = await self.search("Top Hits 2026", limit=10)

        if results:
            self._trend_cache["time"] = now
            self._trend_cache["results"] = results

        return results

    def _sync_download(self, target: str, output_id: str) -> Optional[Dict[str, Any]]:
        """
        Tezlashtirilgan ko'p oqimli yuklab olish va FFmpeg konvertatsiya
        """
        output_template = str(DOWNLOADS_DIR / f"{output_id}.%(ext)s")
        expected_mp3 = str(DOWNLOADS_DIR / f"{output_id}.mp3")

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 10,
            'source_address': '0.0.0.0',
            'concurrent_fragment_downloads': 4,
            'buffersize': 1024 * 1024,
            'http_chunk_size': 10485760,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web']
                }
            },
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'postprocessor_args': {
                'FFmpegExtractAudio': ['-threads', '4']
            }
        }
        if self.ffmpeg_location:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_location

        try:
            url = target if is_url(target) else f"https://www.youtube.com/watch?v={target}"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None

                if 'entries' in info:
                    entries = list(info['entries'])
                    if not entries:
                        return None
                    info = entries[0]

                video_id = info.get('id') or output_id
                raw_title = info.get('title') or "Musiqa"
                artist = (info.get('artist') or info.get('uploader') or "Noma'lum").replace(" - Topic", "").strip()
                duration = int(info.get('duration') or 0)
                thumb_url = info.get('thumbnail')

                mp3_path = expected_mp3
                if not os.path.exists(mp3_path):
                    for ext in ['.mp3', '.m4a', '.webm']:
                        alt = str(DOWNLOADS_DIR / f"{output_id}{ext}")
                        if os.path.exists(alt):
                            mp3_path = alt
                            break

                # Agar MP3 hajmi Telegram limitidan (50MB) katta bo'lsa (konsertlar), uni 46MB ga moslab siqamiz
                if os.path.exists(mp3_path):
                    file_size = os.path.getsize(mp3_path)
                    MAX_TELEGRAM_AUDIO_BYTES = 49 * 1024 * 1024  # 49 MB
                    if file_size > MAX_TELEGRAM_AUDIO_BYTES and duration > 0:
                        logger.info(f"Katta audio fayl: {round(file_size / (1024 * 1024), 1)} MB ({duration}s). 50MB ichiga optimallash...")
                        target_kbps = max(24, min(128, int((45 * 1024 * 8) / duration)))
                        compressed_mp3 = str(DOWNLOADS_DIR / f"{output_id}_opt.mp3")

                        ffmpeg_bin = "ffmpeg"
                        if self.ffmpeg_location:
                            candidate = os.path.join(self.ffmpeg_location, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
                            if os.path.exists(candidate):
                                ffmpeg_bin = candidate

                        import subprocess
                        cmd = [
                            ffmpeg_bin, "-y", "-i", mp3_path,
                            "-b:a", f"{target_kbps}k",
                            "-threads", "4",
                            compressed_mp3
                        ]
                        try:
                            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
                            if res.returncode == 0 and os.path.exists(compressed_mp3):
                                comp_size = os.path.getsize(compressed_mp3)
                                if comp_size < MAX_TELEGRAM_AUDIO_BYTES:
                                    try:
                                        os.remove(mp3_path)
                                    except Exception:
                                        pass
                                    mp3_path = compressed_mp3
                                    logger.info(f"Audio muvaffaqiyatli siqildi: {round(comp_size / (1024 * 1024), 1)} MB ({target_kbps} kbps)")
                        except Exception as comp_err:
                            logger.warning(f"Audio optimallashtirishda xatolik: {comp_err}")

                return {
                    'id': video_id,
                    'file_path': mp3_path,
                    'title': clean_title(raw_title),
                    'artist': artist,
                    'duration': duration,
                    'thumbnail_url': thumb_url
                }
        except Exception as e:
            logger.error(f"Yuklab olishda xatolik ({target}): {e}")
            return None

    async def download(self, target: str, output_id: str, thumb_url_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Asinxron yuklab olish + bot avatari bilan muqovalash
        """
        # Audio faylni yuklab olamiz
        data = await asyncio.to_thread(self._sync_download, target, output_id)
        if not data or not os.path.exists(data['file_path']):
            return None

        # Har doim botning rasmiy avatarini MP3 muqovasi (cover art) sifatida o'rnatamiz
        bot_logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot_avatar.jpg")
        if not os.path.exists(bot_logo_path):
            bot_logo_path = "bot_avatar.jpg"

        actual_thumb_path = bot_logo_path if os.path.exists(bot_logo_path) else None

        # ID3 teglarni asinxron oqimda o'rnatamiz (Artist nomiga @ChiroqchiMuzbot, muqovaga botning rasmi)
        await asyncio.to_thread(
            set_mp3_tags,
            file_path=data['file_path'],
            title=data['title'],
            artist="@ChiroqchiMuzbot",
            cover_path=actual_thumb_path
        )

        data['cover_path'] = actual_thumb_path
        return data

    def _sync_get_media_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Havola haqida tezkor ma'lumot olish (title, duration, mavjud formatlar)"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'ignoreerrors': True,
            'nocheckcertificate': True,
            'socket_timeout': 10,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web']
                }
            },
        }
        if self.ffmpeg_location:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_location

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None
                if 'entries' in info:
                    entries = list(info['entries'])
                    if not entries:
                        return None
                    info = entries[0]

                raw_title = info.get('title') or "Video"
                artist = (info.get('artist') or info.get('uploader') or info.get('channel') or "Noma'lum").replace(" - Topic", "").strip()
                duration = int(info.get('duration') or 0)
                duration_str = format_duration(duration)
                thumb = info.get('thumbnail')
                video_id = info.get('id') or f"vid_{int(time.time())}"

                # Mavjud sifatlarni aniqlash
                formats = info.get('formats', [])
                heights = set()
                for f in formats:
                    h = f.get('height')
                    if h and isinstance(h, int):
                        heights.add(h)

                return {
                    'id': video_id,
                    'title': clean_title(raw_title),
                    'raw_title': raw_title,
                    'artist': artist,
                    'duration': duration,
                    'duration_str': duration_str,
                    'thumbnail': thumb,
                    'available_heights': sorted(list(heights), reverse=True),
                    'url': url
                }
        except Exception as e:
            logger.error(f"Media ma'lumotini olishda xatolik ({url}): {e}")
            return None

    async def get_media_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Asinxron media ma'lumoti oluvchi"""
        return await asyncio.to_thread(self._sync_get_media_info, url)

    def _sync_download_video(self, url: str, output_id: str, max_height: int = 2160) -> Optional[Dict[str, Any]]:
        """
        4K gacha (2160p, 1080p, 720p, 480p) videoni audio bilan birga yuklab olish.
        Agar so'ralgan sifat mavjud bo'lmasa, avtomatik eng yuqori mavjud sifatga tushadi.
        """
        import glob

        # Format tanlash zanjiri: kerakli sifat -> undan past eng yaxshi -> umumiy eng yaxshi
        if max_height >= 2160:
            fmt = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/bestvideo+bestaudio/best'
        elif max_height >= 1080:
            fmt = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/bestvideo+bestaudio/best'
        elif max_height >= 720:
            fmt = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/bestvideo+bestaudio/best'
        else:
            fmt = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/bestvideo+bestaudio/best'

        output_template = str(DOWNLOADS_DIR / f"{output_id}.%(ext)s")

        ydl_opts = {
            'format': fmt,
            'outtmpl': output_template,
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 30,
            'retries': 3,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web']
                }
            },
            'postprocessor_args': {
                'Merger': ['-threads', '4']
            }
        }
        if self.ffmpeg_location:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_location

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None
                if 'entries' in info:
                    entries = [e for e in (info['entries'] or []) if e]
                    if not entries:
                        return None
                    info = entries[0]

                raw_title = info.get('title') or "Video"
                duration = int(info.get('duration') or 0)
                thumb = info.get('thumbnail')
                width = info.get('width')
                height = info.get('height')

                # Yuklab olingan faylni topish
                mp4_files = glob.glob(str(DOWNLOADS_DIR / f"{output_id}.mp4"))
                if not mp4_files:
                    # Boshqa kengaytmalarni ham tekshiramiz
                    all_files = glob.glob(str(DOWNLOADS_DIR / f"{output_id}.*"))
                    # .jpg va .webp kabi rasm fayllarini chiqarib tashlaymiz
                    video_exts = {'.mp4', '.mkv', '.webm', '.avi', '.mov'}
                    mp4_files = [f for f in all_files if os.path.splitext(f)[1].lower() in video_exts]

                if not mp4_files:
                    logger.error(f"Yuklab olingan video fayl topilmadi: {output_id}")
                    return None

                video_path = mp4_files[0]
                file_size = os.path.getsize(video_path)

                if file_size < 1024:  # 1KB dan kichik bo'lsa yaroqsiz
                    logger.error(f"Yuklab olingan video fayl juda kichik ({file_size} bytes): {video_path}")
                    os.remove(video_path)
                    return None

                return {
                    'file_path': video_path,
                    'title': clean_title(raw_title),
                    'duration': duration,
                    'width': width or 1280,
                    'height': height or 720,
                    'file_size': file_size,
                    'thumbnail_url': thumb
                }
        except Exception as e:
            logger.error(f"Videoni yuklashda xatolik ({url}, {max_height}p): {e}")
            # Qisman yuklab olingan fayllarni tozalash
            for leftover in glob.glob(str(DOWNLOADS_DIR / f"{output_id}.*")):
                try:
                    os.remove(leftover)
                except Exception:
                    pass
            return None

    async def download_video(self, url: str, output_id: str, max_height: int = 2160) -> Optional[Dict[str, Any]]:
        """Asinxron video yuklovchi (4K gacha, agar mavjud bo'lsa)"""
        data = await asyncio.to_thread(self._sync_download_video, url, output_id, max_height)
        if not data or not os.path.exists(data['file_path']):
            return None

        thumb_path = str(DOWNLOADS_DIR / f"{output_id}_vthumb.jpg")


        if data.get('thumbnail_url'):
            success = await self._fetch_thumb(data['thumbnail_url'], thumb_path)
            if success and os.path.exists(thumb_path):
                data['cover_path'] = thumb_path
            else:
                data['cover_path'] = None
        else:
            data['cover_path'] = None

        return data

    async def _fetch_thumb(self, url: str, save_path: str) -> bool:
        """Rasmni tezkor asinxron yuklab olish"""
        try:
            timeout = aiohttp.ClientTimeout(total=4)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(save_path, 'wb') as f:
                            f.write(content)
                        return True
        except Exception:
            pass
        return False

# Yagona xizmat nusxasi
music_service = MusicSearchService()
