import time
from datetime import datetime, timezone
from html import escape

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
        return "Подписка активна, бессрочно."
    return f"Подписка активна до {fmt_date(sub.expire)}, осталось {plural_days(days_left(sub.expire))}."


def home(sub: Subscription | None, greeting: str | None = None) -> str:
    intro = escape(greeting) if greeting else "Быстрый VPN, который работает при блокировках."
    return (
        f"{BRAND}\n\n"
        f"{intro}\n\n"
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


def gift(sub: Subscription) -> str:
    when = "бессрочно" if sub.expire == 0 else f"до {fmt_date(sub.expire)}"
    return f"{BRAND}\n\nВам выдали доступ к VPN, {when}. Нажмите «Открыть», чтобы подключиться."


REMIND_SOON = (
    f"{BRAND}\n\nПодписка закончится завтра. Продлите её, чтобы VPN не отключился."
)
REMIND_ENDED = f"{BRAND}\n\nПодписка закончилась. Продлите её, чтобы снова пользоваться VPN."


def admin(stats: dict[str, int]) -> str:
    return (
        f"{BRAND}  Админка\n\n"
        f"Пользователей: {stats['users']}\n"
        f"Платежей: {stats['payments']}\n"
        f"Звёзд получено: {stats['stars']}"
    )


ADMIN_GIVE_HELP = (
    f"{BRAND}  Выдать доступ\n\n"
    "Пришлите ID или @username и срок в днях:\n"
    "<code>123456789 30</code>\n"
    "<code>@friend навсегда</code>\n\n"
    "Без срока будет 30 дней. Если доступ уже есть, срок добавится к нему. "
    "Свой ID человек может узнать командой /id в боте."
)
ADMIN_TAKE_HELP = (
    f"{BRAND}  Забрать доступ\n\n"
    "Пришлите ID или @username. Подписка выключится сразу."
)
ADMIN_NOT_FOUND = (
    "Не нашёл такого человека. По @username ищу только тех, кто уже запускал бота. "
    "Пришлите числовой ID: его можно узнать командой /id."
)


def who(tg_id: int, username: str | None) -> str:
    return f"@{escape(username)} ({tg_id})" if username else str(tg_id)


def admin_given(tg_id: int, username: str | None, sub: Subscription, notified: bool) -> str:
    when = "бессрочно" if sub.expire == 0 else f"до {fmt_date(sub.expire)}"
    note = (
        "Уведомление отправлено."
        if notified
        else "Уведомить не вышло: человек ещё не запускал бота. Доступ появится, когда он нажмёт /start."
    )
    return f"Готово: {who(tg_id, username)}, доступ {when}.\n{note}"


def admin_taken(tg_id: int, username: str | None, ok: bool) -> str:
    if not ok:
        return f"У {who(tg_id, username)} нет подписки."
    return f"Готово: доступ {who(tg_id, username)} выключен."


def admin_users(rows: list[tuple[int, str | None, str]]) -> str:
    lines = [f"{BRAND}  Последние пользователи", ""]
    lines += [f"{who(tg_id, username)}: {status}" for tg_id, username, status in rows]
    if not rows:
        lines.append("Пока никого.")
    return "\n".join(lines)


def invite(link: str, invited: int, paid: int, days: int) -> str:
    return (
        f"{BRAND}  Пригласить друга\n\n"
        f"Когда друг впервые оплатит подписку, вы получите {plural_days(days)} бесплатно.\n\n"
        f"Ваша ссылка:\n<code>{link}</code>\n\n"
        f"Пришли по ссылке: {invited}, из них оплатили: {paid}."
    )


def referral_reward(days: int, sub: Subscription) -> str:
    when = "бессрочно" if sub.expire == 0 else f"до {fmt_date(sub.expire)}"
    return f"{BRAND}\n\nВаш друг оплатил подписку. Дарим {plural_days(days)}, теперь доступ {when}."
