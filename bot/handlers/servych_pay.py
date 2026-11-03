"""Оплата Сервыча звёздами: счёт создаёт сайт, а платёж приходит сюда, к боту."""

import logging

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery

from bot.config import Settings
from servych.app import format_date
from servych.payments import Stars
from servych.store import Store

router = Router()
log = logging.getLogger(__name__)
PREFIX = Stars.payload_prefix


def payment_id(payload: str) -> int:
    return int(payload.removeprefix(PREFIX))


@router.pre_checkout_query(F.invoice_payload.startswith(PREFIX))
async def pre_checkout(query: PreCheckoutQuery, settings: Settings) -> None:
    payment = await Store(settings.servych_db_path).get_payment(payment_id(query.invoice_payload))
    ok = payment is not None and payment["status"] == "pending"
    await query.answer(ok=ok, error_message=None if ok else "Счёт устарел, оформите оплату на сайте заново.")


@router.message(F.successful_payment.invoice_payload.startswith(PREFIX))
async def successful_payment(message: Message, settings: Settings) -> None:
    paid = message.successful_payment
    pid = payment_id(paid.invoice_payload)
    # Номер платежа в Telegram нужен для возврата звёзд
    log.info("servych payment %s paid, charge %s", pid, paid.telegram_payment_charge_id)
    store = Store(settings.servych_db_path)
    await store.mark_paid(pid)
    server = await store.get_server((await store.get_payment(pid))["server_id"])
    text = f"Оплата получена, спасибо! Сервер Сервыча оплачен до {format_date(server['paid_until'])}."
    site = settings.servych_public_url.rstrip("/")
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Открыть кабинет", url=f"{site}/cabinet"
    )]]) if site.startswith("https://") else None
    await message.answer(text, reply_markup=markup)
