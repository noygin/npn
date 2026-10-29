from aiogram import Router

from bot.handlers import admin, menu, payments


def setup() -> Router:
    router = Router()
    router.include_routers(menu.router, payments.router, admin.router)
    return router
