#!/usr/bin/env bash
# Holt neuen Code von GitHub und startet den Bot neu, wenn sich etwas geaendert hat.
# Laeuft alle 5 Minuten per systemd-Timer (siehe deploy/README in README.md).
set -euo pipefail

cd "$(dirname "$0")/.."
BOT_DIR=$(pwd)

notify() {
    # Telegram-Nachricht, Fehler beim Senden sind egal
    set +u
    source "$BOT_DIR/.env" 2>/dev/null || true
    if [ -n "${TELEGRAM_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -s -m 10 "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=$1" > /dev/null || true
    fi
    set -u
}

# Weboberflaeche: Zugangsdaten einmalig zufaellig erzeugen (nur in .env auf dem Pi), Bot damit neu
# starten und Adresse + Login privat per Telegram schicken
if [ -f "$BOT_DIR/.env" ] && ! grep -q '^UI_ENABLED=' "$BOT_DIR/.env"; then
    rnd() { python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("p"+"".join(secrets.choice(a) for _ in range(int("'"$1"'"))))'; }
    UI_PW=$(rnd 15)
    {
        echo ""
        echo "# Weboberflaeche (automatisch erzeugt)"
        echo "UI_USER=lars"
        echo "UI_PASSWORD=$UI_PW"
        echo "UI_JWT_SECRET=$(rnd 48)"
        echo "UI_WS_TOKEN=$(rnd 30)"
        echo "UI_ENABLED=true"
    } >> "$BOT_DIR/.env"
    if docker compose up -d --remove-orphans > /dev/null 2>&1; then
        notify "Weboberflaeche ist bereit (nur im Heimnetz):
http://tradingpi.local:8080
Benutzer: lars
Passwort: $UI_PW
(steht auch in ~/trading-bot/.env auf dem Pi)"
    fi
fi

# Waechter: laeuft der Bot nicht oder ist er seit dem letzten Lauf abgestuerzt,
# letzte Log-Zeilen per Telegram schicken und neu starten
STATE=$(docker inspect -f '{{.State.Running}} {{.RestartCount}}' freqtrade 2>/dev/null || echo "missing 0")
RUNNING=${STATE% *}
RESTARTS=${STATE#* }
LAST_RESTARTS=$(cat "$BOT_DIR/.restart_count" 2>/dev/null || echo "$RESTARTS")
echo "$RESTARTS" > "$BOT_DIR/.restart_count"
# Freqtrade schreibt jede Minute eine Heartbeat-Zeile; 10 Minuten ohne Log heisst: haengt
SILENT=false
LOGFILE="$BOT_DIR/user_data/logs/freqtrade.log"
if [ "$RUNNING" = "true" ] && [ -f "$LOGFILE" ] && [ -z "$(find "$LOGFILE" -mmin -10)" ]; then
    SILENT=true
fi
if [ "$RUNNING" != "true" ] || [ "$RESTARTS" -gt "$LAST_RESTARTS" ] || [ "$SILENT" = "true" ]; then
    LOGS=$(docker logs --tail 15 freqtrade 2>&1 | grep -v -i "token\|secret\|key" | cut -c1-200 || true)
    if [ "$SILENT" = "true" ]; then
        docker compose restart > /dev/null 2>&1 || true
    else
        docker compose up -d --remove-orphans > /dev/null 2>&1 || true
    fi
    notify "Bot war gestoppt oder abgestuerzt, Neustart versucht. Letzte Log-Zeilen:
$LOGS"
fi

git fetch -q origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0

# Echtgeld-Sperre: Code, der dry_run abschaltet, wird nur mit Freischaltung auf dem Pi uebernommen
# (prueft alle Konfigurationen, auch die des Daytraders)
NEW_DRY_RUN=True
for CFG in $(git ls-tree --name-only origin/main user_data/ | grep -E '^user_data/config.*\.json$'); do
    VAL=$(git show "origin/main:$CFG" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("dry_run", True))')
    [ "$VAL" != "True" ] && NEW_DRY_RUN=False
done
if [ "$NEW_DRY_RUN" != "True" ] && [ ! -f "$BOT_DIR/LIVE_OK" ]; then
    MSG="Update NICHT eingespielt: Die neue Version schaltet auf ECHTGELD. Zum Freigeben auf dem Pi: touch ~/trading-bot/LIVE_OK"
    # nur einmal pro Version melden
    if [ "$(cat "$BOT_DIR/.blocked_rev" 2>/dev/null)" != "$REMOTE" ]; then
        notify "$MSG"
        echo "$REMOTE" > "$BOT_DIR/.blocked_rev"
    fi
    echo "$MSG"
    exit 0
fi

git merge -q --ff-only origin/main
SUMMARY=$(git log --format='- %s' "$LOCAL..$REMOTE" | head -10)

if docker compose up -d --force-recreate --remove-orphans; then
    notify "Update eingespielt und Bot neu gestartet:
$SUMMARY"
else
    notify "Update geholt, aber Neustart fehlgeschlagen. Bitte pruefen: docker compose logs --tail 50"
    exit 1
fi
