from aiogram import Router, F, types
from config import ADMIN_TELEGRAM_IDS
from database import (
    get_db_settings,
    update_db_settings,
    get_expanded_stats,
    run_full_diagnostics,
)
from keyboards import admin_dashboard_keyboard

diag_router = Router()

@diag_router.callback_query(F.data == "adm_diagnostics")
async def cb_adm_diagnostics(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await call.message.answer("⏳ Neon PostgreSQL va tizim diagnostikasi o'tkazilmoqda...")
    report = await run_full_diagnostics(call.bot)
    await call.message.answer(report, parse_mode="Markdown")
    await call.answer()

@diag_router.callback_query(F.data == "adm_toggle_maintenance")
async def cb_adm_toggle_m(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    sett = await get_db_settings()
    new_status = not sett.get("is_maintenance", False)
    await update_db_settings(is_maintenance=new_status)
    
    st_text = "🔴 BOT O'CHIRILDI (TEXNIK REJIM YOQILDI)" if new_status else "🟢 BOT YOQILDI (ISHCHI REJIM)"
    await call.message.edit_reply_markup(reply_markup=admin_dashboard_keyboard(new_status))
    await call.message.answer(f"⚙️ **REJIM O'ZGARDi:** {st_text}", parse_mode="Markdown")
    await call.answer()

@diag_router.callback_query(F.data == "adm_stats")
async def cb_adm_stats(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    stats = await get_expanded_stats()
    msg = (
        f"📊 **BOTNING KENGAYTIRILGAN STATISTIKASI:**\n\n"
        f"👥 Jami foydalanuvchilar: **{stats['users_total']} ta**\n"
        f"🆕 Bugun qo'shilganlar: **+{stats['users_today']} ta**\n"
        f"📁 Bo'limlar / Xizmatlar: **{stats['categories_count']} ta bo'lim / {stats['services_count']} ta xizmat**\n"
        f"🛍 Jami bajarilgan buyurtmalar: **{stats['total_orders']} ta**\n"
        f"📥 Kutilayotgan to'lov arizalari: **{stats['pending_topups']} ta**\n"
        f"💰 Jami tasdiqlangan kassa: **{stats['total_revenue']:,.0f} so'm**\n"
        f"👥 Referallarga to'lab berilgan bonus: **{stats['total_ref_paid']:,.0f} so'm**"
    )
    await call.message.answer(msg, parse_mode="Markdown")
    await call.answer()
