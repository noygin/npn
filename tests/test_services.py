import json

import httpx

from bot.db import Database
from bot.marzban import MarzbanClient


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
        if request.url.path == "/api/admin/token":
            return httpx.Response(200, json={"access_token": "t"})
        if request.method == "GET":
            return httpx.Response(200, json=existing) if existing else httpx.Response(404)
        body = json.loads(request.content)
        return httpx.Response(200, json={"subscription_url": "/sub/abc", **body})

    return httpx.MockTransport(handler), calls


async def test_extend_creates_missing_user():
    transport, calls = fake_panel(None)
    client = MarzbanClient("http://panel/", "a", "b", "VLESS TCP REALITY", transport)
    user = await client.extend_user("tg1", 3)
    create = calls[-1]
    assert create.method == "POST" and create.headers["Authorization"] == "Bearer t"
    assert json.loads(create.content)["inbounds"] == {"vless": ["VLESS TCP REALITY"]}
    assert client.subscription_url(user) == "http://panel/sub/abc"


async def test_extend_updates_existing_user():
    transport, calls = fake_panel({"username": "tg1", "expire": 4_000_000_000})
    client = MarzbanClient("http://panel", "a", "b", "VLESS TCP REALITY", transport)
    await client.extend_user("tg1", 30)
    update = calls[-1]
    assert update.method == "PUT"
    assert json.loads(update.content)["expire"] == 4_000_000_000 + 30 * 86400
