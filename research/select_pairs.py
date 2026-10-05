"""Waehlt die liquidesten Bitvavo-Paare (EUR und USDC) nach 24h-Umsatz in EUR."""
import json
import sys

import ccxt

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
ex = ccxt.bitvavo()
markets = ex.load_markets()
tickers = ex.fetch_tickers()
rows = []
for sym, t in tickers.items():
    m = markets.get(sym)
    if not m or not m.get("active") or m["quote"] not in ("EUR", "USDC"):
        continue
    if m["base"] in ("USDC", "USDT", "EURC", "EURT", "DAI"):
        continue
    qv = t.get("quoteVolume") or 0
    rows.append((sym, m["quote"], qv))
rows.sort(key=lambda r: -r[2])
eur = [r for r in rows if r[1] == "EUR"][:N]
usdc = [r for r in rows if r[1] == "USDC"]
json.dump({"eur": eur, "usdc": usdc, "all_eur_count": sum(r[1] == "EUR" for r in rows)}, open("pairs.json", "w"), indent=1)
print(f"EUR-Paare aktiv: {sum(r[1]=='EUR' for r in rows)}, USDC-Paare: {len(usdc)}")
print(" ".join(r[0] for r in eur + usdc))
