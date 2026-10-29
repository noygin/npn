from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.tariffs import TARIFFS


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Попробовать бесплатно", callback_data="trial")],
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
            [InlineKeyboardButton(text="🔑 Моя подписка", callback_data="my")],
            [InlineKeyboardButton(text="📖 Как подключиться", callback_data="help")],
        ]
    )


def tariffs_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{t.title} · {t.stars} ⭐", callback_data=f"buy:{t.code}")]
        for t in TARIFFS.values()
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="← В меню", callback_data="menu")]]
    )
