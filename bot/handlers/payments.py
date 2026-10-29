import logging

import httpx
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from bot import texts
from bot.config import Settings
from bot.db import Database
from bot.keyboards import back_menu
from bot.panel import PanelError, XuiClient, client_email
from bot.tariffs import TARIFFS

router = Router()
log = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("buy:"))
async def send_invoice(call: CallbackQuery) -> None:
    tariff = TARIFFS.get(call.data.removeprefix("buy:"))
    if tariff is None:
        await call.answer()
        return
    await call.message.answer_invoice(
        title=f"VPN · {tariff.title}",
        description=f"Доступ к VPN на {tariff.days} дней",
        payload=tariff.code,
        currency="XTR",
        prices=[LabeledPrice(label=tariff.title, amount=tariff.stars)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    tariff = TARIFFS.get(query.invoice_payload)
    ok = tariff is not None and query.currency == "XTR" and query.total_amount == tariff.stars
    await query.answer(ok=ok, error_message=None if ok else "Тариф устарел, выберите заново.")


@router.message(F.successful_payment)
async def successful_payment(
    message: Message, bot: Bot, db: Database, panel: XuiClient, settings: Settings
) -> None:
    payment = message.successful_payment
    tariff = TARIFFS[payment.invoice_payload]
    tg_id = message.from_user.id
    await db.upsert_user(tg_id, message.from_user.username)
    if not await db.add_payment(
        tg_id, tariff.code, payment.total_amount, payment.currency,
        payment.telegram_payment_charge_id,
    ):
        return  # повторная доставка уже обработанного платежа
    try:
        sub = await panel.extend(client_email(tg_id), tariff.days, tg_id)
    except (httpx.HTTPError, PanelError):
        log.exception("extend after payment failed for %s", tg_id)
        await message.answer(texts.PAYMENT_ERROR)
        for admin_id in settings.admin_ids:
            await bot.send_message(
                admin_id,
                f"⚠️ Оплата без выдачи доступа: tg {tg_id}, тариф {tariff.code}, "
                f"charge {payment.telegram_payment_charge_id}",
            )
        return
    await message.answer(
        "Спасибо за оплату! 🎉\n\n" + texts.subscription(sub),
        reply_markup=back_menu(),
    )
