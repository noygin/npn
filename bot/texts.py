import time
from datetime import datetime, timezone

from bot.panel import Subscription
from bot.tariffs import TARIFFS

BRAND = "<b>n.</b>"

PANEL_ERROR = "Сервер не ответил. Попробуйте через минуту."
TRIAL_USED = "Пробный период уже использован."
PAYMENT_ERROR = (
    f"{BRAND}\n\n"
    "Оплата прошла, но выдать доступ автоматически не вышло.\n"
    "Мы уже знаем об этом и скоро всё исправим."
)


def fmt_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y")


def fmt_bytes(n: int) -> str:
    size = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def days_left(expire: int) -> int:
    return max(0, -(-(expire - int(time.time())) // 86400))


def plural_days(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} дня"
    return f"{n} дней"


def status_line(sub: Subscription | None) -> str:
    if sub is None:
        return "Подписки пока нет."
    if not sub.active:
        return "Подписка закончилась."
    if sub.expire == 0:
        return "Подписка активна, без срока."
    return f"Подписка активна до {fmt_date(sub.expire)}, осталось {plural_days(days_left(sub.expire))}."


def home(sub: Subscription | None) -> str:
    return (
        f"{BRAND}\n\n"
        "Быстрый VPN, который работает при блокировках.\n\n"
        f"{status_line(sub)}"
    )


def connect(sub: Subscription) -> str:
    return (
        f"{BRAND}  Подключение\n\n"
        f"{status_line(sub)}\n"
        f"Трафик за всё время: {fmt_bytes(sub.used_traffic)}\n\n"
        "Ваша ссылка-подписка. Нажмите на неё, чтобы скопировать, "
        "и добавьте в приложение:\n\n"
        f"<code>{sub.url}</code>"
    )


def tariffs() -> str:
    lines = [f"{BRAND}  Тарифы", ""]
    for t in TARIFFS.values():
        months = t.days // 30
        per_month = f", {t.stars // months} ⭐ в месяц" if months > 1 else ""
        lines.append(f"{t.title}: {t.stars} ⭐{per_month}")
    lines += ["", "Оплата звёздами Telegram. Срок добавляется к текущей подписке."]
    return "\n".join(lines)


HELP = (
    f"{BRAND}  Как подключиться\n\n"
    "1. Установите приложение Happ (iPhone, Android) или Hiddify (компьютер).\n"
    "2. Откройте «Подключение» и скопируйте ссылку.\n"
    "3. В приложении нажмите «+» и выберите вставку из буфера.\n"
    "4. Включите VPN.\n\n"
    "В подписке несколько протоколов. Если один не работает, "
    "выберите в приложении другой сервер из списка."
)


def paid(sub: Subscription) -> str:
    return f"Оплата прошла, спасибо!\n\n{connect(sub)}"
