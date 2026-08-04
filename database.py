import os
import logging
import asyncpg
import aiohttp
from aiogram.fsm.state import State, StatesGroup

# ==========================================
# ⚙️ SOZLAMALAR VA NEON POSTGRESQL ULANISHI
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "7832829103:AAH_YOUR_TELEGRAM_BOT_TOKEN_HERE")

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://neondb_owner:npg_UZpcfN20OHqG@ep-silent-dew-asqaa9za-pooler.c-4.eu-central-1.aws.neon.tech/neondb?sslmode=require"
)

# Ziyodbekning shaxsiy Telegram ID raqami:
ADMIN_TELEGRAM_IDS = [8926978756]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_pool = None

# ==========================================
# 📝 FSM BOSQICHLARI
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

# ==========================================
# ⚡ BAZANI INIZIALIZATSIYA QILISH
# ==========================================

async def init_db():
    """Neon PostgreSQL jadvallarini avtomatik yaratish"""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=10)
        logger.info("✅ Neon PostgreSQL bazasiga muvaffaqiyatli ulandi!")
        
        async with db_pool.acquire() as conn:
            # 1. Users Jadvali (Referal ustunlari bilan)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    email TEXT UNIQUE,
                    full_name TEXT,
                    balance DOUBLE PRECISION DEFAULT 0.0,
                    referrer_id BIGINT DEFAULT NULL,
                    total_ref_earnings DOUBLE PRECISION DEFAULT 0.0,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                    ref_percent DOUBLE PRECISION DEFAULT 10.0,
                    is_maintenance BOOLEAN DEFAULT FALSE
                );
            """)

            await conn.execute("""
                INSERT INTO settings (id, card_number, card_holder)
                VALUES (1, '8600 0000 0000 0000', 'Ziyodbek G.')
                ON CONFLICT (id) DO NOTHING;
            """)

            # 3. Categories Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE
                );
            """)

            # 4. Services Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS services (
                    id SERIAL PRIMARY KEY,
                    category TEXT,
                    title TEXT,
                    price DOUBLE PRECISION,
                    provider_service_id TEXT,
                    description TEXT DEFAULT 'Kafolatlangan xizmat'
                );
            """)

            # 5. Topups Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS topups (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    user_email TEXT,
                    amount DOUBLE PRECISION,
                    receipt_info TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 6. Orders Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    service_title TEXT,
                    link TEXT,
                    quantity INT,
                    price DOUBLE PRECISION,
                    order_provider_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 7. Channels Jadvali (Majburiy Obuna)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id SERIAL PRIMARY KEY,
                    channel_id TEXT UNIQUE,
                    title TEXT,
                    invite_link TEXT
                );
            """)
            logger.info("✅ Barcha SQL jadvallar tayyor holatga keltirildi!")
    except Exception as e:
        logger.error(f"❌ PostgreSQL ulanishda xatolik: {e}")

# ==========================================
# 👥 FOYDALANUVCHILAR VA REFERAL TIZIM
# ==========================================

async def get_or_create_user_async(user, referrer_id=None):
    email = f"tg_{user.id}@telegram.com"
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user.id)
        if row:
            return dict(row)
        
        is_adm = user.id in ADMIN_TELEGRAM_IDS
        ref_id = None
        if referrer_id and str(referrer_id).isdigit() and int(referrer_id) != user.id:
            ref_exists = await conn.fetchval("SELECT id FROM users WHERE id = $1", int(referrer_id))
            if ref_exists:
                ref_id = int(referrer_id)

        await conn.execute(
            """INSERT INTO users (id, email, full_name, balance, referrer_id, is_admin)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            user.id, email, user.full_name or user.username or "Foydalanuvchi", 0.0, ref_id, is_adm
        )
        return {
            "id": user.id, "email": email, "full_name": user.full_name,
            "balance": 0.0, "referrer_id": ref_id, "total_ref_earnings": 0.0, "is_admin": is_adm
        }

async def get_user_referrals_info(user_id):
    """Foydalanuvchining referal ma'lumotlarini olish"""
    async with db_pool.acquire() as conn:
        invited_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id = $1", user_id)
        ref_earnings = await conn.fetchval("SELECT COALESCE(total_ref_earnings, 0) FROM users WHERE id = $1", user_id)
        recent_refs = await conn.fetch("SELECT full_name, created_at FROM users WHERE referrer_id = $1 ORDER BY created_at DESC LIMIT 5", user_id)
        return {
            "count": invited_count or 0,
            "earnings": ref_earnings or 0.0,
            "recent": [dict(r) for r in recent_refs]
        }

# ==========================================
# ⚙️ SOZLAMALAR VA KATEGORIYALAR
# ==========================================

async def get_db_settings():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM settings WHERE id = 1")
        return dict(row) if row else {
            "card_number": "8600 0000 0000 0000", "card_holder": "Ziyodbek G.",
            "smm_api_url": "", "smm_api_key": "", "ref_percent": 10.0, "is_maintenance": False
        }

async def update_db_settings(**kwargs):
    async with db_pool.acquire() as conn:
        for key, value in kwargs.items():
            await conn.execute(f"UPDATE settings SET {key} = $1 WHERE id = 1", value)

async def get_categories():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM categories ORDER BY name ASC")
        return [dict(r) for r in rows]

async def add_category_db(name):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO categories (name) VALUES ($1) ON CONFLICT DO NOTHING", name)

async def delete_category_db(cat_id):
    async with db_pool.acquire() as conn:
        cat = await conn.fetchrow("SELECT name FROM categories WHERE id = $1", int(cat_id))
        if cat:
            await conn.execute("DELETE FROM services WHERE category = $1", cat["name"])
            await conn.execute("DELETE FROM categories WHERE id = $1", int(cat_id))

# ==========================================
# 🛍 XIZMATLAR VA BUYURTMALAR
# ==========================================

async def get_all_services():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM services ORDER BY id DESC")
        return [dict(r) for r in rows]

async def get_services_by_category(category_name):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM services WHERE category = $1 ORDER BY id DESC", category_name)
        return [dict(r) for r in rows]

async def add_service(category, title, price, provider_service_id):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO categories (name) VALUES ($1) ON CONFLICT DO NOTHING", category)
        await conn.execute(
            "INSERT INTO services (category, title, price, provider_service_id) VALUES ($1, $2, $3, $4)",
            category, title, price, provider_service_id
        )

async def delete_service(service_id):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM services WHERE id = $1", int(service_id))

async def create_order_db(user_id, service_title, link, quantity, price, provider_order_id):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO orders (user_id, service_title, link, quantity, price, order_provider_id)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            user_id, service_title, link, quantity, price, str(provider_order_id)
        )

# ==========================================
# 💳 TO'LOVLAR VA TASDIQLASH (BONUS BILAN)
# ==========================================

async def create_topup(user_id, email, amount, receipt_info):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO topups (user_id, user_email, amount, receipt_info, status)
               VALUES ($1, $2, $3, $4, 'pending') RETURNING id""",
            user_id, email, amount, receipt_info
        )
        return row["id"] if row else 0

async def get_pending_topups():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM topups WHERE status = 'pending' ORDER BY id DESC")
        return [dict(r) for r in rows]

async def approve_topup_db(topup_id):
    """To'lovni tasdiqlash + Referalga 10% bonus taqsimlash"""
    async with db_pool.acquire() as conn:
        topup = await conn.fetchrow("SELECT * FROM topups WHERE id = $1", int(topup_id))
        if topup and topup["status"] == "pending":
            amount = float(topup["amount"])
            user_id = topup["user_id"]
            user_email = topup["user_email"]

            # Topup holatini o'zgartirish
            await conn.execute("UPDATE topups SET status = 'approved' WHERE id = $1", int(topup_id))
            
            # Balansni to'ldirish
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE email = $2", amount, user_email)

            # Referal hisob kitobi
            user = await conn.fetchrow("SELECT referrer_id FROM users WHERE email = $1", user_email)
            referrer_notify = None
            if user and user["referrer_id"]:
                ref_id = user["referrer_id"]
                sett = await conn.fetchrow("SELECT ref_percent FROM settings WHERE id = 1")
                ref_percent = sett["ref_percent"] if sett else 10.0
                bonus = (amount * ref_percent) / 100.0

                if bonus > 0:
                    await conn.execute(
                        """UPDATE users SET balance = balance + $1, total_ref_earnings = total_ref_earnings + $1
                           WHERE id = $2""",
                        bonus, ref_id
                    )
                    referrer_notify = {"ref_id": ref_id, "bonus": bonus, "from_user": user_email}

            return {"topup": dict(topup), "ref_notify": referrer_notify}
        return None

async def reject_topup_db(topup_id):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE topups SET status = 'rejected' WHERE id = $1", int(topup_id))

# ==========================================
# 📢 MAJBURIY OBUNA KANALLARI
# ==========================================

async def get_channels_db():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM channels ORDER BY id DESC")
        return [dict(r) for r in rows]

async def add_channel_db(channel_id, title, invite_link):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO channels (channel_id, title, invite_link) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            str(channel_id), title, invite_link
        )

async def delete_channel_db(channel_id):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM channels WHERE id = $1", int(channel_id))

# ==========================================
# 📊 KENGAYTIRILGAN STATISTIKA VA TASHXIS
# ==========================================

async def get_expanded_stats():
    async with db_pool.acquire() as conn:
        u_cnt = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
        u_today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE") or 0
        s_cnt = await conn.fetchval("SELECT COUNT(*) FROM services") or 0
        c_cnt = await conn.fetchval("SELECT COUNT(*) FROM categories") or 0
        tot_rev = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM topups WHERE status = 'approved'") or 0.0
        pending_topups = await conn.fetchval("SELECT COUNT(*) FROM topups WHERE status = 'pending'") or 0
        tot_orders = await conn.fetchval("SELECT COUNT(*) FROM orders") or 0
        tot_ref_paid = await conn.fetchval("SELECT COALESCE(SUM(total_ref_earnings), 0) FROM users") or 0.0

        return {
            "users_total": u_cnt, "users_today": u_today,
            "services_count": s_cnt, "categories_count": c_cnt,
            "total_revenue": tot_rev, "pending_topups": pending_topups,
            "total_orders": tot_orders, "total_ref_paid": tot_ref_paid
        }

async def run_full_diagnostics(bot_instance):
    report = ["🔍 **NEON POSTGRESQL DIAGNOSTIKA HISOBOТI**\n"]

    try:
        me = await bot_instance.get_me()
        report.append(f"✅ **Telegram Bot API:** A'lo (`@{me.username}` online)")
    except Exception as e:
        report.append(f"❌ **Telegram Bot API:** Xatolik ({e})")

    try:
        stats = await get_expanded_stats()
        report.append(f"✅ **Neon PostgreSQL Baza:** A'lo")
        report.append(f" └ Foydalanuvchilar: **{stats['users_total']} ta** (Bugun: **+{stats['users_today']} ta**)")
        report.append(f" └ Bo'limlar / Xizmatlar: **{stats['categories_count']} ta bo'lim / {stats['services_count']} ta xizmat**")
        report.append(f" └ Buyurtmalar / Kassa: **{stats['total_orders']} ta buyurtma / {stats['total_revenue']:,.0f} so'm**")
    except Exception as e:
        report.append(f"❌ **Neon PostgreSQL:** Ulanib bo'lmadi ({e})")

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
                            report.append(f"⚠️ **SMM API Ulanishi:** Kalit xato")
                    else:
                        report.append(f"❌ **SMM API:** HTTP {res.status}")
        except Exception as e:
            report.append(f"❌ **SMM API:** {e}")

    chans = await get_channels_db()
    report.append(f"📢 **Majburiy Obuna Kanallari:** **{len(chans)} ta aktiv kanal**")
    is_m = sett.get("is_maintenance", False)
    report.append(f"\n⚙️ **Bot Rejimi:** {'🔴 Texnik Ishlar' if is_m else '🟢 Ishchi Rejim'}")

    return "\n".join(report)
