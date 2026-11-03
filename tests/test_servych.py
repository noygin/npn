"""Сайт Сервыча целиком: вход через Telegram, заказ, админка, люди на сервере, оплата."""

import asyncio
import json
import re

import httpx
from aiogram.types import Update
from fastapi.testclient import TestClient

from bot.panel import XuiClient
from servych.app import create_app
from servych.config import Settings
from servych.store import Store
from tests.test_flow import CHAT, NOW, USER, make, msg_update, texts_sent

OWNER, ADMIN, STRANGER = 100, 1, 200


def fake_panel(clients: dict, calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path.split("/panel/api")[1]
        if path.startswith("/clients/get/"):
            c = clients.get(path.rsplit("/", 1)[1])
            if c is None:
                return httpx.Response(200, json={"success": False, "msg": "(record not found)"})
            return httpx.Response(200, json={"success": True, "obj": {"client": c, "usedTraffic": 3 * 1024**3}})
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


class World:
    def __init__(self, tmp_path, **settings):
        self.settings = Settings(
            _env_file=None, bot_token="1:x", servych_bot_username="testbot", admin_ids=[ADMIN],
            servych_db_path=str(tmp_path / "servych.db"), support_username="help", **settings,
        )
        self.clients: dict = {}
        self.panel_calls: list = []
        self.telegram: list = []
        self.crypto: list = []
        self.stars: list = []
        self.crypto_paid = False

        def panel_factory(server):
            return XuiClient(server["panel_url"], server["api_token"], server["inbound_ids"],
                             server["sub_url"], transport=fake_panel(self.clients, self.panel_calls))

        def telegram(request):
            self.telegram.append(json.loads(request.content or b"{}"))
            return httpx.Response(200, json={"ok": True, "result": {}})

        def crypto(request):
            body = json.loads(request.content)
            if request.url.path.endswith("/createInvoiceLink"):
                self.stars.append(body)
                return httpx.Response(200, json={"ok": True, "result": "https://t.me/$stars1"})
            self.crypto.append((request.url.path, body, request.headers.get("Crypto-Pay-API-Token")))
            if request.url.path.endswith("/createInvoice"):
                return httpx.Response(200, json={"ok": True, "result": {
                    "invoice_id": 77, "bot_invoice_url": "https://t.me/CryptoBot?start=IV77"}})
            status = "paid" if self.crypto_paid else "active"
            return httpx.Response(200, json={"ok": True, "result": {"items": [{"status": status}]}})

        def sub(request):
            return httpx.Response(200, text="vless://config", headers={
                "subscription-userinfo": "upload=0; download=1", "x-secret": "no"})

        self.app = create_app(
            self.settings, panel_factory=panel_factory,
            payment_transport=httpx.MockTransport(crypto),
            telegram_transport=httpx.MockTransport(telegram),
            sub_transport=httpx.MockTransport(sub),
        )
        self.store: Store = self.app.state.store

    def client(self, tg_id: int | None = None) -> TestClient:
        c = TestClient(self.app)
        c.__enter__()
        if tg_id is not None:
            page = c.get("/login").text
            code = re.search(r"start=login_([\w-]+)", page).group(1)
            assert asyncio.run(self.store.confirm_login(code, tg_id, f"user{tg_id}", f"Имя{tg_id}"))
            assert c.get(f"/login/check/{code}").json() == {"ok": True}
        return c


def setup_server(world: World, admin: TestClient, sub_url="https://5.6.7.8:2096/sub"):
    server_id = asyncio.run(world.store.server_of(OWNER))["id"]
    r = admin.post(f"/admin/servers/{server_id}", data={
        "title": "Нидерланды", "panel_url": "https://5.6.7.8:2053/secret", "api_token": "tok",
        "inbound_ids": "3, 4", "sub_url": sub_url,
    })
    assert r.status_code == 200
    return server_id


def test_landing_and_login_link(tmp_path):
    world = World(tmp_path)
    c = world.client()
    assert "Свой VPN для всей семьи" in c.get("/").text
    page = c.get("/login").text
    assert "https://t.me/testbot?start=login_" in page
    code = re.search(r"start=login_([\w-]+)", page).group(1)
    assert c.get(f"/login/check/{code}").json() == {"ok": False}
    # Без входа кабинет отправляет на страницу входа
    r = c.get("/cabinet", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_order_setup_people_and_invite(tmp_path):
    world = World(tmp_path)
    owner, admin = world.client(OWNER), world.client(ADMIN)

    assert "У вас пока нет своего сервера" in owner.get("/cabinet").text
    r = owner.post("/order")
    assert "Оплата сервера" in r.text and "Через поддержку" in r.text
    r = owner.post("/pay", data={"months": "3", "method": "support"})
    assert "Заказ №1" in r.text and "2250 ₽" in r.text
    assert "Готовим ваш сервер" in owner.get("/cabinet").text

    page = admin.get("/admin").text
    assert "Новый сервер" in page and "@user100" in page
    admin.post("/admin/payments/1/paid")
    server_id = setup_server(world, admin)
    assert "Новых заявок нет" in admin.get("/admin").text
    assert world.telegram[-1]["chat_id"] == OWNER and "готов" in world.telegram[-1]["text"]

    cabinet = owner.get("/cabinet").text
    assert "Нидерланды" in cabinet and "Включён" in cabinet and "Оплачен до" in cabinet

    r = owner.post("/people", data={"name": "  Мама  "})
    assert "Отправьте это приглашение" in r.text
    [(email, client)] = world.clients.items()
    assert email.startswith(f"s{server_id}-") and client["expiryTime"] == 0
    add = [c for c in world.panel_calls if c.url.path.endswith("/clients/add")][0]
    assert json.loads(add.content)["inboundIds"] == [3, 4]

    member = asyncio.run(world.store.members(server_id))[0]
    assert member["name"] == "Мама"
    assert f"/c/{member['share_token']}" in r.text
    assert "3,0 ГБ" in owner.get("/cabinet").text

    # Приглашение открывается без входа и ведёт прямо на сервер клиента
    invite = world.client().get(f"/c/{member['share_token']}").text
    assert "Привет, Мама!" in invite
    assert f"happ://add/https://5.6.7.8:2096/sub/{client['subId']}" in invite

    # Чужой человек не видит и не может убрать
    stranger = world.client(STRANGER)
    assert stranger.get(f"/people/{member['id']}").status_code == 404
    assert stranger.get("/admin").status_code == 404

    r = owner.post(f"/people/{member['id']}/remove")
    assert "Человек убран" in r.text
    assert world.clients[email]["enable"] is False
    assert world.client().get(f"/c/{member['share_token']}").status_code == 404


def test_change_ip_request_and_new_address(tmp_path):
    world = World(tmp_path)
    owner, admin = world.client(OWNER), world.client(ADMIN)
    owner.post("/order")
    setup_server(world, admin)
    assert "сменим адрес сервера" in owner.post("/change-ip").text
    assert "уже есть" in owner.post("/change-ip").text
    assert "Сменить IP" in admin.get("/admin").text
    assert "Мы уже меняем адрес" in owner.get("/cabinet").text

    # Админ вписывает новый адрес: заявка закрывается, клиенту приходит сообщение
    setup_server(world, admin, sub_url="https://9.9.9.9:2096/sub")
    assert "Новых заявок нет" in admin.get("/admin").text
    assert "сменили адрес" in world.telegram[-1]["text"]
    server = asyncio.run(world.store.server_of(OWNER))
    assert server["api_token"] == "tok"  # пустое поле токена не стирает старый


def test_cryptobot_payment(tmp_path):
    world = World(tmp_path, cryptobot_token="ct")
    owner = world.client(OWNER)
    owner.post("/order")
    assert "Криптовалютой" in owner.get("/pay").text
    r = owner.post("/pay", data={"months": "1", "method": "cryptobot"}, follow_redirects=False)
    assert r.headers["location"] == "/pay/1"
    path, body, token = world.crypto[0]
    assert path.endswith("/createInvoice") and token == "ct"
    assert body["fiat"] == "RUB" and body["amount"] == "790" and body["payload"] == "1"

    page = owner.get("/pay/1").text
    assert "Оплатите счёт" in page and "https://t.me/CryptoBot?start=IV77" in page
    world.crypto_paid = True
    assert "Оплачено" in owner.get("/pay/1").text
    assert asyncio.run(world.store.server_of(OWNER))["paid_until"] is not None
    # Повторная проверка не продлевает второй раз
    paid_until = asyncio.run(world.store.server_of(OWNER))["paid_until"]
    owner.get("/pay/1")
    assert asyncio.run(world.store.server_of(OWNER))["paid_until"] == paid_until
    assert world.client(STRANGER).get("/pay/1").status_code == 404


def test_subscription_goes_through_site_with_https(tmp_path):
    world = World(tmp_path, servych_public_url="https://servych.example")
    owner, admin = world.client(OWNER), world.client(ADMIN)
    owner.post("/order")
    setup_server(world, admin)
    owner.post("/people", data={"name": "Папа"})
    member = asyncio.run(world.store.members(asyncio.run(world.store.server_of(OWNER))["id"]))[0]
    invite = world.client().get(f"/c/{member['share_token']}").text
    assert f"happ://add/https://servych.example/s/{member['share_token']}" in invite
    r = world.client().get(f"/s/{member['share_token']}")
    assert r.text == "vless://config"
    assert r.headers["subscription-userinfo"] == "upload=0; download=1"
    assert "x-secret" not in r.headers


async def test_bot_confirms_site_login(tmp_path):
    dp, bot, session, _db, _clients = await make(tmp_path)
    dp["settings"].servych_db_path = str(tmp_path / "servych.db")
    store = Store(str(tmp_path / "servych.db"))
    await store.init()
    code = await store.new_login_code("http://1.2.3.4:8088")
    await dp.feed_update(bot, msg_update(1, f"/start login_{code}"))
    assert "вы вошли на сайт" in texts_sent(session)[-1]
    button = session.calls[-1].reply_markup.inline_keyboard[0][0]
    assert button.url == f"http://1.2.3.4:8088/login/finish/{code}"
    assert await store.login_owner(code) == 10
    # Второй раз тот же код не подходит
    await dp.feed_update(bot, msg_update(2, f"/start login_{code}"))
    assert "устарела" in texts_sent(session)[-1]


def test_stars_payment_through_bot(tmp_path):
    world = World(tmp_path)
    owner = world.client(OWNER)
    owner.post("/order")
    assert "760 ⭐ в месяц" in owner.get("/pay").text
    page = owner.post("/pay", data={"months": "3", "method": "stars"}).text
    assert "https://t.me/$stars1" in page and "2170 ⭐" in page
    [invoice] = world.stars
    assert invoice["currency"] == "XTR" and invoice["payload"] == "servych:1"
    assert invoice["prices"][0]["amount"] == 2170

    # Платёж приходит боту: он подтверждает счёт и отмечает оплату в базе сайта
    async def bot_side():
        dp, bot, session, _db, _clients = await make(tmp_path)
        dp["settings"].servych_db_path = world.settings.servych_db_path
        checkout = {"id": "q1", "from": USER, "currency": "XTR", "total_amount": 2170,
                    "invoice_payload": "servych:1"}
        await dp.feed_update(bot, Update.model_validate({"update_id": 1, "pre_checkout_query": checkout}))
        assert session.calls[-1].ok is True
        paid = {"currency": "XTR", "total_amount": 2170, "invoice_payload": "servych:1",
                "telegram_payment_charge_id": "ch1", "provider_payment_charge_id": ""}
        await dp.feed_update(bot, Update.model_validate({"update_id": 2, "message": {
            "message_id": 2, "date": NOW, "chat": CHAT, "from": USER, "successful_payment": paid}}))
        assert "Оплата получена" in texts_sent(session)[-1]
        # Повторно оплатить тот же счёт нельзя
        await dp.feed_update(bot, Update.model_validate({"update_id": 3, "pre_checkout_query": checkout}))
        assert session.calls[-1].ok is False

    asyncio.run(bot_side())
    assert asyncio.run(world.store.server_of(OWNER))["paid_until"] is not None
    page = owner.get("/pay/1").text
    assert "Оплачено" in page and "2170 ⭐" in page


async def test_old_database_gets_site_column(tmp_path):
    import aiosqlite
    path = str(tmp_path / "old.db")
    async with aiosqlite.connect(path) as db:
        await db.execute("CREATE TABLE login_codes (code TEXT PRIMARY KEY, tg_id INTEGER, created_at INTEGER NOT NULL)")
        await db.commit()
    store = Store(path)
    await store.init()
    code = await store.new_login_code("http://site")
    assert await store.confirm_login(code, 1, "u", "U") == "http://site"
