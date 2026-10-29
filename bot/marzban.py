import time

import httpx

DAY = 86400


def compute_expire(current: int | None, now: int, days: int) -> int:
    """Продлевает от текущего срока, если он ещё не истёк, иначе от сейчас."""
    base = max(current or 0, now)
    return base + days * DAY


def marzban_username(tg_id: int) -> str:
    return f"tg{tg_id}"


class MarzbanClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        inbound: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._inbound = inbound
        self._token: str | None = None
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=15, transport=transport)

    async def close(self) -> None:
        await self._http.aclose()

    async def _auth(self) -> None:
        r = await self._http.post(
            "/api/admin/token",
            data={"username": self._username, "password": self._password},
        )
        r.raise_for_status()
        self._token = r.json()["access_token"]

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self._token is None:
            await self._auth()
        for attempt in range(2):
            r = await self._http.request(
                method, path, headers={"Authorization": f"Bearer {self._token}"}, **kwargs
            )
            if r.status_code == 401 and attempt == 0:
                await self._auth()
                continue
            return r
        return r

    async def get_user(self, username: str) -> dict | None:
        r = await self._request("GET", f"/api/user/{username}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    async def extend_user(self, username: str, days: int) -> dict:
        """Создаёт пользователя или продлевает ему подписку на days дней."""
        now = int(time.time())
        user = await self.get_user(username)
        if user is None:
            r = await self._request(
                "POST",
                "/api/user",
                json={
                    "username": username,
                    "proxies": {"vless": {"flow": "xtls-rprx-vision"}},
                    "inbounds": {"vless": [self._inbound]},
                    "expire": compute_expire(None, now, days),
                    "data_limit": 0,
                    "data_limit_reset_strategy": "no_reset",
                    "status": "active",
                },
            )
        else:
            r = await self._request(
                "PUT",
                f"/api/user/{username}",
                json={
                    "expire": compute_expire(user.get("expire"), now, days),
                    "status": "active",
                },
            )
        r.raise_for_status()
        return r.json()

    def subscription_url(self, user: dict) -> str:
        url = user.get("subscription_url", "")
        # Без XRAY_SUBSCRIPTION_URL_PREFIX панель отдаёт относительный путь
        return self.base_url + url if url.startswith("/") else url
