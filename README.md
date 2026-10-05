# Trading-Bot auf dem Raspberry Pi 5

Krypto-Bot auf Basis von [Freqtrade](https://www.freqtrade.io), läuft in Docker auf dem Pi und meldet sich per Telegram.

- **Strategie:** `TrendFollowV1`, Trendfolge auf BTC/EUR und ETH/EUR mit 4-Stunden-Kerzen
- **Börse:** Bitvavo (wechselbar in `user_data/config.json`)
- **Modus:** Spielgeld (`"dry_run": true`) mit 50 EUR Startkapital

## Risikoregeln

| Regel | Wert | Wo |
| --- | --- | --- |
| Einsatz pro Trade | 10 EUR (20 % von 50) | `config.json`: `stake_amount` |
| Gleichzeitige Positionen | max. 2 | `config.json`: `max_open_trades` |
| Kapital, das der Bot nutzen darf | 50 EUR, auch wenn mehr auf dem Konto liegt | `config.json`: `available_capital` |
| Stop-Loss | 8 % pro Position, ab 8 % Gewinn nachgezogen (4 % Abstand) | Strategie |
| Tagesverlust-Limit | mehr als 3 % Verlust in 24 h, dann 24 h keine Käufe | Strategie, `MaxDrawdown` |
| Pech-Serie | 2 Stop-Losses in 2 Tagen, dann 2 Tage Pause | Strategie, `StoplossGuard` |
| Gesamtverlust-Limit | ab 15 % Verlust: Datei `user_data/HALT`, keine Käufe mehr bis zur Freigabe | Strategie |
| Termine | 12 h vor bis 2 h nach US-Zinsentscheid und US-Inflationszahlen keine Käufe | `market_filter.json` |
| Marktstimmung | bei Fear & Greed ab 85 („extreme Gier“) keine Käufe | `market_filter.json` |

News- und Terminfilter gelten nur im Spielgeld- und Echtbetrieb. Im Backtest wird die reine Strategie getestet.

## Telegram

Automatisch: jeder Kauf und Verkauf, ausgelöste Schutzregeln, Fehler, wichtige Schlagzeilen (stündlich geprüft) und um 21:00 ein Tagesbericht.

| Befehl | Wirkung |
| --- | --- |
| `/status` | offene Positionen |
| `/profit` | Gewinn/Verlust gesamt |
| `/daily` | Gewinn/Verlust pro Tag |
| `/balance` | Kontostand |
| `/stopentry` | Pause: keine neuen Käufe, offene Positionen laufen weiter |
| `/start` | wieder normal handeln |
| `/forceexit all` | **Notbremse:** alle Positionen sofort verkaufen |
| `/stop` | Bot anhalten |
| `/help` | alle Befehle |

## Einrichtung auf dem Pi (einmalig)

Voraussetzung: Docker ist installiert, und `~/trading-bot/.env` enthält `TELEGRAM_TOKEN` und `TELEGRAM_CHAT_ID`.

1. Schlüssel nur für dieses Repo erzeugen (Lesezugriff):

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/github_trading_bot -N "" -C tradingpi
   printf "Host github.com\n  IdentityFile ~/.ssh/github_trading_bot\n" >> ~/.ssh/config
   cat ~/.ssh/github_trading_bot.pub
   ```

   Die ausgegebene Zeile auf GitHub unter **Repo → Settings → Deploy keys → Add deploy key** einfügen (ohne „Allow write access“).

2. Code holen (die vorhandene `.env` bleibt erhalten):

   ```bash
   cd ~/trading-bot
   git init -b main
   git remote add origin git@github.com:lars-fischer-4/trading-bot.git
   git pull origin main
   ```

3. Kursdaten laden und Backtest laufen lassen:

   ```bash
   docker compose run --rm freqtrade download-data --config /freqtrade/user_data/config.json -t 4h --timerange 20230101-
   docker compose run --rm freqtrade backtesting --config /freqtrade/user_data/config.json --strategy TrendFollowV1 --timerange 20230701-
   ```

4. Bot im Spielgeld-Modus starten:

   ```bash
   docker compose up -d
   docker compose logs -f   # Ausgabe ansehen, beenden mit Ctrl+C (Bot läuft weiter)
   ```

5. Automatische Updates einschalten (der Pi holt alle 5 Minuten neuen Code von GitHub, startet den Bot neu und meldet es per Telegram):

   ```bash
   sudo cp ~/trading-bot/deploy/trading-bot-update.service ~/trading-bot/deploy/trading-bot-update.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now trading-bot-update.timer
   ```

   Sicherung: Eine Version, die auf Echtgeld umschaltet (`"dry_run": false`), wird nur eingespielt, wenn auf dem Pi die Datei `~/trading-bot/LIVE_OK` existiert. Sonst kommt nur eine Warnung per Telegram.

## Alltag


```bash
cd ~/trading-bot
deploy/auto-update.sh                                # Update sofort statt in 5 Minuten
journalctl -u trading-bot-update --since today       # Update-Protokoll
docker compose restart                               # neu starten
docker compose down                                  # Bot stoppen
rm user_data/HALT                                    # nach Gesamtverlust-Stopp wieder freigeben
```

Die Termine in `user_data/market_filter.json` reichen bis Ende 2027 (US-Inflation nur bis Dezember 2026, weitere Daten veröffentlicht die BLS laufend) und müssen ergänzt werden.

## Echtgeld (erst nach Freigabe)

Erst wenn Backtest und mehrere Wochen Spielgeld überzeugen:

1. Bei der Börse einen API-Schlüssel **nur mit Lese- und Handelsrecht, ohne Auszahlung** erstellen, wenn möglich auf die eigene IP beschränkt.
2. `EXCHANGE_KEY` und `EXCHANGE_SECRET` in `~/trading-bot/.env` auf dem Pi eintragen (nie ins Repo).
3. In `user_data/config.json` `"dry_run": false` setzen und in `docker-compose.yml` die Datenbank auf `tradesv3.sqlite` ändern.

## Entwicklung

```bash
pip install freqtrade pytest
python -m pytest -q tests
```

Die Tests prüfen Signale, Risikoregeln, Tagesbericht und den News-/Terminfilter. GitHub führt sie bei jedem Push automatisch aus.
