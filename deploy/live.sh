#!/usr/bin/env bash
# Echtgeld vorbereiten, starten und stoppen. Auf dem Pi ausfuehren:
#   deploy/live.sh check   Schluessel und Kontostand pruefen, handelt nicht
#   deploy/live.sh start   auf Echtgeld umschalten (fragt nach Bestaetigung)
#   deploy/live.sh stop    zurueck auf Spielgeld
set -euo pipefail
cd "$(dirname "$0")/.."
BOT_DIR=$(pwd)
ENV_FILE="$BOT_DIR/.env"
LIVE_CFG="$BOT_DIR/user_data/config.live.json"
COMPOSE_LINE="COMPOSE_FILE=docker-compose.yml:docker-compose.live.yml"

notify() {
    set +u
    source "$ENV_FILE" 2>/dev/null || true
    if [ -n "${TELEGRAM_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -s -m 10 "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=$1" > /dev/null || true
    fi
    set -u
}

capital() {
    python3 -c 'import json; print(json.load(open("user_data/config.json"))["available_capital"])'
}

check() {
    set +u
    source "$ENV_FILE" 2>/dev/null || true
    set -u
    if [ -z "${EXCHANGE_KEY:-}" ] || [ -z "${EXCHANGE_SECRET:-}" ]; then
        echo "FEHLT: EXCHANGE_KEY und EXCHANGE_SECRET in $ENV_FILE eintragen (siehe docs/echtgeld.md)."
        return 1
    fi
    echo "Pruefe Schluessel bei Bitvavo (liest nur den Kontostand) ..."
    EUR=$(docker compose -f docker-compose.yml run --rm --no-deps -T --entrypoint python freqtrade -c '
import os, ccxt
ex = ccxt.bitvavo({"apiKey": os.environ["FREQTRADE__EXCHANGE__KEY"], "secret": os.environ["FREQTRADE__EXCHANGE__SECRET"]})
print(ex.fetch_balance().get("EUR", {}).get("free") or 0)
' 2>/dev/null | tail -1) || { echo "FEHLER: Bitvavo lehnt den Schluessel ab (falsch, abgelaufen oder IP nicht freigegeben)."; return 1; }
    NEED=$(capital)
    echo "Freies Guthaben: $EUR EUR, der Bot nutzt hoechstens $NEED EUR."
    if python3 -c "import sys; sys.exit(0 if float('$EUR') >= float('$NEED') else 1)"; then
        echo "OK: Schluessel funktioniert, genug Guthaben."
    else
        echo "ZU WENIG: mindestens $NEED EUR auf Bitvavo einzahlen."
        return 1
    fi
}

start() {
    check
    echo
    echo "Der Bot handelt danach mit ECHTEM Geld (hoechstens $(capital) EUR)."
    read -r -p "Zum Starten JA eintippen: " ANSWER
    [ "$ANSWER" = "JA" ] || { echo "Abgebrochen, nichts geaendert."; exit 1; }
    echo '{"dry_run": false}' > "$LIVE_CFG"
    touch "$BOT_DIR/LIVE_OK"
    grep -qx "$COMPOSE_LINE" "$ENV_FILE" || echo "$COMPOSE_LINE" >> "$ENV_FILE"
    docker compose up -d --force-recreate --remove-orphans
    notify "ECHTGELD gestartet: Der Bot handelt jetzt mit hoechstens $(capital) EUR. Notbremse: /stopentry oder deploy/live.sh stop"
    echo "Echtgeld laeuft."
}

stop() {
    echo "Offene Echtgeld-Positionen bleiben bei Bitvavo liegen. Vorher in Telegram /forceexit all senden, wenn alles verkauft werden soll."
    sed -i "\|^$COMPOSE_LINE\$|d" "$ENV_FILE"
    rm -f "$LIVE_CFG" "$BOT_DIR/LIVE_OK"
    docker compose up -d --force-recreate --remove-orphans
    notify "Echtgeld gestoppt, der Bot laeuft wieder mit Spielgeld."
    echo "Zurueck auf Spielgeld."
}

case "${1:-}" in
    check) check ;;
    start) start ;;
    stop) stop ;;
    *) echo "Benutzung: deploy/live.sh check|start|stop"; exit 1 ;;
esac
