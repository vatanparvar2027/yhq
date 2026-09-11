import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
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
        "➕ <b>Qo'shmoqchi bo'lgan kanalingiz usernamesini yuboring:</b>\n"
        "<i>Masalan: @kanal_nomi yoki kanal_nomi\n(Bekor qilish uchun /cancel deb yozing)</i>",
        parse_mode="HTML"
    )

@admin_router.message(ChannelState.waiting_for_channel)
async def process_add_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    ch_name = message.text.strip()
    if not ch_name.startswith("@") and not ch_name.startswith("http"):
        ch_name = "@" + ch_name

    # Botning kanalda adminligini tekshirib ko'ramiz
    try:
        chat = await message.bot.get_chat(ch_name)
        member = await message.bot.get_chat_member(chat.id, message.bot.id)
        if member.status not in ["administrator", "creator"]:
            await message.answer(
                f"⚠️ <b>Ogohlantirish:</b> Bot <b>{ch_name}</b> kanalida admin emas!\n"
                "Iltimos, avval botni kanalingizga admin qiling, aks holda obunani tekshira olmaydi.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.warning(f"Kanalni tekshirishda xatolik: {e}")

    success = await db.add_channel(ch_name)
    await state.clear()

    if success:
        await message.answer(f"✅ <b>{ch_name}</b> majburiy obuna ro'yxatiga muvaffaqiyatli qo'shildi!", parse_mode="HTML")
    else:
        await message.answer("❌ Kanalni qo'shishda xatolik yuz berdi.")

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

