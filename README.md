# Trading-Bot auf dem Raspberry Pi 5

Krypto-Bot auf Basis von [Freqtrade](https://www.freqtrade.io), läuft in Docker auf dem Pi und meldet sich per Telegram.

- **Strategie:** `ComboV1`, ein Bot für alles: Trendfolge auf BTC und ETH (investiert, solange der Kurs über dem 50-Tage-Durchschnitt liegt, je 50 % des Kontos) und schnelle Abprall-Käufe nach Einbrüchen von mehr als 7 % in einer Stunde (je 25 % des Kontos) auf den 10 umsatzstärksten Coins (BTC, ETH, XRP, SOL, ADA, SUI, DOGE, LINK, FET, TAO). Beobachtet die Kurse alle paar Sekunden.
- **Börse:** Bitvavo (wechselbar in `user_data/config.json`)
- **Modus:** Spielgeld (`"dry_run": true`) mit 50 EUR Startkapital

## Backtest

Bitvavo-Kurse, 0.25 % Gebühr, Schutzregeln aktiv, Kontostand inklusive offener Positionen, Start mit 50 EUR:

| Zeitraum | ComboV1 jetzt | vorher (10 EUR fest, Trend nur beim Beginn) | Markt (10 Coins) |
| --- | --- | --- | --- |
| 20.01.2025 bis 31.12.2025 | +80 % | +35 % | −55 % |
| 01.01.2026 bis 05.10.2026 | +41 % | +16 % | +5 % |
| gesamt | 50 → 127 EUR, grösster Rückgang 17 % | +51 %, 8 % | −54 % |

Über alle 30-Tage-Zeiträume: im Schnitt +5 %, in 24 % der Zeiträume +10 % oder mehr, in 36 % im Minus, schlechtester −14 %. Die letzten 30 Tage: 50 → 56 EUR.

Rund 100 Trades in 20 Monaten. Der Einsatz wächst mit dem Kontostand mit. Der Grossteil des Gewinns kommt aus wenigen langen Trendphasen bei BTC und ETH; in Seitwärtsphasen verliert der Bot leicht.

Mehr Coins bringen nicht mehr Gewinn: Mit den 20 grössten Coins kam der Test auf +6 %, mit 40 Coins auf −37 %. Kleine Coins fallen nach einem Einbruch oft weiter. Die Coin-Liste ist nach dem heutigen Umsatz gewählt, das Ergebnis ist deshalb eher etwas zu gut. Kurze Rücksetzer-Käufe und Scalping verlieren nach Gebühren ([docs/daytrading-research.md](docs/daytrading-research.md)).

## Risikoregeln

| Regel | Wert | Wo |
| --- | --- | --- |
| Einsatz pro Trade | Trend 50 %, Abprall-Kauf 25 % des aktuellen Kontostands | Strategie: `trend_stake`, `crash_stake` |
| Gleichzeitige Positionen | max. 4 | `config.json`: `max_open_trades` |
| Kapital, das der Bot nutzen darf | 50 EUR, auch wenn mehr auf dem Konto liegt | `config.json`: `available_capital` |
| Stop-Loss | 8 % pro Position, fest ab Einstieg (bei 50 % Einsatz also 4 % des Kontos) | Strategie |
| Tagesverlust-Limit | mehr als 3 % Verlust in 24 h, dann 24 h keine Käufe | Strategie, `MaxDrawdown` |
| Pech-Serie | 2 Stop-Losses in 2 Tagen, dann 2 Tage Pause | Strategie, `StoplossGuard` |
| Gesamtverlust-Limit | ab 15 % Verlust: Datei `user_data/HALT`, keine Käufe mehr bis zur Freigabe | Strategie |
| Termine | 12 h vor bis 2 h nach US-Zinsentscheid und US-Inflationszahlen keine Käufe | `market_filter.json` |
| Marktstimmung | bei Fear & Greed ab 85 („extreme Gier“) keine Käufe | `market_filter.json` |

News- und Terminfilter gelten nur im Spielgeld- und Echtbetrieb. Im Backtest wird die reine Strategie getestet.

## Telegram

Automatisch:

- jeder ausgeführte Kauf und Verkauf
- alle 10 Minuten ein kurzer Status: Kontostand, Gewinn heute, offene Positionen
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
   docker compose run --rm freqtrade download-data --config /freqtrade/user_data/config.json -t 5m 4h --timerange 20241101-
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
