"""Вход на сайт Сервыча: сайт даёт ссылку t.me/<бот>?start=login_<код>, бот подтверждает код."""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import Settings
from servych.store import Store

router = Router()
log = logging.getLogger(__name__)
PREFIX = "login_"


@router.message(CommandStart(deep_link=True, magic=F.args.startswith(PREFIX)))
async def site_login(message: Message, command: CommandObject, settings: Settings) -> None:
    code = command.args.removeprefix(PREFIX)
    store = Store(settings.servych_db_path)
    await store.init()
    user = message.from_user
    if not await store.confirm_login(code, user.id, user.username, user.first_name):
        await message.answer("Ссылка для входа устарела. Откройте сайт и нажмите «Войти» ещё раз.")
        return
    text = "✅ Готово, вы вошли на сайт Сервыча. Вернитесь в браузер, страница откроется сама."
    site = settings.servych_public_url.rstrip("/")
    if site:
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Открыть сайт", url=f"{site}/login/finish/{code}"
        )]])
        try:
            await message.answer(text, reply_markup=markup)
            return
        except TelegramBadRequest:
            log.exception("login button rejected")
    await message.answer(text)
