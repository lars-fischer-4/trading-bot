#!/usr/bin/env bash
# Einmalig mit sudo ausfuehren: sudo ~/trading-bot/deploy/pi-selbstheilung.sh
# - Hardware-Waechter: haengt der Pi (Kernel reagiert nicht mehr), startet er nach 15 s selbst neu
# - Docker, Bot und Update-Timer starten nach jedem Neustart automatisch
# - Systemprotokoll bleibt ueber Neustarts erhalten (begrenzt auf 50 MB, schont die SD-Karte)
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten: sudo $0"; exit 1; }

mkdir -p /etc/systemd/system.conf.d /etc/systemd/journald.conf.d /var/log/journal
cat > /etc/systemd/system.conf.d/watchdog.conf <<'CONF'
[Manager]
RuntimeWatchdogSec=15s
RebootWatchdogSec=2min
CONF
cat > /etc/systemd/journald.conf.d/trading-bot.conf <<'CONF'
[Journal]
Storage=persistent
SystemMaxUse=50M
CONF

systemctl enable docker
cp "$(dirname "$0")/trading-bot-update.service" "$(dirname "$0")/trading-bot-update.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now trading-bot-update.timer
systemctl daemon-reexec
systemctl restart systemd-journald

echo "Fertig. Hardware-Waechter: $(systemctl show -p RuntimeWatchdogUSec --value)"
echo "Stromversorgung: $(vcgencmd get_throttled 2>/dev/null || echo unbekannt) (0x0 = alles gut)"
