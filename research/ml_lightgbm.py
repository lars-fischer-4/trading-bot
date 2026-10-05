import sys, glob, os, time
import numpy as np, pandas as pd, talib, lightgbm as lgb
DATA = os.environ.get("DATA", "data")
t0 = time.time()
btc = pd.read_feather(f"{DATA}/BTC_EUR-5m.feather").set_index("date")["close"]
btcf = pd.DataFrame({f"btc_r{n}": btc / btc.shift(n) - 1 for n in (1, 12, 48, 288)})
H = 12
frames = []
for f in sorted(glob.glob(f"{DATA}/*_EUR-5m.feather")):
    df = pd.read_feather(f)
    if len(df) < 60000: continue
    pair = os.path.basename(f).split("-")[0]
    c = df.close.values.astype(float); h = df.high.values.astype(float); l = df.low.values.astype(float); v = df.volume.values.astype(float); o = df.open.values.astype(float)
    X = pd.DataFrame(index=df.date)
    cs = pd.Series(c, index=df.date)
    for n in (1, 3, 6, 12, 24, 48, 288): X[f"r{n}"] = (cs / cs.shift(n) - 1).values
    X["rsi14"] = talib.RSI(c, 14); X["rsi3"] = talib.RSI(c, 3)
    u, m, lo = talib.BBANDS(c, 20, 2, 2); X["bbpos"] = (c - lo) / (u - lo)
    X["atr"] = talib.ATR(h, l, c, 14) / c
    vs = pd.Series(v); X["vratio"] = (vs / vs.rolling(48).mean()).values
    for n in (50, 200, 600): X[f"dema{n}"] = c / talib.EMA(c, n) - 1
    X["dd12"] = c / pd.Series(h).rolling(12).max().values - 1
    X["hour"] = df.date.dt.hour.values
    X["qv"] = np.log1p(pd.Series(v * c).rolling(288).sum().values)
    X = X.join(btcf, how="left")
    # Ziel: Einstieg Open t+1, Ausstieg Close t+H
    fwd = np.r_[c[H:], np.full(H, np.nan)]
    nxt = np.r_[o[1:], np.nan]
    X["y"] = fwd / nxt - 1
    X["pair"] = pair
    frames.append(X.iloc[600:-H].astype({c_: "float32" for c_ in X.columns if c_ not in ("pair",)}))
D = pd.concat(frames); del frames
D = D.replace([np.inf, -np.inf], np.nan).dropna()
D = D[D.qv > np.log1p(2e5)]
print("rows", len(D), "load", round(time.time() - t0), flush=True)
feats = [c_ for c_ in D.columns if c_ not in ("y", "pair")]
split = pd.Timestamp("2026-01-01", tz="UTC")
tr = D[D.index < split - pd.Timedelta(days=1)]; te = D[D.index >= split]
trs = tr.iloc[::3]
model = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=63, min_child_samples=2000, subsample=0.5, subsample_freq=1, colsample_bytree=0.7, verbose=-1)
model.fit(trs[feats], trs["y"].clip(-0.1, 0.1))
print("train", round(time.time() - t0), flush=True)
te = te.copy(); te["p"] = model.predict(te[feats])
tr2 = tr.iloc[1::7].copy(); tr2["p"] = model.predict(tr2[feats])
for lab, part in (("train(2025)", tr2), ("test(2026)", te)):
    print(lab, "corr", round(np.corrcoef(part.p, part.y)[0, 1], 4))
    for q in (0.99, 0.999, 0.9999):
        thr = part.p.quantile(q)
        sel = part[part.p >= thr]
        print(f"  top {100*(1-q):.2f}%: n={len(sel)} pred={sel.p.mean()*100:.3f}% real={sel.y.mean()*100:.3f}% net_taker={(sel.y.mean()-0.005)*100:.3f}% net_maker={(sel.y.mean()-0.003)*100:.3f}% days={sel.index.normalize().nunique()}")
imp = pd.Series(model.feature_importances_, feats).sort_values(ascending=False); print(imp.head(10).to_dict())
