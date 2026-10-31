"""Прогон реальных обновлений Telegram через диспетчер с подставным API."""

import json
import time

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import Update

from bot import handlers
from bot.config import Settings
from bot.db import Database
from bot.panel import XuiClient

NOW = int(time.time())
CHAT = {"id": 10, "type": "private"}
USER = {"id": 10, "is_bot": False, "first_name": "N", "username": "noah"}
BOT_USER = {"id": 1, "is_bot": True, "first_name": "bot", "username": "testbot"}


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        name = type(method).__name__
        if name == "GetMe":
            result = BOT_USER
        elif name in ("SendMessage", "EditMessageText", "SendInvoice"):
            result = {"message_id": 99, "date": NOW, "chat": CHAT, "from": BOT_USER, "text": "x"}
        else:
            result = True
        return method.__returning__.model_validate(result) if name in (
            "GetMe", "SendMessage", "EditMessageText", "SendInvoice"
        ) else result

    async def stream_content(self, *a, **k):  # pragma: no cover
        yield b""

    async def close(self):
        pass


def panel_transport(clients: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.split("/panel/api")[1]
        if path.startswith("/clients/get/"):
            c = clients.get(path.rsplit("/", 1)[1])
            if c is None:
                return httpx.Response(200, json={"success": False, "msg": " (record not found)"})
            return httpx.Response(200, json={"success": True, "obj": {"client": c, "usedTraffic": 0}})
        if path == "/clients/add":
            c = json.loads(request.content)["client"]
            clients[c["email"]] = c
        elif path.startswith("/clients/update/"):
            c = json.loads(request.content)
            clients[c["email"]] = c
        elif path == "/clients/list":
            return httpx.Response(200, json={"success": True, "obj": list(clients.values())})
        return httpx.Response(200, json={"success": True, "obj": None})

    return httpx.MockTransport(handler)


async def make(tmp_path, admin=False):
    settings = Settings(
        bot_token="1:x", panel_url="https://p/s", panel_api_token="t", panel_inbound_ids=[5],
        panel_sub_url="https://p:2096/sub", admin_ids=[10] if admin else [],
    )
    db = Database(str(tmp_path / "bot.db"))
    await db.init()
    clients: dict = {}
    panel = XuiClient(settings.panel_url, "t", [5], settings.panel_sub_url,
                      transport=panel_transport(clients))
    session = FakeSession()
    bot = Bot("1:x", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(db=db, panel=panel, settings=settings)
    # Роутеры модульные, отцепляем их от диспетчера прошлого теста
    for r in (handlers.menu.router, handlers.payments.router, handlers.admin.router,
              handlers.fallback):
        r._parent_router = None
    dp.include_router(handlers.setup())
    return dp, bot, session, db, clients


def msg_update(uid, text):
    return Update.model_validate({"update_id": uid, "message": {
        "message_id": uid, "date": NOW, "chat": CHAT, "from": USER, "text": text,
        **({"entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]}
           if text.startswith("/") else {}),
    }})


def cb_update(uid, data):
    return Update.model_validate({"update_id": uid, "callback_query": {
        "id": str(uid), "from": USER, "chat_instance": "c", "data": data,
        "message": {"message_id": 99, "date": NOW, "chat": CHAT, "from": BOT_USER, "text": "x"},
    }})


def texts_sent(session):
    return [getattr(c, "text", "") or "" for c in session.calls]


async def test_start_trial_and_invite(tmp_path):
    dp, bot, session, _db, clients = await make(tmp_path)
    await dp.feed_update(bot, msg_update(1, "/start ref555"))
    assert "Подписки пока нет" in texts_sent(session)[0]
    await dp.feed_update(bot, cb_update(2, "trial"))
    assert "tg10" in clients and "https://p:2096/sub/" in texts_sent(session)[-2]
    await dp.feed_update(bot, cb_update(3, "invite"))
    assert any("t.me/testbot?start=ref10" in t for t in texts_sent(session))
    await dp.feed_update(bot, msg_update(4, "привет"))
    assert "Подписка активна" in texts_sent(session)[-1]


async def test_admin_gives_access_by_id(tmp_path):
    dp, bot, session, _db, clients = await make(tmp_path, admin=True)
    await dp.feed_update(bot, msg_update(1, "/start"))
    await dp.feed_update(bot, cb_update(2, "admin:give"))
    await dp.feed_update(bot, msg_update(3, "777 навсегда"))
    assert clients["tg777"]["expiryTime"] == 0
    assert any("Готово: 777" in t for t in texts_sent(session))


async def test_non_admin_cannot_open_admin(tmp_path):
    dp, bot, _session, _db, clients = await make(tmp_path)
    await dp.feed_update(bot, msg_update(1, "/give 777 30"))
    assert "tg777" not in clients


async def test_payment_extends_and_rewards_referrer(tmp_path):
    dp, bot, _session, db, clients = await make(tmp_path)
    await db.register(555, "inviter", None)
    await dp.feed_update(bot, msg_update(1, "/start ref555"))
    payment = {
        "currency": "XTR", "total_amount": 150, "invoice_payload": "m1",
        "telegram_payment_charge_id": "ch1", "provider_payment_charge_id": "",
    }
    upd = Update.model_validate({"update_id": 2, "message": {
        "message_id": 2, "date": NOW, "chat": CHAT, "from": USER, "successful_payment": payment,
    }})
    await dp.feed_update(bot, upd)
    assert clients["tg10"]["expiryTime"] > NOW * 1000
    assert "tg555" in clients  # пригласивший получил дни
    await dp.feed_update(bot, upd.model_copy(update={"update_id": 3}))
    assert await db.stats() == {"users": 2, "payments": 1, "stars": 150}


async def test_user_redeems_promo_by_sending_it(tmp_path):
    dp, bot, session, db, clients = await make(tmp_path)
    await db.save_promo("GIFT", 10, 5)
    await dp.feed_update(bot, msg_update(1, "gift"))
    assert "Промокод принят: +10 дней" in texts_sent(session)[-1]
    assert clients["tg10"]["expiryTime"] > NOW * 1000
    await dp.feed_update(bot, msg_update(2, "gift"))
    assert "уже использовали" in texts_sent(session)[-1]


async def test_admin_creates_promo(tmp_path):
    dp, bot, _session, db, _clients = await make(tmp_path, admin=True)
    await dp.feed_update(bot, cb_update(1, "admin:promo"))
    await dp.feed_update(bot, msg_update(2, "spring 30 100"))
    assert await db.active_promos() == [("SPRING", 30, 100)]


async def test_admin_ovpn_command(tmp_path, monkeypatch):
    dp, bot, session, _db, _clients = await make(tmp_path, admin=True)
    from bot.handlers import admin as admin_h
    base = tmp_path / "ovpn"
    monkeypatch.setattr(admin_h.ovpn, "WAIT_SECONDS", 0.3)
    dp["settings"].ovpn_dir = str(base)
    await dp.feed_update(bot, msg_update(1, "/ovpn 3"))
    assert "Готовлю OpenVPN-файл на 3 дня" in texts_sent(session)[-1]
    assert len(list((base / "requests").glob("*.req"))) == 1
    await dp.feed_update(bot, msg_update(2, "/ovpn abc"))
    assert "Срок в днях" in texts_sent(session)[-1]


async def test_admin_ovpn_delivers_files(tmp_path):
    _dp, bot, session, _db, _clients = await make(tmp_path, admin=True)
    from bot.handlers import admin as admin_h
    done = tmp_path / "done" / "n1"
    done.mkdir(parents=True)
    (done / "antizapret-n1-(1.2.3.4).ovpn").write_text("x")
    (done / "status").write_text("ok\n")
    await admin_h.deliver_ovpn(bot, 10, tmp_path, "n1", 3)
    names = [type(c).__name__ for c in session.calls]
    assert names == ["SendMessage", "SendDocument"]
    assert "работает до" in session.calls[0].text
    assert not done.exists()
