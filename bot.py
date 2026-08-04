import asyncio
import logging
import os
import aiohttp
from aiohttp import web

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import (
    BOT_TOKEN,
    ADMIN_TELEGRAM_IDS,
    UserStates,
    AdminStates,
    db_query_async,
    get_or_create_user_async,
    get_db_settings,
    update_db_settings,
    run_full_diagnostics,
    logger,
)
from keyboards import (
    main_keyboard,
    categories_inline_keyboard,
    services_by_category_keyboard,
    admin_dashboard_keyboard,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================================
# 🛑 TEXNIK REJIM PRE-CHECK (MIDDLEWARE)
# ==========================================

async def check_maintenance(event: types.TelegramObject) -> bool:
    """Oddiy foydalanuvchilar uchun bot o'chirilgan bo'lsa to'xtatib qoladi"""
    user_id = event.from_user.id if event.from_user else 0
    if user_id in ADMIN_TELEGRAM_IDS:
        return False # Adminlarga doim ruxsat

    sett = await get_db_settings()
    if sett.get("is_maintenance", False):
        msg_text = "🛠 **BOTDA TEXNIK ISHLAR OLIB BORILMOQDA!**\n\nHozirda botimizda profilaktika va yangilanish ishlari ketmoqda. Birozdan so'ng qayta urinib ko'ring."
        if isinstance(event, types.Message):
            await event.answer(msg_text, parse_mode="Markdown")
        elif isinstance(event, types.CallbackQuery):
            await event.answer("🛠 Botda texnik ishlar ketmoqda!", show_alert=True)
        return True # Foydalanuvchini bloklaydi
    return False

# ==========================================
# 🤖 FOYDALANUVCHI HANDLERLARI
# ==========================================

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if await check_maintenance(message): return
    user = await get_or_create_user_async(message.from_user)
    is_admin = message.from_user.id in ADMIN_TELEGRAM_IDS or user.get("is_admin", False)
    msg = f"🔥 **Salom, {message.from_user.full_name}!**\n\n⚡ **Ziyodbek MultiTool SMM Engine'ga xush kelibsiz!**\n\nKerakli bo'limni pastdagi menyudan tanlang 👇"
    await message.answer(msg, reply_markup=main_keyboard(is_admin), parse_mode="Markdown")

@dp.message(F.text == "👤 Profilim")
async def cmd_profile(message: types.Message):
    if await check_maintenance(message): return
    user = await get_or_create_user_async(message.from_user)
    is_admin = message.from_user.id in ADMIN_TELEGRAM_IDS or user.get("is_admin", False)
    msg = f"👤 **SHAXSIY PROFILINGIZ:**\n\nIsm: **{user.get('full_name')}**\n🆔 Telegram ID: `{message.from_user.id}`\n💰 Balans: **{user.get('balance', 0.0):,.0f} so'm**\nMaqom: **{'👑 Administrator' if is_admin else '👤 Mijoz'}**"
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "💳 Balans")
async def cmd_balance(message: types.Message):
    if await check_maintenance(message): return
    user = await get_or_create_user_async(message.from_user)
    sett = await get_db_settings()
    msg = f"💳 **BALANS SOZLAMALARI**\n\nSizning joriy balansingiz: **{user.get('balance', 0.0):,.0f} so'm**\n\n📌 **To'lov uchun karta ma'lumotlari:**\n💳 Karta: `{sett.get('card_number')}`\n👤 Ega: **{sett.get('card_holder')}**\n\nO'tkazmani bajargach, **'➕ To'lov Arizasi Yuborish'** tugmasini bosing va chekni yuboring."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ To'lov Arizasi Yuborish", callback_data="start_topup_flow")]
    ])
    await message.answer(msg, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "start_topup_flow")
async def cb_topup_start(call: types.CallbackQuery, state: FSMContext):
    if await check_maintenance(call): return
    await state.set_state(UserStates.waiting_topup_amount)
    await call.message.answer("💵 O'tkazgan sumangizni kiriting (masalan: `50000`):", parse_mode="Markdown")
    await call.answer()

@dp.message(UserStates.waiting_topup_amount)
async def process_topup_amt(message: types.Message, state: FSMContext):
    if await check_maintenance(message): return
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Faqat raqam kiriting (masalan: 50000):")
        return
    await state.update_data(amt=message.text)
    await state.set_state(UserStates.waiting_topup_receipt)
    await message.answer("🧾 Chek rasmini, TxID kodi yoki izohini yuboring:")

@dp.message(UserStates.waiting_topup_receipt, F.photo | F.text)
async def process_topup_rec(message: types.Message, state: FSMContext):
    if await check_maintenance(message): return
    data = await state.get_data()
    amt = data.get("amt")
    email = f"tg_{message.from_user.id}@telegram.com"

    photo_id = None
    receipt_info = ""

    if message.photo:
        photo_id = message.photo[-1].file_id
        receipt_info = message.caption or "📸 Chek rasmi yuborildi"
    elif message.text:
        receipt_info = message.text.strip()
    else:
        receipt_info = "Chek ma'lumoti"

    payload = {"user_email": email, "amount": float(amt), "receipt_info": receipt_info, "status": "pending"}
    res = await db_query_async("topups", method="POST", payload=payload)
    await state.clear()

    topup_id = "0"
    if isinstance(res, list) and len(res) > 0:
        topup_id = str(res[0].get("id", "0"))

    await message.answer("✅ **To'lov arizangiz muvaffaqiyatli yuborildi!**\nAdmin tekshirib balansga qo'shadi.", parse_mode="Markdown")

    txt = (
        f"🔔 **YANGI TO'LOV ARIZASI!**\n\n"
        f"👤 User: {message.from_user.full_name} (`{message.from_user.id}`)\n"
        f"💰 Summa: **{amt} so'm**\n"
        f"🧾 Chek/Izoh: `{receipt_info}`\n"
        f"🆔 Ariza ID: `{topup_id}`"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"appr_{topup_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{topup_id}")
        ]
    ])

    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            if photo_id:
                await bot.send_photo(admin_id, photo=photo_id, caption=txt, reply_markup=kb, parse_mode="Markdown")
            else:
                await bot.send_message(admin_id, txt, reply_markup=kb, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

@dp.message(F.text == "🚀 Nakrutka Buyurtma Qilish")
async def cmd_services(message: types.Message):
    if await check_maintenance(message): return
    services = await db_query_async("services?select=*")
    kb = categories_inline_keyboard(services)
    if not kb.inline_keyboard:
        await message.answer("🛍 Hozircha xizmatlar kategoriyalari kiritilmagan. Admin panel orqali qo'shing yoki SMM API'dan yuklang.")
        return
    await message.answer("📁 **KATEGORIYANI TANLANG:**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def cb_category(call: types.CallbackQuery):
    if await check_maintenance(call): return
    cat = call.data.split("cat_")[1]
    services = await db_query_async("services?select=*")
    kb = services_by_category_keyboard(services, cat)
    await call.message.edit_text(f"📁 **{cat}** bo'limidagi xizmatlar:", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "back_to_categories")
async def cb_back_cat(call: types.CallbackQuery):
    if await check_maintenance(call): return
    services = await db_query_async("services?select=*")
    kb = categories_inline_keyboard(services)
    await call.message.edit_text("📁 **KATEGORIYANI TANLANG:**", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("srv_"))
async def cb_service_select(call: types.CallbackQuery, state: FSMContext):
    if await check_maintenance(call): return
    srv_id = call.data.split("srv_")[1]
    res = await db_query_async(f"services?id=eq.{srv_id}")
    if not isinstance(res, list) or len(res) == 0:
        await call.answer("❌ Xizmat topilmadi!", show_alert=True)
        return
    srv = res[0]
    await state.update_data(srv=srv)
    await state.set_state(UserStates.waiting_order_link)
    await call.message.answer(f"🔗 **{srv['title']}**\n1000 ta narxi: **{float(srv['price']):,.0f} so'm**\n\nIltimos, HAVOLA (LINK)ni yuboring:", parse_mode="Markdown")
    await call.answer()

@dp.message(UserStates.waiting_order_link)
async def process_order_link(message: types.Message, state: FSMContext):
    if await check_maintenance(message): return
    if not message.text:
        await message.answer("❌ Iltimos, havola matnini yuboring:")
        return
    await state.update_data(link=message.text.strip())
    await state.set_state(UserStates.waiting_order_quantity)
    await message.answer("🔢 Qancha miqdorda kerak? (Masalan: `1000`):", parse_mode="Markdown")

@dp.message(UserStates.waiting_order_quantity)
async def process_order_qty(message: types.Message, state: FSMContext):
    if await check_maintenance(message): return
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Miqdorni raqamda kiriting:")
        return
    qty = int(message.text)
    data = await state.get_data()
    srv = data["srv"]
    link = data["link"]
    await state.clear()

    total_price = (float(srv["price"]) / 1000.0) * qty
    user = await get_or_create_user_async(message.from_user)
    balance = float(user.get("balance", 0.0))

    if balance < total_price:
        await message.answer(f"❌ **Balansingizda mablag' yetarli emas!**\nKerakli summa: **{total_price:,.0f} so'm**\nSizning balansingiz: **{balance:,.0f} so'm**", parse_mode="Markdown")
        return

    new_bal = balance - total_price
    email = f"tg_{message.from_user.id}@telegram.com"
    await db_query_async(f"users?email=eq.{email}", method="PATCH", payload={"balance": new_bal})

    sett = await get_db_settings()
    api_url = sett.get("smm_api_url")
    api_key = sett.get("smm_api_key")
    order_id = "Avto-Bajarilmoqda"
    
    if api_url and api_key:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "key": api_key,
                    "action": "add",
                    "service": srv.get("provider_service_id", srv["id"]),
                    "link": link,
                    "quantity": qty
                }
                async with session.post(api_url, data=payload, timeout=10) as s_res:
                    res_json = await s_res.json()
                    order_id = res_json.get("order", "Qabul qilindi")
        except Exception as e:
            logger.error(f"SMM Order Error: {e}")

    await message.answer(f"🎉 **BUYURTMA MUVAFFAQIYATLI QABUL QILINDI!**\n\n🔹 Xizmat: **{srv['title']}**\n🔗 Link: `{link}`\n🔢 Miqdor: **{qty} ta**\n💰 Yechilgan summa: **{total_price:,.0f} so'm**\n🆔 Order ID: `{order_id}`", parse_mode="Markdown")

@dp.message(F.text == "👥 Referal Tizim")
async def cmd_ref(message: types.Message):
    if await check_maintenance(message): return
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start={message.from_user.id}"
    msg = f"👥 **REFERAL DASTUR**\n\nDo'stlaringizni taklif qiling va har bir to'lovidan **10% daromad** oling!\n\nSizning havolangiz:\n`{ref_link}`"
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "📞 Qo'llab-quvvatlash")
async def cmd_supp(message: types.Message):
    if await check_maintenance(message): return
    await message.answer("📞 Qo'llab-quvvatlash xizmati admini: @Ziyodbek_Admin")

# ==========================================
# 👑 ADMIN PANEL HANDLERLARI
# ==========================================

@dp.message(Command("admin"))
@dp.message(F.text == "👑 Admin Panel")
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        await message.answer("❌ Siz admin emassiz!")
        return
    sett = await get_db_settings()
    is_m = sett.get("is_maintenance", False)
    await message.answer("👑 **ADMINISTRATOR BOSHGARUV DASHBOARDI:**", reply_markup=admin_dashboard_keyboard(is_m), parse_mode="Markdown")

@dp.callback_query(F.data == "adm_diagnostics")
async def cb_adm_diagnostics(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await call.message.answer("⏳ Tizim diagnostikasi o'tkazilmoqda...")
    report = await run_full_diagnostics(bot)
    await call.message.answer(report, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "adm_toggle_maintenance")
async def cb_adm_toggle_m(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    sett = await get_db_settings()
    new_status = not sett.get("is_maintenance", False)
    await update_db_settings({"is_maintenance": new_status})
    
    st_text = "🔴 BOT O'CHIRILDI (TEXNIK REJIM YOQILDI)" if new_status else "🟢 BOT YOQILDI (ISHCHI REJIM)"
    await call.message.edit_reply_markup(reply_markup=admin_dashboard_keyboard(new_status))
    await call.message.answer(f"⚙️ **REJIM O'ZGARDi:** {st_text}", parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "adm_topups")
async def cb_adm_topups(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    topups = await db_query_async("topups?status=eq.pending&select=*")
    if not isinstance(topups, list) or len(topups) == 0:
        await call.message.answer("📥 Kutilayotgan to'lovlar yo'q.")
        await call.answer()
        return
    for t in topups:
        txt = f"🆔 Ariza #{t['id']}\n📧 User: `{t['user_email']}`\n💰 Summa: **{t['amount']:,.0f} so'm**\n🧾 Izoh/Chek: `{t['receipt_info']}`"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"appr_{t['id']}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{t['id']}")
            ]
        ])
        await call.message.answer(txt, reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("appr_"))
async def cb_appr_topup(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    topup_id = call.data.split("appr_")[1]
    topup_res = await db_query_async(f"topups?id=eq.{topup_id}")
    
    if isinstance(topup_res, list) and len(topup_res) > 0:
        topup = topup_res[0]
        email = topup["user_email"]
        amount = float(topup["amount"])

        await db_query_async(f"topups?id=eq.{topup_id}", method="PATCH", payload={"status": "approved"})
        u_res = await db_query_async(f"users?email=eq.{email}")
        if isinstance(u_res, list) and len(u_res) > 0:
            curr_b = float(u_res[0].get("balance", 0.0))
            await db_query_async(f"users?email=eq.{email}", method="PATCH", payload={"balance": curr_b + amount})

        try:
            tg_id_str = email.replace("tg_", "").replace("@telegram.com", "")
            if tg_id_str.isdigit():
                await bot.send_message(int(tg_id_str), f"🎉 **BALANSINGIZ TO'LDIRILDI!**\n\n💰 +{amount:,.0f} so'm balansingizga o'tdi.", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"User notify error: {e}")

    success_msg = f"✅ **Ariza #{topup_id} TASDIQLANDI!**"
    if call.message.caption:
        await call.message.edit_caption(caption=success_msg, parse_mode="Markdown")
    else:
        await call.message.edit_text(text=success_msg, parse_mode="Markdown")
    await call.answer("✅ Tasdiqlandi!")

@dp.callback_query(F.data.startswith("rej_"))
async def cb_rej_topup(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    topup_id = call.data.split("rej_")[1]
    await db_query_async(f"topups?id=eq.{topup_id}", method="PATCH", payload={"status": "rejected"})

    reject_msg = f"❌ **Ariza #{topup_id} RAD ETILDI.**"
    if call.message.caption:
        await call.message.edit_caption(caption=reject_msg, parse_mode="Markdown")
    else:
        await call.message.edit_text(text=reject_msg, parse_mode="Markdown")
    await call.answer("❌ Rad etildi!")

@dp.callback_query(F.data == "adm_smm_config")
async def cb_adm_smm_config(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_smm_url)
    await call.message.answer("🔑 SMM Panel API URL manzilini kiriting (masalan: `https://topsmm.uz/api/v2`):", parse_mode="Markdown")
    await call.answer()

@dp.message(AdminStates.waiting_smm_url)
async def process_smm_url(message: types.Message, state: FSMContext):
    await state.update_data(smm_url=message.text.strip())
    await state.set_state(AdminStates.waiting_smm_key)
    await message.answer("🔑 SMM Panel API Kalitini (API Key) kiriting:")

@dp.message(AdminStates.waiting_smm_key)
async def process_smm_key(message: types.Message, state: FSMContext):
    data = await state.get_data()
    url = data["smm_url"]
    key = message.text.strip()

    await update_db_settings({"smm_api_url": url, "smm_api_key": key})

    await state.clear()
    await message.answer(f"✅ **SMM API BAZAGA SAQLANDI!**\n\n🌐 URL: `{url}`\n🔑 KEY: `{key[:6]}...`", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_fetch_smm")
async def cb_adm_fetch_smm(call: types.CallbackQuery, state: FSMContext):
    sett = await get_db_settings()
    api_url = sett.get("smm_api_url")
    api_key = sett.get("smm_api_key")

    if not api_url or not api_key:
        await call.message.answer("⚠️ Avval '🔑 SMM API Sozlash' bo'limidan SMM API URL va KEY sozlang!")
        await call.answer()
        return

    await call.message.answer("⏳ SMM Provayderidan xizmatlar ro'yxati yuklanmoqda...")
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"key": api_key, "action": "services"}
            async with session.post(api_url, data=payload, timeout=12) as res:
                services_list = await res.json()
                if isinstance(services_list, list):
                    await state.update_data(api_services=services_list[:20])
                    await state.set_state(AdminStates.waiting_markup_percent)
                    await call.message.answer(f"📦 API'dan **{len(services_list)} ta** xizmat topildi!\n\nXizmatlar ustiga necha foiz ustama qo'shamiz? (Masalan: `50`):", parse_mode="Markdown")
                else:
                    await call.message.answer("❌ SMM API javob bermadi. API key yoki URL xato bo'lishi mumkin.")
    except Exception as e:
        await call.message.answer(f"❌ Xatolik yuz berdi: {e}")
    await call.answer()

@dp.message(AdminStates.waiting_markup_percent)
async def process_markup_percent(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Ustama foizni raqamda kiriting (masalan: 50):")
        return

    markup = float(message.text) / 100.0
    data = await state.get_data()
    api_services = data.get("api_services", [])
    await state.clear()

    imported_count = 0
    for s in api_services:
        base_rate = float(s.get("rate", 1000)) * 12500 / 1000.0
        final_price = base_rate * (1.0 + markup)
        
        item = {
            "title": s.get("name", "Xizmat"),
            "price": round(final_price, -2),
            "category": s.get("category", "SMM"),
            "provider_service_id": str(s.get("service")),
            "description": "Kafolatlangan xizmat"
        }
        await db_query_async("services", method="POST", payload=item)
        imported_count += 1

    await message.answer(f"🎉 **{imported_count} ta** xizmat Supabase bazasiga saqlandi!", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_add_srv")
async def cb_adm_add_srv(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_new_cat)
    await call.message.answer("📁 Kategoriya nomini kiriting (masalan: `Telegram Obunachilar`):", parse_mode="Markdown")
    await call.answer()

@dp.message(AdminStates.waiting_new_cat)
async def process_new_cat(message: types.Message, state: FSMContext):
    await state.update_data(cat=message.text.strip())
    await state.set_state(AdminStates.waiting_new_srv_name)
    await message.answer("🔹 Xizmat nomini kiriting:")

@dp.message(AdminStates.waiting_new_srv_name)
async def process_new_srv_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminStates.waiting_new_srv_price)
    await message.answer("💰 1000 ta uchun sotuv narxini kiriting (masalan: `15000`):")

@dp.message(AdminStates.waiting_new_srv_price)
async def process_new_srv_price(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Narxni raqamda kiriting:")
        return
    await state.update_data(price=message.text.strip())
    await state.set_state(AdminStates.waiting_new_srv_provider_id)
    await message.answer("🆔 SMM Provayder Service ID'sini kiriting (masalan: `102`):")

@dp.message(AdminStates.waiting_new_srv_provider_id)
async def process_new_srv_provider_id(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    new_item = {
        "category": data["cat"],
        "title": data["name"],
        "price": float(data["price"]),
        "provider_service_id": message.text.strip(),
        "description": "Kafolatlangan xizmat"
    }
    
    await db_query_async("services", method="POST", payload=new_item)

    await state.clear()
    await message.answer(f"✅ **YANGI XIZMAT BAZAGA SAQLANDI!**\n📁 {data['cat']} -> 🔹 {data['name']} ({data['price']} so'm)", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_manage_srv")
async def cb_adm_manage_srv(call: types.CallbackQuery):
    services = await db_query_async("services?select=*")
    if not isinstance(services, list) or len(services) == 0:
        await call.message.answer("🛍 Hozircha bazada xizmatlar yo'q.")
        await call.answer()
        return

    await call.message.answer("⚙️ **MAVJUD XIZMATLAR RO'YXATI:**")
    for s in services[:15]:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Ushbu Xizmatni O'chirish", callback_data=f"delsrv_{s['id']}")]
        ])
        await call.message.answer(f"🔹 **{s['title']}**\n📁 {s.get('category')} | Narxi: {s['price']} so'm", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("delsrv_"))
async def cb_delsrv(call: types.CallbackQuery):
    srv_id = call.data.split("delsrv_")[1]
    await db_query_async(f"services?id=eq.{srv_id}", method="DELETE")
    await call.message.edit_text("❌ **Xizmat Supabase bazasidan o'chirildi!**", parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "adm_card")
async def cb_adm_card(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_card_number)
    await call.message.answer("💳 Yangi karta raqamini kiriting:")
    await call.answer()

@dp.message(AdminStates.waiting_card_number)
async def process_card_num(message: types.Message, state: FSMContext):
    await state.update_data(c_num=message.text.strip())
    await state.set_state(AdminStates.waiting_card_holder)
    await message.answer("👤 Karta egasining ismini kiriting:")

@dp.message(AdminStates.waiting_card_holder)
async def process_card_hold(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await update_db_settings({"card_number": data["c_num"], "card_holder": message.text.strip()})
    await state.clear()
    await message.answer("✅ Karta ma'lumotlari Supabase bazasida yangilandi!")

@dp.callback_query(F.data == "adm_stats")
async def cb_adm_stats(call: types.CallbackQuery):
    users = await db_query_async("users?select=id")
    topups = await db_query_async("topups?status=eq.approved&select=amount")
    services = await db_query_async("services?select=id")
    
    total_users = len(users) if isinstance(users, list) else 0
    total_revenue = sum([float(t.get("amount", 0)) for t in topups]) if isinstance(topups, list) else 0.0
    total_services = len(services) if isinstance(services, list) else 0

    msg = (
        f"📊 **BOTNING UMUMIY STATISTIKASI:**\n\n"
        f"👥 Foydalanuvchilar: **{total_users} ta**\n"
        f"🛍 Aktiv xizmatlar: **{total_services} ta**\n"
        f"💰 Jami tasdiqlangan kassa: **{total_revenue:,.0f} so'm**"
    )
    await call.message.answer(msg, parse_mode="Markdown")
    await call.answer()

# ==========================================
# 🌐 RENDER HTTP SERVER
# ==========================================

async def handle_ping(request):
    return web.Response(text="Pro Diagnostics SMM Bot Engine Live 24/7", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Server running on port {port}")

async def main():
    asyncio.create_task(start_web_server())
    await get_db_settings()
    logger.info("🚀 Pro Diagnostics SMM Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
