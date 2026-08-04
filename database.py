import os
import logging
import aiohttp
from aiogram.fsm.state import State, StatesGroup

# ==========================================
# ⚙️ SOZLAMALAR VA ABADIY ADMIN ID
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "7832829103:AAH_YOUR_TELEGRAM_BOT_TOKEN_HERE")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wskiglwygorhjmhrmoxm.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_udznrMLszrXelL-P1CbLNA_ayort0ja")

# Ziyodbekning shaxsiy Telegram ID raqami (O'zgarmas):
ADMIN_TELEGRAM_IDS = [8926978756]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
# ⚡ ANIQLASHTIRILGAN DATABASE SO'ROVLARI (LOG BILAN)
# ==========================================

async def db_query_async(endpoint, method="GET", payload=None):
    """Supabase REST API bilan muloqot va xatoliklarni to'g'ridan-to'g'ri chiqarish"""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    async with aiohttp.ClientSession() as session:
        try:
            if method == "GET":
                async with session.get(url, headers=HEADERS, timeout=10) as res:
                    response_text = await res.text()
                    if res.status in [200, 201]:
                        return await res.json()
                    logger.error(f"Supabase GET Error [{res.status}]: {response_text}")
                    return []
            elif method == "POST":
                async with session.post(url, headers=HEADERS, json=payload, timeout=10) as res:
                    response_text = await res.text()
                    if res.status in [200, 201]:
                        return await res.json()
                    logger.error(f"Supabase POST Error [{res.status}] on {endpoint}: {response_text}")
                    return None
            elif method == "PATCH":
                async with session.patch(url, headers=HEADERS, json=payload, timeout=10) as res:
                    response_text = await res.text()
                    if res.status in [200, 204]:
                        return True
                    logger.error(f"Supabase PATCH Error [{res.status}] on {endpoint}: {response_text}")
                    return False
            elif method == "DELETE":
                async with session.delete(url, headers=HEADERS, timeout=10) as res:
                    response_text = await res.text()
                    if res.status in [200, 204]:
                        return True
                    logger.error(f"Supabase DELETE Error [{res.status}] on {endpoint}: {response_text}")
                    return False
        except Exception as e:
            logger.error(f"Async DB Exception [{endpoint}]: {e}")
            return [] if method == "GET" else None

async def get_or_create_user_async(user):
    """Foydalanuvchini bazadan izlaydi yoki yangi ro'yxatdan o'tkazadi"""
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

async def get_db_settings():
    res = await db_query_async("settings?id=eq.1")
    if isinstance(res, list) and len(res) > 0:
        return res[0]
    
    default_settings = {
        "id": 1,
        "card_number": "8600 0000 0000 0000",
        "card_holder": "Ziyodbek G.",
        "smm_api_url": "",
        "smm_api_key": "",
        "is_maintenance": False
    }
    await db_query_async("settings", method="POST", payload=default_settings)
    return default_settings

async def update_db_settings(payload):
    await get_db_settings()
    return await db_query_async("settings?id=eq.1", method="PATCH", payload=payload)

# ==========================================
# 🔍 TO'LIQ TIZIM DIAGNOSTIKASI
# ==========================================

async def run_full_diagnostics(bot_instance):
    report = ["🔍 **TIZIM DIAGNOSTIKASI VA HOLAT HISOBOТI**\n"]

    try:
        me = await bot_instance.get_me()
        report.append(f"✅ **Telegram Bot API:** A'lo (`@{me.username}` online)")
    except Exception as e:
        report.append(f"❌ **Telegram Bot API:** Xatolik ({e})")

    sett = await get_db_settings()
    if isinstance(sett, dict) and "error" not in sett:
        report.append("✅ **Supabase Settings Jadvali:** Ishlayapti")
    else:
        report.append(f"❌ **Supabase Settings Jadvali:** Xatolik")

    users = await db_query_async("users?select=id")
    if isinstance(users, list):
        report.append(f"✅ **Supabase Users Jadvali:** Ishlayapti ({len(users)} ta user bazada mavjud)")
    else:
        report.append(f"❌ **Supabase Users Jadvali:** Ulanib bo'lmadi (Loglarni tekshiring)")

    services = await db_query_async("services?select=id")
    if isinstance(services, list):
        report.append(f"✅ **Supabase Services Jadvali:** Ishlayapti ({len(services)} ta xizmat)")
    else:
        report.append(f"❌ **Supabase Services Jadvali:** Ulanib bo'lmadi")

    api_url = sett.get("smm_api_url", "")
    api_key = sett.get("smm_api_key", "")

    if not api_url or not api_key:
        report.append("⚠️ **SMM Panel API:** URL yoki Key sozlanmagan!")
    else:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"key": api_key, "action": "balance"}
                async with session.post(api_url, data=payload, timeout=8) as res:
                    if res.status == 200:
                        data = await res.json()
                        if "balance" in data:
                            report.append(f"✅ **SMM API Ulanishi:** A'lo (Balans: `{data['balance']}`)")
                        else:
                            report.append(f"⚠️ **SMM API Ulanishi:** Kalit xato: `{data}`")
                    else:
                        report.append(f"❌ **SMM API Ulanishi:** HTTP {res.status}")
        except Exception as e:
            report.append(f"❌ **SMM API Ulanishi:** {e}")

    is_m = sett.get("is_maintenance", False)
    report.append(f"\n⚙️ **Bot Rejimi:** {'🔴 Texnik Ishlar' if is_m else '🟢 Ishchi Rejim'}")

    return "\n".join(report)
            
