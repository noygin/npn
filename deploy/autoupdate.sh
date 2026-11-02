#!/usr/bin/env bash
# Проверяет ветку main на GitHub и, если есть новые коммиты, обновляет бота.
# Запускается таймером systemd (npn-autoupdate.timer).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/noygin/npn.git}"
BRANCH="${BRANCH:-main}"
SRC=/opt/npn-src
APP=/opt/npn

# Заявки бота на OpenVPN-профили обрабатываем до проверки GitHub,
# чтобы они не зависели от сети и от наличия обновлений
if [ -f "$APP/deploy/ovpn-helper.sh" ]; then
    bash "$APP/deploy/ovpn-helper.sh" || echo "ovpn helper failed"
fi

if [ ! -d "$SRC/.git" ]; then
    git clone -q --branch "$BRANCH" "$REPO_URL" "$SRC"
    rm -f "$SRC/.deployed"
fi

cd "$SRC"
git fetch -q origin "$BRANCH"
remote=$(git rev-parse "origin/$BRANCH")
deployed=$(cat .deployed 2>/dev/null || true)
[ "$remote" = "$deployed" ] && exit 0

git reset -q --hard "$remote"
# .env и база живут только на сервере, их не трогаем
rsync -a --delete --exclude .git --exclude .env --exclude data/ --exclude .deployed "$SRC/" "$APP/"
cd "$APP"
docker compose up -d --build --remove-orphans
echo "$remote" > "$SRC/.deployed"
echo "deployed $remote"
