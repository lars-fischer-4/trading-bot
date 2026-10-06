# Daytrading-Test: Ergebnisse (Oktober 2026)

Frage: Gibt es eine Daytrading-Strategie, die auf Bitvavo nach Gebühren verlässlich Gewinn bringt und dabei viel handelt?

**Kurz:** Nein, nicht mit den getesteten Ansätzen. Jede Variante, die mehrmals pro Tag handelt, verliert nach Gebühren. Die wenigen Varianten im Plus handeln seltener als einmal in fünf Tagen, und ihr Gewinn hängt an einzelnen Crash-Tagen.

## Daten

- Bitvavo-Kurse der 130 umsatzstärksten Coins (EUR und USDC), 5-Minuten- und 1-Stunden-Kerzen, Januar 2025 bis Oktober 2026. Geladen über GitHub Actions (`.github/workflows/research-data.yml`, Branch `data-files`).
- Für 96 Coins liegt die volle 5-Minuten-Historie vor.
- Gebühren pro Kauf oder Verkauf: 0.25 % (Taker), 0.15 % (Maker, Limit-Order). Ein Trade kostet also 0.3 bis 0.5 %.
- Entwicklung mit 2025, Prüfung mit 2026. Zusätzlich gerechnet: Ergebnis ohne die 5 besten Tage, damit einzelne Crash-Tage nichts vortäuschen.

## Was getestet wurde

| Ansatz | Varianten | Trades pro Tag (alle Coins) | Ergebnis pro Trade nach Gebühren |
| --- | --- | --- | --- |
| RSI-Rücksetzer im Aufwärtstrend | 72 | 1 bis 24 | −0.2 bis −1.2 % |
| Bollinger-Band-Abpraller | 32 | 4 bis 49 | −0.4 bis −0.5 % |
| Kurzfristiger RSI(3)-Rücksetzer | 16 | 60 bis 230 | −0.4 bis −0.5 % |
| Ausbruch mit hohem Volumen | 48 | 40 bis 110 | rund −0.5 % |
| Momentum (schneller Anstieg), nur 2026 | 32 | 35 bis 55 | −0.5 bis −0.6 % |
| Kauf nach Einbruch (Crash-Kauf) | 518 | 0.1 bis 23 | −4 bis +4 %, je nach Jahr und Tag |
| Limit-Kauf unter dem Kurs, nur 2026 | 288 | 0.5 bis 650 | −1.2 bis +0.3 %, fast immer im Minus |
| USDC-Paare (0.05 % Gebühr), nur 2026 | 216 | unter 15 | nur 5 Coins mit genug Umsatz, kein stabiles Plus |
| Trendfolge stündlich auf allen Coins | 244 | 1 bis 17 | 2025 fast überall im Minus |
| KI-Modell (LightGBM, 9 Mio. Datenpunkte) | 1 | frei wählbar | Vorhersage 2026 nicht besser als Zufall (Korrelation 0.006) |

Von den 686 Varianten der ersten vier und der sechsten Zeile, die über alle 21 Monate liefen, sind mit Maker-Gebühren nur 4 sowohl 2025 als auch 2026 und ohne die 5 besten Tage im Plus. Alle 4 handeln höchstens alle 5 Tage einmal. Mit Taker-Gebühren bleibt eine.

Vor Gebühren liegt der Vorteil der häufigen Strategien bei 0.0 bis 0.3 % pro Trade. Die Gebühren sind höher.

### Crash-Kauf im Detail

Auf den ersten Blick die beste Idee: Ein Coin fällt in einer Stunde um mehr als 9 %, der Bot kauft und verkauft beim Abprall. In den Daten von 2026 brachte das über 1 % pro Trade.

Fast der ganze Gewinn stammt aber vom 6. Februar 2026, einem einzigen Crash-Tag mit 48 Trades. Ohne die 5 besten Tage ist jede Variante im Minus. 2025 hat dieselbe Regel meistens verloren. Mit maximal 5 gleichzeitigen Trades hätte der Bot an einem solchen Tag ohnehin nur einen Bruchteil davon mitgenommen.

## Freqtrade-Backtest des Daytraders

`DayTraderV1` kombiniert die zwei am wenigsten schlechten Einstiege: Rücksetzer im Aufwärtstrend und Crash-Kauf. Dazu kommen alle Schutzregeln, 10 EUR pro Trade, maximal 5 Trades gleichzeitig und die 40 umsatzstärksten Coins.

| Zeitraum | Trades | pro Tag | Ergebnis | Gewinnfaktor |
| --- | --- | --- | --- | --- |
| 20.01.2025 bis 05.10.2026 | 1150 | 1.9 | −80 % | 0.63 |

- Rücksetzer: 1018 Trades, im Schnitt −0.41 %.
- Crash-Kauf: 132 Trades, im Schnitt +0.14 %.
- Im echten Betrieb hätte das Gesamtverlust-Limit den Bot bei −15 % angehalten.
- Die Coin-Liste ist die von heute. Coins, die in dieser Zeit untergegangen sind, fehlen, deshalb ist das Ergebnis eher noch zu gut.

## Zum Vergleich: TrendFollowV2 (läuft)

| Zeitraum | BTC | ETH | Gesamt |
| --- | --- | --- | --- |
| 01.2025 bis 10.2026 | −2.2 % | +22.9 % | +20.7 % |
| 07.2025 bis 10.2026 | +0.9 % | +18.8 % | +19.7 % |

V2 handelt selten, verdient aber nach Gebühren. Der Gewinn kam zuletzt fast ganz von ETH.

## Folgerungen

1. Für echtes Geld kommt nur TrendFollowV2 in Frage, und erst nach einigen Wochen Spielgeld.
2. Der Daytrader kann als Spielgeld-Experiment mitlaufen. Erwartung: Er verliert langsam und stoppt bei −15 % von selbst.
3. Aktives Daytrading lohnt sich erst mit deutlich tieferen Gebühren, etwa bei sehr hohem Handelsvolumen oder auf einer Börse mit Maker-Gebühren nahe 0. Bei 50 bis einigen hundert Franken Kapital ist das nicht erreichbar.

## Nachrechnen

```bash
pip install freqtrade numba lightgbm scikit-learn
git clone -b data-files --depth 1 https://github.com/lars-fischer-4/trading-bot.git data
DATA=data python research/grid_21m.py          # alle Varianten, schreibt run8.csv
DATA=data python research/ml_lightgbm.py       # KI-Modell
```

## Nachtrag: Wie viele Coins? (6. Oktober 2026)

ComboV1 mit den N umsatzstärksten EUR-Coins, max. 4 Positionen, 12.50 EUR pro Trade, 20.01.2025 bis 05.10.2026:

| Coins | Trades | Ergebnis | grösster Rückgang |
| --- | --- | --- | --- |
| 4 | 51 | +44 % | 8 % |
| 7 | 80 | +55 % | 8 % |
| 10 | 125 | +64 % | 10 % |
| 12 | 243 | +56 % | 15 % |
| 20 | 307 | +6 % | 28 % |
| 40 | 457 | −37 % | 55 % |

Mit 10 Coins hält das Ergebnis in beiden Jahren (2025: +43 % statt +23 %, 2026: +19 % wie mit 4 Coins). Ab etwa 12 Coins kommen Meme-Coins dazu (MOODENG, WIF, PEPE), deren Einbrüche nicht abprallen. Der Bot nutzt deshalb die 10 grössten.
