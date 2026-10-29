import logging

import httpx
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import keyboards, texts
from bot.config import Settings
from bot.db import Database
from bot.panel import PanelError, XuiClient, client_email

router = Router()
log = logging.getLogger(__name__)


async def show(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Перерисовывает текущее окно на месте, чтобы чат не засорялся."""
    try:
        await call.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            await call.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
    await call.answer()


async def home_screen(
    tg_id: int, db: Database, panel: XuiClient, settings: Settings
) -> tuple[str, InlineKeyboardMarkup]:
    try:
        sub = await panel.get_subscription(client_email(tg_id))
    except (httpx.HTTPError, PanelError):
        log.exception("get_subscription failed for %s", tg_id)
        sub = None
    trial_days = None if await db.trial_used(tg_id) else settings.trial_days
    return texts.home(sub), keyboards.home(sub, trial_days, settings.support_username)


@router.message(CommandStart())
async def start(message: Message, db: Database, panel: XuiClient, settings: Settings) -> None:
    await db.upsert_user(message.from_user.id, message.from_user.username)
    text, markup = await home_screen(message.from_user.id, db, panel, settings)
    await message.answer(text, reply_markup=markup)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "home")
async def home(call: CallbackQuery, db: Database, panel: XuiClient, settings: Settings) -> None:
    await show(call, *await home_screen(call.from_user.id, db, panel, settings))


@router.callback_query(F.data == "help")
async def help_(call: CallbackQuery) -> None:
    await show(call, texts.HELP, keyboards.help_())


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(texts.HELP, reply_markup=keyboards.help_(), disable_web_page_preview=True)


@router.callback_query(F.data == "tariffs")
async def tariffs(call: CallbackQuery) -> None:
    await show(call, texts.tariffs(), keyboards.tariffs())


@router.callback_query(F.data == "connect")
async def connect(call: CallbackQuery, db: Database, panel: XuiClient, settings: Settings) -> None:
    try:
        sub = await panel.get_subscription(client_email(call.from_user.id))
    except (httpx.HTTPError, PanelError):
        log.exception("get_subscription failed for %s", call.from_user.id)
        await call.answer(texts.PANEL_ERROR, show_alert=True)
        return
    if sub is None:
        await show(call, *await home_screen(call.from_user.id, db, panel, settings))
        return
    await show(call, texts.connect(sub), keyboards.connect(sub))


@router.callback_query(F.data == "trial")
async def trial(call: CallbackQuery, db: Database, panel: XuiClient, settings: Settings) -> None:
    await db.upsert_user(call.from_user.id, call.from_user.username)
    if not await db.take_trial(call.from_user.id):
        await call.answer(texts.TRIAL_USED, show_alert=True)
        return
    try:
        sub = await panel.extend(
            client_email(call.from_user.id), settings.trial_days, call.from_user.id
        )
    except (httpx.HTTPError, PanelError):
        log.exception("trial failed for %s", call.from_user.id)
        await call.answer(texts.PANEL_ERROR, show_alert=True)
        return
    await show(call, texts.connect(sub), keyboards.connect(sub))
