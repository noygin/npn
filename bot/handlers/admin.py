from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Settings
from bot.db import Database

router = Router()


@router.message(Command("stats"))
async def stats(message: Message, db: Database, settings: Settings) -> None:
    if message.from_user.id not in settings.admin_ids:
        return
    s = await db.stats()
    await message.answer(
        f"Пользователей: {s['users']}\nПлатежей: {s['payments']}\nЗвёзд получено: {s['stars']}"
    )
