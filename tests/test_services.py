import json

import httpx

from bot.db import Database
from bot.panel import XuiClient


async def test_trial_is_taken_once(tmp_path):
    db = Database(str(tmp_path / "bot.db"))
    await db.init()
    await db.upsert_user(1, "noah")
    assert await db.take_trial(1)
    assert not await db.take_trial(1)


async def test_payment_is_recorded_once(tmp_path):
    db = Database(str(tmp_path / "bot.db"))
    await db.init()
    assert await db.add_payment(1, "m1", 150, "XTR", "charge-1")
    assert not await db.add_payment(1, "m1", 150, "XTR", "charge-1")
    assert await db.stats() == {"users": 0, "payments": 1, "stars": 150}


def fake_panel(existing: dict | None):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            if existing is None:
                return httpx.Response(200, json={"success": False, "msg": "get (record not found)"})
            return httpx.Response(200, json={"success": True, "obj": existing})
        return httpx.Response(200, json={"success": True, "msg": "ok", "obj": None})

    return httpx.MockTransport(handler), calls


def make_client(transport):
    return XuiClient(
        "https://panel:48453/secret/", "tok", [5, 2], "https://panel:2096/sub/", transport=transport
    )


async def test_extend_creates_missing_client():
    transport, calls = fake_panel(None)
    sub = await make_client(transport).extend("tg1", 3, tg_id=1)
    create = calls[-1]
    assert create.url.path == "/secret/panel/api/clients/add"
    assert create.headers["Authorization"] == "Bearer tok"
    body = json.loads(create.content)
    assert body["inboundIds"] == [5, 2]
    assert body["client"]["email"] == "tg1" and body["client"]["tgId"] == 1
    assert sub.active and sub.url == f"https://panel:2096/sub/{body['client']['subId']}"


async def test_extend_keeps_client_fields_and_extends_expiry():
    expire_ms = 4_000_000_000_000
    existing = {
        "client": {
            "id": 7, "uuid": "u", "reverse": "", "email": "tg1", "subId": "s",
            "flow": "xtls-rprx-vision", "limitIp": 2, "expiryTime": expire_ms, "enable": False,
        },
        "usedTraffic": 1024,
    }
    transport, calls = fake_panel(existing)
    sub = await make_client(transport).extend("tg1", 30)
    update = calls[-1]
    assert update.url.path == "/secret/panel/api/clients/update/tg1"
    body = json.loads(update.content)
    # Поля, которые панель не сможет разобрать в model.Client, не отправляем
    assert "id" not in body and "uuid" not in body and "reverse" not in body
    assert body["limitIp"] == 2 and body["enable"] is True
    assert body["expiryTime"] == expire_ms + 30 * 86400 * 1000
    assert sub.used_traffic == 1024 and sub.url == "https://panel:2096/sub/s"


async def test_missing_client_has_no_subscription():
    transport, _ = fake_panel(None)
    assert await make_client(transport).get_subscription("tg1") is None


async def test_unlimited_subscription_is_created_without_expiry():
    transport, calls = fake_panel(None)
    sub = await make_client(transport).extend("tg1", None)
    assert json.loads(calls[-1].content)["client"]["expiryTime"] == 0
    assert sub.active and sub.expire == 0


async def test_paying_does_not_cut_unlimited_subscription():
    transport, calls = fake_panel({"client": {"email": "tg1", "subId": "s", "expiryTime": 0, "enable": True}})
    await make_client(transport).extend("tg1", 30)
    assert json.loads(calls[-1].content)["expiryTime"] == 0


async def test_find_user_by_id_and_username(tmp_path):
    db = Database(str(tmp_path / "bot.db"))
    await db.init()
    await db.upsert_user(42, "Friend")
    assert await db.find_user("@friend") == (42, "Friend")
    assert await db.find_user("42") == (42, "Friend")
    assert await db.find_user("777") == (777, None)
    assert await db.find_user("@nobody") is None


async def test_reminder_is_sent_once(tmp_path):
    db = Database(str(tmp_path / "bot.db"))
    await db.init()
    assert await db.mark_reminded(1, 100, "soon")
    assert not await db.mark_reminded(1, 100, "soon")
    assert await db.mark_reminded(1, 100, "ended")


async def test_disable_keeps_other_fields():
    transport, calls = fake_panel({"client": {"email": "tg1", "subId": "s", "expiryTime": 5, "enable": True}})
    assert await make_client(transport).disable("tg1")
    body = json.loads(calls[-1].content)
    assert body == {"email": "tg1", "subId": "s", "expiryTime": 5, "enable": False}


async def test_disable_missing_client():
    transport, _ = fake_panel(None)
    assert not await make_client(transport).disable("tg1")


async def test_referral_is_rewarded_once_and_only_for_new_users(tmp_path):
    db = Database(str(tmp_path / "bot.db"))
    await db.init()
    await db.register(1, "inviter", None)
    assert await db.register(2, "friend", 1)
    assert not await db.register(1, "inviter", 2)  # старый пользователь не меняет пригласившего
    assert await db.register(3, "self", 3)  # сам себя пригласить нельзя
    assert await db.register(4, "ghost", 999)  # пригласивший должен быть в базе
    assert await db.referral_stats(1) == (1, 0)
    assert await db.take_referral_reward(2) == 1
    assert await db.take_referral_reward(2) is None
    assert await db.take_referral_reward(3) is None
    assert await db.take_referral_reward(4) is None
    assert await db.referral_stats(1) == (1, 1)


async def test_migration_adds_referral_columns(tmp_path):
    import aiosqlite

    path = str(tmp_path / "bot.db")
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            "CREATE TABLE users (tg_id INTEGER PRIMARY KEY, username TEXT, "
            "trial_used INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        await conn.execute("INSERT INTO users (tg_id, username) VALUES (1, 'old')")
        await conn.commit()
    db = Database(path)
    await db.init()
    await db.init()  # повторный запуск не падает
    assert await db.register(2, "new", 1)
    assert await db.referral_stats(1) == (1, 0)
