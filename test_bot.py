import asyncio
import os
import sys

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Test script
async def test_all():
    print("1. Konfiguratsiyani tekshirish...")
    import config
    print(f"   FFMPEG_PATH: {config.FFMPEG_PATH}")
    print(f"   Mavjudligi: {os.path.exists(config.FFMPEG_PATH)}")

    print("\n2. Ma'lumotlar bazasini tekshirish...")
    from database.db import db
    await db.init_db()
    stats = await db.get_stats()
    print(f"   Baza ishga tushdi: {stats}")

    print("\n3. Qidiruv xizmatini tekshirish (yt-dlp)...")
    from services.music_search import music_service
    results = await music_service.search("Yulduz Usmonova", limit=3)
    print(f"   Topilgan natijalar soni: {len(results)}")
    for r in results:
        print(f"   - {r['title']} [{r['duration_str']}] (ID: {r['id']})")

    print("\n4. Shazam xizmatini tekshirish...")
    from services.shazam_service import shazam_service
    print(f"   Shazam instansiyasi: {type(shazam_service.shazam)}")

    print("\n5. Routerlar va handlerni tekshirish...")
    from handlers.start import start_router
    from handlers.search import search_router
    from handlers.shazam import shazam_router
    from handlers.inline import inline_router
    from handlers.admin import admin_router
    print("   Barcha routerlar xatosiz import bo'ldi!")

    print("\n✅ Barcha tizimlar muvaffaqiyatli tekshirildi!")

if __name__ == "__main__":
    asyncio.run(test_all())
