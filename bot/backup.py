"""Ежедневная копия базы бота рядом с ней, хранится неделя."""

import asyncio
import logging
import os
from datetime import UTC, date, datetime

from bot.db import Database

log = logging.getLogger(__name__)
KEEP = 7


async def make_backup(db: Database, today: date | None = None) -> str:
    folder = os.path.join(os.path.dirname(db.path) or ".", "backups")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"bot-{(today or datetime.now(UTC).date()).isoformat()}.db")
    if not os.path.exists(dest):
        await db.backup(dest)
    old = sorted(f for f in os.listdir(folder) if f.startswith("bot-") and f.endswith(".db"))
    for name in old[:-KEEP]:
        os.remove(os.path.join(folder, name))
    return dest


async def run(db: Database) -> None:
    while True:
        try:
            await make_backup(db)
        except Exception:
            log.exception("backup failed")
        await asyncio.sleep(6 * 3600)
