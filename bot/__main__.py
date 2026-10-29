import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot import handlers
from bot.config import Settings
from bot.db import Database
from bot.marzban import MarzbanClient


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    db = Database(settings.db_path)
    await db.init()
    marzban = MarzbanClient(
        settings.marzban_url,
        settings.marzban_username,
        settings.marzban_password,
        settings.marzban_inbound,
    )
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(db=db, marzban=marzban, settings=settings)
    dp.include_router(handlers.setup())
    try:
        await dp.start_polling(bot)
    finally:
        await marzban.close()


if __name__ == "__main__":
    asyncio.run(main())
