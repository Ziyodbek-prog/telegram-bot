import asyncio
import logging
import os
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers.user import user_router
from handlers.referal import referal_router
from handlers.admin import admin_router
from handlers.diagnostics import diag_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# 🌐 RENDER HTTP SERVER (KEEP-ALIVE PORT)
# ==========================================

async def handle_ping(request):
    return web.Response(text="Neon Postgres SMM Bot Live 24/7", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Keep-Alive Server running on port {port}")

# ==========================================
# 🚀 MAIN RUNNER (ROUTERLAR MAIN ICHIDA)
# ==========================================

async def main():
    # 1. Render Port Serverini Yoqish
    asyncio.create_task(start_web_server())
    
    # 2. Neon PostgreSQL Bazasini Inizializatsiya Qilish
    await init_db()

    # 3. Bot va Dispatcher Yaratish (Main Ichida)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # 4. Routerlarni Xavfsiz Ulash (Crash Himoyasi)
    dp.include_router(user_router)
    dp.include_router(referal_router)
    dp.include_router(admin_router)
    dp.include_router(diag_router)

    logger.info("🚀 Modular SMM Bot polling rejimida ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
