from aiogram import Router, F, types
from database import get_user_referrals_info, get_db_settings
from middlewares import check_guard

referal_router = Router()

@referal_router.message(F.text == "👥 Referal Tizim")
async def cmd_ref(message: types.Message):
    if await check_guard(message, message.bot): return
    me = await message.bot.get_me()
    ref_link = f"https://t.me/{me.username}?start={message.from_user.id}"
    ref_info = await get_user_referrals_info(message.from_user.id)
    sett = await get_db_settings()

    recent_str = ""
    if ref_info["recent"]:
        recent_str = "\n\n👥 **Oxirgi taklif qilingan do'stlar:**\n" + "\n".join([f"• {r['full_name']}" for r in ref_info["recent"]])

    msg = (
        f"👥 **REFERAL DASTURI**\n\n"
        f"Do'stlaringizni taklif qiling va har bir to'lovidan **{sett.get('ref_percent', 10.0)}% daromad** oling!\n\n"
        f"🔗 **Sizning havolangiz:**\n`{ref_link}`\n\n"
        f"📊 **Sizning statistikangiz:**\n"
        f"👤 Taklif qilingan do'stlar: **{ref_info['count']} ta**\n"
        f"💰 Ishlangan jami daromad: **{ref_info['earnings']:,.0f} so'm**"
        f"{recent_str}"
    )
    await message.answer(msg, parse_mode="Markdown")
