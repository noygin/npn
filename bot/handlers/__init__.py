import logging
import re

import httpx
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent, Message

from bot import keyboards, texts
from bot.config import Settings
from bot.db import Database
from bot.handlers import admin, menu, payments
from bot.panel import PanelError, XuiClient, client_email

log = logging.getLogger(__name__)
fallback = Router()


PROMO_RE = re.compile(r"^[A-Za-zА-Яа-я0-9_-]{3,32}$")


@fallback.message(F.text)
async def unknown_text(message: Message, db: Database, panel: XuiClient, settings: Settings) -> None:
    """Промокод активирует подписку, на любой другой текст показываем главное меню."""
    word = message.text.strip()
    if PROMO_RE.match(word):
        days = await db.redeem_promo(word, message.from_user.id)
        if isinstance(days, int):
            await db.register(message.from_user.id, message.from_user.username, None)
            try:
                sub = await panel.extend(
                    client_email(message.from_user.id), days, message.from_user.id
                )
            except (httpx.HTTPError, PanelError):
                log.exception("promo extend failed for %s", message.from_user.id)
                await message.answer(texts.PANEL_ERROR)
                return
            await message.answer(
                texts.promo_ok(days, sub), reply_markup=keyboards.connect(sub),
                disable_web_page_preview=True,
            )
            return
        if days == "used":
            await message.answer(texts.PROMO_USED, reply_markup=keyboards.open_home())
            return
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
