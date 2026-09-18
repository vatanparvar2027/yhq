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

URL_FINDER_REGEX = re.compile(
    r'(https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b[-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
    re.IGNORECASE
)

URL_REGEX = re.compile(
    r'^(?:http|ftp)s?://' # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
    r'localhost|' # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
    r'(?::\d+)?' # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,uz;q=0.8',
    'Sec-Fetch-Mode': 'navigate',
}

def clean_url(url: str) -> str:
    """
    Havolani keraksiz tracking va statistika parametrlaridan (stkn, igsh, si, utm_* va b.) tozalash.
    Instagram, YouTube, TikTok va b. platformalarda yuklash barqarorligini oshiradi.
    """
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    # Oxiridagi ortiqcha tinish belgilarini olib tashlaymiz
    url = re.sub(r'[\.,;:!?\)\>\]\'"»«]+$', '', url)
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()

        # Instagram havolalari (/reel/..., /p/..., /reels/..., /tv/...)
        if any(d in netloc for d in ["instagram.com", "instagr.am", "ddinstagram.com"]):
            path = parsed.path
            if not path.endswith('/'):
                path += '/'
            return urlunparse((parsed.scheme or "https", parsed.netloc, path, '', '', ''))

        # YouTube havolalari
        elif "youtu.be" in netloc:
            return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, '', '', ''))
        elif "youtube.com" in netloc:
            if "/shorts/" in parsed.path:
                return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, '', '', ''))
            elif "/watch" in parsed.path:
                qs = parse_qs(parsed.query)
                v = qs.get('v')
                if v:
                    new_query = urlencode({'v': v[0]})
                    return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, '', new_query, ''))

        # TikTok havolalari
        elif "tiktok.com" in netloc:
            return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, '', '', ''))

        # Boshqa platformalar uchun keraksiz tracking parametrlarini olib tashlash
        qs = parse_qs(parsed.query)
        tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid', 'si', 'igsh', 'stkn'}
        filtered_qs = {k: v for k, v in qs.items() if k.lower() not in tracking_params}
        new_query = urlencode(filtered_qs, doseq=True) if filtered_qs else ''
        return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, '', new_query, ''))
    except Exception:
        return url

def extract_url(text: str) -> Optional[str]:
    """
    Har qanday xabar matni, izoh (caption), heshteglar yoki repost ichidan havolani ajratib oladi va tozalaydi.
    """
    if not text or not isinstance(text, str):
        return None
    # 1. Regex orqali xabar ichidan havolani izlaymiz
    match = URL_FINDER_REGEX.search(text)
    if match:
        found = match.group(1).strip()
        if found.startswith("www."):
            found = "https://" + found
        return clean_url(found)
    # 2. Agar butun matn to'g'ridan-to'g'ri URL bo'lsa
    if URL_REGEX.match(text.strip()):
        return clean_url(text.strip())
    return None

def is_url(text: str) -> bool:
    """Matnda to'g'ri havola bor yoki yo'qligini tekshirish"""
    return extract_url(text) is not None

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
            'socket_timeout': 20,
            'http_headers': DEFAULT_HEADERS,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            },
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

    def _sync_download(self, target: str, output_id: str, fallback_query: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Tezlashtirilgan ko'p oqimli yuklab olish, FFmpeg konvertatsiya va Smart Fallback tizimi.
        Agar asosiy target (video_id) cheklangan bo'lsa, fallback_query orqali avtomatik zaxira qidiradi.
        """
        output_template = str(DOWNLOADS_DIR / f"{output_id}.%(ext)s")
        expected_mp3 = str(DOWNLOADS_DIR / f"{output_id}.mp3")
        clean_target = clean_url(target) if is_url(target) else target
        url = clean_target if is_url(clean_target) else f"https://www.youtube.com/watch?v={clean_target}"
        is_yt = any(d in url.lower() for d in ["youtube.com", "youtu.be"])

        def build_dl_opts(clients: Optional[list] = None, with_ffmpeg: bool = True):
            opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best',
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': False,
                'noplaylist': True,
                'nocheckcertificate': True,
                'socket_timeout': 30,
                'retries': 3,
                'fragment_retries': 3,
            }
            if clients:
                opts['extractor_args'] = {
                    'youtube': {
                        'player_client': clients
                    }
                }
            if with_ffmpeg:
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
                opts['postprocessor_args'] = {
                    'FFmpegExtractAudio': ['-threads', '4']
                }
                if self.ffmpeg_location:
                    opts['ffmpeg_location'] = self.ffmpeg_location
            return opts

        attempts = []
        if is_yt:
            attempts.append((build_dl_opts(['ios'], with_ffmpeg=True), "ios_mp3"))
            attempts.append((build_dl_opts(['android'], with_ffmpeg=True), "android_mp3"))
            attempts.append((build_dl_opts(['mweb'], with_ffmpeg=True), "mweb_mp3"))
            attempts.append((build_dl_opts(['web'], with_ffmpeg=True), "web_mp3"))
            attempts.append((build_dl_opts(['android'], with_ffmpeg=False), "android_raw"))
        else:
            attempts.append((build_dl_opts(None, with_ffmpeg=True), "platform_native_mp3"))
            attempts.append((build_dl_opts(None, with_ffmpeg=False), "platform_raw"))

        info = None
        for opts, mode in attempts:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info:
                        break
            except Exception as e:
                logger.warning(f"Audio yuklashda ({mode}) xatosi: {e}")
                continue

        # Smart Fallback: agar asosiy URL yuklanmasa va fallback_query bo'lsa
        if not info and fallback_query:
            logger.info(f"Smart Fallback ishga tushdi: «{fallback_query}» bo'yicha zaxira qidirilmoqda...")
            fallback_opts = build_dl_opts(['ios', 'android'], with_ffmpeg=True)
            fallback_opts['noplaylist'] = False
            try:
                with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                    fallback_info = ydl.extract_info(f"ytsearch3:{fallback_query} audio", download=True)
                    if fallback_info and 'entries' in fallback_info:
                        for entry in fallback_info['entries']:
                            if entry:
                                info = entry
                                logger.info(f"Smart Fallback muvaffaqiyatli topdi: {entry.get('title')}")
                                break
            except Exception as fe:
                logger.warning(f"Smart Fallback xatosi: {fe}")

        if not info:
            logger.error(f"Barcha audio yuklab olish urinishlari muvaffaqiyatsiz bo'ldi ({target})")
            return None

        if 'entries' in info:
            entries = [e for e in info['entries'] if e]
            if not entries:
                return None
            info = entries[0]

        video_id = info.get('id') or output_id
        raw_title = info.get('title') or info.get('description') or "Musiqa"
        first_line = raw_title.strip().split('\n')[0].strip()
        display_title = clean_title(first_line)
        if len(display_title) > 80:
            display_title = display_title[:77] + "..."
        artist = (info.get('artist') or info.get('uploader') or "Noma'lum").replace(" - Topic", "").strip()
        duration = int(info.get('duration') or 0)
        thumb_url = info.get('thumbnail')

        mp3_path = expected_mp3
        if not os.path.exists(mp3_path):
            for ext in ['.mp3', '.m4a', '.webm', '.ogg', '.opus', '.mp4']:
                alt = str(DOWNLOADS_DIR / f"{output_id}{ext}")
                if os.path.exists(alt):
                    mp3_path = alt
                    break

        if not os.path.exists(mp3_path):
            logger.error(f"Yuklab olingan fayl topilmadi: {output_id}")
            return None

        file_size = os.path.getsize(mp3_path)
        MAX_TELEGRAM_AUDIO_BYTES = 49 * 1024 * 1024  # 49 MB
        if file_size > MAX_TELEGRAM_AUDIO_BYTES and duration > 0:
            logger.info(f"Katta audio fayl: {round(file_size / (1024 * 1024), 1)} MB ({duration}s). 49MB ichiga siqish...")
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
            'title': display_title or "Musiqa",
            'artist': artist,
            'duration': duration,
            'thumbnail_url': thumb_url
        }

    async def download(
        self,
        target: str,
        output_id: str,
        thumb_url_hint: Optional[str] = None,
        fallback_query: Optional[str] = None,
        cover_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Asinxron yuklab olish + Smart Fallback + HD muqova va ID3 teglash
        """
        data = await asyncio.to_thread(self._sync_download, target, output_id, fallback_query)
        if not data or not os.path.exists(data['file_path']):
            return None

        chosen_cover_path = None
        temp_cover_file = None
        if cover_url and cover_url.startswith("http"):
            try:
                temp_cover_file = str(DOWNLOADS_DIR / f"cover_{output_id}.jpg")
                async with aiohttp.ClientSession() as session:
                    async with session.get(cover_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            with open(temp_cover_file, "wb") as f:
                                f.write(content)
                            if os.path.exists(temp_cover_file) and os.path.getsize(temp_cover_file) > 1000:
                                chosen_cover_path = temp_cover_file
            except Exception as ce:
                logger.warning(f"Cover rasmini yuklab olishda xatolik: {ce}")

        if not chosen_cover_path:
            bot_logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot_avatar.jpg")
            if not os.path.exists(bot_logo_path):
                bot_logo_path = "bot_avatar.jpg"
            if os.path.exists(bot_logo_path):
                chosen_cover_path = bot_logo_path

        await asyncio.to_thread(
            set_mp3_tags,
            file_path=data['file_path'],
            title=data['title'],
            artist="@ChiroqchiMuzbot",
            cover_path=chosen_cover_path
        )

        data['cover_path'] = chosen_cover_path
        data['temp_cover'] = temp_cover_file
        return data

    async def download_by_query(
        self,
        query: str,
        output_id: str,
        cover_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        To'g'ridan-to'g'ri qo'shiq nomi bo'yicha eng yaxshi audioni topib yuklash (Shazam uchun tezkor)
        """
        search_results = await self.search(query, limit=3)
        target = None
        thumb_hint = None
        if search_results:
            target = search_results[0]['id']
            thumb_hint = search_results[0].get('thumbnail')
        else:
            target = f"ytsearch1:{query}"

        return await self.download(
            target=target,
            output_id=output_id,
            thumb_url_hint=thumb_hint,
            fallback_query=query,
            cover_url=cover_url
        )

    def _sync_get_media_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Havola haqida tezkor ma'lumot olish (YouTube, TikTok, Instagram va boshqa platformalar)"""
        clean_target_url = clean_url(url)
        is_yt = any(d in clean_target_url.lower() for d in ["youtube.com", "youtu.be"])

        def make_opts(player_clients=None, headers=None):
            opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'ignoreerrors': False,
                'nocheckcertificate': True,
                'socket_timeout': 30,
            }
            if headers:
                opts['http_headers'] = headers
            if player_clients:
                opts['extractor_args'] = {
                    'youtube': {
                        'player_client': player_clients
                    }
                }
            if self.ffmpeg_location:
                opts['ffmpeg_location'] = self.ffmpeg_location
            return opts

        attempts = []
        if is_yt:
            attempts.append(make_opts(['android'], headers=DEFAULT_HEADERS))
            attempts.append(make_opts(['android_creator'], headers=DEFAULT_HEADERS))
            attempts.append(make_opts(None, headers=DEFAULT_HEADERS))
        else:
            # Instagram, TikTok va b. platformalar: yt-dlp native headers birinchi, keyin DEFAULT_HEADERS
            attempts.append(make_opts(None, headers=None))
            attempts.append(make_opts(None, headers=DEFAULT_HEADERS))

        info = None
        for opts in attempts:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(clean_target_url, download=False)
                    if info:
                        break
            except Exception as e:
                logger.warning(f"Media ma'lumotini olishda ogohlantirish ({clean_target_url}): {e}")
                continue

        if not info:
            logger.error(f"Media ma'lumoti topilmadi ({clean_target_url})")
            return None

        if 'entries' in info:
            entries = [e for e in (info.get('entries') or []) if e]
            if not entries:
                return None
            info = entries[0]

        raw_title = info.get('title') or info.get('description') or "Video"
        first_line = raw_title.strip().split('\n')[0].strip()
        display_title = clean_title(first_line)
        if len(display_title) > 80:
            display_title = display_title[:77] + "..."

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
            'title': display_title or "Media",
            'raw_title': raw_title,
            'artist': artist,
            'duration': duration,
            'duration_str': duration_str,
            'thumbnail': thumb,
            'available_heights': sorted(list(heights), reverse=True),
            'url': clean_target_url
        }

    async def get_media_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Asinxron media ma'lumoti oluvchi"""
        return await asyncio.to_thread(self._sync_get_media_info, url)

    def _sync_download_video(self, url: str, output_id: str, max_height: int = 2160) -> Optional[Dict[str, Any]]:
        """
        4K gacha (2160p, 1080p, 720p, 480p) videoni audio bilan birga yuklab olish.
        Agar so'ralgan sifat mavjud bo'lmasa, avtomatik eng yuqori mavjud sifatga tushadi.
        """
        import glob

        clean_target_url = clean_url(url)
        is_yt = any(d in clean_target_url.lower() for d in ["youtube.com", "youtu.be"])

        if max_height >= 2160:
            fmt = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[height<=2160]/bestvideo+bestaudio/best'
        elif max_height >= 1080:
            fmt = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best'
        elif max_height >= 720:
            fmt = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best'
        else:
            fmt = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/bestvideo+bestaudio/best'

        output_template = str(DOWNLOADS_DIR / f"{output_id}.%(ext)s")

        def build_video_opts(clients: Optional[list] = None, headers: Optional[dict] = None):
            ydl_opts = {
                'format': fmt,
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': False,
                'noplaylist': True,
                'nocheckcertificate': True,
                'socket_timeout': 45,
                'retries': 3,
                'postprocessor_args': {
                    'Merger': ['-threads', '4']
                }
            }
            if headers:
                ydl_opts['http_headers'] = headers
            if clients:
                ydl_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': clients
                    }
                }
            if self.ffmpeg_location:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_location
            return ydl_opts

        attempts = []
        if is_yt:
            attempts.append(build_video_opts(['android'], headers=DEFAULT_HEADERS))
            attempts.append(build_video_opts(['android_creator'], headers=DEFAULT_HEADERS))
            attempts.append(build_video_opts(None, headers=DEFAULT_HEADERS))
        else:
            attempts.append(build_video_opts(None, headers=None))
            attempts.append(build_video_opts(None, headers=DEFAULT_HEADERS))

        info = None
        for opts in attempts:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(clean_target_url, download=True)
                    if info:
                        break
            except Exception as e:
                logger.warning(f"Video yuklab olishda xatolik ({clean_target_url}): {e}")
                continue

        if not info:
            return None
        if 'entries' in info:
            entries = [e for e in (info['entries'] or []) if e]
            if not entries:
                return None
            info = entries[0]

        try:
            raw_title = info.get('title') or info.get('description') or "Video"
            first_line = raw_title.strip().split('\n')[0].strip()
            display_title = clean_title(first_line)
            if len(display_title) > 80:
                display_title = display_title[:77] + "..."

            duration = int(info.get('duration') or 0)
            thumb = info.get('thumbnail')
            width = info.get('width')
            height = info.get('height')

            # Yuklab olingan faylni topish
            mp4_files = glob.glob(str(DOWNLOADS_DIR / f"{output_id}.mp4"))
            if not mp4_files:
                all_files = glob.glob(str(DOWNLOADS_DIR / f"{output_id}.*"))
                video_exts = {'.mp4', '.mkv', '.webm', '.avi', '.mov'}
                mp4_files = [f for f in all_files if os.path.splitext(f)[1].lower() in video_exts]

            if not mp4_files:
                logger.error(f"Yuklab olingan video fayl topilmadi: {output_id}")
                return None

            video_path = mp4_files[0]
            file_size = os.path.getsize(video_path)

            if file_size < 1024:  # 1KB dan kichik bo'lsa yaroqsiz
                logger.error(f"Yuklab olingan video fayl juda kichik ({file_size} bytes): {video_path}")
                try:
                    os.remove(video_path)
                except Exception:
                    pass
                return None

            return {
                'file_path': video_path,
                'title': display_title or "Video",
                'duration': duration,
                'width': width or 1280,
                'height': height or 720,
                'file_size': file_size,
                'thumbnail_url': thumb
            }
        except Exception as e:
            logger.error(f"Videoni yuklashda xatolik ({clean_target_url}, {max_height}p): {e}")
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
