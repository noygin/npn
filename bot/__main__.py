import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot import handlers, reminders
from bot.config import Settings
from bot.db import Database
from bot.panel import XuiClient
from bot.texts import plural_days


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
    await bot.set_my_commands(
        [BotCommand(command="start", description="Главное меню"),
         BotCommand(command="help", description="Как подключиться"),
         BotCommand(command="id", description="Мой Telegram ID")]
    )
    await bot.set_my_short_description("Быстрый VPN, который работает при блокировках.")
    await bot.set_my_description(
        f"n. — быстрый VPN, который работает при блокировках.\n\n"
        f"Первые {plural_days(settings.trial_days)} бесплатно. Нажмите «Запустить»."
    )
    dp = Dispatcher(db=db, panel=panel, settings=settings)
    dp.include_router(handlers.setup())
    reminders_task = asyncio.create_task(reminders.run(bot, db, panel))
    try:
        await dp.start_polling(bot)
    finally:
        reminders_task.cancel()
        await panel.close()


if __name__ == "__main__":
    asyncio.run(main())
