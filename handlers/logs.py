import os
import logging
from aiogram import Router, F, types
from aiogram.types import FSInputFile

from config import ADMIN_TELEGRAM_IDS

logs_router = Router()
LOG_FILE_PATH = "bot_logs.txt"

# ==========================================
# ⚙️ LOGGING SOZLAMALARI (FILE + CONSOLE)
# ==========================================

def setup_logger():
    """Barcha log va xatoliklarni bot_logs.txt fayliga yozishni sozlash"""
    file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

# ==========================================
# 📑 LOGLARNI YUKLASH VA AVTO-TOZALASH
# ==========================================

@logs_router.callback_query(F.data == "adm_get_logs")
async def cb_get_logs(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS:
        return

    # 1. Fayl mavjudligi va bo'sh emasligini tekshirish
    if not os.path.exists(LOG_FILE_PATH) or os.path.getsize(LOG_FILE_PATH) == 0:
        await call.message.answer("📑 **Hozircha hech qanday xatolik yoki log mavjud emas (fayl bo'sh).**", parse_mode="Markdown")
        await call.answer()
        return

    await call.message.answer("⏳ Log fayli tayyorlanmoqda...")

    try:
        # 2. Log faylini Telegram'ga yuborish
        log_document = FSInputFile(LOG_FILE_PATH, filename="bot_logs.txt")
        await call.bot.send_document(
            chat_id=call.from_user.id,
            document=log_document,
            caption="📑 **BOTNING BARCHA LOGLARI VA XATOLIKLARI FAYLI**\n\n⚠️ *Server xotirasini to'ldirmasligi uchun fayl xotiradan avtomatik tozalandi.*",
            parse_mode="Markdown"
        )

        # 3. Fayl tarkibini avtomatik tozalash (Truncate)
        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.write("") # Faylni bo'shatadi

        await call.answer("✅ Loglar yuborildi va xotira tozalandi!")
    except Exception as e:
        await call.message.answer(f"❌ Loglarni yuborishda xatolik yuz berdi: {e}")
        await call.answer()
      
