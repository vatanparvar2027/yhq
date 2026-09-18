import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMINS, CHANNELS
from database.db import db
from keyboards.inline_kb import (
    get_admin_keyboard,
    get_admin_channels_keyboard,
    get_back_to_admin_keyboard
)
from keyboards.reply_kb import get_main_menu

logger = logging.getLogger(__name__)
admin_router = Router()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class ChannelState(StatesGroup):
    waiting_for_channel = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

async def show_admin_panel(message: Message):
    stats = await db.get_stats()
    text = (
        "👑 <b>Admin Boshqaruv Paneliga xush kelibsiz!</b>\n\n"
        f"👥 <b>Jami foydalanuvchilar:</b> {stats['total_users']:,} ta\n"
        f"🆕 <b>Bugun qo'shilganlar:</b> {stats.get('today_users', 0):,} ta\n"
        f"⚡️ <b>Bugun faollar:</b> {stats.get('active_today', 0):,} ta\n"
        f"💾 <b>Keshdagi musiqalar:</b> {stats['cached_songs']:,} ta\n"
        f"📥 <b>Jami yuklashlar soni:</b> {stats['total_downloads']:,} ta\n"
        f"🔍 <b>Qidiruvlar soni:</b> {stats['total_queries']:,} ta\n"
        f"🚀 <b>RAM keshida:</b> {stats.get('ram_cached', 0):,} ta trek (0ms)\n\n"
        "<i>Kerakli bo'limni tanlang:</i>"
    )
    await message.answer(
        text,
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )

ADMIN_TRIGGERS = ["admin", "/admin", "panel", "/panel", "⚙️ admin panel", "admin panel", "⚙️ admin", "админ"]

@admin_router.message(Command("admin"))
@admin_router.message(Command("panel"))
async def cmd_admin_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Kechirasiz, siz bot administratori emassiz.")
        return
    await show_admin_panel(message)

@admin_router.message(F.text.lower().in_(ADMIN_TRIGGERS), F.from_user.id.in_(ADMINS))
async def cmd_admin_text(message: Message):
    await show_admin_panel(message)

@admin_router.callback_query(F.data == "admin_home")
async def cb_admin_home(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not is_admin(call.from_user.id):
        await call.message.answer("❌ Ruxsat berilmagan!")
        return

    await state.clear()
    stats = await db.get_stats()
    text = (
        "👑 <b>Admin Boshqaruv Paneli:</b>\n\n"
        f"👥 <b>Jami foydalanuvchilar:</b> {stats['total_users']:,} ta\n"
        f"🆕 <b>Bugun qo'shilganlar:</b> {stats.get('today_users', 0):,} ta\n"
        f"⚡️ <b>Bugun faollar:</b> {stats.get('active_today', 0):,} ta\n"
        f"💾 <b>Keshdagi musiqalar:</b> {stats['cached_songs']:,} ta\n"
        f"📥 <b>Jami yuklashlar:</b> {stats['total_downloads']:,} ta\n"
        f"🔍 <b>Qidiruvlar soni:</b> {stats['total_queries']:,} ta\n\n"
        "<i>Kerakli bo'limni tanlang:</i>"
    )
    await call.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")

@admin_router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    await call.answer()
    if not is_admin(call.from_user.id):
        await call.message.answer("❌ Ruxsat berilmagan!")
        return

    stats = await db.get_stats()
    text = (
        "📊 <b>Batafsil Bot Statistikasi:</b>\n\n"
        f"👥 <b>Jami a'zolar:</b> {stats['total_users']:,} ta\n"
        f"🆕 <b>Bugun yangi a'zolar:</b> {stats.get('today_users', 0):,} ta\n"
        f"⚡️ <b>Bugun faol a'zolar:</b> {stats.get('active_today', 0):,} ta\n"
        f"💾 <b>Keshdagi musiqalar soni:</b> {stats['cached_songs']:,} ta\n"
        f"📥 <b>Jami yuklab olingan musiqalar:</b> {stats['total_downloads']:,} ta\n"
        f"🔍 <b>Qidiruvlar umumiy soni:</b> {stats['total_queries']:,} ta\n"
        f"🚀 <b>Tezkor RAM keshida saqlanayotgan:</b> {stats.get('ram_cached', 0):,} ta"
    )
    await call.message.edit_text(text, reply_markup=get_back_to_admin_keyboard(), parse_mode="HTML")

@admin_router.callback_query(F.data == "admin_channels")
async def cb_admin_channels(call: CallbackQuery):
    await call.answer()
    if not is_admin(call.from_user.id):
        await call.message.answer("❌ Ruxsat berilmagan!")
        return

    db_channels = await db.get_db_channels()
    all_channels = list(dict.fromkeys(CHANNELS + db_channels))

    if all_channels:
        ch_text = "\n".join([f"• <b>{ch}</b>" for ch in all_channels])
    else:
        ch_text = "<i>Hozircha majburiy obuna kanallari ulanmagan.</i>"

    text = (
        "📢 <b>Majburiy Obuna Kanallari:</b>\n\n"
        f"{ch_text}\n\n"
        "💡 Yangi kanal qo'shish uchun <b>«➕ Kanal qo'shish»</b> tugmasini bosing.\n"
        "<i>Eslatma: Kanal qo'shishdan oldin botni o'sha kanalga admin qiling!</i>"
    )
    await call.message.edit_text(text, reply_markup=get_admin_channels_keyboard(all_channels), parse_mode="HTML")

@admin_router.callback_query(F.data == "add_ch")
async def cb_start_add_channel(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not is_admin(call.from_user.id):
        return

    await state.set_state(ChannelState.waiting_for_channel)
    await call.message.answer(
        "➕ <b>Kanalni majburiy obunaga qo'shish:</b>\n\n"
        "Quyidagi usullardan biri orqali yuboring:\n"
        "1️⃣ <b>Kanal usernamesi:</b> Masalan: <code>@kanal_nomi</code>\n"
        "2️⃣ <b>Xabarni FORWARD qilish:</b> O'sha kanaldan istalgan biror xabarni shu yerga uzatib yuboring (yopiq kanallar uchun eng qulayi);\n"
        "3️⃣ <b>Kanal ID raqami:</b> Masalan: <code>-1002345678901</code>\n\n"
        "<i>⚠️ DIQQAT: Kanal qo'shishdan oldin botni o'sha kanalga <b>Admin</b> qilgan bo'lishingiz shart!</i>\n"
        "<i>Bekor qilish uchun /cancel deb yozing.</i>",
        parse_mode="HTML"
    )

@admin_router.message(ChannelState.waiting_for_channel)
async def process_add_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    target_chat_id = None
    target_username = None
    target_title = None
    target_invite_link = None

    # 1. Agar kanaldan xabar FORWARD qilingan bo'lsa
    if message.forward_from_chat:
        f_chat = message.forward_from_chat
        target_chat_id = str(f_chat.id)
        target_title = f_chat.title
        target_username = f"@{f_chat.username}" if f_chat.username else target_chat_id
    else:
        # 2. Agar matn (username, havola yoki ID) yozilgan bo'lsa
        raw_text = (message.text or "").strip()
        if not raw_text:
            await message.answer("❌ Iltimos, kanal usernamesini yoki kanaldan xabarni forward qilib yuboring.")
            return

        if raw_text.startswith("-100") and raw_text[4:].isdigit():
            target_chat_id = raw_text
            target_username = raw_text
        elif "t.me/" in raw_text:
            part = raw_text.split("t.me/", 1)[1].strip("/")
            if not part.startswith("+") and not part.startswith("joinchat/"):
                target_username = "@" + part
            else:
                target_invite_link = raw_text
                target_username = raw_text
        else:
            target_username = "@" + raw_text.lstrip("@")

    # Botning kanalda adminligini va ma'lumotlarini aniqlash
    lookup_target = target_chat_id or target_username
    try:
        chat = await message.bot.get_chat(lookup_target)
        target_chat_id = str(chat.id)
        target_title = chat.title or target_title
        if chat.username:
            target_username = f"@{chat.username}"
            target_invite_link = f"https://t.me/{chat.username}"

        # Bot adminligini tekshirish
        member = await message.bot.get_chat_member(chat.id, message.bot.id)
        if member.status not in ["administrator", "creator"]:
            await message.answer(
                f"⚠️ <b>Ogohlantirish:</b> Bot <b>{target_title or lookup_target}</b> kanalida admin emas!\n"
                "Iltimos, avval botni kanalingizga admin qiling, aks holda a'zolarni tekshira olmaydi.",
                parse_mode="HTML"
            )

        # Agar yopiq kanal bo'lsa va invite link bo'lmasa, avtomatik yaratamiz
        if not target_invite_link:
            try:
                invite = await message.bot.create_chat_invite_link(chat.id, name="Majburiy Obuna")
                target_invite_link = invite.invite_link
            except Exception:
                try:
                    target_invite_link = await message.bot.export_chat_invite_link(chat.id)
                except Exception:
                    pass

    except Exception as e:
        logger.warning(f"Kanal ma'lumotlarini olishda xatolik ({lookup_target}): {e}")
        # Agar get_chat xato bersa, kiritilgan nom bilan davom etamiz

    save_key = target_username or target_chat_id or lookup_target
    success = await db.add_channel(
        username=save_key,
        chat_id=target_chat_id,
        title=target_title or save_key,
        invite_link=target_invite_link
    )
    await state.clear()

    if success:
        display_name = target_title or save_key
        await message.answer(
            f"✅ <b>{display_name}</b> majburiy obuna ro'yxatiga muvaffaqiyatli qo'shildi!\n"
            f"🆔 <b>Chat ID:</b> <code>{target_chat_id or 'Aniqlanmadi'}</code>\n"
            f"🔗 <b>Havola:</b> {target_invite_link or 'Mavjud emas'}",
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Kanalni bazaga saqlashda xatolik yuz berdi.")

@admin_router.callback_query(F.data.startswith("del_ch:"))
async def cb_delete_channel(call: CallbackQuery):
    await call.answer()
    if not is_admin(call.from_user.id):
        return

    ch_name = call.data.split(":", 1)[1]
    await db.delete_channel(ch_name)
    await call.answer(f"✅ {ch_name} o'chirildi!", show_alert=True)

    db_channels = await db.get_db_channels()
    all_channels = list(dict.fromkeys(CHANNELS + db_channels))
    await call.message.edit_reply_markup(reply_markup=get_admin_channels_keyboard(all_channels))

@admin_router.callback_query(F.data == "admin_clear_cache")
async def cb_admin_clear_cache(call: CallbackQuery):
    await call.answer()
    if not is_admin(call.from_user.id):
        return

    cleared = db.clear_ram_cache()
    # Bazadan qayta yuklaymiz
    await db.init_db()
    stats = await db.get_stats()
    await call.message.answer(
        f"🔄 <b>Kesh muvaffaqiyatli yangilandi!</b>\n\n"
        f"Eski RAM keshi tozalandi va bazadagi <b>{stats.get('ram_cached', 0)}</b> ta trek xotiraga qayta yuklandi.",
        parse_mode="HTML"
    )

@admin_router.callback_query(F.data == "admin_close")
async def cb_admin_close(call: CallbackQuery):
    await call.answer("Admin panel yopildi")
    await call.message.delete()

@admin_router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not is_admin(call.from_user.id):
        await call.message.answer("❌ Ruxsat berilmagan!")
        return

    await state.set_state(BroadcastState.waiting_for_message)
    await call.message.answer(
        "✍️ <b>Barcha foydalanuvchilarga yuboriladigan xabarni yuboring:</b>\n"
        "<i>(Matn, rasm, video, audio yoki post yuborishingiz mumkin. Bekor qilish uchun /cancel deb yozing)</i>",
        parse_mode="HTML"
    )

@admin_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("❌ Amal bekor qilindi.")

@admin_router.message(BroadcastState.waiting_for_message)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    user_ids = await db.get_all_user_ids()
    total = len(user_ids)
    progress_msg = await message.answer(f"🚀 Xabar tarqatish boshlandi. Jami foydalanuvchilar: {total} ta")
    await state.clear()

    sent = 0
    blocked = 0

    for user_id in user_ids:
        try:
            await message.copy_to(chat_id=user_id)
            sent += 1
            await asyncio.sleep(0.04) # Telegram spam cheklovidan himoya (25 msg/sec)
        except Exception:
            blocked += 1

    await progress_msg.edit_text(
        f"✅ <b>Xabar tarqatish yakunlandi!</b>\n\n"
        f"📨 Yuborildi: <b>{sent}</b> ta\n"
        f"🚫 Bloklangan / Yetkazilmadi: <b>{blocked}</b> ta",
        parse_mode="HTML"
    )

@admin_router.my_chat_member()
async def on_bot_added_to_channel(event: ChatMemberUpdated):
    """Bot biror kanalga admin qilib qo'shilganda kanal ma'lumotlarini avtomatik qayd qilish"""
    chat = event.chat
    if chat.type in ["channel", "supergroup"]:
        new_status = event.new_chat_member.status
        if new_status in ["administrator", "creator"]:
            invite_link = None
            try:
                invite = await event.bot.create_chat_invite_link(chat.id, name="Majburiy Obuna")
                invite_link = invite.invite_link
            except Exception:
                try:
                    invite_link = await event.bot.export_chat_invite_link(chat.id)
                except Exception:
                    pass

            ch_username = f"@{chat.username}" if chat.username else str(chat.id)
            await db.add_channel(
                username=ch_username,
                chat_id=str(chat.id),
                title=chat.title,
                invite_link=invite_link
            )
            logger.info(f"Bot yangi kanalga admin qilindi va bazaga ulandi: {chat.title} ({chat.id})")


