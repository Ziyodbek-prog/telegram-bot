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
    init_db,
    get_or_create_user_async,
    get_user_referrals_info,
    get_db_settings,
    update_db_settings,
    get_categories,
    add_category_db,
    delete_category_db,
    get_all_services,
    get_services_by_category,
    add_service,
    delete_service,
    create_order_db,
    create_topup,
    get_pending_topups,
    approve_topup_db,
    reject_topup_db,
    get_channels_db,
    add_channel_db,
    delete_channel_db,
    get_expanded_stats,
    run_full_diagnostics,
    db_pool,
    logger,
)
from keyboards import (
    main_keyboard,
    categories_inline_keyboard,
    services_by_category_keyboard,
    force_sub_keyboard,
    admin_dashboard_keyboard,
    admin_channels_keyboard,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================================
# 🛑 MIDDLEWARES (TEXNIK REJIM & MAJBURIY OBUNA)
# ==========================================

async def check_user_sub(user_id):
    """Foydalanuvchining majburiy kanallarga obuna bo'lganini tekshirish"""
    channels = await get_channels_db()
    if not channels:
        return True, []

    checks = []
    unsubscribed_count = 0

    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["channel_id"], user_id=user_id)
            is_sub = member.status in ["creator", "administrator", "member"]
        except Exception as e:
            logger.error(f"Channel sub check error ({ch['channel_id']}): {e}")
            is_sub = True # Agar bot kanalda admin bo'lmasa o'tkazib yuboradi

        checks.append({"title": ch["title"], "invite_link": ch["invite_link"], "is_sub": is_sub})
        if not is_sub:
            unsubscribed_count += 1

    return unsubscribed_count == 0, checks

async def check_guard(event: types.TelegramObject) -> bool:
    """Xavfsizlik va obuna nazorati"""
    user_id = event.from_user.id if event.from_user else 0
    if user_id in ADMIN_TELEGRAM_IDS:
        return False

    # 1. Texnik Rejim
    sett = await get_db_settings()
    if sett.get("is_maintenance", False):
        msg_text = "🛠 **BOTDA TEXNIK ISHLAR OLIB BORILMOQDA!**\n\nHozirda botda yangilanish ketmoqda. Birozdan so'ng qayta urinib ko'ring."
        if isinstance(event, types.Message):
            await event.answer(msg_text, parse_mode="Markdown")
        elif isinstance(event, types.CallbackQuery):
            await event.answer("🛠 Botda texnik ishlar ketmoqda!", show_alert=True)
        return True

    # 2. Majburiy Obuna
    is_ok, checks = await check_user_sub(user_id)
    if not is_ok:
        msg_text = "⚠️ **BOTDAN FOYDALANISH UCHUN QUYIDAGI KANALLARGA OBUNA BO'LING:**"
        kb = force_sub_keyboard(checks)
        if isinstance(event, types.Message):
            await event.answer(msg_text, reply_markup=kb, parse_mode="Markdown")
        elif isinstance(event, types.CallbackQuery):
            if event.data != "check_sub_status":
                await event.message.answer(msg_text, reply_markup=kb, parse_mode="Markdown")
                await event.answer()
        return True

    return False

# ==========================================
# 🤖 FOYDALANUVCHI HANDLERLARI
# ==========================================

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    # Referal ID ajratib olish
    args = message.text.split()
    referrer_id = args[1] if len(args) > 1 else None

    if await check_guard(message): return
    user = await get_or_create_user_async(message.from_user, referrer_id)
    is_admin = message.from_user.id in ADMIN_TELEGRAM_IDS or user.get("is_admin", False)
    msg = f"🔥 **Salom, {message.from_user.full_name}!**\n\n⚡ **Ziyodbek MultiTool SMM Engine'ga xush kelibsiz!**\n\nKerakli bo'limni pastdagi menyudan tanlang 👇"
    await message.answer(msg, reply_markup=main_keyboard(is_admin), parse_mode="Markdown")

@dp.callback_query(F.data == "check_sub_status")
async def cb_check_sub_status(call: types.CallbackQuery):
    is_ok, checks = await check_user_sub(call.from_user.id)
    if is_ok:
        await call.message.delete()
        await call.message.answer("✅ **Obunalar tasdiqlandi! Endi botdan to'liq foydalanishingiz mumkin.**", reply_markup=main_keyboard(call.from_user.id in ADMIN_TELEGRAM_IDS), parse_mode="Markdown")
    else:
        await call.message.edit_text("⚠️ **Hali barcha kanallarga obuna bo'lmadingiz!**\nQuyidagi kanallarga obuna bo'ling:", reply_markup=force_sub_keyboard(checks), parse_mode="Markdown")
    await call.answer()

@dp.message(F.text == "👤 Profilim")
async def cmd_profile(message: types.Message):
    if await check_guard(message): return
    user = await get_or_create_user_async(message.from_user)
    is_admin = message.from_user.id in ADMIN_TELEGRAM_IDS or user.get("is_admin", False)
    msg = f"👤 **SHAXSIY PROFILINGIZ:**\n\nIsm: **{user.get('full_name')}**\n🆔 Telegram ID: `{message.from_user.id}`\n💰 Balans: **{user.get('balance', 0.0):,.0f} so'm**\nMaqom: **{'👑 Administrator' if is_admin else '👤 Mijoz'}**"
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "👥 Referal Tizim")
async def cmd_ref(message: types.Message):
    if await check_guard(message): return
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start={message.from_user.id}"
    ref_info = await get_user_referrals_info(message.from_user.id)
    sett = await get_db_settings()

    recent_str = ""
    if ref_info["recent"]:
        recent_str = "\n\n👥 **Oxirgi taklif qilingan do'stlar:**\n" + "\n".join([f"• {r['full_name']}" for r in ref_info["recent"]])

    msg = (
        f"👥 **REFERAL DASTURI**\n\n"
        f"Do'stlaringizni taklif qiling va har bir to'lovidan **{sett.get('ref_percent', 10.0)}% daromad** oling!\n\n"
        f"🔗 **Sizning havolangiz:**\n`{ref_link}`\n\n"
        f"📊 **Sizning statistikangiz:**\n"
        f"👤 Taklif qilingan do'stlar: **{ref_info['count']} ta**\n"
        f"💰 Ishlangan jami daromad: **{ref_info['earnings']:,.0f} so'm**"
        f"{recent_str}"
    )
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "💳 Balans")
async def cmd_balance(message: types.Message):
    if await check_guard(message): return
    user = await get_or_create_user_async(message.from_user)
    sett = await get_db_settings()
    msg = f"💳 **BALANS SOZLAMALARI**\n\nSizning joriy balansingiz: **{user.get('balance', 0.0):,.0f} so'm**\n\n📌 **To'lov uchun karta ma'lumotlari:**\n💳 Karta: `{sett.get('card_number')}`\n👤 Ega: **{sett.get('card_holder')}**\n\nO'tkazmani bajargach, **'➕ To'lov Arizasi Yuborish'** tugmasini bosing va chekni yuboring."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ To'lov Arizasi Yuborish", callback_data="start_topup_flow")]
    ])
    await message.answer(msg, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "start_topup_flow")
async def cb_topup_start(call: types.CallbackQuery, state: FSMContext):
    if await check_guard(call): return
    await state.set_state(UserStates.waiting_topup_amount)
    await call.message.answer("💵 O'tkazgan sumangizni kiriting (masalan: `50000`):", parse_mode="Markdown")
    await call.answer()

@dp.message(UserStates.waiting_topup_amount)
async def process_topup_amt(message: types.Message, state: FSMContext):
    if await check_guard(message): return
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Faqat raqam kiriting (masalan: 50000):")
        return
    await state.update_data(amt=message.text)
    await state.set_state(UserStates.waiting_topup_receipt)
    await message.answer("🧾 Chek rasmini, TxID kodi yoki izohini yuboring:")

@dp.message(UserStates.waiting_topup_receipt, F.photo | F.text)
async def process_topup_rec(message: types.Message, state: FSMContext):
    if await check_guard(message): return
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
                await bot.send_photo(admin_id, photo=photo_id, caption=txt, reply_markup=kb, parse_mode="Markdown")
            else:
                await bot.send_message(admin_id, txt, reply_markup=kb, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

@dp.message(F.text == "🚀 Nakrutka Buyurtma Qilish")
async def cmd_services(message: types.Message):
    if await check_guard(message): return
    cats = await get_categories()
    kb = categories_inline_keyboard(cats)
    if not kb.inline_keyboard:
        await message.answer("🛍 Hozircha xizmatlar bo'limlari kiritilmagan. Admin panel orqali qo'shing yoki SMM API'dan yuklang.")
        return
    await message.answer("📁 **BO'LIMNI (KATEGORIYANI) TANLANG:**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def cb_category(call: types.CallbackQuery):
    if await check_guard(call): return
    cat = call.data.split("cat_")[1]
    services = await get_services_by_category(cat)
    if not services:
        await call.answer("❌ Ushbu bo'limda hozircha xizmatlar yo'q!", show_alert=True)
        return
    kb = services_by_category_keyboard(services, cat)
    await call.message.edit_text(f"📁 **{cat}** bo'limidagi xizmatlar:", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "back_to_categories")
async def cb_back_cat(call: types.CallbackQuery):
    if await check_guard(call): return
    cats = await get_categories()
    kb = categories_inline_keyboard(cats)
    await call.message.edit_text("📁 **BO'LIMNI (KATEGORIYANI) TANLANG:**", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("srv_"))
async def cb_service_select(call: types.CallbackQuery, state: FSMContext):
    if await check_guard(call): return
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

@dp.message(UserStates.waiting_order_link)
async def process_order_link(message: types.Message, state: FSMContext):
    if await check_guard(message): return
    if not message.text:
        await message.answer("❌ Iltimos, havola matnini yuboring:")
        return
    await state.update_data(link=message.text.strip())
    await state.set_state(UserStates.waiting_order_quantity)
    await message.answer("🔢 Qancha miqdorda kerak? (Masalan: `1000`):", parse_mode="Markdown")

@dp.message(UserStates.waiting_order_quantity)
async def process_order_qty(message: types.Message, state: FSMContext):
    if await check_guard(message): return
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

    # Balansdan ayirish
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance - $1 WHERE id = $2", total_price, message.from_user.id)

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

    await create_order_db(message.from_user.id, srv['title'], link, qty, total_price, order_id)
    await message.answer(f"🎉 **BUYURTMA MUVAFFAQIYATLI QABUL QILINDI!**\n\n🔹 Xizmat: **{srv['title']}**\n🔗 Link: `{link}`\n🔢 Miqdor: **{qty} ta**\n💰 Yechilgan summa: **{total_price:,.0f} so'm**\n🆔 Order ID: `{order_id}`", parse_mode="Markdown")

@dp.message(F.text == "📞 Qo'llab-quvvatlash")
async def cmd_supp(message: types.Message):
    if await check_guard(message): return
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
    await call.message.answer("⏳ Neon PostgreSQL va tizim diagnostikasi o'tkazilmoqda...")
    report = await run_full_diagnostics(bot)
    await call.message.answer(report, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "adm_toggle_maintenance")
async def cb_adm_toggle_m(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    sett = await get_db_settings()
    new_status = not sett.get("is_maintenance", False)
    await update_db_settings(is_maintenance=new_status)
    
    st_text = "🔴 BOT O'CHIRILDI (TEXNIK REJIM YOQILDI)" if new_status else "🟢 BOT YOQILDI (ISHCHI REJIM)"
    await call.message.edit_reply_markup(reply_markup=admin_dashboard_keyboard(new_status))
    await call.message.answer(f"⚙️ **REJIM O'ZGARDi:** {st_text}", parse_mode="Markdown")
    await call.answer()

# Majburiy Obuna Sozlamalari
@dp.callback_query(F.data == "adm_channels")
async def cb_adm_channels(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await call.message.answer("📢 **MAJBURIY OBUNA KANALLARI BOSHGARUVI:**", reply_markup=admin_channels_keyboard())
    await call.answer()

@dp.callback_query(F.data == "adm_add_chan")
async def cb_adm_add_chan(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.set_state(AdminStates.waiting_channel_id)
    await call.message.answer("🆔 Kanal Username (masalan `@MeningKanalim`) yoki ID raqamini kiriting:")
    await call.answer()

@dp.message(AdminStates.waiting_channel_id)
async def process_chan_id(message: types.Message, state: FSMContext):
    await state.update_data(chan_id=message.text.strip())
    await state.set_state(AdminStates.waiting_channel_title)
    await message.answer("📢 Kanal nomini kiriting (masalan: `Mening Rasmiy Kanalim`):")

@dp.message(AdminStates.waiting_channel_title)
async def process_chan_title(message: types.Message, state: FSMContext):
    await state.update_data(chan_title=message.text.strip())
    await state.set_state(AdminStates.waiting_channel_link)
    await message.answer("🔗 Kanalga taklif havolasini kiriting (masalan: `https://t.me/MeningKanalim`):")

@dp.message(AdminStates.waiting_channel_link)
async def process_chan_link(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await add_channel_db(data["chan_id"], data["chan_title"], message.text.strip())
    await state.clear()
    await message.answer("✅ **Yangi majburiy obuna kanali qo'shildi!**\nBotni o'sha kanalda ADMIN qilishni unutmang!", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_list_chan")
async def cb_adm_list_chan(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    chans = await get_channels_db()
    if not chans:
        await call.message.answer("📋 Hozircha majburiy kanallar yo'q.")
        await call.answer()
        return

    for ch in chans:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Kanalni O'chirish", callback_data=f"delchan_{ch['id']}")]
        ])
        await call.message.answer(f"📢 **{ch['title']}** (`{ch['channel_id']}`)\n🔗 {ch['invite_link']}", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("delchan_"))
async def cb_delchan(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    ch_id = call.data.split("delchan_")[1]
    await delete_channel_db(ch_id)
    await call.message.edit_text("❌ **Kanal ro'yxatdan o'chirildi!**", parse_mode="Markdown")
    await call.answer()

# To'lovlar va Tasdiqlash
@dp.callback_query(F.data == "adm_topups")
async def cb_adm_topups(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    topups = await get_pending_topups()
    if not topups:
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
    res = await approve_topup_db(topup_id)
    
    if res:
        topup = res["topup"]
        ref = res["ref_notify"]
        email = topup["user_email"]
        amount = topup["amount"]

        try:
            tg_id_str = email.replace("tg_", "").replace("@telegram.com", "")
            if tg_id_str.isdigit():
                await bot.send_message(int(tg_id_str), f"🎉 **BALANSINGIZ TO'LDIRILDI!**\n\n💰 +{amount:,.0f} so'm balansingizga o'tdi.", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"User notify error: {e}")

        # Referalga bonus xabari yuborish
        if ref:
            try:
                await bot.send_message(
                    ref["ref_id"],
                    f"🎉 **REFERAL BONUSI!**\n\nTaklif qilgan do'stingiz hisobini to'ldirdi!\n💰 Sizga **+{ref['bonus']:,.0f} so'm** bonus berildi!",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Referrer notify error: {e}")

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
    await reject_topup_db(topup_id)

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
    await update_db_settings(smm_api_url=url, smm_api_key=key)
    await state.clear()
    await message.answer(f"✅ **SMM API NEON POSTGRESQL'GA SAQLANDI!**\n\n🌐 URL: `{url}`\n🔑 KEY: `{key[:6]}...`", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_fetch_smm")
async def cb_adm_fetch_smm(call: types.CallbackQuery, state: FSMContext):
    sett = await get_db_settings()
    api_url = sett.get("smm_api_url")
    api_key = sett.get("smm_api_key")

    if not api_url or not api_key:
        await call.message.answer("⚠️ Avval '🔑 SMM API Sozlash' bo'limidan SMM API URL va KEY sozlang!")
        await call.answer()
        return

    await call.message.answer("⏳ SMM Provayderidan xizmatlar va bo'limlar yuklanmoqda...")
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"key": api_key, "action": "services"}
            async with session.post(api_url, data=payload, timeout=12) as res:
                services_list = await res.json()
                if isinstance(services_list, list):
                    await state.update_data(api_services=services_list[:30])
                    await state.set_state(AdminStates.waiting_markup_percent)
                    await call.message.answer(f"📦 API'dan **{len(services_list)} ta** xizmat topildi!\n\nXizmatlar ustiga necha foiz ustama qo'shamiz? (Masalan: `50`):", parse_mode="Markdown")
                else:
                    await call.message.answer("❌ SMM API javob bermadi.")
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
        cat_name = s.get("category", "Boshqa SMM")
        
        await add_service(
            category=cat_name,
            title=s.get("name", "Xizmat"),
            price=round(final_price, -2),
            provider_service_id=str(s.get("service"))
        )
        imported_count += 1

    await message.answer(f"🎉 **{imported_count} ta** xizmat va bo'limlar Neon PostgreSQL bazasiga avto-yuklandi!", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_manage_cats")
async def cb_adm_manage_cats(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    cats = await get_categories()
    msg = "📁 **MAVJUD BO'LIMLAR (KATEGORIYALAR):**\n\n"
    for c in cats:
        msg += f"• **{c['name']}**\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi Bo'lim Qo'shish", callback_data="adm_add_cat_btn")]
    ])
    await call.message.answer(msg, reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "adm_add_cat_btn")
async def cb_adm_add_cat_btn(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_new_cat)
    await call.message.answer("📁 Yangi bo'lim nomini kiriting (masalan: `Telegram`, `Instagram`, `TikTok`):")
    await call.answer()

@dp.message(AdminStates.waiting_new_cat)
async def process_new_cat(message: types.Message, state: FSMContext):
    cat_name = message.text.strip()
    await add_category_db(cat_name)
    await state.clear()
    await message.answer(f"✅ **Yangi '{cat_name}' bo'limi yaratildi!**", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_add_srv")
async def cb_adm_add_srv(call: types.CallbackQuery, state: FSMContext):
    cats = await get_categories()
    if not cats:
        await call.message.answer("⚠️ Avval '📁 Bo'limlar Sozlash' tugmasi orqali kamida 1 ta bo'lim yaratib oling!")
        await call.answer()
        return
    await state.set_state(AdminStates.waiting_new_srv_name)
    await call.message.answer("🔹 Yangi xizmat nomini kiriting:")
    await call.answer()

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
    await state.update_data(prov_id=message.text.strip())
    cats = await get_categories()
    kb = categories_inline_keyboard(cats)
    await message.answer("📁 Ushbu xizmat qaysi bo'limga tegishli? Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(AdminStates.waiting_new_srv_provider_id, F.data.startswith("cat_"))
async def process_srv_cat_choice(call: types.CallbackQuery, state: FSMContext):
    cat_name = call.data.split("cat_")[1]
    data = await state.get_data()
    
    await add_service(
        category=cat_name,
        title=data["name"],
        price=float(data["price"]),
        provider_service_id=data["prov_id"]
    )
    await state.clear()
    await call.message.answer(f"✅ **YANGI XIZMAT SAQLANDI!**\n📁 Bo'lim: **{cat_name}**\n🔹 Xizmat: **{data['name']}**\n💰 Narx: **{data['price']} so'm**", parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "adm_manage_srv")
async def cb_adm_manage_srv(call: types.CallbackQuery):
    services = await get_all_services()
    if not services:
        await call.message.answer("🛍 Hozircha bazada xizmatlar yo'q.")
        await call.answer()
        return

    await call.message.answer("⚙️ **MAVJUD XIZMATLAR RO'YXATI:**")
    for s in services[:15]:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Ushbu Xizmatni O'chirish", callback_data=f"delsrv_{s['id']}")]
        ])
        await call.message.answer(f"🔹 **{s['title']}**\n📁 Bo'lim: {s.get('category')} | Narxi: {s['price']} so'm", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("delsrv_"))
async def cb_delsrv(call: types.CallbackQuery):
    srv_id = call.data.split("delsrv_")[1]
    await delete_service(srv_id)
    await call.message.edit_text("❌ **Xizmat Neon PostgreSQL bazasidan o'chirildi!**", parse_mode="Markdown")
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
    await update_db_settings(card_number=data["c_num"], card_holder=message.text.strip())
    await state.clear()
    await message.answer("✅ Karta ma'lumotlari Neon PostgreSQL'da yangilandi!")

@dp.callback_query(F.data == "adm_stats")
async def cb_adm_stats(call: types.CallbackQuery):
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

# ==========================================
# 🌐 RENDER HTTP SERVER
# ==========================================

async def handle_ping(request):
    return web.Response(text="Neon Postgres Pro SMM Bot Engine Live 24/7", status=200)

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
    await init_db()
    logger.info("🚀 Neon Postgres Pro SMM Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
