"""OpenVPN-профили AntiZapret через хост.

Бот работает в контейнере и сам выпустить сертификат не может. Он кладёт заявку
в общую папку data/ovpn, а deploy/ovpn-helper.sh на хосте (раз в 2 минуты)
создаёт клиента через /root/antizapret/client.sh и возвращает .ovpn туда же.
"""

import asyncio
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

WAIT_SECONDS = 6 * 60


@dataclass
class Result:
    ok: bool
    files: list[Path]
    error: str = ""


def client_name(days: int, now: float | None = None) -> str:
    return time.strftime(f"tmp{days}d-%y%m%d-%H%M%S", time.gmtime(time.time() if now is None else now))


def submit(base: Path, name: str, days: int) -> None:
    req = base / "requests"
    req.mkdir(parents=True, exist_ok=True)
    tmp = req / f".{name}.tmp"
    tmp.write_text(f"{name} {days}\n")
    tmp.rename(req / f"{name}.req")


async def wait(
    base: Path, name: str, timeout: float | None = None, step: float = 5
) -> Result | None:
    done = base / "done" / name
    deadline = time.monotonic() + (WAIT_SECONDS if timeout is None else timeout)
    while time.monotonic() < deadline:
        status = done / "status"
        if status.exists():
            lines = status.read_text().splitlines()
            files = sorted(done.glob("*.ovpn"))
            if lines and lines[0] == "ok":
                return Result(True, files)
            return Result(False, [], "\n".join(lines[1:]))
        await asyncio.sleep(step)
    return None


def cleanup(base: Path, name: str) -> None:
    shutil.rmtree(base / "done" / name, ignore_errors=True)
    (base / "requests" / f"{name}.req").unlink(missing_ok=True)
