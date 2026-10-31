#!/usr/bin/env bash
# Выпускает OpenVPN-профили AntiZapret по заявкам бота.
# Бот кладёт заявку в /opt/npn/data/ovpn/requests/<имя>.req (строка «<имя> <дней>»),
# скрипт создаёт клиента через /root/antizapret/client.sh с сертификатом на нужный срок
# и складывает .ovpn в /opt/npn/data/ovpn/done/<имя>/ вместе с файлом status.
# Запускается из autoupdate.sh от root на хосте, то есть раз в 2 минуты.
set -uo pipefail

DIR="${OVPN_DIR:-/opt/npn/data/ovpn}"
AZ="${AZ_DIR:-/root/antizapret}"
REQ="$DIR/requests"
DONE="$DIR/done"

shopt -s nullglob
reqs=("$REQ"/*.req)
[ ${#reqs[@]} -eq 0 ] && exit 0
mkdir -p "$DONE"

diagnose() {
    echo "--- /root/antizapret:"
    ls -la "$AZ" 2>&1 | head -40
    echo "--- client.sh / easyrsa:"
    find /root /etc/openvpn /opt -maxdepth 4 \( -name client.sh -o -name easyrsa \) 2>/dev/null | head -20
    echo "--- openvpn units:"
    systemctl list-units --all --no-pager 2>/dev/null | grep -iE 'openvpn|antizapret' | head -20
    echo "--- containers:"
    docker ps --format '{{.Names}} {{.Image}}' 2>/dev/null | head -20
    command -v lxc >/dev/null && lxc list 2>/dev/null | head -20
}

for req in "${reqs[@]}"; do
    read -r name days _ < "$req" || true
    rm -f "$req"
    if ! [[ "$name" =~ ^[a-zA-Z0-9_-]{1,32}$ ]] || ! [[ "$days" =~ ^[0-9]+$ ]] \
        || [ "$days" -lt 1 ] || [ "$days" -gt 3650 ]; then
        continue
    fi
    tmp="$DONE/.$name.tmp"
    rm -rf "$tmp" "$DONE/$name"
    mkdir -p "$tmp"
    if [ ! -x "$AZ/client.sh" ] && [ ! -f "$AZ/client.sh" ]; then
        { echo "error"; echo "Не нашёл $AZ/client.sh"; diagnose; } > "$tmp/status"
    elif ! out=$(cd "$AZ" && timeout 300 bash ./client.sh 1 "$name" "$days" </dev/null 2>&1); then
        { echo "error"; echo "client.sh завершился с ошибкой:"; echo "$out" | tail -30; } > "$tmp/status"
    else
        base="$AZ/client/openvpn"
        found=0
        # Общие профили (UDP с запасным TCP), а если их нет, то все, что есть
        for f in "$base"/antizapret/antizapret-"$name"-*.ovpn "$base"/vpn/vpn-"$name"-*.ovpn; do
            cp "$f" "$tmp/" && found=1
        done
        if [ "$found" -eq 0 ]; then
            for f in "$base"/*/*"$name"*.ovpn; do
                cp "$f" "$tmp/" && found=1
            done
        fi
        if [ "$found" -eq 1 ]; then
            echo "ok" > "$tmp/status"
        else
            { echo "error"; echo "client.sh отработал, но .ovpn не нашлись:"; echo "$out" | tail -20; diagnose; } > "$tmp/status"
        fi
    fi
    mv "$tmp" "$DONE/$name"
    echo "ovpn: $name $days -> $(head -1 "$DONE/$name/status")"
done
