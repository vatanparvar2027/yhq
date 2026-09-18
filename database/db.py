import asyncio
import aiosqlite
from datetime import datetime
from typing import Optional, Dict, Any, List
from config import DATABASE_PATH

class Database:
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = str(db_path)
        # 0ms tezkor xotira (RAM) keshi
        self._ram_cache: Dict[str, Dict[str, Any]] = {}

    async def init_db(self):
        """Ma'lumotlar bazasi jadvallarini yaratish va WAL rejimini yoqish"""
        async with aiosqlite.connect(self.db_path) as db:
            # Tezlikni 10-50 barobarga oshiruvchi SQLite optimallashtirishlari
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA synchronous = NORMAL;")
            await db.execute("PRAGMA temp_store = MEMORY;")
            await db.execute("PRAGMA cache_size = 10000;")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS music_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT UNIQUE,
                    file_id TEXT NOT NULL,
                    title TEXT,
                    performer TEXT,
                    duration INTEGER,
                    download_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS search_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    query TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Kanallar jadvalini xavfsiz kengaytirish (migratsiya)
            for col in ["chat_id TEXT", "title TEXT", "invite_link TEXT"]:
                try:
                    await db.execute(f"ALTER TABLE channels ADD COLUMN {col};")
                except Exception:
                    pass

            await db.commit()

            # Barcha oldin yuklangan musiqalarni RAM keshiga yuklab olamiz (0ms tezlik uchun)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT video_id, file_id, title, performer, duration, download_count FROM music_cache")
            rows = await cursor.fetchall()
            for r in rows:
                self._ram_cache[r['video_id']] = {
                    'video_id': r['video_id'],
                    'file_id': r['file_id'],
                    'title': r['title'],
                    'performer': r['performer'],
                    'duration': r['duration'],
                    'download_count': r['download_count']
                }

    def is_cached(self, video_id: str) -> bool:
        """Musiqa tezkor RAM keshida bormi (0ms)"""
        return video_id in self._ram_cache

    def get_cached_ids(self) -> set:
        """Barcha keshdagi video_id lar to'plami"""
        return set(self._ram_cache.keys())

    def clear_ram_cache(self) -> int:
        """RAM keshini tozalash"""
        count = len(self._ram_cache)
        self._ram_cache.clear()
        return count

    async def add_channel(self, username: str, chat_id: Optional[str] = None, title: Optional[str] = None, invite_link: Optional[str] = None) -> bool:
        """Majburiy obuna kanalini qo'shish"""
        username = username.strip()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO channels (username, chat_id, title, invite_link)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        chat_id = COALESCE(excluded.chat_id, channels.chat_id),
                        title = COALESCE(excluded.title, channels.title),
                        invite_link = COALESCE(excluded.invite_link, channels.invite_link)
                """, (username, str(chat_id) if chat_id else None, title, invite_link))
                await db.commit()
                return True
        except Exception:
            return False

    async def delete_channel(self, username: str) -> bool:
        """Kanalni o'chirish"""
        username = username.strip()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM channels WHERE username = ? OR chat_id = ?", (username, username))
                await db.commit()
                return True
        except Exception:
            return False

    async def get_db_channels(self) -> List[str]:
        """Bazadagi majburiy kanallar ro'yxati (username yoki havola)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("SELECT username FROM channels")
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        except Exception:
            return []

    async def get_db_channels_full(self) -> List[Dict[str, Any]]:
        """Bazadagi barcha kanallarni to'liq ma'lumotlari bilan olish"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT id, username, chat_id, title, invite_link FROM channels")
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    async def add_or_update_user(self, user_id: int, full_name: str, username: Optional[str]):
        """Foydalanuvchini bazaga qo'shish yoki faolligini yangilash"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO users (user_id, full_name, username, last_active)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        full_name = excluded.full_name,
                        username = excluded.username,
                        last_active = CURRENT_TIMESTAMP
                """, (user_id, full_name, username))
                await db.commit()
        except Exception:
            pass

    async def _increment_download(self, video_id: str):
        """Orqa fonda yuklashlar hisoblagichini oshirish"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE music_cache SET download_count = download_count + 1 WHERE video_id = ?", (video_id,))
                await db.commit()
        except Exception:
            pass

    async def get_cached_music(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Keshdan musiqa ma'lumotlarini olish (RAM keshidan 0ms da beradi)"""
        if video_id in self._ram_cache:
            cached = dict(self._ram_cache[video_id])
            asyncio.create_task(self._increment_download(video_id))
            return cached

        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT file_id, title, performer, duration, download_count
                    FROM music_cache WHERE video_id = ?
                """, (video_id,))
                row = await cursor.fetchone()
                if row:
                    data = dict(row)
                    data['video_id'] = video_id
                    self._ram_cache[video_id] = data
                    asyncio.create_task(self._increment_download(video_id))
                    return data
        except Exception:
            pass
        return None

    async def save_music_cache(self, video_id: str, file_id: str, title: str, performer: str, duration: int):
        """Yuklangan musiqani keshga saqlash"""
        self._ram_cache[video_id] = {
            'video_id': video_id,
            'file_id': file_id,
            'title': title,
            'performer': performer,
            'duration': duration,
            'download_count': 1
        }
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO music_cache (video_id, file_id, title, performer, duration)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        file_id = excluded.file_id,
                        title = excluded.title,
                        performer = excluded.performer,
                        duration = excluded.duration
                """, (video_id, file_id, title, performer, duration))
                await db.commit()
        except Exception:
            pass

    async def log_search(self, user_id: int, query: str):
        """Qidiruv so'rovini qayd etish"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO search_queries (user_id, query) VALUES (?, ?)
                """, (user_id, query))
                await db.commit()
        except Exception:
            pass

    async def get_stats(self) -> Dict[str, Any]:
        """Admin uchun batafsil statistika"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor_users = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await cursor_users.fetchone())[0]

            cursor_today = await db.execute("SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')")
            today_users = (await cursor_today.fetchone())[0]

            cursor_active_today = await db.execute("SELECT COUNT(*) FROM users WHERE date(last_active) = date('now')")
            active_today = (await cursor_active_today.fetchone())[0]

            cursor_cache = await db.execute("SELECT COUNT(*), COALESCE(SUM(download_count), 0) FROM music_cache")
            cache_row = await cursor_cache.fetchone()
            cached_songs = cache_row[0]
            total_downloads = cache_row[1]

            cursor_queries = await db.execute("SELECT COUNT(*) FROM search_queries")
            total_queries = (await cursor_queries.fetchone())[0]

            return {
                "total_users": total_users,
                "today_users": today_users,
                "active_today": active_today,
                "cached_songs": cached_songs,
                "total_downloads": total_downloads,
                "total_queries": total_queries,
                "ram_cached": len(self._ram_cache)
            }

    async def get_all_user_ids(self) -> List[int]:
        """Barcha foydalanuvchilar ID ro'yxatini olish"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT user_id FROM users")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

# Yagona db nusxasi
db = Database()
