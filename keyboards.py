from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

def main_keyboard(is_admin=False):
    kb = [
        [KeyboardButton(text="🚀 Nakrutka Buyurtma Qilish"), KeyboardButton(text="💳 Balans")],
        [KeyboardButton(text="👥 Referal Tizim"), KeyboardButton(text="👤 Profilim")],
        [KeyboardButton(text="📞 Qo'llab-quvvatlash")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def categories_inline_keyboard(services):
    categories = list(set([s.get("category", "Boshqa") for s in services])) if isinstance(services, list) else []
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(text=f"📁 {cat}", callback_data=f"cat_{cat}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def services_by_category_keyboard(services, category):
    filtered = [s for s in services if s.get("category") == category] if isinstance(services, list) else []
    buttons = []
    for s in filtered:
        buttons.append([InlineKeyboardButton(text=f"🔹 {s['title']} | {float(s['price']):,.0f} so'm", callback_data=f"srv_{s['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_dashboard_keyboard(is_maintenance=False):
    m_text = "🟢 Botni Yoqish (Ishchi Rejim)" if is_maintenance else "🔴 Botni O'chirish (Texnik Rejim)"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Bot Haqida To'liq Ma'lumot (Tashxis)", callback_data="adm_diagnostics")],
        [InlineKeyboardButton(text=m_text, callback_data="adm_toggle_maintenance")],
        [InlineKeyboardButton(text="📥 Kutilayotgan To'lovlar", callback_data="adm_topups")],
        [InlineKeyboardButton(text="🔄 SMM API'dan Xizmat Yuklash", callback_data="adm_fetch_smm")],
        [InlineKeyboardButton(text="➕ Qo'lda Xizmat Qo'shish", callback_data="adm_add_srv")],
        [InlineKeyboardButton(text="⚙️ Xizmatlarni Boshqarish / O'chirish", callback_data="adm_manage_srv")],
        [InlineKeyboardButton(text="🔑 SMM API Sozlash (URL & KEY)", callback_data="adm_smm_config")],
        [InlineKeyboardButton(text="💳 Karta Sozlamalari", callback_data="adm_card")],
        [InlineKeyboardButton(text="📊 Statistikalar", callback_data="adm_stats")]
    ])
