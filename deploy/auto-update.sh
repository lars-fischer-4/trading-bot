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
