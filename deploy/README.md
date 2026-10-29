# Развёртывание

Бот работает с панелью [3x-ui](https://github.com/MHSanaei/3x-ui) версии 3 и ходит в её API по Bearer-токену.

## 1. Панель

Если 3x-ui ещё нет:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh)
```

В панели создайте inbound:
- **VLESS Reality** на TCP 443. Для SNI лучше свой домен (Self SNI): чужие популярные SNI вроде www.apple.com у части провайдеров в РФ уже режутся.
- **Hysteria2** на UDP, например 8443, можно второй с obfs salamander.

Запишите их ID: они видны в списке inbound или в адресе при редактировании.

## 2. Доступ для бота

1. В панели: **Настройки → API Tokens → создать**. Токен показывается один раз.
2. Подписка должна быть включена (по умолчанию порт 2096, путь `/sub/`).

## 3. Бот

1. Создайте бота у @BotFather и получите токен.
2. На сервере с панелью:

```bash
git clone https://github.com/noygin/npn && cd npn
cp .env.example .env && nano .env
docker compose up -d --build
```

В `.env`:
- `PANEL_URL` — адрес панели вместе с webBasePath, как в браузере, но без `/panel/...`;
- `PANEL_API_TOKEN` — токен из шага 2;
- `PANEL_INBOUND_IDS` — ID inbound через запятую в скобках, например `[5,2,6]`;
- `PANEL_SUB_URL` — например `https://IP:2096/sub`.

3. Проверьте `/start` в боте и `/stats` от админа. Каждый пользователь бота появится в панели как клиент `tg<telegram id>` на всех указанных inbound.

## 4. Автообновление

Сервер сам забирает ветку `main` с GitHub каждые 2 минуты и, если есть новые коммиты, пересобирает бота. `.env` и база не трогаются. Установка один раз:

```bash
cp /opt/npn/deploy/npn-autoupdate.* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now npn-autoupdate.timer
```

Лог обновлений: `journalctl -u npn-autoupdate -n 50`. Репозиторий должен быть публичным, либо на сервере нужен deploy key с доступом на чтение.
