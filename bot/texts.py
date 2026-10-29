from datetime import datetime, timezone

from bot.panel import Subscription

WELCOME = (
    "Привет! Это быстрый VPN, который работает даже при блокировках.\n\n"
    "Можно попробовать бесплатно, а потом выбрать подписку."
)

HELP = (
    "<b>Как подключиться</b>\n\n"
    "1. Установите приложение:\n"
    "• Android: Happ или Hiddify\n"
    "• iPhone: Happ или Streisand из App Store\n"
    "• Windows и macOS: <a href=\"https://github.com/hiddify/hiddify-app/releases\">Hiddify</a>\n\n"
    "2. Скопируйте ссылку-подписку из раздела «Моя подписка».\n"
    "3. В приложении нажмите «+» и выберите импорт из буфера обмена.\n"
    "4. Подключитесь."
)

TRIAL_USED = "Пробный период уже использован. Оформите подписку, чтобы продолжить."
NO_SUBSCRIPTION = "У вас пока нет подписки."
PANEL_ERROR = "Не получилось связаться с сервером. Попробуйте через минуту."
PAYMENT_ERROR = (
    "Оплата прошла, но выдать доступ автоматически не вышло. "
    "Мы уже знаем об этом и всё исправим."
)


def fmt_date(ts: int | None) -> str:
    if not ts:
        return "бессрочно"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def fmt_bytes(n: int | None) -> str:
    n = n or 0
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def subscription(sub: Subscription) -> str:
    status = "активна ✅" if sub.active else "не активна ❌"
    return (
        f"<b>Подписка {status}</b>\n"
        f"Действует до: {fmt_date(sub.expire)}\n"
        f"Трафик: {fmt_bytes(sub.used_traffic)}\n\n"
        f"Ссылка для приложения (нажмите, чтобы скопировать):\n<code>{sub.url}</code>"
    )
