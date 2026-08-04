import aiohttp
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_TELEGRAM_IDS, AdminStates
from database import (
    get_db_settings,
    update_db_settings,
    get_categories,
    add_category_db,
    get_all_services,
    add_service,
    delete_service,
    get_pending_topups,
    approve_topup_db,
    reject_topup_db,
    get_channels_db,
    add_channel_db,
    delete_channel_db,
    logger,
)
from keyboards import (
    categories_inline_keyboard,
    admin_dashboard_keyboard,
    admin_channels_keyboard,
)

admin_router = Router()

@admin_router.message(Command("admin"))
@admin_router.message(F.text == "👑 Admin Panel")
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        await message.answer("❌ Siz admin emassiz!")
        return
    sett = await get_db_settings()
    is_m = sett.get("is_maintenance", False)
    await message.answer("👑 **ADMINISTRATOR BOSHGARUV DASHBOARDI:**", reply_markup=admin_dashboard_keyboard(is_m), parse_mode="Markdown")

# Majburiy Obuna Sozlamalari
@admin_router.callback_query(F.data == "adm_channels")
async def cb_adm_channels(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await call.message.answer("📢 **MAJBURIY OBUNA KANALLARI BOSHGARUVI:**", reply_markup=admin_channels_keyboard())
    await call.answer()

@admin_router.callback_query(F.data == "adm_add_chan")
async def cb_adm_add_chan(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.set_state(AdminStates.waiting_channel_id)
    await call.message.answer("🆔 Kanal Username (masalan `@MeningKanalim`) yoki ID raqamini kiriting:")
    await call.answer()

@admin_router.message(AdminStates.waiting_channel_id)
async def process_chan_id(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.update_data(chan_id=message.text.strip())
    await state.set_state(AdminStates.waiting_channel_title)
    await message.answer("📢 Kanal nomini kiriting (masalan: `Mening Rasmiy Kanalim`):")

@admin_router.message(AdminStates.waiting_channel_title)
async def process_chan_title(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.update_data(chan_title=message.text.strip())
    await state.set_state(AdminStates.waiting_channel_link)
    await message.answer("🔗 Kanalga taklif havolasini kiriting (masalan: `https://t.me/MeningKanalim`):")

@admin_router.message(AdminStates.waiting_channel_link)
async def process_chan_link(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    data = await state.get_data()
    await add_channel_db(data["chan_id"], data["chan_title"], message.text.strip())
    await state.clear()
    await message.answer("✅ **Yangi majburiy obuna kanali qo'shildi!**\nBotni o'sha kanalda ADMIN qilishni unutmang!", parse_mode="Markdown")

@admin_router.callback_query(F.data == "adm_list_chan")
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

@admin_router.callback_query(F.data.startswith("delchan_"))
async def cb_delchan(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    ch_id = call.data.split("delchan_")[1]
    await delete_channel_db(ch_id)
    await call.message.edit_text("❌ **Kanal ro'yxatdan o'chirildi!**", parse_mode="Markdown")
    await call.answer()

# To'lovlar va Tasdiqlash
@admin_router.callback_query(F.data == "adm_topups")
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

@admin_router.callback_query(F.data.startswith("appr_"))
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
                await call.bot.send_message(int(tg_id_str), f"🎉 **BALANSINGIZ TO'LDIRILDI!**\n\n💰 +{amount:,.0f} so'm balansingizga o'tdi.", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"User notify error: {e}")

        if ref:
            try:
                await call.bot.send_message(
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

@admin_router.callback_query(F.data.startswith("rej_"))
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

@admin_router.callback_query(F.data == "adm_smm_config")
async def cb_adm_smm_config(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.set_state(AdminStates.waiting_smm_url)
    await call.message.answer("🔑 SMM Panel API URL manzilini kiriting (masalan: `https://topsmm.uz/api/v2`):", parse_mode="Markdown")
    await call.answer()

@admin_router.message(AdminStates.waiting_smm_url)
async def process_smm_url(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.update_data(smm_url=message.text.strip())
    await state.set_state(AdminStates.waiting_smm_key)
    await message.answer("🔑 SMM Panel API Kalitini (API Key) kiriting:")

@admin_router.message(AdminStates.waiting_smm_key)
async def process_smm_key(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    data = await state.get_data()
    url = data["smm_url"]
    key = message.text.strip()
    await update_db_settings(smm_api_url=url, smm_api_key=key)
    await state.clear()
    await message.answer(f"✅ **SMM API NEON POSTGRESQL'GA SAQLANDI!**\n\n🌐 URL: `{url}`\n🔑 KEY: `{key[:6]}...`", parse_mode="Markdown")

@admin_router.callback_query(F.data == "adm_fetch_smm")
async def cb_adm_fetch_smm(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
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

@admin_router.message(AdminStates.waiting_markup_percent)
async def process_markup_percent(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
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

@admin_router.callback_query(F.data == "adm_manage_cats")
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

@admin_router.callback_query(F.data == "adm_add_cat_btn")
async def cb_adm_add_cat_btn(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.set_state(AdminStates.waiting_new_cat)
    await call.message.answer("📁 Yangi bo'lim nomini kiriting (masalan: `Telegram`, `Instagram`, `TikTok`):")
    await call.answer()

@admin_router.message(AdminStates.waiting_new_cat)
async def process_new_cat(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    cat_name = message.text.strip()
    await add_category_db(cat_name)
    await state.clear()
    await message.answer(f"✅ **Yangi '{cat_name}' bo'limi yaratildi!**", parse_mode="Markdown")

@admin_router.callback_query(F.data == "adm_add_srv")
async def cb_adm_add_srv(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    cats = await get_categories()
    if not cats:
        await call.message.answer("⚠️ Avval '📁 Bo'limlar Sozlash' tugmasi orqali kamida 1 ta bo'lim yaratib oling!")
        await call.answer()
        return
    await state.set_state(AdminStates.waiting_new_srv_name)
    await call.message.answer("🔹 Yangi xizmat nomini kiriting:")
    await call.answer()

@admin_router.message(AdminStates.waiting_new_srv_name)
async def process_new_srv_name(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminStates.waiting_new_srv_price)
    await message.answer("💰 1000 ta uchun sotuv narxini kiriting (masalan: `15000`):")

@admin_router.message(AdminStates.waiting_new_srv_price)
async def process_new_srv_price(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Narxni raqamda kiriting:")
        return
    await state.update_data(price=message.text.strip())
    await state.set_state(AdminStates.waiting_new_srv_provider_id)
    await message.answer("🆔 SMM Provayder Service ID'sini kiriting (masalan: `102`):")

@admin_router.message(AdminStates.waiting_new_srv_provider_id)
async def process_new_srv_provider_id(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.update_data(prov_id=message.text.strip())
    cats = await get_categories()
    kb = categories_inline_keyboard(cats)
    await message.answer("📁 Ushbu xizmat qaysi bo'limga tegishli? Bo'limni tanlang:", reply_markup=kb)

@admin_router.callback_query(AdminStates.waiting_new_srv_provider_id, F.data.startswith("cat_"))
async def process_srv_cat_choice(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
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

@admin_router.callback_query(F.data == "adm_manage_srv")
async def cb_adm_manage_srv(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
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

@admin_router.callback_query(F.data.startswith("delsrv_"))
async def cb_delsrv(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    srv_id = call.data.split("delsrv_")[1]
    await delete_service(srv_id)
    await call.message.edit_text("❌ **Xizmat Neon PostgreSQL bazasidan o'chirildi!**", parse_mode="Markdown")
    await call.answer()

@admin_router.callback_query(F.data == "adm_card")
async def cb_adm_card(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.set_state(AdminStates.waiting_card_number)
    await call.message.answer("💳 Yangi karta raqamini kiriting:")
    await call.answer()

@admin_router.message(AdminStates.waiting_card_number)
async def process_card_num(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    await state.update_data(c_num=message.text.strip())
    await state.set_state(AdminStates.waiting_card_holder)
    await message.answer("👤 Karta egasining ismini kiriting:")

@admin_router.message(AdminStates.waiting_card_holder)
async def process_card_hold(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_TELEGRAM_IDS: return
    data = await state.get_data()
    await update_db_settings(card_number=data["c_num"], card_holder=message.text.strip())
    await state.clear()
    await message.answer("✅ Karta ma'lumotlari Neon PostgreSQL'da yangilandi!")
