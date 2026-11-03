"""Тарифы и способы оплаты.

Способ оплаты знает две вещи: как выставить счёт и как проверить, что его оплатили.
Чтобы подключить СБП, добавьте класс с теми же методами, что у CryptoBot,
и включите его в available_methods.
"""

from dataclasses import dataclass

import httpx

from servych.config import Settings


@dataclass(frozen=True)
class Plan:
    months: int
    discount: int  # процент

    def price(self, monthly: int) -> int:
        full = monthly * self.months * (100 - self.discount) / 100
        return int(round(full / 10) * 10)

    @property
    def title(self) -> str:
        return {1: "1 месяц", 3: "3 месяца", 12: "1 год"}.get(self.months, f"{self.months} мес.")


PLANS = {p.months: p for p in (Plan(1, 0), Plan(3, 5), Plan(12, 15))}


@dataclass
class Invoice:
    external_id: str
    pay_url: str


class PaymentError(Exception):
    pass


class CryptoBot:
    """Счета в рублях через Crypto Pay. Человек платит криптой в @CryptoBot."""

    code = "cryptobot"
    title = "Криптовалютой"
    hint = "USDT, TON, BTC через @CryptoBot"

    def __init__(self, token: str, api: str, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(
            base_url=api.rstrip("/"),
            headers={"Crypto-Pay-API-Token": token},
            timeout=15,
            transport=transport,
        )

    async def _call(self, method: str, params: dict) -> dict:
        r = await self._http.post(f"/{method}", json=params)
        data = r.json()
        if not data.get("ok"):
            raise PaymentError(str(data.get("error")))
        return data["result"]

    async def create(self, payment_id: int, amount: int, description: str, return_url: str) -> Invoice:
        params = {
            "currency_type": "fiat",
            "fiat": "RUB",
            "amount": str(amount),
            "description": description[:1024],
            "payload": str(payment_id),
            "expires_in": 3600,
        }
        if return_url.startswith("https://"):
            params |= {"paid_btn_name": "callback", "paid_btn_url": return_url}
        result = await self._call("createInvoice", params)
        url = result.get("bot_invoice_url") or result.get("pay_url")
        return Invoice(str(result["invoice_id"]), url)

    async def is_paid(self, external_id: str) -> bool:
        result = await self._call("getInvoices", {"invoice_ids": external_id})
        return any(item.get("status") == "paid" for item in result.get("items", []))

    async def close(self) -> None:
        await self._http.aclose()


class Stars:
    """Счёт в Telegram Stars. Оплату принимает бот и сам отмечает её в базе сайта."""

    code = "stars"
    title = "Telegram Stars"
    payload_prefix = "servych:"

    def __init__(self, bot_token: str, monthly: int, transport: httpx.AsyncBaseTransport | None = None):
        self.hint = f"{monthly} ⭐ в месяц, оплата прямо в Telegram"
        self._http = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{bot_token}", timeout=15, transport=transport
        )

    async def create(self, payment_id: int, amount: int, description: str, return_url: str) -> Invoice:
        r = await self._http.post("/createInvoiceLink", json={
            "title": "Сервыч",
            "description": description,
            "payload": f"{self.payload_prefix}{payment_id}",
            "currency": "XTR",
            "prices": [{"label": description, "amount": amount}],
        })
        data = r.json()
        if not data.get("ok"):
            raise PaymentError(str(data.get("description")))
        return Invoice("", data["result"])

    async def close(self) -> None:
        await self._http.aclose()


def available_methods(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    methods = {}
    if settings.bot_token:
        methods[Stars.code] = Stars(settings.bot_token, settings.servych_price_stars, transport)
    if settings.cryptobot_token:
        methods[CryptoBot.code] = CryptoBot(
            settings.cryptobot_token, settings.cryptobot_api, transport
        )
    return methods
