from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Asosiy menyu tugmalari"""
    keyboard = [
        [
            KeyboardButton(text="🔍 Musiqa qidirish"),
            KeyboardButton(text="🎙 Shazam (Ovozdan topish)")
        ],
        [
            KeyboardButton(text="🔝 Trend musiqalar"),
            KeyboardButton(text="📸 Istoriya yuklash")
        ],
        [
            KeyboardButton(text="ℹ️ Bot haqida / Yordam")
        ]
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="⚙️ Admin Panel")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Qo'shiq nomi yoki ijrochisini yozing..."
    )
