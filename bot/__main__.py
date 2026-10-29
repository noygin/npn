import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot import handlers
from bot.config import Settings
from bot.db import Database
from bot.panel import XuiClient


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    db = Database(settings.db_path)
    await db.init()
    panel = XuiClient(
        settings.panel_url,
        settings.panel_api_token,
        settings.panel_inbound_ids,
        settings.panel_sub_url,
    )
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(db=db, panel=panel, settings=settings)
    dp.include_router(handlers.setup())
    try:
        await dp.start_polling(bot)
    finally:
        await panel.close()


if __name__ == "__main__":
    asyncio.run(main())
