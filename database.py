import os
import logging
import aiohttp
from aiogram.fsm.state import State, StatesGroup

# ==========================================
# ⚙️ ASOSIY SOZLAMALAR VA ABADIY ADMIN ID
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "7832829103:AAH_YOUR_TELEGRAM_BOT_TOKEN_HERE")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wskiglwygorhjmhrmoxm.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_udznrMLszrXelL-P1CbLNA_ayort0ja")

# Ziyodbekning shaxsiy Telegram ID raqami (Abadiy qilib belgilandi):
ADMIN_TELEGRAM_IDS = [8926978756]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Keshda saqlanadigan tezkor karta sozlamalari
SETTINGS_CACHE = {
    "card_number": "8600 0000 0000 0000",
    "card_holder": "Ziyodbek G.",
    "smm_api_url": "",
    "smm_api_key": ""
}

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

# ==========================================
# ⚡ ASINXRON DATABASE FUNKSIYALARI
# ==========================================

async def db_query_async(endpoint, method="GET", payload=None):
    """Supabase REST API bilan asinxron muloqot qiluvchi markaziy funksiya"""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    async with aiohttp.ClientSession() as session:
        try:
            if method == "GET":
                async with session.get(url, headers=HEADERS, timeout=10) as res:
                    return await res.json()
            elif method == "POST":
                async with session.post(url, headers=HEADERS, json=payload, timeout=10) as res:
                    return await res.json()
            elif method == "PATCH":
                async with session.patch(url, headers=HEADERS, json=payload, timeout=10) as res:
                    return await res.json()
            elif method == "DELETE":
                async with session.delete(url, headers=HEADERS, timeout=10) as res:
                    return await res.json()
        except Exception as e:
            logger.error(f"Async DB Error [{endpoint}]: {e}")
            return [] if method == "GET" else None

async def get_or_create_user_async(user):
    """Foydalanuvchini bazadan izlaydi yoki yangi yaratadi"""
    email = f"tg_{user.id}@telegram.com"
    res = await db_query_async(f"users?email=eq.{email}")
    if isinstance(res, list) and len(res) > 0:
        return res[0]
    
    payload = {
        "email": email,
        "full_name": user.full_name or user.username or "Foydalanuvchi",
        "balance": 0.0,
        "is_admin": user.id in ADMIN_TELEGRAM_IDS
    }
    new_res = await db_query_async("users", method="POST", payload=payload)
    if isinstance(new_res, list) and len(new_res) > 0:
        return new_res[0]
    return payload

async def update_settings_cache():
    """Karta va SMM API sozlamalarini xotiraga yuklaydi"""
    global SETTINGS_CACHE
    res = await db_query_async("settings?id=eq.1")
    if isinstance(res, list) and len(res) > 0:
        SETTINGS_CACHE = res[0]
