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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Routerlarni ulash
dp.include_router(user_router)
dp.include_router(referal_router)
dp.include_router(admin_router)
dp.include_router(diag_router)

# ==========================================
# 🌐 RENDER HTTP SERVER (KEEP ALIVE)
# ==========================================

async def handle_ping(request):
    return web.Response(text="Modular Neon Postgres SMM Engine Live 24/7", status=200)

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

async def main():
    asyncio.create_task(start_web_server())
    await init_db()
    logger.info("🚀 Modular Neon Postgres SMM Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
