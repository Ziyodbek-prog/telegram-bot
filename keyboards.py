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

def categories_inline_keyboard(categories):
    buttons = []
    if isinstance(categories, list):
        for cat in categories:
            cat_name = cat.get("name") if isinstance(cat, dict) else str(cat)
            buttons.append([InlineKeyboardButton(text=f"📁 {cat_name}", callback_data=f"cat_{cat_name}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def services_by_category_keyboard(services, category):
    filtered = [s for s in services if s.get("category") == category] if isinstance(services, list) else []
    buttons = []
    for s in filtered:
        buttons.append([InlineKeyboardButton(
            text=f"🔹 {s['title']} | {float(s['price']):,.0f} so'm",
            callback_data=f"srv_{s['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def force_sub_keyboard(channel_checks):
    buttons = []
    for ch in channel_checks:
        status_icon = "✅" if ch["is_sub"] else "❌"
        buttons.append([InlineKeyboardButton(
            text=f"{ch['title']} [{status_icon}]",
            url=ch["invite_link"]
        )])

    buttons.append([InlineKeyboardButton(text="🔄 Obunani Tekshirish", callback_data="check_sub_status")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_dashboard_keyboard(is_maintenance=False):
    m_text = "🟢 Botni Yoqish (Ishchi Rejim)" if is_maintenance else "🔴 Botni O'chirish (Texnik Rejim)"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Bot Haqida To'liq Ma'lumot (Tashxis)", callback_data="adm_diagnostics")],
        [InlineKeyboardButton(text=m_text, callback_data="adm_toggle_maintenance")],
        [InlineKeyboardButton(text="📢 Majburiy Obuna Sozlash", callback_data="adm_channels")],
        [InlineKeyboardButton(text="📥 Kutilayotgan To'lovlar", callback_data="adm_topups")],
        [InlineKeyboardButton(text="🔄 SMM API'dan Xizmat Yuklash", callback_data="adm_fetch_smm")],
        [InlineKeyboardButton(text="📁 Bo'limlar / Kategoriyalar Sozlash", callback_data="adm_manage_cats")],
        [InlineKeyboardButton(text="➕ Qo'lda Xizmat Qo'shish", callback_data="adm_add_srv")],
        [InlineKeyboardButton(text="⚙️ Xizmatlarni Boshqarish / O'chirish", callback_data="adm_manage_srv")],
        [InlineKeyboardButton(text="🔑 SMM API Sozlash (URL & KEY)", callback_data="adm_smm_config")],
        [InlineKeyboardButton(text="💳 Karta Sozlamalari", callback_data="adm_card")],
        [InlineKeyboardButton(text="📊 Kengaytirilgan Statistikalar", callback_data="adm_stats")]
    ])

def admin_channels_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi Kanal Qo'shish", callback_data="adm_add_chan")],
        [InlineKeyboardButton(text="📋 Kanallar Ro'yxati / O'chirish", callback_data="adm_list_chan")]
    ])
