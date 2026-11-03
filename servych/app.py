"""Сайт Сервыча: главная, вход через Telegram, личный кабинет и админка."""

import asyncio
import io
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import httpx
import segno
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bot.panel import PanelError, XuiClient
from servych import payments
from servych.config import Settings
from servych.store import Store

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
COOKIE = "servych"
NAME_RE = re.compile(r"\s+")

APPS = {
    "iphone": {
        "title": "iPhone",
        "app": "Happ",
        "store": "https://apps.apple.com/app/happ-proxy-utility/id6504287215",
        "store_title": "Скачать в App Store",
        "scheme": "happ://add/",
    },
    "android": {
        "title": "Android",
        "app": "Happ",
        "store": "https://play.google.com/store/apps/details?id=com.happproxy",
        "store_title": "Скачать в Google Play",
        "scheme": "happ://add/",
    },
    "computer": {
        "title": "Компьютер",
        "app": "Hiddify",
        "store": "https://github.com/hiddify/hiddify-app/releases/latest",
        "store_title": "Скачать Hiddify",
        "scheme": "hiddify://import/",
    },
}

MESSAGES = {
    "added": "Готово! Теперь отправьте человеку приглашение.",
    "removed": "Человек убран. Его доступ больше не работает.",
    "ip": "Заявка принята. Мы сменим адрес сервера, обычно в течение пары часов. "
          "Приложения подхватят новый адрес сами.",
    "ip_already": "Заявка на смену адреса уже есть, мы над ней работаем.",
    "paid": "Оплата прошла, спасибо!",
    "panel": "Сервер сейчас не отвечает. Попробуйте через пару минут "
             "или нажмите «Не работает» внизу страницы.",
    "name": "Напишите имя, например «Мама» или «Ноутбук».",
    "no_server": "Сначала нужен сервер.",
}


def default_panel_factory(server: dict) -> XuiClient:
    # Панели на серверах клиентов обычно с самоподписанным сертификатом
    return XuiClient(
        server["panel_url"],
        server["api_token"],
        server["inbound_ids"],
        server["sub_url"],
        transport=httpx.AsyncHTTPTransport(verify=False),
    )


def clean_name(name: str) -> str:
    return NAME_RE.sub(" ", name).strip()[:40]


def format_date(ts: int | None) -> str:
    if not ts:
        return "—"
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
    t = time.localtime(ts)
    return f"{t.tm_mday} {months[t.tm_mon - 1]} {t.tm_year}"


def format_traffic(size: int | None) -> str:
    if not size:
        return "ещё не пользовались"
    gb = size / 1024**3
    if gb >= 1:
        return f"{gb:.1f} ГБ".replace(".", ",")
    return f"{max(1, round(size / 1024**2))} МБ"


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def create_app(
    settings: Settings | None = None,
    panel_factory: Callable[[dict], XuiClient] = default_panel_factory,
    payment_transport: httpx.AsyncBaseTransport | None = None,
    telegram_transport: httpx.AsyncBaseTransport | None = None,
    sub_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or Settings()
    store = Store(settings.servych_db_path)
    methods = payments.available_methods(settings, payment_transport)
    telegram = httpx.AsyncClient(
        base_url=f"https://api.telegram.org/bot{settings.bot_token}", timeout=10,
        transport=telegram_transport,
    )
    sub_http = httpx.AsyncClient(
        timeout=15, transport=sub_transport or httpx.AsyncHTTPTransport(verify=False)
    )
    state = {"bot_username": settings.servych_bot_username.lstrip("@")}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await store.init()
        if not state["bot_username"] and settings.bot_token:
            try:
                r = await telegram.get("/getMe")
                state["bot_username"] = r.json()["result"]["username"]
            except (httpx.HTTPError, KeyError, ValueError):
                log.exception("getMe failed")
        yield
        for method in methods.values():
            await method.close()
        await telegram.aclose()
        await sub_http.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["date"] = format_date
    templates.env.filters["traffic"] = format_traffic
    templates.env.globals.update(
        plans=payments.PLANS, price=settings.servych_price_rub, support=settings.support_username,
        plural=plural,
    )

    def render(request: Request, name: str, user: dict | None = None, **ctx) -> HTMLResponse:
        message = MESSAGES.get(request.query_params.get("m", ""))
        return templates.TemplateResponse(
            request, name,
            {"user": user, "message": message,
             "is_admin": bool(user and user["tg_id"] in settings.admin_ids), **ctx},
        )

    def base_url(request: Request) -> str:
        return (settings.servych_public_url or str(request.base_url)).rstrip("/")

    def go(path: str, message: str | None = None) -> RedirectResponse:
        return RedirectResponse(f"{path}?m={message}" if message else path, status_code=303)

    async def current_user(request: Request) -> dict | None:
        token = request.cookies.get(COOKIE)
        return await store.session_user(token) if token else None

    async def require_user(request: Request) -> dict:
        user = await current_user(request)
        if user is None:
            raise HTTPException(303, headers={"Location": "/login"})
        return user

    async def require_admin(user: dict = Depends(require_user)) -> dict:
        if user["tg_id"] not in settings.admin_ids:
            raise HTTPException(404)
        return user

    async def notify(tg_id: int, text: str, button: tuple[str, str] | None = None) -> None:
        """Пишет клиенту в Telegram от имени бота. Ошибки не мешают работе сайта."""
        if not settings.bot_token:
            return
        payload = {"chat_id": tg_id, "text": text}
        if button and button[1].startswith("https://"):
            payload["reply_markup"] = {"inline_keyboard": [[{"text": button[0], "url": button[1]}]]}
        try:
            await telegram.post("/sendMessage", json=payload)
        except httpx.HTTPError:
            log.exception("notify failed for %s", tg_id)

    def set_session(response: Response, token: str) -> Response:
        response.set_cookie(
            COOKIE, token, max_age=90 * 86400, httponly=True, samesite="lax",
            secure=settings.servych_secure_cookies,
        )
        return response

    def add_link(request: Request, server: dict, member: dict) -> str:
        """Ссылка, которую человек добавляет в приложение.

        Если у сайта есть HTTPS, отдаём ссылку через сайт: после смены IP сервера
        приложения сами получат новый адрес. Без HTTPS отдаём прямую ссылку сервера,
        чтобы настройки не шли по сети открытым текстом.
        """
        if settings.servych_public_url.startswith("https://"):
            return f"{base_url(request)}/s/{member['share_token']}"
        return f"{server['sub_url'].rstrip('/')}/{member['sub_id']}"

    # Публичные страницы

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return render(request, "index.html", await current_user(request))

    @app.get("/login", response_class=HTMLResponse)
    async def login(request: Request):
        if await current_user(request):
            return go("/cabinet")
        code = await store.new_login_code()
        bot = state["bot_username"]
        link = f"https://t.me/{bot}?start=login_{code}" if bot else ""
        return render(request, "login.html", code=code, link=link)

    @app.get("/login/check/{code}")
    async def login_check(code: str):
        tg_id = await store.login_owner(code)
        if tg_id is None:
            return JSONResponse({"ok": False})
        return set_session(JSONResponse({"ok": True}), await store.create_session(tg_id))

    @app.get("/login/finish/{code}")
    async def login_finish(code: str):
        tg_id = await store.login_owner(code)
        if tg_id is None:
            return go("/login")
        return set_session(go("/cabinet"), await store.create_session(tg_id))

    @app.post("/logout")
    async def logout(request: Request):
        token = request.cookies.get(COOKIE)
        if token:
            await store.delete_session(token)
        response = go("/")
        response.delete_cookie(COOKIE)
        return response

    @app.get("/c/{token}", response_class=HTMLResponse)
    async def invite(request: Request, token: str):
        member = await store.member_by_token(token)
        if member is None:
            raise HTTPException(404)
        server = await store.get_server(member["server_id"])
        return render(
            request, "invite.html", await current_user(request),
            member=member, link=add_link(request, server, member), apps=APPS, quote=quote,
        )

    @app.get("/s/{token}")
    async def subscription(token: str):
        """Отдаёт подписку с сервера клиента. Нужна, чтобы ссылка не менялась при смене IP."""
        member = await store.member_by_token(token)
        if member is None:
            raise HTTPException(404)
        server = await store.get_server(member["server_id"])
        try:
            r = await sub_http.get(f"{server['sub_url'].rstrip('/')}/{member['sub_id']}")
            r.raise_for_status()
        except httpx.HTTPError:
            log.exception("subscription fetch failed for server %s", server["id"])
            raise HTTPException(502)
        headers = {
            k: v for k, v in r.headers.items()
            if k.lower() in ("subscription-userinfo", "profile-update-interval", "profile-title")
        }
        return Response(r.content, media_type="text/plain; charset=utf-8", headers=headers)

    @app.get("/qr")
    async def qr(data: str):
        if len(data) > 1000:
            raise HTTPException(400)
        buf = io.BytesIO()
        segno.make(data, error="m").save(buf, kind="svg", scale=6, border=2, dark="#1f1a17")
        return Response(buf.getvalue(), media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})

    # Личный кабинет

    @app.get("/cabinet", response_class=HTMLResponse)
    async def cabinet(request: Request, user: dict = Depends(require_user)):
        server = await store.server_of(user["tg_id"])
        if server is None or server["status"] != "active":
            return render(request, "cabinet_empty.html", user, server=server)
        members = await store.members(server["id"])
        online = False
        panel = panel_factory(server)
        try:
            subs = await asyncio.gather(
                *(panel.get_subscription(m["email"]) for m in members), return_exceptions=True
            )
            if not members:
                await panel.list_clients()
            online = not members or any(not isinstance(s, Exception) for s in subs)
        except (httpx.HTTPError, PanelError):
            subs = [None] * len(members)
        finally:
            await panel.close()
        for member, sub in zip(members, subs):
            member["traffic"] = None if isinstance(sub, Exception) or sub is None else sub.used_traffic
        unpaid = server["paid_until"] is not None and server["paid_until"] < time.time()
        return render(
            request, "cabinet.html", user,
            server=server, members=members, online=online, unpaid=unpaid,
            ip_request=await store.open_request(user["tg_id"], "change_ip"),
        )

    @app.post("/order")
    async def order(user: dict = Depends(require_user)):
        await store.order_server(user["tg_id"])
        return go("/pay")

    @app.post("/people")
    async def add_person(name: str = Form(""), user: dict = Depends(require_user)):
        server = await store.server_of(user["tg_id"])
        if server is None or server["status"] != "active":
            return go("/cabinet", "no_server")
        name = clean_name(name)
        if not name:
            return go("/cabinet", "name")
        email = f"s{server['id']}-{secrets.token_hex(4)}"
        panel = panel_factory(server)
        try:
            sub = await panel.extend(email, None, tg_id=user["tg_id"])
        except (httpx.HTTPError, PanelError):
            log.exception("add member failed on server %s", server["id"])
            return go("/cabinet", "panel")
        finally:
            await panel.close()
        member = await store.add_member(server["id"], name, email, sub.url.rsplit("/", 1)[-1])
        return go(f"/people/{member['id']}", "added")

    async def own_member(member_id: int, user: dict) -> tuple[dict, dict]:
        member = await store.get_member(member_id)
        server = await store.server_of(user["tg_id"])
        if member is None or member["removed"] or server is None or member["server_id"] != server["id"]:
            raise HTTPException(404)
        return member, server

    @app.get("/people/{member_id}", response_class=HTMLResponse)
    async def person(request: Request, member_id: int, user: dict = Depends(require_user)):
        member, server = await own_member(member_id, user)
        invite_url = f"{base_url(request)}/c/{member['share_token']}"
        return render(request, "person.html", user, member=member, invite_url=invite_url, quote=quote)

    @app.post("/people/{member_id}/remove")
    async def remove_person(member_id: int, user: dict = Depends(require_user)):
        member, server = await own_member(member_id, user)
        panel = panel_factory(server)
        try:
            await panel.disable(member["email"])
        except (httpx.HTTPError, PanelError):
            log.exception("disable member failed on server %s", server["id"])
            return go("/cabinet", "panel")
        finally:
            await panel.close()
        await store.remove_member(member_id)
        return go("/cabinet", "removed")

    @app.post("/change-ip")
    async def change_ip(user: dict = Depends(require_user)):
        server = await store.server_of(user["tg_id"])
        if server is None:
            return go("/cabinet", "no_server")
        created = await store.add_request(user["tg_id"], server["id"], "change_ip")
        return go("/cabinet", "ip" if created else "ip_already")

    # Оплата

    @app.get("/pay", response_class=HTMLResponse)
    async def pay_page(request: Request, user: dict = Depends(require_user)):
        server = await store.server_of(user["tg_id"])
        if server is None:
            return go("/cabinet")
        return render(request, "pay.html", user, server=server, methods=methods)

    @app.post("/pay")
    async def pay(
        request: Request, months: int = Form(1), method: str = Form("support"),
        user: dict = Depends(require_user),
    ):
        server = await store.server_of(user["tg_id"])
        plan = payments.PLANS.get(months)
        if server is None or plan is None or (method != "support" and method not in methods):
            return go("/pay")
        amount = plan.price(settings.servych_price_rub)
        payment_id = await store.add_payment(user["tg_id"], server["id"], months, amount, method)
        if method == "support":
            return go(f"/pay/{payment_id}")
        provider = methods[method]
        try:
            invoice = await provider.create(
                payment_id, amount, f"Сервыч: свой сервер на {plan.title}",
                f"{base_url(request)}/pay/{payment_id}",
            )
        except (httpx.HTTPError, payments.PaymentError):
            log.exception("invoice failed")
            return render(request, "pay.html", user, server=server, methods=methods,
                          error="Не получилось создать счёт. Попробуйте другой способ или чуть позже.")
        await store.set_payment_link(payment_id, invoice.external_id, invoice.pay_url)
        return RedirectResponse(invoice.pay_url, status_code=303)

    @app.get("/pay/{payment_id}", response_class=HTMLResponse)
    async def payment_status(request: Request, payment_id: int, user: dict = Depends(require_user)):
        payment = await store.get_payment(payment_id)
        if payment is None or payment["tg_id"] != user["tg_id"]:
            raise HTTPException(404)
        provider = methods.get(payment["method"])
        if payment["status"] == "pending" and provider and payment["external_id"]:
            try:
                if await provider.is_paid(payment["external_id"]):
                    await store.mark_paid(payment_id)
                    payment = await store.get_payment(payment_id)
            except (httpx.HTTPError, payments.PaymentError):
                log.exception("payment check failed")
        return render(request, "payment.html", user, payment=payment,
                      plan=payments.PLANS.get(payment["months"]))

    # Админка

    @app.get("/admin", response_class=HTMLResponse)
    async def admin(request: Request, user: dict = Depends(require_admin)):
        return render(
            request, "admin.html", user,
            requests=await store.open_requests(), servers=await store.list_servers(),
            payments_list=await store.recent_payments(),
        )

    @app.post("/admin/servers/{server_id}")
    async def admin_setup(
        request: Request, server_id: int,
        title: str = Form(""), panel_url: str = Form(...), api_token: str = Form(""),
        inbound_ids: str = Form(...), sub_url: str = Form(...),
        user: dict = Depends(require_admin),
    ):
        server = await store.get_server(server_id)
        if server is None:
            raise HTTPException(404)
        ids = [int(x) for x in re.findall(r"\d+", inbound_ids)]
        was_active = server["status"] == "active"
        await store.setup_server(server_id, title.strip(), panel_url.strip(), api_token.strip(),
                                 ids, sub_url.strip())
        await store.close_requests(server_id, "new_server")
        cabinet_url = f"{base_url(request)}/cabinet"
        if not was_active:
            await notify(server["owner_id"],
                         "Ваш сервер Сервыч готов! Откройте личный кабинет и добавьте близких.",
                         ("Открыть кабинет", cabinet_url))
        elif server["sub_url"] != sub_url.strip():
            await store.close_requests(server_id, "change_ip")
            await notify(server["owner_id"],
                         "Мы сменили адрес вашего сервера. Если приложение не подключается, "
                         "нажмите в нём «Обновить» или откройте приглашение заново.",
                         ("Открыть кабинет", cabinet_url))
        return go("/admin")

    @app.post("/admin/servers/{server_id}/extend")
    async def admin_extend(server_id: int, days: int = Form(30), user: dict = Depends(require_admin)):
        if await store.get_server(server_id) is None:
            raise HTTPException(404)
        await store.extend_paid(server_id, days)
        return go("/admin")

    @app.post("/admin/requests/{request_id}/done")
    async def admin_request_done(request_id: int, user: dict = Depends(require_admin)):
        await store.close_request(request_id)
        return go("/admin")

    @app.post("/admin/payments/{payment_id}/paid")
    async def admin_payment_paid(payment_id: int, user: dict = Depends(require_admin)):
        await store.mark_paid(payment_id)
        return go("/admin")

    return app
