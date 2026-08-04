import os
from aiogram.fsm.state import State, StatesGroup

# ==========================================
# ⚙️ SOZLAMALAR VA ADMIN ID
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "7832829103:AAH_YOUR_TELEGRAM_BOT_TOKEN_HERE")

# Ziyodbekning Neon.tech PostgreSQL ulanish manzili:
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://neondb_owner:npg_UZpcfN20OHqG@ep-silent-dew-asqaa9za-pooler.c-4.eu-central-1.aws.neon.tech/neondb?sslmode=require"
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
