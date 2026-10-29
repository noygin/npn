import os

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    trial_used INTEGER NOT NULL DEFAULT 0,
    referred_by INTEGER,
    referral_rewarded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reminders (
    tg_id INTEGER NOT NULL,
    expire INTEGER NOT NULL,
    kind TEXT NOT NULL,
    PRIMARY KEY (tg_id, expire, kind)
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER NOT NULL,
    tariff TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    charge_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            # Миграции для баз, созданных до появления колонок
            columns = {row[1] for row in await db.execute_fetchall("PRAGMA table_info(users)")}
            if "referred_by" not in columns:
                await db.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
            if "referral_rewarded" not in columns:
                await db.execute(
                    "ALTER TABLE users ADD COLUMN referral_rewarded INTEGER NOT NULL DEFAULT 0"
                )
            await db.commit()

    async def upsert_user(self, tg_id: int, username: str | None) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO users (tg_id, username) VALUES (?, ?) "
                "ON CONFLICT(tg_id) DO UPDATE SET username = excluded.username",
                (tg_id, username),
            )
            await db.commit()

    async def register(self, tg_id: int, username: str | None, referrer: int | None) -> bool:
        """Добавляет пользователя. True, если он новый.

        Пригласивший запоминается только для новых пользователей и только если
        сам уже есть в базе.
        """
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT OR IGNORE INTO users (tg_id, username) VALUES (?, ?)", (tg_id, username)
            )
            is_new = cur.rowcount == 1
            if not is_new:
                await db.execute(
                    "UPDATE users SET username = ? WHERE tg_id = ?", (username, tg_id)
                )
            elif referrer is not None and referrer != tg_id:
                await db.execute(
                    "UPDATE users SET referred_by = ? WHERE tg_id = ? "
                    "AND EXISTS (SELECT 1 FROM users WHERE tg_id = ?)",
                    (referrer, tg_id, referrer),
                )
            await db.commit()
        return is_new

    async def take_referral_reward(self, tg_id: int) -> int | None:
        """Возвращает пригласившего, если за этого пользователя ещё не награждали."""
        async with aiosqlite.connect(self.path) as db:
            row = await (
                await db.execute(
                    "SELECT referred_by FROM users WHERE tg_id = ? "
                    "AND referred_by IS NOT NULL AND referral_rewarded = 0",
                    (tg_id,),
                )
            ).fetchone()
            if row is None:
                return None
            await db.execute("UPDATE users SET referral_rewarded = 1 WHERE tg_id = ?", (tg_id,))
            await db.commit()
        return row[0]

    async def referral_stats(self, tg_id: int) -> tuple[int, int]:
        """Сколько человек пригласил и сколько из них уже оплатили."""
        async with aiosqlite.connect(self.path) as db:
            row = await (
                await db.execute(
                    "SELECT COUNT(*), COALESCE(SUM(referral_rewarded), 0) FROM users "
                    "WHERE referred_by = ?",
                    (tg_id,),
                )
            ).fetchone()
        return row[0], row[1]

    async def trial_used(self, tg_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            row = await (
                await db.execute("SELECT trial_used FROM users WHERE tg_id = ?", (tg_id,))
            ).fetchone()
        return bool(row and row[0])

    async def take_trial(self, tg_id: int) -> bool:
        """Помечает пробный период использованным. False, если он уже был."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE users SET trial_used = 1 WHERE tg_id = ? AND trial_used = 0",
                (tg_id,),
            )
            await db.commit()
            return cur.rowcount == 1

    async def add_payment(
        self, tg_id: int, tariff: str, amount: int, currency: str, charge_id: str
    ) -> bool:
        """Сохраняет платёж. False, если такой charge_id уже обработан."""
        async with aiosqlite.connect(self.path) as db:
            try:
                await db.execute(
                    "INSERT INTO payments (tg_id, tariff, amount, currency, charge_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (tg_id, tariff, amount, currency, charge_id),
                )
            except aiosqlite.IntegrityError:
                return False
            await db.commit()
            return True

    async def find_user(self, query: str) -> tuple[int, str | None] | None:
        """Ищет пользователя по Telegram ID или @username."""
        query = query.strip()
        async with aiosqlite.connect(self.path) as db:
            if query.lstrip("@").isdigit() and not query.startswith("@"):
                row = await (
                    await db.execute("SELECT tg_id, username FROM users WHERE tg_id = ?", (int(query),))
                ).fetchone()
                return (row[0], row[1]) if row else (int(query), None)
            row = await (
                await db.execute(
                    "SELECT tg_id, username FROM users WHERE lower(username) = lower(?)",
                    (query.lstrip("@"),),
                )
            ).fetchone()
        return (row[0], row[1]) if row else None

    async def recent_users(self, limit: int = 20) -> list[tuple[int, str | None, str]]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (
                await db.execute(
                    "SELECT tg_id, username, created_at FROM users ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    async def mark_reminded(self, tg_id: int, expire: int, kind: str) -> bool:
        """Запоминает напоминание. False, если оно уже было отправлено."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT OR IGNORE INTO reminders (tg_id, expire, kind) VALUES (?, ?, ?)",
                (tg_id, expire, kind),
            )
            await db.commit()
            return cur.rowcount == 1

    async def stats(self) -> dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
            paid = (await (await db.execute("SELECT COUNT(*) FROM payments")).fetchone())[0]
            stars = (
                await (
                    await db.execute(
                        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE currency = 'XTR'"
                    )
                ).fetchone()
            )[0]
        return {"users": users, "payments": paid, "stars": stars}
