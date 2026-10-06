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

## Nachtrag: +1 % mitnehmen auf 50 Coins (6. Oktober 2026)

Idee: viele Coins laufend beobachten, nach einem Rückgang kaufen, bei +0.6 bis +2 % verkaufen. 50 umsatzstärkste EUR-Coins, 20.01.2025 bis 05.10.2026.

| Variante | Varianten | Ergebnis |
| --- | --- | --- |
| Marktkauf nach Rückgang von 1 bis 5 %, Ziel 0.6 bis 1.5 % | 216 | alle im Minus |
| Dasselbe „lernend“: nur Coins, bei denen die Regel in den letzten 14 bis 60 Tagen im Plus war | 48 | alle im Minus |
| Limit-Kauf 3 % unter dem letzten Kurs, Ziel 0.6 bis 2 %, kein Stop, max. 1 Tag | 8 | im Plus in beiden Jahren |

Der Limit-Kauf trifft nur kurze Ausreisser nach unten, die sofort zurückkommen. Im Freqtrade-Backtest auf den 10 grössten Coins: +33 %, 422 Trades, 84 % Gewinner. Mit einem Stop von 10 bis 15 % halbiert sich der Gewinn ungefähr.

Kombiniert mit ComboV1 (ComboV2: Limit-Käufe auf 6 Coins, 8 Positionen à 6 EUR) kam der Backtest auf +33 % statt +51 % für ComboV1 allein: Die kleineren Einsätze kosten bei Trend und Crash-Kauf mehr, als die Limit-Käufe bringen (+6 %). Der Bot bleibt deshalb bei ComboV1.

## Nachtrag: Weitere Strategie-Typen (6. Oktober 2026)

Ganzes Kapital investiert, 0.25 % Gebühr pro Kauf oder Verkauf, 20.01.2025 bis 05.10.2026 (`research/candidates.py`). Zum Vergleich: alle 10 Coins halten −52 %, BTC halten −22 %, ComboV1 +51 % bei 8 % grösstem Rückgang.

| Ansatz | Quelle | bestes Ergebnis | grösster Rückgang |
| --- | --- | --- | --- |
| BTC nur 21 bis 23 Uhr UTC halten | [Quantpedia](https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/) | −86 % | 87 % |
| BTC nur am Wochenende halten | | −34 % | 39 % |
| Zeitreihen-Momentum (EMA, volatilitätsnormiert), top 10 | [Studie 2025](https://www.zurnalai.vu.lt/BATP/article/view/44540) | +11 % | 31 % |
| Zeitreihen-Momentum, nur BTC und ETH | | +41 % | 36 % |
| Querschnitt-Momentum (die 2 bis 3 stärksten Coins der Woche) | | −55 bis −74 % | 75 bis 89 % |
| dasselbe nur bei BTC über dem 50-Tage-Schnitt, top 20 | | +49 %, aber 2025 nur +11 % | 47 % |
| Donchian-Ausbruch 20/55 Tage | | +8 % | 29 % |
| Verlierer des Vortags kaufen | | −98 % | 99 % |
| ETH/BTC-Verhältnis umschichten | | −51 % | 69 % |

Keiner der Ansätze schlägt ComboV1, und alle schwanken deutlich stärker. Der Stunden-Effekt verschwindet nach Gebühren vollständig.

Trendteil von ComboV1 mit längerer Historie (BTC und ETH, 4h-Kerzen seit März 2023, `research/trend_variants.py`): Der 50-Tage-Schnitt mit 2-%-Band ist in jedem Jahr unter den besten (2024 +52 %, 2025 +29 %, 2026 +28 %). Schnellere Schnitte oder EMA-Kreuzungen sind in mindestens einem Jahr deutlich schlechter. Die aktuelle Einstellung bleibt.

## Nachtrag: Optimierung von ComboV1 (6. Oktober 2026)

Ziel von Lars: aus 50 in 30 Tagen mindestens 55, etwas mehr Risiko ist in Ordnung. Freqtrade-Backtest, 10 Coins, 20.01.2025 bis 05.10.2026, Kontostand inklusive offener Positionen.

1. **Fehler gefunden:** Der Trendteil kaufte nur im Moment, in dem ein Trend begann. Ein Bot, der mitten in einem Trend startet (wie nach dem Umzug auf den Pi), blieb bis zum nächsten Trend draussen. In den 2 Wochen vor dem Test: 50.00 → 50.07, obwohl BTC und ETH im Aufwärtstrend waren. Jetzt kauft er, solange der Trend gilt; nach einem Stop-Loss erst beim nächsten Trend. Ergebnis mit 10 EUR fest: +67 % statt +51 %.
2. **Crash-Parameter** (Schwelle 5 bis 10 %, Ziel 5 bis 12 %, Stop 5 bis 12 %, Haltedauer 2 bis 24 h), Trend-Stop 5 bis 12 %, ohne Schutzregeln, mehr Positionen: Die bisherigen Werte sind in beiden Jahren unter den besten, keine Änderung.
3. **Trend auch auf Altcoins** (4 oder 10 Coins): mehr Rückgang (25 bis 32 %), nicht mehr Gewinn.
4. **Einsatz als Anteil am Kontostand:**

| Trend / Crash | Ende (Start 50) | 2025 | 2026 | 30 Tage Schnitt | 30 Tage ≥ +10 % | grösster Rückgang |
| --- | --- | --- | --- | --- | --- | --- |
| 10 EUR fest | 84 | +46 % | +15 % | +2.6 % | 11 % | 9 % |
| 30 % / 15 % | 86 | +42 % | +22 % | +2.8 % | 15 % | 14 % |
| 40 % / 20 % | 105 | +63 % | +30 % | +3.9 % | 22 % | 15 % |
| 45 % / 25 % | 122 | +75 % | +39 % | +4.7 % | 24 % | 16 % |
| **50 % / 25 %** | **127** | **+80 %** | **+41 %** | **+5.0 %** | **24 %** | **17 %** |

Gewählt: 50 % / 25 %. Monate reichen von −8 % bis +25 %; etwa jeder dritte 30-Tage-Zeitraum endet im Minus. +10 % in jedem Monat schafft keine Variante.

### Zweite Runde (6. Oktober 2026, Nachmittag)

Ausgehend von 50 % / 25 % (50 → 127), je eine Änderung:

| Änderung | Ende | 2025 | 2026 | grösster Rückgang |
| --- | --- | --- | --- | --- |
| Crash-Käufe 35 % statt 25 % | 143 | +98 % | +44 % | 17 % |
| Trend-Stop 15 % statt 8 % | 135 | +80 % | +49 % | 15 % |
| 250er statt 300er Schnitt | 134 | +73 % | +55 % | 17 % |
| Band 1 % / 3 % | 128 / 122 | | | 18 / 19 % |
| Nachkauf nach Stop im selben Trend | 127 | | | 20 % |
| Trailing-Stop 15 / 20 % unter Hoch | 124 / 122 | | | 18 % |
| 360er Schnitt | 118 | | | 21 % |
| Tagesverlust-Limit 5 % statt 3 % | 126 | | | 19 % |
| ohne Schutzregeln | 101 | | | 28 % |
| **Crash 35 % und Trend-Stop 12 bis 15 %** | **153** | **+98 %** | **+54 %** | **15 %** |

Übernommen: Crash-Käufe 35 %, Trend-Stop 12 % (12 und 15 % ergaben dasselbe). Der 250er Schnitt war nur 2026 besser und bleibt deshalb bei 300.
