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
    get_services_paginated,
    get_service_by_id,
    add_service,
    delete_service,
    get_pending_topups,
    approve_topup_db,
    reject_topup_db,
    get_channels_db,
    add_channel_db,
    delete_channel_db,
    SERVICES_PAGE_SIZE,
    logger,
)
from keyboards import (
    categories_inline_keyboard,
    admin_dashboard_keyboard,
    admin_channels_keyboard,
)

admin_router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_TELEGRAM_IDS


async def _deny(event) -> None:
    if isinstance(event, types.CallbackQuery):
        await event.answer("⛔ Sizda ushbu amal uchun ruxsat yo'q!", show_alert=True)
    else:
        await event.answer("⛔ Siz admin emassiz!")


@admin_router.message(Command("admin"))
@admin_router.message(F.text == "👑 Admin Panel")
async def cmd_admin(message: types.Message):
    if not _is_admin(message.from_user.id):
        await _deny(message)
        return
    sett = await get_db_settings()
    is_m = sett.get("is_maintenance", False)
    await message.answer("👑 **ADMINISTRATOR BOSHGARUV DASHBOARDI:**", reply_markup=admin_dashboard_keyboard(is_m), parse_mode="Markdown")

# ==========================================
# 📢 Majburiy Obuna Sozlamalari
# ==========================================

@admin_router.callback_query(F.data == "adm_channels")
async def cb_adm_channels(call: types.CallbackQuery):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    await call.message.answer("📢 **MAJBURIY OBUNA KANALLARI BOSHGARUVI:**", reply_markup=admin_channels_keyboard())
    await call.answer()

@admin_router.callback_query(F.data == "adm_add_chan")
async def cb_adm_add_chan(call: types.CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    await state.set_state(AdminStates.waiting_channel_id)
    await call.message.answer("🆔 Kanal Username (masalan `@MeningKanalim`) yoki ID raqamini kiriting:")
    await call.answer()

@admin_router.message(AdminStates.waiting_channel_id)
async def process_chan_id(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text:
        await message.answer("❌ Iltimos, matn kiriting:")
        return
    await state.update_data(chan_id=message.text.strip())
    await state.set_state(AdminStates.waiting_channel_title)
    await message.answer("📢 Kanal nomini kiriting (masalan: `Mening Rasmiy Kanalim`):")

@admin_router.message(AdminStates.waiting_channel_title)
async def process_chan_title(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text:
        await message.answer("❌ Iltimos, matn kiriting:")
        return
    await state.update_data(chan_title=message.text.strip())
    await state.set_state(AdminStates.waiting_channel_link)
    await message.answer("🔗 Kanalga taklif havolasini kiriting (masalan: `https://t.me/MeningKanalim`):")

@admin_router.message(AdminStates.waiting_channel_link)
async def process_chan_link(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text:
        await message.answer("❌ Iltimos, havola matnini yuboring:")
        return
    data = await state.get_data()
    await add_channel_db(data["chan_id"], data["chan_title"], message.text.strip())
    await state.clear()
    await message.answer("✅ **Yangi majburiy obuna kanali qo'shildi!**\nBotni o'sha kanalda ADMIN qilishni unutmang!", parse_mode="Markdown")

@admin_router.callback_query(F.data == "adm_list_chan")
async def cb_adm_list_chan(call: types.CallbackQuery):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
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
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    ch_id = call.data.split("delchan_")[1]
    await delete_channel_db(ch_id)
    await call.message.edit_text("❌ **Kanal ro'yxatdan o'chirildi!**", parse_mode="Markdown")
    await call.answer()

# ==========================================
# 💳 To'lovlar va Tasdiqlash
# ==========================================

@admin_router.callback_query(F.data == "adm_topups")
async def cb_adm_topups(call: types.CallbackQuery):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    topups = await get_pending_topups()
    if not topups:
        await call.message.answer("📥 Kutilayotgan to'lovlar yo'q.")
        await call.answer()
        return
    for t in topups:
        txt = f"🆔 Ariza #{t['id']}\n📧 User: `{t['user_email']}`\n💰 Summa: **{t['amount']:,.0f} so'm**\n🧾 Izoh: `{t['receipt_info']}`"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"appr_{t['id']}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{t['id']}")
            ]
        ])
        photo_id = t.get("receipt_photo_id")
        if photo_id:
            await call.message.answer_photo(photo_id, caption=txt, reply_markup=kb, parse_mode="Markdown")
        else:
            await call.message.answer(txt, reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@admin_router.callback_query(F.data.startswith("appr_"))
async def cb_appr_topup(call: types.CallbackQuery):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    topup_id = call.data.split("appr_")[1]
    res = await approve_topup_db(topup_id)

    if res:
        topup = res["topup"]
        ref = res["ref_notify"]
        user_id = topup["user_id"]
        amount = topup["amount"]

        try:
            await call.bot.send_message(user_id, f"🎉 **BALANSINGIZ TO'LDIRILDI!**\n\n💰 +{amount:,.0f} so'm balansingizga o'tdi.", parse_mode="Markdown")
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
    else:
        await call.answer("⚠️ Bu ariza allaqachon ko'rib chiqilgan yoki topilmadi.", show_alert=True)

@admin_router.callback_query(F.data.startswith("rej_"))
async def cb_rej_topup(call: types.CallbackQuery):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    topup_id = call.data.split("rej_")[1]
    await reject_topup_db(topup_id)

    reject_msg = f"❌ **Ariza #{topup_id} RAD ETILDI.**"
    if call.message.caption:
        await call.message.edit_caption(caption=reject_msg, parse_mode="Markdown")
    else:
        await call.message.edit_text(text=reject_msg, parse_mode="Markdown")
    await call.answer("❌ Rad etildi!")

# ==========================================
# 🔑 SMM API Sozlash
# ==========================================

@admin_router.callback_query(F.data == "adm_smm_config")
async def cb_adm_smm_config(call: types.CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    await state.set_state(AdminStates.waiting_smm_url)
    await call.message.answer("🔑 SMM Panel API URL manzilini kiriting (masalan: `https://topsmm.uz/api/v2`):", parse_mode="Markdown")
    await call.answer()

@admin_router.message(AdminStates.waiting_smm_url)
async def process_smm_url(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text:
        await message.answer("❌ Iltimos, URL manzilini matn ko'rinishida kiriting:")
        return
    await state.update_data(smm_url=message.text.strip())
    await state.set_state(AdminStates.waiting_smm_key)
    await message.answer("🔑 SMM Panel API Kalitini (API Key) kiriting:")

@admin_router.message(AdminStates.waiting_smm_key)
async def process_smm_key(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text:
        await message.answer("❌ Iltimos, kalitni matn ko'rinishida kiriting:")
        return
    data = await state.get_data()
    url = data["smm_url"]
    key = message.text.strip()
    await update_db_settings(smm_api_url=url, smm_api_key=key)
    await state.clear()
    await message.answer(f"✅ **SMM API NEON POSTGRESQL'GA SAQLANDI!**\n\n🌐 URL: `{url}`\n🔑 KEY: `{key[:6]}...`", parse_mode="Markdown")

@admin_router.callback_query(F.data == "adm_fetch_smm")
async def cb_adm_fetch_smm(call: types.CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
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
            async with session.post(api_url, data=payload, timeout=aiohttp.ClientTimeout(total=15)) as res:
                services_list = await res.json(content_type=None)
                if isinstance(services_list, list):
                    # Juda katta katalog FSM xotirasini (MemoryStorage) og'irlashtirmasligi
                    # uchun cheklov qo'yilgan — kerak bo'lsa oshirishingiz mumkin.
                    MAX_IMPORT = 200
                    await state.update_data(api_services=services_list[:MAX_IMPORT])
                    await state.set_state(AdminStates.waiting_markup_percent)
                    note = "" if len(services_list) <= MAX_IMPORT else f"\n⚠️ Faqat birinchi {MAX_IMPORT} tasi yuklanadi (jami {len(services_list)} ta topildi)."
                    await call.message.answer(f"📦 API'dan **{len(services_list)} ta** xizmat topildi!{note}\n\nXizmatlar ustiga necha foiz ustama qo'shamiz? (Masalan: `50`):", parse_mode="Markdown")
                else:
                    await call.message.answer("❌ SMM API javob bermadi yoki noto'g'ri formatda javob qaytardi.")
    except Exception as e:
        await call.message.answer(f"❌ Xatolik yuz berdi: {e}")
    await call.answer()

@admin_router.message(AdminStates.waiting_markup_percent)
async def process_markup_percent(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Ustama foizni raqamda kiriting (masalan: 50):")
        return

    markup = float(message.text) / 100.0
    data = await state.get_data()
    api_services = data.get("api_services", [])
    await state.clear()

    imported_count = 0
    for s in api_services:
        try:
            base_rate = float(s.get("rate", 1000)) * 12500 / 1000.0
        except (TypeError, ValueError):
            continue
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

# ==========================================
# 📁 Kategoriyalar
# ==========================================

@admin_router.callback_query(F.data == "adm_manage_cats")
async def cb_adm_manage_cats(call: types.CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    cats = await get_categories()
    msg = "📁 **MAVJUD BO'LIMLAR (KATEGORIYALAR):**\n\n"
    if not cats:
        msg += "_Hozircha bo'limlar yo'q._\n"
    for c in cats:
        msg += f"• **{c['name']}**\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi Bo'lim Qo'shish", callback_data="adm_add_cat_btn")]
    ])
    await call.message.answer(msg, reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@admin_router.callback_query(F.data == "adm_add_cat_btn")
async def cb_adm_add_cat_btn(call: types.CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    await state.set_state(AdminStates.waiting_new_cat)
    await call.message.answer("📁 Yangi bo'lim nomini kiriting (masalan: `Telegram`, `Instagram`, `TikTok`):")
    await call.answer()

@admin_router.message(AdminStates.waiting_new_cat)
async def process_new_cat(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text:
        await message.answer("❌ Iltimos, bo'lim nomini kiriting:")
        return
    cat_name = message.text.strip()
    await add_category_db(cat_name)
    await state.clear()
    await message.answer(f"✅ **Yangi '{cat_name}' bo'limi yaratildi!**", parse_mode="Markdown")

# ==========================================
# ➕ Xizmat qo'shish
# ==========================================

@admin_router.callback_query(F.data == "adm_add_srv")
async def cb_adm_add_srv(call: types.CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
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
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text:
        await message.answer("❌ Iltimos, xizmat nomini kiriting:")
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminStates.waiting_new_srv_price)
    await message.answer("💰 1000 ta uchun sotuv narxini kiriting (masalan: `15000`):")

@admin_router.message(AdminStates.waiting_new_srv_price)
async def process_new_srv_price(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Narxni raqamda kiriting:")
        return
    await state.update_data(price=message.text.strip())
    await state.set_state(AdminStates.waiting_new_srv_provider_id)
    await message.answer("🆔 SMM Provayder Service ID'sini kiriting (masalan: `102`):")

@admin_router.message(AdminStates.waiting_new_srv_provider_id)
async def process_new_srv_provider_id(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear(); return
    if not message.text:
        await message.answer("❌ Iltimos, Provider Service ID'ni kiriting:")
        return
    await state.update_data(prov_id=message.text.strip())
    cats = await get_categories()
    kb = categories_inline_keyboard(cats)
    await message.answer("📁 Ushbu xizmat qaysi bo'limga tegishli? Bo'limni tanlang:", reply_markup=kb)

@admin_router.callback_query(AdminStates.waiting_new_srv_provider_id, F.data.startswith("cat_"))
async def process_srv_cat_choice(call: types.CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
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

# ==========================================
# ⚙️ Xizmatlarni boshqarish (pagination bilan)
# ==========================================

def _services_page_keyboard(services, offset, total):
    buttons = []
    for s in services:
        buttons.append([InlineKeyboardButton(
            text=f"❌ {s['title'][:35]} | {s['price']:,.0f} so'm",
            callback_data=f"delsrv_{s['id']}_{offset}"
        )])
    nav = []
    if offset > 0:
        prev_offset = max(0, offset - SERVICES_PAGE_SIZE)
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"srvlist_{prev_offset}"))
    if offset + SERVICES_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"srvlist_{offset + SERVICES_PAGE_SIZE}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def _render_services_page(message: types.Message, offset: int, edit: bool = False):
    services, total = await get_services_paginated(offset=offset)
    if total == 0:
        text = "🛍 Hozircha bazada xizmatlar yo'q."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    page_num = offset // SERVICES_PAGE_SIZE + 1
    total_pages = (total - 1) // SERVICES_PAGE_SIZE + 1
    text = f"⚙️ **XIZMATLAR RO'YXATI** ({page_num}/{total_pages} sahifa, jami {total} ta)\nO'chirish uchun bosing:"
    kb = _services_page_keyboard(services, offset, total)

    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@admin_router.callback_query(F.data == "adm_manage_srv")
async def cb_adm_manage_srv(call: types.CallbackQuery):
    if not _is_admin(call.from_user.id):
        await _deny(call); return
    await _render_services_page(call.message, offset=0, edit=False)
    await call.answer()

@admin_router.callback_query(F.data.startswith("srvlist_"))
async def cb_srvlist_page(call: types.CallbackQuery):
    if not _is_admin(call.from_us
