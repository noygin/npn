"""Клиент API панели 3x-ui (v3): один клиент на пользователя, привязанный ко всем inbound."""

import secrets
import time
from dataclasses import dataclass

import httpx

DAY = 86400


def compute_expire(current: int | None, now: int, days: int) -> int:
    """Продлевает от текущего срока, если он ещё не истёк, иначе от сейчас."""
    base = max(current or 0, now)
    return base + days * DAY


def client_email(tg_id: int) -> str:
    return f"tg{tg_id}"


def tg_id_from_email(email: str) -> int | None:
    rest = email.removeprefix("tg")
    return int(rest) if rest != email and rest.isdigit() else None


@dataclass
class Subscription:
    active: bool
    expire: int  # unix-время в секундах
    used_traffic: int
    url: str


class PanelError(Exception):
    pass


class XuiClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        inbound_ids: list[int],
        sub_url: str,
        flow: str = "xtls-rprx-vision",
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._inbound_ids = inbound_ids
        self._sub_url = sub_url.rstrip("/")
        self._flow = flow
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/panel/api",
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=15,
            transport=transport,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, path: str, **kwargs) -> dict:
        r = await self._http.request(method, path, **kwargs)
        r.raise_for_status()
        return r.json()

    async def _get_client(self, email: str) -> dict | None:
        data = await self._call("GET", f"/clients/get/{email}")
        if not data["success"]:
            if "record not found" in data.get("msg", ""):
                return None
            raise PanelError(data.get("msg"))
        return data["obj"]

    def _subscription(self, client: dict, used_traffic: int) -> Subscription:
        expire_ms = client.get("expiryTime") or 0
        expire = expire_ms // 1000
        active = client.get("enable", False) and (expire == 0 or expire > time.time())
        return Subscription(active, expire, used_traffic, f"{self._sub_url}/{client['subId']}")

    async def get_subscription(self, email: str) -> Subscription | None:
        obj = await self._get_client(email)
        if obj is None:
            return None
        return self._subscription(obj["client"], obj.get("usedTraffic", 0))

    async def extend(self, email: str, days: int | None, tg_id: int = 0) -> Subscription:
        """Создаёт клиента или продлевает ему подписку на days дней.

        days=None делает подписку бессрочной. Бессрочная подписка при продлении
        остаётся бессрочной.
        """
        now = int(time.time())

        def new_expire_ms(current: int | None) -> int:
            if days is None or current == 0:
                return 0
            return compute_expire(current, now, days) * 1000

        obj = await self._get_client(email)
        if obj is None:
            client = {
                "email": email,
                "subId": secrets.token_hex(12),
                "flow": self._flow,
                "limitIp": 0,
                "totalGB": 0,
                "expiryTime": new_expire_ms(None),
                "enable": True,
                "tgId": tg_id,
                "comment": "bot",
                "reset": 0,
            }
            data = await self._call(
                "POST", "/clients/add", json={"client": client, "inboundIds": self._inbound_ids}
            )
            used = 0
        else:
            current = obj["client"]
            client, data = await self._update(
                current,
                expiryTime=new_expire_ms((current.get("expiryTime") or 0) // 1000),
                enable=True,
            )
            used = obj.get("usedTraffic", 0)
        if not data["success"]:
            raise PanelError(data.get("msg"))
        return self._subscription(client, used)

    async def _update(self, current: dict, **changes) -> tuple[dict, dict]:
        # Обновление в 3x-ui заменяет все поля, кроме ключей доступа,
        # поэтому передаём текущие значения целиком.
        client = {
            k: current[k]
            for k in ("email", "subId", "flow", "security", "limitIp", "totalGB",
                      "expiryTime", "enable", "tgId", "group", "comment", "reset")
            if k in current
        }
        client.update(changes)
        data = await self._call("POST", f"/clients/update/{current['email']}", json=client)
        return client, data

    async def disable(self, email: str) -> bool:
        """Выключает клиента. False, если такого клиента нет."""
        obj = await self._get_client(email)
        if obj is None:
            return False
        _, data = await self._update(obj["client"], enable=False)
        if not data["success"]:
            raise PanelError(data.get("msg"))
        return True

    async def list_clients(self) -> list[dict]:
        data = await self._call("GET", "/clients/list")
        if not data["success"]:
            raise PanelError(data.get("msg"))
        return data["obj"] or []
