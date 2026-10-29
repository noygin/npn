import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.config import Settings
from bot.db import Database
from bot.keyboards import back_menu, main_menu, tariffs_menu
from bot.marzban import MarzbanClient, marzban_username

router = Router()
log = logging.getLogger(__name__)


@router.message(CommandStart())
async def start(message: Message, db: Database) -> None:
    await db.upsert_user(message.from_user.id, message.from_user.username)
    await message.answer(texts.WELCOME, reply_markup=main_menu())


@router.callback_query(F.data == "menu")
async def menu(call: CallbackQuery) -> None:
    await call.message.edit_text(texts.WELCOME, reply_markup=main_menu())
    await call.answer()


@router.message(Command("help"))
@router.callback_query(F.data == "help")
async def help_(event: Message | CallbackQuery) -> None:
    message = event.message if isinstance(event, CallbackQuery) else event
    await message.answer(texts.HELP, reply_markup=back_menu(), disable_web_page_preview=True)
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data == "buy")
async def buy(call: CallbackQuery) -> None:
    await call.message.edit_text("Выберите срок подписки:", reply_markup=tariffs_menu())
    await call.answer()


@router.callback_query(F.data == "trial")
async def trial(call: CallbackQuery, db: Database, marzban: MarzbanClient, settings: Settings) -> None:
    await db.upsert_user(call.from_user.id, call.from_user.username)
    if not await db.take_trial(call.from_user.id):
        await call.answer(texts.TRIAL_USED, show_alert=True)
        return
    try:
        user = await marzban.extend_user(marzban_username(call.from_user.id), settings.trial_days)
    except httpx.HTTPError:
        log.exception("trial failed for %s", call.from_user.id)
        await call.answer(texts.PANEL_ERROR, show_alert=True)
        return
    await call.message.answer(
        texts.subscription(user, marzban.subscription_url(user)), reply_markup=back_menu()
    )
    await call.answer()


@router.message(Command("my"))
@router.callback_query(F.data == "my")
async def my(event: Message | CallbackQuery, marzban: MarzbanClient) -> None:
    message = event.message if isinstance(event, CallbackQuery) else event
    try:
        user = await marzban.get_user(marzban_username(event.from_user.id))
    except httpx.HTTPError:
        log.exception("get_user failed for %s", event.from_user.id)
        text = texts.PANEL_ERROR
    else:
        text = (
            texts.subscription(user, marzban.subscription_url(user))
            if user is not None
            else texts.NO_SUBSCRIPTION
        )
    await message.answer(text, reply_markup=back_menu())
    if isinstance(event, CallbackQuery):
        await event.answer()
