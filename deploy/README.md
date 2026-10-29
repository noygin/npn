# Развёртывание

## 1. Сервер

Купите VPS (Ubuntu 22.04 или 24.04, от 1 ГБ RAM) в Нидерландах или Финляндии. Хостеры, которые принимают рубли или крипту: Aeza, PQ.Hosting, VDSina; из зарубежных Hetzner и DigitalOcean.

## 2. Marzban

```bash
sudo bash -c "$(curl -sL https://github.com/Gozargah/Marzban-scripts/raw/master/marzban.sh)" @ install
marzban cli admin create --sudo
```

Панель слушает `127.0.0.1:8000`. Наружу её не открывайте, заходите через SSH-туннель:
`ssh -L 8000:127.0.0.1:8000 root@SERVER`, затем http://127.0.0.1:8000/dashboard.

## 3. Reality

Сгенерируйте ключи:

```bash
docker exec marzban-marzban-1 xray x25519   # Private key и Public key
openssl rand -hex 8                          # shortId
```

Скопируйте [xray_config.json](xray_config.json) в `/var/lib/marzban/xray_config.json`, подставьте `PRIVATE_KEY` и `SHORT_ID`, затем `marzban restart`.

Сайт в `dest` и `serverNames` должен открываться из РФ без VPN, поддерживать TLS 1.3 и HTTP/2. Лучше подобрать сайт в той же сети, что и сервер, с помощью [RealiTLScanner](https://github.com/XTLS/RealiTLScanner).

Чтобы ссылки-подписки были полными, в `/opt/marzban/.env` задайте
`XRAY_SUBSCRIPTION_URL_PREFIX=https://ваш-домен` (нужен домен и HTTPS).

## 4. Бот

1. Создайте бота у @BotFather и получите токен.
2. На том же сервере:

```bash
git clone https://github.com/noygin/npn && cd npn
cp .env.example .env && nano .env
docker compose up -d --build
```

3. Проверьте `/start` в боте и `/stats` от админа.
