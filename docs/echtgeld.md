# Echtgeld starten

Alles ist vorbereitet. Umgeschaltet wird nur von Hand auf dem Pi, nie über ein Update aus dem Repo.

## Einmalig vorbereiten

1. **Euro auf Bitvavo:** Bitvavo führt das Konto in EUR. Mindestens so viel einzahlen, wie der Bot nutzen darf (`available_capital` in `user_data/config.json`, zurzeit 50 EUR). Liegt mehr auf dem Konto, rührt der Bot den Rest nicht an.
2. **API-Schlüssel erstellen:** Bitvavo → Einstellungen → API → Neuer Schlüssel.
   - Rechte: **Ansehen** und **Handeln**. **Auszahlen niemals** anhaken.
   - IP-Beschränkung: die öffentliche IP des Pi eintragen (auf dem Pi: `curl -s ifconfig.me`).
3. **Schlüssel auf dem Pi eintragen**, nie im Chat oder Repo:
   ```bash
   nano ~/trading-bot/.env
   ```
   Zwei Zeilen ergänzen:
   ```
   EXCHANGE_KEY=...
   EXCHANGE_SECRET=...
   ```
4. **Prüfen** (handelt nicht, liest nur den Kontostand):
   ```bash
   cd ~/trading-bot && deploy/live.sh check
   ```
   Erwartet: `OK: Schluessel funktioniert, genug Guthaben.`

## Starten

```bash
cd ~/trading-bot && deploy/live.sh start
```

Das Skript prüft noch einmal Schlüssel und Guthaben und will `JA` als Bestätigung. Danach:

- Der Bot nutzt eine eigene Datenbank (`tradesv3.live.sqlite`). Spielgeld-Trades zählen nicht mit.
- Status und Tagesbericht tragen den Vermerk ECHTGELD.
- Automatische Updates laufen weiter und bleiben im Echtgeld-Modus.
- Läuft gerade ein Trend bei BTC oder ETH, kauft er sofort mit dem ganzen freien Betrag (sind beide im Trend, je die Hälfte).
- Die Weboberfläche (http://tradingpi.local:8080) zeigt dann echtes Geld; Knöpfe wie „Verkaufen“ handeln echt.

## Notbremse

- Telegram `/stopentry`: keine neuen Käufe, offene Positionen laufen weiter.
- Telegram `/forceexit all`: alles sofort verkaufen.
- Auf dem Pi `touch ~/trading-bot/user_data/HALT`: keine neuen Käufe, bis die Datei gelöscht ist.

## Zurück auf Spielgeld

Erst in Telegram `/forceexit all` senden, wenn alles verkauft werden soll. Sonst bleiben die Coins bei Bitvavo liegen. Dann:

```bash
cd ~/trading-bot && deploy/live.sh stop
```
