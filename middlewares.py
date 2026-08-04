import logging
from aiogram import types
from config import ADMIN_TELEGRAM_IDS
from database import get_db_settings, get_channels_db
from keyboards import force_sub_keyboard

logger = logging.getLogger(__name__)

async def check_user_sub(bot, user_id):
    try:
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
                is_sub = True

            checks.append({"title": ch["title"], "invite_link": ch["invite_link"], "is_sub": is_sub})
            if not is_sub:
                unsubscribed_count += 1

        return unsubscribed_count == 0, checks
    except Exception as e:
        logger.error(f"check_user_sub exception: {e}")
        return True, []

async def check_guard(event: types.TelegramObject, bot) -> bool:
    try:
        user_id = event.from_user.id if event.from_user else 0
        if user_id in ADMIN_TELEGRAM_IDS:
            return False

        # 1. Texnik Rejim
        sett = await get_db_settings()
        if sett and sett.get("is_maintenance", False):
            msg_text = "🛠 **BOTDA TEXNIK ISHLAR OLIB BORILMOQDA!**\n\nHozirda botda yangilanish ketmoqda. Birozdan so'ng qayta urinib ko'ring."
            if isinstance(event, types.Message):
                await event.answer(msg_text, parse_mode="Markdown")
            elif isinstance(event, types.CallbackQuery):
                await event.answer("🛠 Botda texnik ishlar ketmoqda!", show_alert=True)
            return True

        # 2. Majburiy Obuna
        is_ok, checks = await check_user_sub(bot, user_id)
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
    except Exception as e:
        logger.error(f"check_guard exception: {e}")
        return False
        
