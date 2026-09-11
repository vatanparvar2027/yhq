from typing import List, Dict, Any, Optional, Set
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def build_search_keyboard(results: List[Dict[str, Any]], page: int = 0, per_page: int = 6, cached_ids: Optional[Set[str]] = None) -> InlineKeyboardMarkup:
    """Qidiruv natijalari uchun sahifalangan tezkor inline klaviatura"""
    start_idx = page * per_page
    end_idx = start_idx + per_page
    current_items = results[start_idx:end_idx]

    buttons = []
    # Har bir qo'shiq / konsert uchun alohida tugma
    for i, item in enumerate(current_items, start=start_idx + 1):
        title = item.get('title', 'Musiqa')
        video_id = item.get('id', '')
        is_concert = item.get('is_concert', False)

        # Belgi: Konsert bo'lsa 🎬, keshda bo'lsa ⚡️, oddiy bo'lsa 🎵
        if is_concert:
            icon = "🎬 "
        elif cached_ids and video_id in cached_ids:
            icon = "⚡️ "
        else:
            icon = "🎵 "

        display_text = f"{icon}{i}. {title[:32]} ({item.get('duration_str', '00:00')})"
        buttons.append([
            InlineKeyboardButton(text=display_text, callback_data=f"dl:{video_id}")
        ])

    # Sahifalash (Pagination) tugmalari
    total_pages = max(1, (len(results) + per_page - 1) // per_page)
    nav_row = []

    # Birinchi sahifaga sakrash
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⏪ 1", callback_data="page:0"))

    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"page:{page - 1}"))

    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

    if end_idx < len(results):
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"page:{page + 1}"))

    # Oxirgi sahifaga sakrash
    if page < total_pages - 2:
        nav_row.append(InlineKeyboardButton(text=f"{total_pages} ⏩", callback_data=f"page:{total_pages - 1}"))

    if nav_row:
        buttons.append(nav_row)

    # Qidiruvni yopish yoki do'stlarga ulashish
    buttons.append([
        InlineKeyboardButton(text="🔍 Guruhda qidirish", switch_inline_query_current_chat=""),
        InlineKeyboardButton(text="❌ Yopish", callback_data="close_search")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_audio_keyboard(video_id: str, title: str) -> InlineKeyboardMarkup:
    """Musiqa yuborilganda ostida chiqadigan qulay tugmalar"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Do'stlarga ulashish", switch_inline_query=title[:30]),
            InlineKeyboardButton(text="❤️ Sevimlilar", callback_data=f"fav:{video_id}")
        ],
        [
            InlineKeyboardButton(text="🎬 Video sifatida yuklash (HD)", callback_data=f"dl_as_video:{video_id}")
        ]
    ])

def get_channel_sub_keyboard(channels: List[str]) -> InlineKeyboardMarkup:
    """Majburiy a'zo bo'lish tugmalari"""
    buttons = []
    for i, ch in enumerate(channels, start=1):
        url = f"https://t.me/{ch.lstrip('@')}" if not ch.startswith("http") else ch
        buttons.append([InlineKeyboardButton(text=f"➕ {i}-kanalga a'zo bo'lish", url=url)])

    buttons.append([InlineKeyboardButton(text="✅ A'zo bo'ldim / Tekshirish", callback_data="check_subscription")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Admin panel asosiy inline klaviaturasi"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Batafsil Statistika", callback_data="admin_stats"),
            InlineKeyboardButton(text="📢 Xabar tarqatish", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton(text="📢 Kanallar (Majburiy obuna)", callback_data="admin_channels"),
            InlineKeyboardButton(text="🔄 Keshni tozalash", callback_data="admin_clear_cache")
        ],
        [
            InlineKeyboardButton(text="❌ Yopish", callback_data="admin_close")
        ]
    ])

def get_admin_channels_keyboard(channels: List[str]) -> InlineKeyboardMarkup:
    """Kanallarni boshqarish inline klaviaturasi"""
    buttons = []
    # Mavjud kanallar uchun o'chirish tugmalari
    for ch in channels:
        buttons.append([
            InlineKeyboardButton(text=f"❌ O'chirish: {ch}", callback_data=f"del_ch:{ch}")
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_ch"),
        InlineKeyboardButton(text="🔄 Yangilash", callback_data="admin_channels")
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Admin Panelga qaytish", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_admin_keyboard() -> InlineKeyboardMarkup:
    """Orqaga qaytish tugmasi"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Admin Panelga qaytish", callback_data="admin_home")]
    ])

def get_media_choice_keyboard(url_key: str, available_heights: Optional[List[int]] = None) -> InlineKeyboardMarkup:
    """Havola orqali MP3 yoki Video (4K gacha) sifatini tanlash menyusi"""
    buttons = [
        [
            InlineKeyboardButton(text="🎵 MP3 (Audio yuklab olish)", callback_data=f"dl_url_audio:{url_key}")
        ]
    ]

    video_row_1 = []
    # 4K (2160p) yoki 1440p mavjud bo'lsa
    if available_heights and any(h >= 2160 for h in available_heights):
        video_row_1.append(InlineKeyboardButton(text="🎬 4K Ultra HD (2160p)", callback_data=f"dl_url_video:{url_key}:2160"))
    else:
        video_row_1.append(InlineKeyboardButton(text="🎬 4K / Eng yuqori", callback_data=f"dl_url_video:{url_key}:2160"))

    video_row_1.append(InlineKeyboardButton(text="🎬 1080p Full HD", callback_data=f"dl_url_video:{url_key}:1080"))
    buttons.append(video_row_1)

    video_row_2 = [
        InlineKeyboardButton(text="🎬 720p HD", callback_data=f"dl_url_video:{url_key}:720"),
        InlineKeyboardButton(text="🎬 480p (Tezkor)", callback_data=f"dl_url_video:{url_key}:480")
    ]
    buttons.append(video_row_2)

    buttons.append([
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="close_search")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


