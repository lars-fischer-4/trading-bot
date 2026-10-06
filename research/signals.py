import glob, json, os, sys, itertools, time
import numpy as np, pandas as pd, talib
sys.path.insert(0, os.path.dirname(__file__))
from sim import simulate

DATA = os.environ.get("DATA", "data")
SPLIT = pd.Timestamp("2026-07-01", tz="UTC")


def load(tf="5m", min_rows=20000):
    out = {}
    for f in sorted(glob.glob(f"{DATA}/*-{tf}.feather")):
        pair = os.path.basename(f).rsplit("-", 1)[0]
        df = pd.read_feather(f)
        if len(df) < min_rows:
            continue
        out[pair] = df.reset_index(drop=True)
    return out


def regime_from_btc(btc5, btc1h, idx_dates):
    """BTC-Regime: 1h-Close ueber EMA50(1h) -> True. Auf 5m-Daten gemappt (nur abgeschlossene 1h-Kerzen)."""
    b = btc1h[["date", "close"]].copy()
    b["ema"] = talib.EMA(b["close"].values, 50)
    b["ok"] = b["close"] > b["ema"]
    b["date"] = b["date"] + pd.Timedelta(hours=1)  # erst nach Kerzenschluss bekannt
    b["date"] = b["date"].astype("datetime64[ns, UTC]")
    m = pd.merge_asof(pd.DataFrame({"date": pd.Series(idx_dates).astype("datetime64[ns, UTC]")}), b[["date", "ok"]], on="date")
    return m["ok"].fillna(False).values


def features(df):
    c = df["close"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float); v = df["volume"].values.astype(float)
    f = {}
    f["rsi"] = talib.RSI(c, 14)
    f["rsi3"] = talib.RSI(c, 3)
    f["ema20"] = talib.EMA(c, 20); f["ema50"] = talib.EMA(c, 50); f["ema200"] = talib.EMA(c, 200)
    f["ema_1h50"] = talib.EMA(c, 600)  # ~50h
    u, m, lo = talib.BBANDS(c, 20, 2, 2); f["bbl"] = lo; f["bbm"] = m; f["bbu"] = u
    f["vol_avg"] = pd.Series(v).rolling(48).mean().shift(1).values
    for w in (3, 6, 12, 24, 48):
        f[f"hh{w}"] = pd.Series(h).rolling(w).max().shift(1).values
    f["roc12"] = c / np.r_[np.full(12, np.nan), c[:-12]] - 1
    f["atr"] = talib.ATR(h, l, c, 14) / c
    f["qv"] = pd.Series(v * c).rolling(288).sum().values  # Tagesumsatz in Quote
    return f


def signals(name, p, df, f, reg):
    c = df["close"].values; o = df["open"].values; v = df["volume"].values
    liquid = f["qv"] > p.get("min_qv", 20000)
    base = liquid & (reg if p.get("regime", True) else True)
    if name == "rsi_dip":
        e = (f["rsi"] < p["rsi"]) & (c > f["ema_1h50"]) & base
        x = f["rsi"] > p.get("rsi_exit", 70)
    elif name == "bb_revert":
        e = (c < f["bbl"]) & (f["rsi"] < p["rsi"]) & (c > f["ema_1h50"] * (1 - p.get("trend_tol", 0.0))) & base
        x = c > f["bbm"]
    elif name == "breakout":
        e = (c > f["hh48"]) & (v > p["vmult"] * f["vol_avg"]) & (c > o) & base
        x = c < f["ema20"]
    elif name == "momentum":
        e = (f["roc12"] > p["roc"]) & (v > p["vmult"] * f["vol_avg"]) & base
        x = c < f["ema20"]
    elif name == "rsi3_pullback":
        e = (f["rsi3"] < p["rsi"]) & (f["ema50"] > f["ema200"]) & (c > f["ema200"]) & base
        x = c > f["ema20"]
    elif name == "crash":
        drop = c / f[f"hh{p.get('win', 12)}"] - 1
        e = (drop < -p["drop"]) & (f["rsi"] < p["rsi"]) & base
        if p.get("trend"):
            e = e & (c > f["ema_1h50"] * (1 - p["trend"]))
        x = np.zeros(len(c), bool)
    elif name == "crash_rebound":
        drop = c / f["hh12"] - 1
        prev = np.r_[False, (drop < -p["drop"])[:-1]]
        e = prev & (c > o) & (f["rsi"] < p["rsi"] + 10) & base  # erste gruene Kerze nach dem Absturz
        x = np.zeros(len(c), bool)
    else:
        raise ValueError(name)
    if p.get("no_exit_sig"):
        x = np.zeros(len(c), bool)
    return np.nan_to_num(e).astype(bool), np.nan_to_num(x).astype(bool)


def evaluate(pairs, feats, regs, name, p, fee):
    rows = []
    for pair, df in pairs.items():
        f = feats[pair]
        e, x = signals(name, p, df, f, regs[pair])
        ei, xi, rr = simulate(df["open"].values.astype(float), df["high"].values.astype(float),
                              df["low"].values.astype(float), df["close"].values.astype(float),
                              e, x, p["tp"], p["sl"], p["max_bars"], fee,
                              p.get("trail_start", 0.0), p.get("trail_dist", 0.0))
        if len(rr):
            d = df["date"].values[ei]
            rows.append(pd.DataFrame({"pair": pair, "date": d, "ret": rr, "bars": xi - ei + 1}))
    if not rows:
        return None
    t = pd.concat(rows)
    t["date"] = pd.to_datetime(t["date"], utc=True)
    return t


def summarize(t, days_is, days_oos):
    out = {}
    for lab, part, days in (("IS", t[t.date < SPLIT], days_is), ("OOS", t[t.date >= SPLIT], days_oos)):
        n = len(part)
        out[f"{lab}_n"] = n
        out[f"{lab}_perday"] = round(n / days, 1)
        out[f"{lab}_avg%"] = round(part.ret.mean() * 100, 3) if n else np.nan
        out[f"{lab}_win%"] = round((part.ret > 0).mean() * 100, 1) if n else np.nan
        # Anteil der Paare im Plus
        if n:
            pp = part.groupby("pair").ret.sum()
            out[f"{lab}_pairs+%"] = round((pp > 0).mean() * 100)
    out["bars"] = round(t.bars.mean(), 1)
    return out
