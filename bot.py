import asyncio
import logging
import os
import requests
from aiohttp import web

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# ==========================================
# ⚙️ SOZLAMALAR VA KONFIGURATSIYA
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "7832829103:AAH_YOUR_TELEGRAM_BOT_TOKEN_HERE")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wskiglwygorhjmhrmoxm.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_udznrMLszrXelL-P1CbLNA_ayort0ja")

# Admin Telegram ID lar ro'yxati (O'zingizning Telegram ID'ingizni qo'ying)
ADMIN_TELEGRAM_IDS = [123456789]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================================
# 📝 FSM STATES (BOSQICHLAR)
# ==========================================

class UserStates(StatesGroup):
    waiting_topup_amount = State()
    waiting_topup_receipt = State()
    waiting_order_link = State()
    waiting_order_quantity = State()
    waiting_promo_code = State()

class AdminStates(StatesGroup):
    waiting_card_number = State()
    waiting_card_holder = State()
    waiting_smm_api_url = State()
    waiting_smm_api_key = State()
    waiting_broadcast_text = State()
    waiting_promo_name = State()
    waiting_promo_sum = State()
    waiting_user_id_for_balance = State()
    waiting_user_new_balance = State()
    waiting_new_service_name = State()
    waiting_new_service_price = State()
    waiting_new_service_category = State()

# ==========================================
# 🗄 DATABASE & SMM API WRAPPER
# ==========================================

def db_query(endpoint, method="GET", payload=None):
    """Supabase bilan xavfsiz muloqot qiluvchi universal yordamchi"""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    try:
        if method == "GET":
            return requests.get(url, headers=HEADERS, timeout=10).json()
        elif method == "POST":
            return requests.post(url, headers=HEADERS, json=payload, timeout=10).json()
        elif method == "PATCH":
            return requests.patch(url, headers=HEADERS, json=payload, timeout=10)
        elif method == "DELETE":
            return requests.delete(url, headers=HEADERS, timeout=10)
    except Exception as e:
        logger.error(f"DB Error [{endpoint}]: {e}")
        return [] if method == "GET" else None

def get_or_create_user(user: types.User):
    email = f"tg_{user.id}@telegram.com"
    res = db_query(f"users?email=eq.{email}")
    if isinstance(res, list) and len(res) > 0:
        return res[0]
    
    payload = {
        "email": email,
        "full_name": user.full_name or user.username or "Foydalanuvchi",
        "balance": 0.0,
        "is_admin": user.id in ADMIN_TELEGRAM_IDS
    }
    new_res = db_query("users", method="POST", payload=payload)
    return new_res[0] if isinstance(new_res, list) and len(new_res) > 0 else payload

def get_settings():
    res = db_query("settings?id=eq.1")
    if isinstance(res, list) and len(res) > 0:
        return res[0]
    return {"card_number": "8600 0000 0000 0000", "card_holder": "Ziyodbek G.", "smm_api_url": "", "smm_api_key": ""}

def call_smm_api(api_url, api_key, action, **kwargs):
    """PerfectPanel API v2 Moslashuvchan Integratsiyasi"""
    if not api_url or not api_key:
        return {"error": "API URL yoki Key sozlanmagan"}
    
    data = {"key": api_key, "action": action}
    data.update(kwargs)
    try:
        res = requests.post(api_url, data=data, timeout=12).json()
        return res
    except Exception as e:
        logger.error(f"SMM API Exception: {e}")
        return {"error": str(e)}

# ==========================================
# ⌨️ MENU & KEYBOARDS (INTERFAOL INTERFEYS)
# ==========================================

def main_keyboard(is_admin=False):
    kb = [
        [KeyboardButton(text="🚀 Nakrutka Buyurtma Qilish"), KeyboardButton(text="💳 Balans")],
        [KeyboardButton(text="📦 Buyurtmalar Tarixi"), KeyboardButton(text="🎁 Promokod")],
        [KeyboardButton(text="👥 Referal Tizim"), KeyboardButton(text="👤 Profilim")],
        [KeyboardButton(text="📞 Qo'llab-quvvatlash")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def categories_inline_keyboard():
    services = db_query("services?select=*")
    categories = list(set([s.get("category", "Boshqa") for s in services])) if isinstance(services, list) else []
    
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(text=f"📁 {cat}", callback_data=f"cat_{cat}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def services_by_category_keyboard(category):
    services = db_query(f"services?category=eq.{category}&select=*")
    buttons = []
    if isinstance(services, list):
        for s in services:
            buttons.append([InlineKeyboardButton(text=f"🔹 {s['title']} | {s['price']:,.0f} so'm", callback_data=f"srv_{s['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_dashboard_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Kutilayotgan To'lovlar", callback_data="adm_topups"), InlineKeyboardButton(text="📊 Statistikalar", callback_data="adm_stats")],
        [InlineKeyboardButton(text="💳 Karta Sozlamalari", callback_data="adm_card"), InlineKeyboardButton(text="🔑 SMM API Sozlash", callback_data="adm_api")],
        [InlineKeyboardButton(text="➕ Yangi Xizmat Qo'shish", callback_data="adm_add_srv"), InlineKeyboardButton(text="➕ Promokod Yaratish", callback_data="adm_add_promo")],
        [InlineKeyboardButton(text="👤 User Balansini O'zgartirish", callback_data="adm_edit_bal")],
        [InlineKeyboardButton(text="📢 Xabar Tarqatish (Broadcast)", callback_data="adm_broadcast")]
    ])

# ==========================================
# 🤖 BOT HANDLERLARI (FOYDALANUVCHI BO'LIMI)
# ==========================================

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = get_or_create_user(message.from_user)
    is_admin = user.get("is_admin", False) or message.from_user.id in ADMIN_TELEGRAM_IDS
    
    msg = (
        f"🔥 **Salom, {message.from_user.full_name}!**\n\n"
        "⚡ **Ziyodbek MultiTool SMM Engine'ga xush kelibsiz!**\n"
        "Telegram, Instagram, TikTok va YouTube uchun eng tezkor hamda arzon nakrutka xizmatlari.\n\n"
        "Kerakli bo'limni pastdagi menyudan tanlang 👇"
    )
    await message.answer(msg, reply_markup=main_keyboard(is_admin), parse_mode="Markdown")

@dp.message(F.text == "👤 Profilim")
async def cmd_profile(message: types.Message):
    user = get_or_create_user(message.from_user)
    msg = (
        f"👤 **SHAXSIY PROFILINGIZ:**\n\n"
        f" Ism: **{user.get('full_name')}**\n"
        f"🆔 Telegram ID: `{message.from_user.id}`\n"
        f"📧 Pochta ID: `{user.get('email')}`\n"
        f"💰 Balans: **{user.get('balance', 0.0):,.0f} so'm**\n"
        f" Key: **{'👑 Administrator' if user.get('is_admin') else '👤 Mijoz'}**"
    )
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "💳 Balans")
async def cmd_balance(message: types.Message):
    user = get_or_create_user(message.from_user)
    sett = get_settings()
    
    msg = (
        f"💳 **BALANS SOZLAMALARI**\n\n"
        f"Sizning joriy balansingiz: **{user.get('balance', 0.0):,.0f} so'm**\n\n"
        f"📌 **To'lov uchun karta ma'lumotlari:**\n"
        f"💳 Karta: `{sett.get('card_number')}`\n"
        f"👤 Ega: **{sett.get('card_holder')}**\n\n"
        f"O'tkazmani bajargach, **'➕ To'lov Arizasi Yuborish'** tugmasini bosing va chekni yuboring."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ To'lov Arizasi Yuborish", callback_data="start_topup_flow")]
    ])
    await message.answer(msg, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "start_topup_flow")
async def cb_topup_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_topup_amount)
    await call.message.answer("💵 O'tkazgan sumangizni kiriting (masalan: `50000`):", parse_mode="Markdown")
    await call.answer()

@dp.message(UserStates.waiting_topup_amount)
async def process_topup_amt(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Faqat raqam kiriting (masalan: 50000):")
        return
    await state.update_data(amt=message.text)
    await state.set_state(UserStates.waiting_topup_receipt)
    await message.answer("🧾 Chek rasmi, TxID raqami yoki izohni yuboring:")

@dp.message(UserStates.waiting_topup_receipt)
async def process_topup_rec(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amt = data.get("amt")
    receipt = message.text.strip()
    email = f"tg_{message.from_user.id}@telegram.com"

    payload = {"user_email": email, "amount": float(amt), "receipt_info": receipt, "status": "pending"}
    res = db_query("topups", method="POST", payload=payload)
    await state.clear()

    if res:
        await message.answer("✅ **To'lov arizasi yuborildi!** Admin tekshirib balansga qo'shadi.", parse_mode="Markdown")
        topup_id = res[0]["id"] if isinstance(res, list) else res.get("id", "0")
        
        for admin_id in ADMIN_TELEGRAM_IDS:
            try:
                txt = (
                    f"🔔 **YANGI TO'LOV ARIZASI!**\n\n"
                    f"👤 User: {message.from_user.full_name} (`{message.from_user.id}`)\n"
                    f"💰 Summa: **{amt} so'm**\n"
                    f"🧾 Chek/TxID: `{receipt}`"
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"appr_{topup_id}_{message.from_user.id}_{amt}"),
                        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{topup_id}_{message.from_user.id}")
                    ]
                ])
                await bot.send_message(admin_id, txt, reply_markup=kb, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Admin inform error: {e}")

@dp.message(F.text == "🚀 Nakrutka Buyurtma Qilish")
async def cmd_services(message: types.Message):
    kb = categories_inline_keyboard()
    if not kb.inline_keyboard:
        await message.answer("🛍 Hozircha xizmatlar kategoriyalari kiritilmagan.")
        return
    await message.answer("📁 **KATEGORIYANI TANLANG:**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def cb_category(call: types.CallbackQuery):
    cat = call.data.split("cat_")[1]
    kb = services_by_category_keyboard(cat)
    await call.message.edit_text(f"📁 **{cat}** bo'limidagi xizmatlar:", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "back_to_categories")
async def cb_back_cat(call: types.CallbackQuery):
    kb = categories_inline_keyboard()
    await call.message.edit_text("📁 **KATEGORIYANI TANLANG:**", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("srv_"))
async def cb_service_select(call: types.CallbackQuery, state: FSMContext):
    srv_id = call.data.split("srv_")[1]
    res = db_query(f"services?id=eq.{srv_id}")
    if not res:
        await call.answer("❌ Xizmat topilmadi!", show_alert=True)
        return
    
    srv = res[0]
    await state.update_data(srv=srv)
    await state.set_state(UserStates.waiting_order_link)
    await call.message.answer(
        f"🔗 **{srv['title']}**\n"
        f"1000 ta narxi: **{srv['price']:,.0f} so'm**\n\n"
        f"Iltimos, nakrutka urilishi kerak bo'lgan **HAVOLA (LINK)**ni yuboring:",
        parse_mode="Markdown"
    )
    await call.answer()

@dp.message(UserStates.waiting_order_link)
async def process_order_link(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text.strip())
    await state.set_state(UserStates.waiting_order_quantity)
    await message.answer("🔢 Qancha miqdorda buyurtma qilmoqchisiz? (Masalan: `1000`):", parse_mode="Markdown")

@dp.message(UserStates.waiting_order_quantity)
async def process_order_qty(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Miqdorni raqamda kiriting (masalan: 1000):")
        return

    qty = int(message.text)
    data = await state.get_data()
    srv = data["srv"]
    link = data["link"]
    await state.clear()

    total_price = (float(srv["price"]) / 1000.0) * qty
    user = get_or_create_user(message.from_user)
    balance = float(user.get("balance", 0.0))

    if balance < total_price:
        await message.answer(
            f"❌ **Balansingizda mablag' yetarli emas!**\n\n"
            f"Kerakli summa: **{total_price:,.0f} so'm**\n"
            f"Sizning balansingiz: **{balance:,.0f} so'm**\n\n"
            f"Iltimos, balansingizni to'ldiring.",
            parse_mode="Markdown"
        )
        return

    # Balansdan pulni ayirish
    new_bal = balance - total_price
    email = f"tg_{message.from_user.id}@telegram.com"
    db_query(f"users?email=eq.{email}", method="PATCH", payload={"balance": new_bal})

    # SMM Panel API so'rovi
    sett = get_settings()
    api_res = call_smm_api(sett.get("smm_api_url"), sett.get("smm_api_key"), "add", service=srv.get("provider_service_id", srv["id"]), link=link, quantity=qty)
    
    order_id = api_res.get("order", "Avto-bajarilmoqda")

    await message.answer(
        f"🎉 **BUYURTMA MUVAFFAQIYATLI QABUL QILINDI!**\n\n"
        f"🔹 Xizmat: **{srv['title']}**\n"
        f"🔗 Link: `{link}`\n"
        f"🔢 Miqdor: **{qty} ta**\n"
        f"💰 Yechilgan summa: **{total_price:,.0f} so'm**\n"
        f"🆔 SMM Order ID: `{order_id}`\n\n"
        f"Qolgan balansingiz: **{new_bal:,.0f} so'm**",
        parse_mode="Markdown"
    )

@dp.message(F.text == "🎁 Promokod")
async def cmd_promo(message: types.Message, state: FSMContext):
    await state.set_state(UserStates.waiting_promo_code)
    await message.answer("🎁 Promokodni kiriting:", parse_mode="Markdown")

@dp.message(UserStates.waiting_promo_code)
async def process_promo(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    await state.clear()
    
    res = db_query(f"promos?code=eq.{code}")
    if not isinstance(res, list) or len(res) == 0:
        await message.answer("❌ Noto'g'ri yoki eskirgan promokod!")
        return
    
    promo = res[0]
    if promo.get("used", False):
        await message.answer("❌ Bu promokod allaqachon ishlatilgan!")
        return

    # Promokod balansi foydalanuvchiga o'tadi
    user = get_or_create_user(message.from_user)
    bonus = float(promo.get("amount", 0.0))
    new_bal = float(user.get("balance", 0.0)) + bonus
    
    email = f"tg_{message.from_user.id}@telegram.com"
    db_query(f"users?email=eq.{email}", method="PATCH", payload={"balance": new_bal})
    db_query(f"promos?id=eq.{promo['id']}", method="PATCH", payload={"used": True})

    await message.answer(f"🎉 **TABRIKLAYMIZ!** Promokod aktivlashtirildi. Balansingizga +{bonus:,.0f} so'm qo'shildi!", parse_mode="Markdown")

@dp.message(F.text == "👥 Referal Tizim")
async def cmd_ref(message: types.Message):
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start={message.from_user.id}"
    msg = (
        f"👥 **REFERAL DASTUR**\n\n"
        f"Do'stlaringizni taklif qiling va har bir to'lovidan **10% daromad** oling!\n\n"
        f"Sizning referal havolangiz:\n`{ref_link}`"
    )
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "📞 Qo'llab-quvvatlash")
async def cmd_supp(message: types.Message):
    await message.answer("📞 Qo'llab-quvvatlash xizmati: @Ziyodbek_Admin")

# ==========================================
# 👑 ADMIN PANEL & BOSHGARUV
# ==========================================

@dp.message(Command("admin"))
@dp.message(F.text == "👑 Admin Panel")
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        await message.answer("❌ Boshqaruv faqat adminlar uchun!")
        return
    await message.answer("👑 **ADMINISTRATOR DASHBOARD:**", reply_markup=admin_dashboard_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "adm_topups")
async def cb_adm_topups(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    topups = db_query("topups?status=eq.pending&select=*")
    if not isinstance(topups, list) or len(topups) == 0:
        await call.message.answer("📥 Kutilayotgan to'lovlar yo'q.")
        await call.answer()
        return

    for t in topups:
        txt = (
            f"🆔 Ariza #{t['id']}\n"
            f"📧 User: `{t['user_email']}`\n"
            f"💰 Summa: **{t['amount']:,.0f} so'm**\n"
            f"🧾 Chek/TxID: `{t['receipt_info']}`"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"appr_{t['id']}_0_{t['amount']}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{t['id']}_0")
            ]
        ])
        await call.message.answer(txt, reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("appr_"))
async def cb_appr_topup(call: types.CallbackQuery):
    parts = call.data.split("_")
    topup_id, user_tg_id, amount = parts[1], parts[2], float(parts[3])

    topup_res = db_query(f"topups?id=eq.{topup_id}")
    if isinstance(topup_res, list) and len(topup_res) > 0:
        email = topup_res[0]["user_email"]
        
        # Statusni yangilash va balansga pul qo'shish
        db_query(f"topups?id=eq.{topup_id}", method="PATCH", payload={"status": "approved"})
        
        u_res = db_query(f"users?email=eq.{email}")
        if isinstance(u_res, list) and len(u_res) > 0:
            curr_b = float(u_res[0].get("balance", 0.0))
            db_query(f"users?email=eq.{email}", method="PATCH", payload={"balance": curr_b + amount})
            
            await call.message.edit_text(f"✅ Ariza #{topup_id} tasdiqlandi. Balansga +{amount:,.0f} so'm o'tdi.")
            if user_tg_id != "0":
                try:
                    await bot.send_message(int(user_tg_id), f"🎉 Balansingiz to'ldirildi! +{amount:,.0f} so'm.")
                except:
                    pass
    await call.answer()

@dp.callback_query(F.data.startswith("rej_"))
async def cb_rej_topup(call: types.CallbackQuery):
    topup_id = call.data.split("_")[1]
    db_query(f"topups?id=eq.{topup_id}", method="PATCH", payload={"status": "rejected"})
    await call.message.edit_text(f"❌ Ariza #{topup_id} rad etildi.")
    await call.answer()

@dp.callback_query(F.data == "adm_stats")
async def cb_adm_stats(call: types.CallbackQuery):
    users = db_query("users?select=id")
    topups = db_query("topups?status=eq.approved&select=amount")
    
    total_users = len(users) if isinstance(users, list) else 0
    total_revenue = sum([float(t.get("amount", 0)) for t in topups]) if isinstance(topups, list) else 0.0
    
    msg = (
        f
