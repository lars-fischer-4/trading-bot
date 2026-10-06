# Trading-Bot auf dem Raspberry Pi 5

Krypto-Bot auf Basis von [Freqtrade](https://www.freqtrade.io), läuft in Docker auf dem Pi und meldet sich per Telegram.

- **Strategie:** `ComboV1`, ein Bot für alles: Trendfolge auf BTC und ETH (Kauf über dem 50-Tage-Durchschnitt) und schnelle Abprall-Käufe nach Einbrüchen von mehr als 7 % in einer Stunde auf BTC, ETH, SOL und XRP. Beobachtet die Kurse alle paar Sekunden.
- **Börse:** Bitvavo (wechselbar in `user_data/config.json`)
- **Modus:** Spielgeld (`"dry_run": true`) mit 50 EUR Startkapital

## Backtest

Bitvavo-Kurse, 0.25 % Gebühr, 10 EUR pro Trade, Schutzregeln aktiv (Gewinn in % der 50 EUR):

| Zeitraum | ComboV1 | Markt (BTC, ETH, SOL, XRP) |
| --- | --- | --- |
| 20.01.2025 bis 31.12.2025 | +18 % | −36 % |
| 01.01.2026 bis 05.10.2026 | +16 % | −3 % |
| gesamt | +35 %, grösster Rückgang 7 % | −38 % |

51 Trades in 20 Monaten: 18 Trend-Trades (+6.8 % im Schnitt) und 33 Abprall-Käufe (+1.6 % im Schnitt). Im Ergebnis für 2026 stecken 16 % aus zwei Trend-Positionen, die am Ende des Tests noch offen waren. Kurze Rücksetzer-Käufe, Scalping und kleine Coins verlieren nach Gebühren und sind deshalb nicht drin ([docs/daytrading-research.md](docs/daytrading-research.md)).

## Risikoregeln

| Regel | Wert | Wo |
| --- | --- | --- |
| Einsatz pro Trade | 10 EUR (20 % von 50) | `config.json`: `stake_amount` |
| Gleichzeitige Positionen | max. 4 | `config.json`: `max_open_trades` |
| Kapital, das der Bot nutzen darf | 50 EUR, auch wenn mehr auf dem Konto liegt | `config.json`: `available_capital` |
| Stop-Loss | 8 % pro Position, fest ab Einstieg | Strategie |
| Tagesverlust-Limit | mehr als 3 % Verlust in 24 h, dann 24 h keine Käufe | Strategie, `MaxDrawdown` |
| Pech-Serie | 2 Stop-Losses in 2 Tagen, dann 2 Tage Pause | Strategie, `StoplossGuard` |
| Gesamtverlust-Limit | ab 15 % Verlust: Datei `user_data/HALT`, keine Käufe mehr bis zur Freigabe | Strategie |
| Termine | 12 h vor bis 2 h nach US-Zinsentscheid und US-Inflationszahlen keine Käufe | `market_filter.json` |
| Marktstimmung | bei Fear & Greed ab 85 („extreme Gier“) keine Käufe | `market_filter.json` |

News- und Terminfilter gelten nur im Spielgeld- und Echtbetrieb. Im Backtest wird die reine Strategie getestet.

## Telegram

Automatisch:

- jeder ausgeführte Kauf und Verkauf
- alle 30 Minuten ein kurzer Status: Kontostand, Gewinn heute, offene Positionen
- um 21:00 ein Tagesbericht: Kontostand, Gewinn heute, Woche, Monat, Quartal und gesamt, offene Positionen, Marktstimmung, nächster Wirtschaftstermin
- ausgelöste Schutzregeln, Fehler und wichtige Schlagzeilen (stündlich geprüft)

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
   docker compose run --rm freqtrade download-data --config /freqtrade/user_data/config.json -t 5m 4h --timerange 20250101-
   docker compose run --rm freqtrade backtesting --config /freqtrade/user_data/config.json --strategy ComboV1 --timerange 20250120-
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
