import os
import sys, itertools
sys.path.insert(0, os.path.dirname(__file__))
import signals as R
from signals import *
R.SPLIT = pd.Timestamp("2026-01-01", tz="UTC")
pairs = {k: v for k, v in load("5m", min_rows=60000).items() if k.endswith("_EUR")}
btc1h = pd.read_feather(f"{DATA}/BTC_EUR-1h.feather")
feats = {k: features(v) for k, v in pairs.items()}
regs = {k: regime_from_btc(None, btc1h, v["date"]) for k, v in pairs.items()}
print(len(pairs), "pairs", flush=True)
grid = []
for rsi, tp, sl, mb in itertools.product((20, 25, 30), (0.01, 0.02, 0.03), (0.02, 0.04), (36, 144)):
    grid.append(("rsi_dip", dict(rsi=rsi, tp=tp, sl=sl, max_bars=mb, rsi_exit=101)))
for rsi, tp, sl, mb in itertools.product((25, 35), (0.01, 0.02), (0.02, 0.04), (36, 144)):
    grid.append(("bb_revert", dict(rsi=rsi, tp=tp, sl=sl, max_bars=mb)))
for rsi, tp, sl in itertools.product((10, 20), (0.01, 0.02), (0.02, 0.04)):
    grid.append(("rsi3_pullback", dict(rsi=rsi, tp=tp, sl=sl, max_bars=72)))
for win, drop, rsi, tp, sl, mb in itertools.product((3, 12, 24), (0.05, 0.07, 0.09, 0.12), (20, 30), (0.03, 0.05, 0.08), (0.06, 0.10), (24, 48)):
    grid.append(("crash", dict(win=win, drop=drop, rsi=rsi, tp=tp, sl=sl, max_bars=mb)))
for vm, tp, sl, mb in itertools.product((2, 4), (0.02, 0.04, 0.08), (0.015, 0.03), (36, 144)):
    grid.append(("breakout", dict(vmult=vm, tp=tp, sl=sl, max_bars=mb)))
res = []
for name, p in grid:
    for regime in (True, False):
        q = dict(p, regime=regime, min_qv=2e5)
        t = evaluate(pairs, feats, regs, name, q, 0.0)  # brutto, Gebuehren unten
        if t is None or len(t) < 50: continue
        s = {"name": name, **q, "n": len(t)}
        for fee_lab, rt in (("tak", 0.005), ("mak", 0.003)):
            r = t.ret - rt
            s[f"IS_{fee_lab}"] = round(r[t.date < R.SPLIT].mean() * 100, 3)
            s[f"OOS_{fee_lab}"] = round(r[t.date >= R.SPLIT].mean() * 100, 3)
            m = r.groupby(t.date.dt.to_period("M")).sum()
            s[f"mpos_{fee_lab}"] = round((m > 0).mean() * 100)
            day = r.groupby(t.date.dt.date).sum().sort_values(ascending=False)
            s[f"wo5_{fee_lab}"] = round((r.sum() - day.head(5).sum()) / len(r) * 100, 3)
        s["perday"] = round(len(t) / 643, 1)
        res.append(s)
d = pd.DataFrame(res); d.to_csv("run8.csv", index=False)
print("done", len(d))
