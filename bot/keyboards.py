from urllib.parse import quote

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from bot.panel import Subscription
from bot.tariffs import TARIFFS
from bot.texts import plural_days

APP_IOS = "https://apps.apple.com/app/happ-proxy-utility/id6504287215"
APP_ANDROID = "https://play.google.com/store/apps/details?id=com.happproxy"
APP_DESKTOP = "https://github.com/hiddify/hiddify-app/releases"

BACK = InlineKeyboardButton(text="← Назад", callback_data="home")


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[row for row in rows if row])


def home(
    sub: Subscription | None, trial_days: int | None, support: str, is_admin: bool = False
) -> InlineKeyboardMarkup:
    """trial_days=None, если пробный период уже использован."""
    if sub is not None and sub.active and sub.expire == 0:
        first = [InlineKeyboardButton(text="Подключиться", callback_data="connect")]
    elif sub is not None:
        first = [
            InlineKeyboardButton(text="Подключиться", callback_data="connect"),
            InlineKeyboardButton(text="Продлить", callback_data="tariffs"),
        ]
    else:
        first = [InlineKeyboardButton(text="Тарифы", callback_data="tariffs")]
    trial = (
        [InlineKeyboardButton(text=f"Попробовать {plural_days(trial_days)} бесплатно", callback_data="trial")]
        if sub is None and trial_days
        else []
    )
    last = [
        InlineKeyboardButton(text="Инструкция", callback_data="help"),
        InlineKeyboardButton(text="Пригласить друга", callback_data="invite"),
    ]
    if support:
        last.append(InlineKeyboardButton(text="Поддержка", url=f"https://t.me/{support}"))
    admin_row = [InlineKeyboardButton(text="Админка", callback_data="admin")] if is_admin else []
    return _kb(trial, first, last, admin_row)


def connect(sub: Subscription) -> InlineKeyboardMarkup:
    return _kb(
        [InlineKeyboardButton(text="Скопировать ссылку", copy_text=CopyTextButton(text=sub.url))],
        [InlineKeyboardButton(text="Инструкция", callback_data="help"), BACK],
    )


def tariffs() -> InlineKeyboardMarkup:
    return _kb(
        *[
            [InlineKeyboardButton(text=f"{t.title} · {t.stars} ⭐", callback_data=f"buy:{t.code}")]
            for t in TARIFFS.values()
        ],
        [BACK],
    )


def help_() -> InlineKeyboardMarkup:
    return _kb(
        [
            InlineKeyboardButton(text="iPhone", url=APP_IOS),
            InlineKeyboardButton(text="Android", url=APP_ANDROID),
            InlineKeyboardButton(text="Компьютер", url=APP_DESKTOP),
        ],
        [InlineKeyboardButton(text="Подключение", callback_data="connect"), BACK],
    )


def open_home() -> InlineKeyboardMarkup:
    return _kb([InlineKeyboardButton(text="Открыть", callback_data="home")])


def renew() -> InlineKeyboardMarkup:
    return _kb(
        [InlineKeyboardButton(text="Продлить", callback_data="tariffs")],
        [InlineKeyboardButton(text="Главное меню", callback_data="home")],
    )


def admin() -> InlineKeyboardMarkup:
    return _kb(
        [
            InlineKeyboardButton(text="Выдать доступ", callback_data="admin:give"),
            InlineKeyboardButton(text="Забрать", callback_data="admin:take"),
        ],
        [
            InlineKeyboardButton(text="Пользователи", callback_data="admin:users"),
            InlineKeyboardButton(text="Промокоды", callback_data="admin:promos"),
        ],
        [BACK],
    )


def admin_cancel() -> InlineKeyboardMarkup:
    return _kb([InlineKeyboardButton(text="Отмена", callback_data="admin")])


def admin_back() -> InlineKeyboardMarkup:
    return _kb([InlineKeyboardButton(text="← Админка", callback_data="admin")])


def invite(link: str) -> InlineKeyboardMarkup:
    share = f"https://t.me/share/url?url={quote(link)}&text={quote('Быстрый VPN, работает при блокировках')}"
    return _kb(
        [InlineKeyboardButton(text="Отправить другу", url=share)],
        [InlineKeyboardButton(text="Скопировать ссылку", copy_text=CopyTextButton(text=link))],
        [BACK],
    )


def admin_promos() -> InlineKeyboardMarkup:
    return _kb(
        [InlineKeyboardButton(text="Создать промокод", callback_data="admin:promo")],
        [InlineKeyboardButton(text="← Админка", callback_data="admin")],
    )
