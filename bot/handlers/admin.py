import logging
import time

import httpx
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import keyboards, texts
from bot.config import Settings
from bot.db import Database
from bot.handlers.menu import show
from bot.panel import PanelError, XuiClient, client_email, tg_id_from_email

router = Router()
log = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        return event.from_user.id in settings.admin_ids


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class AdminInput(StatesGroup):
    give = State()
    take = State()


def parse_duration(word: str | None) -> int | None | bool:
    """Число дней, None для «навсегда», False, если не разобрали."""
    if word is None:
        return 30
    word = word.lower()
    if word in ("навсегда", "forever", "бессрочно", "∞"):
        return None
    return int(word) if word.isdigit() and int(word) > 0 else False


async def admin_screen(db: Database) -> str:
    s = await db.stats()
    return texts.admin(s)


async def give(
    args: str, bot: Bot, db: Database, panel: XuiClient
) -> str:
    parts = args.split()
    if not parts:
        return texts.ADMIN_GIVE_HELP
    days = parse_duration(parts[1] if len(parts) > 1 else None)
    if days is False:
        return texts.ADMIN_GIVE_HELP
    found = await db.find_user(parts[0])
    if found is None:
        return texts.ADMIN_NOT_FOUND
    tg_id, username = found
    try:
        sub = await panel.extend(client_email(tg_id), days, tg_id)
    except (httpx.HTTPError, PanelError):
        log.exception("admin give failed for %s", tg_id)
        return texts.PANEL_ERROR
    try:
        await bot.send_message(tg_id, texts.gift(sub), reply_markup=keyboards.open_home())
        notified = True
    except TelegramAPIError:
        notified = False
    return texts.admin_given(tg_id, username, sub, notified)


async def take(args: str, db: Database, panel: XuiClient) -> str:
    query = args.strip()
    if not query:
        return texts.ADMIN_TAKE_HELP
    found = await db.find_user(query)
    if found is None:
        return texts.ADMIN_NOT_FOUND
    tg_id, username = found
    try:
        ok = await panel.disable(client_email(tg_id))
    except (httpx.HTTPError, PanelError):
        log.exception("admin take failed for %s", tg_id)
        return texts.PANEL_ERROR
    return texts.admin_taken(tg_id, username, ok)


@router.callback_query(F.data == "admin")
async def admin(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await show(call, await admin_screen(db), keyboards.admin())


@router.callback_query(F.data == "admin:give")
async def ask_give(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminInput.give)
    await state.update_data(menu_id=call.message.message_id)
    await show(call, texts.ADMIN_GIVE_HELP, keyboards.admin_cancel())


@router.callback_query(F.data == "admin:take")
async def ask_take(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminInput.take)
    await state.update_data(menu_id=call.message.message_id)
    await show(call, texts.ADMIN_TAKE_HELP, keyboards.admin_cancel())


async def answer_in_menu(message: Message, state: FSMContext, bot: Bot, text: str) -> None:
    """Показывает результат в том же окне админки и убирает введённое сообщение."""
    menu_id = (await state.get_data()).get("menu_id")
    await state.clear()
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    if menu_id:
        try:
            await bot.edit_message_text(
                text, chat_id=message.chat.id, message_id=menu_id, reply_markup=keyboards.admin()
            )
            return
        except TelegramBadRequest:
            pass
    await message.answer(text, reply_markup=keyboards.admin())


@router.message(AdminInput.give, F.text)
async def give_input(
    message: Message, state: FSMContext, bot: Bot, db: Database, panel: XuiClient
) -> None:
    await answer_in_menu(message, state, bot, await give(message.text, bot, db, panel))


@router.message(AdminInput.take, F.text)
async def take_input(
    message: Message, state: FSMContext, bot: Bot, db: Database, panel: XuiClient
) -> None:
    await answer_in_menu(message, state, bot, await take(message.text, db, panel))


@router.message(Command("give"))
async def give_command(
    message: Message, command: CommandObject, bot: Bot, db: Database, panel: XuiClient
) -> None:
    await message.answer(await give(command.args or "", bot, db, panel))


@router.message(Command("take"))
async def take_command(
    message: Message, command: CommandObject, db: Database, panel: XuiClient
) -> None:
    await message.answer(await take(command.args or "", db, panel))


@router.message(Command("stats"))
async def stats(message: Message, db: Database) -> None:
    await message.answer(await admin_screen(db), reply_markup=keyboards.admin())


@router.callback_query(F.data == "admin:users")
async def users(call: CallbackQuery, db: Database, panel: XuiClient) -> None:
    try:
        clients = {
            tg_id_from_email(c.get("email", "")): c for c in await panel.list_clients()
        }
    except (httpx.HTTPError, PanelError):
        log.exception("list_clients failed")
        clients = {}
    rows = []
    now = time.time()
    for tg_id, username, _created in await db.recent_users():
        c = clients.get(tg_id)
        if c is None:
            status = "без подписки"
        elif not c.get("enable"):
            status = "выключен"
        elif not c.get("expiryTime"):
            status = "бессрочно"
        elif c["expiryTime"] / 1000 < now:
            status = "истекла"
        else:
            status = f"до {texts.fmt_date(c['expiryTime'] // 1000)}"
        rows.append((tg_id, username, status))
    await show(call, texts.admin_users(rows), keyboards.admin_back())
