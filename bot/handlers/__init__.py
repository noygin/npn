import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent, Message

from bot.config import Settings
from bot.db import Database
from bot.handlers import admin, menu, payments
from bot.panel import XuiClient

log = logging.getLogger(__name__)
fallback = Router()


@fallback.message(F.text)
async def unknown_text(message: Message, db: Database, panel: XuiClient, settings: Settings) -> None:
    """На любой текст показываем главное меню, чтобы человек не оставался без ответа."""
    text, markup = await menu.home_screen(message.from_user, db, panel, settings)
    await message.answer(text, reply_markup=markup)


@fallback.error()
async def on_error(event: ErrorEvent) -> None:
    log.error("handler failed", exc_info=event.exception)
    call = event.update.callback_query
    if call is not None:
        try:
            await call.answer("Что-то пошло не так, попробуйте ещё раз.", show_alert=True)
        except TelegramAPIError:
            pass


def setup() -> Router:
    router = Router()
    router.include_routers(menu.router, payments.router, admin.router, fallback)
    return router
