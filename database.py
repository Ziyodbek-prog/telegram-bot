import os
import logging
import asyncpg
import aiohttp
from aiogram.fsm.state import State, StatesGroup

# ==========================================
# ⚙️ SOZLAMALAR VA NEON POSTGRESQL ULANISHI
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "7832829103:AAH_YOUR_TELEGRAM_BOT_TOKEN_HERE")

# Ziyodbekning Neon.tech PostgreSQL ulanish manzili:
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://neondb_owner:npg_UZpcfN20OHqG@ep-silent-dew-asqaa9za-pooler.c-4.eu-central-1.aws.neon.tech/neondb?sslmode=require"
)

# Ziyodbekning shaxsiy Telegram ID raqami (O'zgarmas):
ADMIN_TELEGRAM_IDS = [8926978756]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Connection Pool
db_pool = None

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
# ⚡ BAZA BILAN BOG'LANISH VA AVTO-JADVAL YARATISH
# ==========================================

async def init_db():
    """Neon PostgreSQL'ga ulanish va barcha SQL jadvallarni avtomatik yaratish"""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=10)
        logger.info("✅ Neon PostgreSQL bazasiga muvaffaqiyatli ulandi!")
        
        async with db_pool.acquire() as conn:
            # 1. Users Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    email TEXT UNIQUE,
                    full_name TEXT,
                    balance DOUBLE PRECISION DEFAULT 0.0,
                    is_admin BOOLEAN DEFAULT FALSE
                );
            """)

            # 2. Settings Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    id INT PRIMARY KEY DEFAULT 1,
                    card_number TEXT DEFAULT '8600 0000 0000 0000',
                    card_holder TEXT DEFAULT 'Ziyodbek G.',
                    smm_api_url TEXT DEFAULT '',
                    smm_api_key TEXT DEFAULT '',
                    is_maintenance BOOLEAN DEFAULT FALSE
                );
            """)

            # Unikal 1-qatorni yaratish (Default sozlamalar)
            await conn.execute("""
                INSERT INTO settings (id, card_number, card_holder)
                VALUES (1, '8600 0000 0000 0000', 'Ziyodbek G.')
                ON CONFLICT (id) DO NOTHING;
            """)

            # 3. Services Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS services (
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    price DOUBLE PRECISION,
                    category TEXT,
                    provider_service_id TEXT,
                    description TEXT DEFAULT 'Kafolatlangan xizmat'
                );
            """)

            # 4. Topups Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS topups (
                    id SERIAL PRIMARY KEY,
                    user_email TEXT,
                    amount DOUBLE PRECISION,
                    receipt_info TEXT,
                    status TEXT DEFAULT 'pending'
                );
            """)
            logger.info("✅ Barcha SQL jadvallar tayyor holatga keltirildi!")
    except Exception as e:
        logger.error(f"❌ PostgreSQL ulanishda xatolik: {e}")

# ==========================================
# 🛠 BAZA AMALLARI (CRUD)
# ==========================================

async def get_or_create_user_async(user):
    """Foydalanuvchini bazadan izlaydi yoki yangi ro'yxatdan o'tkazadi"""
    email = f"tg_{user.id}@telegram.com"
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user.id)
        if row:
            return dict(row)
        
        is_adm = user.id in ADMIN_TELEGRAM_IDS
        await conn.execute(
            "INSERT INTO users (id, email, full_name, balance, is_admin) VALUES ($1, $2, $3, $4, $5)",
            user.id, email, user.full_name or user.username or "Foydalanuvchi", 0.0, is_adm
        )
        return {"id": user.id, "email": email, "full_name": user.full_name, "balance": 0.0, "is_admin": is_adm}

async def get_db_settings():
    """Sozlamalarni bazadan olish"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM settings WHERE id = 1")
        return dict(row) if row else {
            "card_number": "8600 0000 0000 0000", "card_holder": "Ziyodbek G.",
            "smm_api_url": "", "smm_api_key": "", "is_maintenance": False
        }

async def update_db_settings(**kwargs):
    """Sozlamalarni yangilash"""
    async with db_pool.acquire() as conn:
        for key, value in kwargs.items():
            await conn.execute(f"UPDATE settings SET {key} = $1 WHERE id = 1", value)

async def get_all_services():
    """Barcha xizmatlarni olish"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM services ORDER BY id DESC")
        return [dict(r) for r in rows]

async def add_service(category, title, price, provider_service_id):
    """Yangi xizmat qo'shish"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO services (category, title, price, provider_service_id) VALUES ($1, $2, $3, $4)",
            category, title, price, provider_service_id
        )

async def delete_service(service_id):
    """Xizmatni o'chirish"""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM services WHERE id = $1", int(service_id))

async def create_topup(email, amount, receipt_info):
    """To'lov arizasini yaratish"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO topups (user_email, amount, receipt_info, status) VALUES ($1, $2, $3, 'pending') RETURNING id",
            email, amount, receipt_info
        )
        return row["id"] if row else 0

async def get_pending_topups():
    """Kutilayotgan to'lovlarni olish"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM topups WHERE status = 'pending'")
        return [dict(r) for r in rows]

async def approve_topup_db(topup_id):
    """To'lovni tasdiqlash va balansga pul o'tkazish"""
    async with db_pool.acquire() as conn:
        topup = await conn.fetchrow("SELECT * FROM topups WHERE id = $1", int(topup_id))
        if topup and topup["status"] == "pending":
            await conn.execute("UPDATE topups SET status = 'approved' WHERE id = $1", int(topup_id))
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE email = $2", float(topup["amount"]), topup["user_email"])
            return dict(topup)
        return None

async def reject_topup_db(topup_id):
    """To'lovni rad etish"""
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE topups SET status = 'rejected' WHERE id = $1", int(topup_id))

# ==========================================
# 🔍 TO'LIQ TIZIM DIAGNOSTIKASI
# ==========================================

async def run_full_diagnostics(bot_instance):
    """Botning barcha tizimlarini birma-bir tekshiradi"""
    report = ["🔍 **NEON POSTGRESQL DIAGNOSTIKA HISOBOТI**\n"]

    # 1. Telegram Bot API
    try:
        me = await bot_instance.get_me()
        report.append(f"✅ **Telegram Bot API:** A'lo (`@{me.username}` online)")
    except Exception as e:
        report.append(f"❌ **Telegram Bot API:** Xatolik ({e})")

    # 2. Neon Postgres
    try:
        async with db_pool.acquire() as conn:
            u_cnt = await conn.fetchval("SELECT COUNT(*) FROM users")
            s_cnt = await conn.fetchval("SELECT COUNT(*) FROM services")
            report.append(f"✅ **Neon PostgreSQL Baza:** A'lo (Aktiv userlar: **{u_cnt} ta**, Xizmatlar: **{s_cnt} ta**)")
    except Exception as e:
        report.append(f"❌ **Neon PostgreSQL:** Ulanib bo'lmadi ({e})")

    # 3. SMM API
    sett = await get_db_settings()
    api_url = sett.get("smm_api_url", "")
    api_key = sett.get("smm_api_key", "")

    if not api_url or not api_key:
        report.append("⚠️ **SMM Panel API:** URL yoki Key kiritilmagan!")
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
                            report.append(f"⚠️ **SMM API Ulanishi:** API key xato: `{data}`")
                    else:
                        report.append(f"❌ **SMM API:** HTTP {res.status}")
        except Exception as e:
            report.append(f"❌ **SMM API:** {e}")

    is_m = sett.get("is_maintenance", False)
    report.append(f"\n⚙️ **Bot Rejimi:** {'🔴 Texnik Ishlar (O\'chirilgan)' if is_m else '🟢 Ishchi Rejim (Uyg\'oq)'}")

    return "\n".join(report)

