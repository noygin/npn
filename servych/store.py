"""База сайта: пользователи, их серверы, люди на серверах, заявки и платежи.

Этот модуль импортирует и бот: он подтверждает вход на сайт через Telegram.
Поэтому здесь нет зависимостей от FastAPI.
"""

import json
import os
import secrets
import time

import aiosqlite

DAY = 86400
MONTH = 30 * DAY
LOGIN_TTL = 10 * 60
SESSION_TTL = 90 * DAY

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS login_codes (
    code TEXT PRIMARY KEY,
    tg_id INTEGER,
    -- адрес сайта, с которого начали вход: бот даёт на него кнопку возврата
    site TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    tg_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL UNIQUE,
    -- ordered: заказан и ждёт настройки; active: работает
    status TEXT NOT NULL DEFAULT 'ordered',
    title TEXT NOT NULL DEFAULT '',
    panel_url TEXT NOT NULL DEFAULT '',
    api_token TEXT NOT NULL DEFAULT '',
    inbound_ids TEXT NOT NULL DEFAULT '[]',
    sub_url TEXT NOT NULL DEFAULT '',
    paid_until INTEGER,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    sub_id TEXT NOT NULL,
    share_token TEXT NOT NULL UNIQUE,
    removed INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER NOT NULL,
    server_id INTEGER,
    -- new_server, change_ip
    kind TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER NOT NULL,
    server_id INTEGER NOT NULL,
    months INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    method TEXT NOT NULL,
    external_id TEXT NOT NULL DEFAULT '',
    pay_url TEXT NOT NULL DEFAULT '',
    -- pending, paid
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL
);
"""


def now() -> int:
    return int(time.time())


class Store:
    def __init__(self, path: str):
        self.path = path

    def _connect(self) -> aiosqlite.Connection:
        return aiosqlite.connect(self.path, timeout=10)

    async def _fetchone(self, sql: str, args: tuple = ()) -> dict | None:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(sql, args)).fetchone()
            return dict(row) if row else None

    async def _fetchall(self, sql: str, args: tuple = ()) -> list[dict]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            return [dict(r) for r in await db.execute_fetchall(sql, args)]

    async def _execute(self, sql: str, args: tuple = ()) -> int:
        """Выполняет запрос и возвращает число изменённых строк."""
        async with self._connect() as db:
            cur = await db.execute(sql, args)
            await db.commit()
            return cur.rowcount

    async def _insert(self, sql: str, args: tuple = ()) -> int:
        async with self._connect() as db:
            cur = await db.execute(sql, args)
            await db.commit()
            return cur.lastrowid

    async def init(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        async with self._connect() as db:
            # Сайт и бот пишут в базу из разных процессов
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(SCHEMA)
            # Миграция для баз, созданных до появления колонки
            columns = {r[1] for r in await db.execute_fetchall("PRAGMA table_info(login_codes)")}
            if "site" not in columns:
                await db.execute("ALTER TABLE login_codes ADD COLUMN site TEXT NOT NULL DEFAULT ''")
            await db.commit()

    # Вход через Telegram

    async def new_login_code(self, site: str = "") -> str:
        code = secrets.token_urlsafe(18)
        await self._execute(
            "INSERT INTO login_codes (code, site, created_at) VALUES (?, ?, ?)", (code, site, now())
        )
        return code

    async def confirm_login(
        self, code: str, tg_id: int, username: str | None, name: str | None
    ) -> str | None:
        """Бот вызывает это, когда человек нажал «Старт» по ссылке входа.

        Возвращает адрес сайта, с которого начали вход, или None, если код не подошёл.
        """
        changed = await self._execute(
            "UPDATE login_codes SET tg_id = ? WHERE code = ? AND tg_id IS NULL AND created_at > ?",
            (tg_id, code, now() - LOGIN_TTL),
        )
        if not changed:
            return None
        await self.upsert_user(tg_id, username, name)
        row = await self._fetchone("SELECT site FROM login_codes WHERE code = ?", (code,))
        return row["site"]

    async def login_owner(self, code: str) -> int | None:
        row = await self._fetchone(
            "SELECT tg_id FROM login_codes WHERE code = ? AND created_at > ?",
            (code, now() - LOGIN_TTL),
        )
        return row["tg_id"] if row else None

    async def create_session(self, tg_id: int) -> str:
        token = secrets.token_urlsafe(32)
        await self._execute(
            "INSERT INTO sessions (token, tg_id, created_at) VALUES (?, ?, ?)",
            (token, tg_id, now()),
        )
        return token

    async def session_user(self, token: str) -> dict | None:
        return await self._fetchone(
            "SELECT u.* FROM sessions s JOIN users u ON u.tg_id = s.tg_id "
            "WHERE s.token = ? AND s.created_at > ?",
            (token, now() - SESSION_TTL),
        )

    async def delete_session(self, token: str) -> None:
        await self._execute("DELETE FROM sessions WHERE token = ?", (token,))

    # Пользователи

    async def upsert_user(self, tg_id: int, username: str | None, name: str | None) -> None:
        await self._execute(
            "INSERT INTO users (tg_id, username, name, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(tg_id) DO UPDATE SET username = excluded.username, name = excluded.name",
            (tg_id, username, name, now()),
        )

    async def get_user(self, tg_id: int) -> dict | None:
        return await self._fetchone("SELECT * FROM users WHERE tg_id = ?", (tg_id,))

    # Серверы

    @staticmethod
    def _server(row: dict | None) -> dict | None:
        if row is not None:
            row["inbound_ids"] = json.loads(row["inbound_ids"] or "[]")
        return row

    async def server_of(self, tg_id: int) -> dict | None:
        return self._server(
            await self._fetchone("SELECT * FROM servers WHERE owner_id = ?", (tg_id,))
        )

    async def get_server(self, server_id: int) -> dict | None:
        return self._server(
            await self._fetchone("SELECT * FROM servers WHERE id = ?", (server_id,))
        )

    async def order_server(self, tg_id: int) -> dict:
        """Создаёт заказ сервера, если у человека его ещё нет."""
        async with self._connect() as db:
            cur = await db.execute(
                "INSERT OR IGNORE INTO servers (owner_id, created_at) VALUES (?, ?)",
                (tg_id, now()),
            )
            if cur.rowcount:
                await db.execute(
                    "INSERT INTO requests (tg_id, server_id, kind, created_at) "
                    "VALUES (?, ?, 'new_server', ?)",
                    (tg_id, cur.lastrowid, now()),
                )
            await db.commit()
        return await self.server_of(tg_id)

    async def setup_server(
        self,
        server_id: int,
        title: str,
        panel_url: str,
        api_token: str,
        inbound_ids: list[int],
        sub_url: str,
    ) -> None:
        """Админ вписывает доступ к 3x-ui. Пустой токен оставляет прежний."""
        await self._execute(
            "UPDATE servers SET status = 'active', title = ?, panel_url = ?, "
            "api_token = CASE WHEN ? = '' THEN api_token ELSE ? END, "
            "inbound_ids = ?, sub_url = ? WHERE id = ?",
            (title, panel_url, api_token, api_token, json.dumps(inbound_ids), sub_url, server_id),
        )

    async def extend_paid(self, server_id: int, days: int) -> int:
        server = await self.get_server(server_id)
        paid_until = max(server["paid_until"] or 0, now()) + days * DAY
        await self._execute(
            "UPDATE servers SET paid_until = ? WHERE id = ?", (paid_until, server_id)
        )
        return paid_until

    async def list_servers(self) -> list[dict]:
        rows = await self._fetchall(
            "SELECT s.*, u.username, u.name, "
            "(SELECT COUNT(*) FROM members m WHERE m.server_id = s.id AND m.removed = 0) AS people "
            "FROM servers s LEFT JOIN users u ON u.tg_id = s.owner_id ORDER BY s.id DESC"
        )
        return [self._server(r) for r in rows]

    # Люди на сервере

    async def add_member(self, server_id: int, name: str, email: str, sub_id: str) -> dict:
        member_id = await self._insert(
            "INSERT INTO members (server_id, name, email, sub_id, share_token, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (server_id, name, email, sub_id, secrets.token_urlsafe(16), now()),
        )
        return await self.get_member(member_id)

    async def members(self, server_id: int) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM members WHERE server_id = ? AND removed = 0 ORDER BY id", (server_id,)
        )

    async def get_member(self, member_id: int) -> dict | None:
        return await self._fetchone("SELECT * FROM members WHERE id = ?", (member_id,))

    async def member_by_token(self, token: str) -> dict | None:
        return await self._fetchone(
            "SELECT * FROM members WHERE share_token = ? AND removed = 0", (token,)
        )

    async def remove_member(self, member_id: int) -> None:
        await self._execute("UPDATE members SET removed = 1 WHERE id = ?", (member_id,))

    # Заявки

    async def add_request(self, tg_id: int, server_id: int | None, kind: str, note: str = "") -> bool:
        """Новая заявка. False, если такая же ещё не закрыта."""
        open_ = await self._fetchone(
            "SELECT id FROM requests WHERE tg_id = ? AND kind = ? AND done = 0", (tg_id, kind)
        )
        if open_:
            return False
        await self._insert(
            "INSERT INTO requests (tg_id, server_id, kind, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (tg_id, server_id, kind, note, now()),
        )
        return True

    async def open_request(self, tg_id: int, kind: str) -> dict | None:
        return await self._fetchone(
            "SELECT * FROM requests WHERE tg_id = ? AND kind = ? AND done = 0", (tg_id, kind)
        )

    async def open_requests(self) -> list[dict]:
        return await self._fetchall(
            "SELECT r.*, u.username, u.name FROM requests r "
            "LEFT JOIN users u ON u.tg_id = r.tg_id WHERE r.done = 0 ORDER BY r.id"
        )

    async def close_request(self, request_id: int) -> dict | None:
        await self._execute("UPDATE requests SET done = 1 WHERE id = ?", (request_id,))
        return await self._fetchone("SELECT * FROM requests WHERE id = ?", (request_id,))

    async def close_requests(self, server_id: int, kind: str) -> None:
        await self._execute(
            "UPDATE requests SET done = 1 WHERE server_id = ? AND kind = ?", (server_id, kind)
        )

    # Платежи

    async def add_payment(
        self, tg_id: int, server_id: int, months: int, amount: int, method: str
    ) -> int:
        return await self._insert(
            "INSERT INTO payments (tg_id, server_id, months, amount, method, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tg_id, server_id, months, amount, method, now()),
        )

    async def set_payment_link(self, payment_id: int, external_id: str, pay_url: str) -> None:
        await self._execute(
            "UPDATE payments SET external_id = ?, pay_url = ? WHERE id = ?",
            (external_id, pay_url, payment_id),
        )

    async def get_payment(self, payment_id: int) -> dict | None:
        return await self._fetchone("SELECT * FROM payments WHERE id = ?", (payment_id,))

    async def mark_paid(self, payment_id: int) -> bool:
        """Отмечает платёж оплаченным и продлевает сервер. Повторный вызов ничего не делает."""
        changed = await self._execute(
            "UPDATE payments SET status = 'paid' WHERE id = ? AND status = 'pending'",
            (payment_id,),
        )
        if not changed:
            return False
        payment = await self.get_payment(payment_id)
        await self.extend_paid(payment["server_id"], payment["months"] * 30)
        return True

    async def recent_payments(self, limit: int = 30) -> list[dict]:
        return await self._fetchall(
            "SELECT p.*, u.username, u.name FROM payments p "
            "LEFT JOIN users u ON u.tg_id = p.tg_id ORDER BY p.id DESC LIMIT ?",
            (limit,),
        )
