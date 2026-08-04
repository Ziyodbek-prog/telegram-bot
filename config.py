import os
from aiogram.fsm.state import State, StatesGroup

# ==========================================
# ⚙️ SOZLAMALAR VA ADMIN ID
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Neon.tech PostgreSQL ulanish manzili — FAQAT Render.com "Environment" bo'limidagi
# DATABASE_URL o'zgaruvchisidan olinadi. Bu yerda hech qachon haqiqiy parolni yozib qo'ymang —
# fayl repo yoki boshqa odamga tushib qolsa, butun bazangiz ochiq bo'lib qoladi.
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not BOT_TOKEN or not DATABASE_URL:
    raise RuntimeError(
        "❌ BOT_TOKEN va DATABASE_URL muhit o'zgaruvchilari (Environment Variables) sozlanmagan! "
        "Render.com > Environment bo'limida ularni kiriting."
    )

# Ziyodbekning shaxsiy Telegram ID raqami (O'zgarmas):
ADMIN_TELEGRAM_IDS = [8926978756]

# ==========================================
# 📝 FSM BOSQICHLARI (STATES)
# ==========================================

class UserStates(StatesGroup):
    waiting_topup_amount = State()
    waiting_topup_receipt = State()
    waiting_order_link = State()
    waiting_order_quantity = State()

class AdminStates(StatesGroup):
    waiting_card_number = State()
    waiting_card_holder = State()
    waiting_smm_url = State()
    waiting_smm_key = State()
    waiting_markup_percent = State()
    waiting_new_cat = State()
    waiting_new_srv_name = State()
    waiting_new_srv_price = State()
    waiting_new_srv_provider_id = State()
    waiting_channel_id = State()
    waiting_channel_title = State()
    waiting_channel_link = State()
