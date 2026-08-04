from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_TELEGRAM_IDS, UserStates
from database import (
    get_or_create_user_async,
    get_db_settings,
    get_categories,
    get_services_by_category,
    get_all_services,
    create_topup,
    create_order_db,
    subtract_user_balance,
    logger,
)
from keyboards import (
    main_keyboard,
    categories_inline_keyboard,
    services_by_category_keyboard,
    force_sub_keyboard,
)
from middlewares import check_guard, check_user_sub

user_router = Router()

@user_router.message(CommandStart())
async def cmd_start(message: types.Message):
    args = message.text.split()
    referrer_id = args[1] if len(args) > 1 else None

    if await check_guard(message, message.bot): return
    user = await get_or_create_user_async(message.from_user, referrer_id)
    is_admin = message.from_user.id in ADMIN_TELEGRAM_IDS or user.get("is_admin", False)
    msg = f"🔥 **Salom, {message.from_user.full_name}!**\n\n⚡ **Ziyodbek MultiTool SMM Engine'ga xush kelibsiz!**\n\nKerakli bo'limni pastdagi menyudan tanlang 👇"
    await message.answer(msg, reply_markup=main_keyboard(is_admin), parse_mode="Markdown")

@user_router.callback_query(F.data == "check_sub_status")
async def cb_check_sub_status(call: types.CallbackQuery):
    is_ok, checks = await check_user_sub(call.bot, call.from_user.id)
    if is_ok:
        await call.message.delete()
        await call.message.answer("✅ **Obunalar tasdiqlandi! Endi botdan to'liq foydalanishingiz mumkin.**", reply_markup=main_keyboard(call.from_user.id in ADMIN_TELEGRAM_IDS), parse_mode="Markdown")
    else:
        await call.message.edit_text("⚠️ **Hali barcha kanallarga obuna bo'lmadingiz!**\nQuyidagi kanallarga obuna bo'ling:", reply_markup=force_sub_keyboard(checks), parse_mode="Markdown")
    await call.answer()

@user_router.message(F.text == "👤 Profilim")
async def cmd_profile(message: types.Message):
    if await check_guard(message, message.bot): return
    user = await get_or_create_user_async(message.from_user)
    is_admin = message.from_user.id in ADMIN_TELEGRAM_IDS or user.get("is_admin", False)
    msg = f"👤 **SHAXSIY PROFILINGIZ:**\n\nIsm: **{user.get('full_name')}**\n🆔 Telegram ID: `{message.from_user.id}`\n💰 Balans: **{user.get('balance', 0.0):,.0f} so'm**\nMaqom: **{'👑 Administrator' if is_admin else '👤 Mijoz'}**"
    await message.answer(msg, parse_mode="Markdown")

@user_router.message(F.text == "💳 Balans")
async def cmd_balance(message: types.Message):
    if await check_guard(message, message.bot): return
    user = await get_or_create_user_async(message.from_user)
    sett = await get_db_settings()
    msg = f"💳 **BALANS SOZLAMALARI**\n\nSizning joriy balansingiz: **{user.get('balance', 0.0):,.0f} so'm**\n\n📌 **To'lov uchun karta ma'lumotlari:**\n💳 Karta: `{sett.get('card_number')}`\n👤 Ega: **{sett.get('card_holder')}**\n\nO'tkazmani bajargach, **'➕ To'lov Arizasi Yuborish'** tugmasini bosing va chekni yuboring."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ To'lov Arizasi Yuborish", callback_data="start_topup_flow")]
    ])
    await message.answer(msg, reply_markup=kb, parse_mode="Markdown")

@user_router.callback_query(F.data == "start_topup_flow")
async def cb_topup_start(call: types.CallbackQuery, state: FSMContext):
    if await check_guard(call, call.bot): return
    await state.set_state(UserStates.waiting_topup_amount)
    await call.message.answer("💵 O'tkazgan sumangizni kiriting (masalan: `50000`):", parse_mode="Markdown")
    await call.answer()

@user_router.message(UserStates.waiting_topup_amount)
async def process_topup_amt(message: types.Message, state: FSMContext):
    if await check_guard(message, message.bot): return
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Faqat raqam kiriting (masalan: 50000):")
        return
    await state.update_data(amt=message.text)
    await state.set_state(UserStates.waiting_topup_receipt)
    await message.answer("🧾 Chek rasmini, TxID kodi yoki izohini yuboring:")

@user_router.message(UserStates.waiting_topup_receipt, F.photo | F.text)
async def process_topup_rec(message: types.Message, state: FSMContext):
    if await check_guard(message, message.bot): return
    data = await state.get_data()
    amt = float(data.get("amt"))
    email = f"tg_{message.from_user.id}@telegram.com"

    photo_id = None
    receipt_info = ""

    if message.photo:
        photo_id = message.photo[-1].file_id
        receipt_info = message.caption or "📸 Chek rasmi yuborildi"
    elif message.text:
        receipt_info = message.text.strip()

    topup_id = await create_topup(message.from_user.id, email, amt, receipt_info)
    await state.clear()

    await message.answer("✅ **To'lov arizangiz muvaffaqiyatli yuborildi!**\nAdmin tekshirib balansga qo'shadi.", parse_mode="Markdown")

    txt = (
        f"🔔 **YANGI TO'LOV ARIZASI!**\n\n"
        f"👤 User: {message.from_user.full_name} (`{message.from_user.id}`)\n"
        f"💰 Summa: **{amt:,.0f} so'm**\n"
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
                await message.bot.send_photo(admin_id, photo=photo_id, caption=txt, reply_markup=kb, parse_mode="Markdown")
            else:
                await message.bot.send_message(admin_id, txt, reply_markup=kb, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

@user_router.message(F.text == "🚀 Nakrutka Buyurtma Qilish")
async def cmd_services(message: types.Message):
    if await check_guard(message, message.bot): return
    cats = await get_categories()
    kb = categories_inline_keyboard(cats)
    if not kb.inline_keyboard:
        await message.answer("🛍 Hozircha xizmatlar bo'limlari kiritilmagan. Admin panel orqali qo'shing yoki SMM API'dan yuklang.")
        return
    await message.answer("📁 **BO'LIMNI (KATEGORIYANI) TANLANG:**", reply_markup=kb, parse_mode="Markdown")

@user_router.callback_query(F.data.startswith("cat_"))
async def cb_category(call: types.CallbackQuery):
    if await check_guard(call, call.bot): return
    cat = call.data.split("cat_")[1]
    services = await get_services_by_category(cat)
    if not services:
        await call.answer("❌ Ushbu bo'limda hozircha xizmatlar yo'q!", show_alert=True)
        return
    kb = services_by_category_keyboard(services, cat)
    await call.message.edit_text(f"📁 **{cat}** bo'limidagi xizmatlar:", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@user_router.callback_query(F.data == "back_to_categories")
async def cb_back_cat(call: types.CallbackQuery):
    if await check_guard(call, call.bot): return
    cats = await get_categories()
    kb = categories_inline_keyboard(cats)
    await call.message.edit_text("📁 **BO'LIMNI (KATEGORIYANI) TANLANG:**", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@user_router.callback_query(F.data.startswith("srv_"))
async def cb_service_select(call: types.CallbackQuery, state: FSMContext):
    if await check_guard(call, call.bot): return
    srv_id = call.data.split("srv_")[1]
    services = await get_all_services()
    srv = next((s for s in services if str(s["id"]) == srv_id), None)
    if not srv:
        await call.answer("❌ Xizmat topilmadi!", show_alert=True)
        return
    await state.update_data(srv=srv)
    await state.set_state(UserStates.waiting_order_link)
    await call.message.answer(f"🔗 **{srv['title']}**\n1000 ta narxi: **{float(srv['price']):,.0f} so'm**\n\nIltimos, HAVOLA (LINK)ni yuboring:", parse_mode="Markdown")
    await call.answer()

@user_router.message(UserStates.waiting_order_link)
async def process_order_link(message: types.Message, state: FSMContext):
    if await check_guard(message, message.bot): return
    if not message.text:
        await message.answer("❌ Iltimos, havola matnini yuboring:")
        return
    await state.update_data(link=message.text.strip())
    await state.set_state(UserStates.waiting_order_quantity)
    await message.answer("🔢 Qancha miqdorda kerak? (Masalan: `1000`):", parse_mode="Markdown")

@user_router.message(UserStates.waiting_order_quantity)
async def process_order_qty(message: types.Message, state: FSMContext):
    if await check_guard(message, message.bot): return
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

    await subtract_user_balance(message.from_user.id, total_price)

    sett = await get_db_settings()
    api_url = sett.get("smm_api_url")
    api_key = sett.get("smm_api_key")
    order_id = "Avto-Bajarilmoqda"
    
    if api_url and api_key:
        try:
            import aiohttp
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

    await create_order_db(message.from_user.id, srv['title'], link, qty, total_price, order_id)
    await message.answer(f"🎉 **BUYURTMA MUVAFFAQIYATLI QABUL QILINDI!**\n\n🔹 Xizmat: **{srv['title']}**\n🔗 Link: `{link}`\n🔢 Miqdor: **{qty} ta**\n💰 Yechilgan summa: **{total_price:,.0f} so'm**\n🆔 Order ID: `{order_id}`", parse_mode="Markdown")

@user_router.message(F.text == "📞 Qo'llab-quvvatlash")
async def cmd_supp(message: types.Message):
    if await check_guard(message, message.bot): return
    await message.answer("📞 Qo'llab-quvvatlash xizmati admini: @plus_ignore")
    
