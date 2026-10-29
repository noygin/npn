"""Напоминания пользователям о конце подписки. Админам ничего не пишет."""

import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot import keyboards, texts
from bot.db import Database
from bot.panel import DAY, XuiClient, tg_id_from_email

log = logging.getLogger(__name__)
CHECK_EVERY = 3600


def reminder_kind(expire: int, now: float) -> str | None:
    if expire == 0:
        return None
    left = expire - now
    if 0 < left <= DAY:
        return "soon"
    if -2 * DAY < left <= 0:
        return "ended"
    return None


async def send_reminders(bot: Bot, db: Database, panel: XuiClient) -> None:
    now = time.time()
    for client in await panel.list_clients():
        tg_id = tg_id_from_email(client.get("email", ""))
        expire = (client.get("expiryTime") or 0) // 1000
        kind = reminder_kind(expire, now)
        if tg_id is None or kind is None or not await db.mark_reminded(tg_id, expire, kind):
            continue
        text = texts.REMIND_SOON if kind == "soon" else texts.REMIND_ENDED
        try:
            await bot.send_message(tg_id, text, reply_markup=keyboards.renew())
        except TelegramAPIError:
            pass


async def run(bot: Bot, db: Database, panel: XuiClient) -> None:
    while True:
        try:
            await send_reminders(bot, db, panel)
        except Exception:
            log.exception("reminders failed")
        await asyncio.sleep(CHECK_EVERY)
