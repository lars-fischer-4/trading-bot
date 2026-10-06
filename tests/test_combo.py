import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ComboV1 import ComboV1

ROOT = Path(__file__).resolve().parent.parent


def candles(n, freq, start, drift=0.0, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.002, n)))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({
        "date": pd.date_range(start, periods=n, freq=freq, tz="UTC"),
        "open": open_, "high": np.maximum(open_, close) * 1.001, "low": np.minimum(open_, close) * 0.999,
        "close": close, "volume": rng.uniform(10, 100, n),
    })


class FakeDP:
    def __init__(self, big, analyzed=None):
        self.big = big
        self.analyzed = analyzed
        self.runmode = type("RM", (), {"value": "backtest"})()

    def get_pair_dataframe(self, pair, timeframe):
        return self.big

    def get_analyzed_dataframe(self, pair, timeframe):
        return self.analyzed, None


def strategy(big):
    s = ComboV1({"user_data_dir": "/tmp", "stake_currency": "EUR"})
    s.dp = FakeDP(big)
    return s


def run(s, df, pair):
    meta = {"pair": pair}
    df = s.populate_indicators(df, meta)
    return s.populate_entry_trend(df, meta)


def big_with_breakout():
    # 4h: lange flach, dann klarer Anstieg ueber den 50-Tage-Durchschnitt
    big = candles(400, "4h", "2025-09-01")
    big.loc[380:, "close"] = big.loc[379, "close"] * np.linspace(1.01, 1.10, 20)
    return big


def test_trend_entry_only_for_btc_eth():
    big = big_with_breakout()
    df = candles(1500, "5min", str(big["date"].iloc[370].tz_convert(None)))
    btc = run(strategy(big), df.copy(), "BTC/EUR")
    sol = run(strategy(big), df.copy(), "SOL/EUR")
    assert (btc["enter_tag"] == "trend").sum() == 1
    assert not (sol["enter_tag"] == "trend").any()


def test_crash_entry():
    df = candles(600, "5min", "2026-01-01")
    df.loc[500:505, "close"] = df.loc[499, "close"] * np.linspace(0.98, 0.90, 6)
    df["open"] = np.r_[df["close"].iloc[0], df["close"].iloc[:-1]]
    df["low"] = np.minimum(df["open"], df["close"]) * 0.999
    out = run(strategy(None), df, "XRP/EUR")
    assert "crash" in set(out.loc[500:510, "enter_tag"].dropna())


class FakeTrade:
    def __init__(self, tag, minutes):
        self.enter_tag = tag
        self.open_date_utc = datetime(2026, 1, 1, tzinfo=UTC)
        self.now = self.open_date_utc + timedelta(minutes=minutes)
        self.is_short = False
        self.leverage = 1.0


def test_exits():
    s = strategy(None)
    t = FakeTrade("crash", 30)
    assert s.custom_exit("XRP/EUR", t, t.now, 1.0, 0.081) == "crash_target"
    assert s.custom_exit("XRP/EUR", t, t.now, 1.0, 0.02) is None
    t = FakeTrade("crash", 241)
    assert s.custom_exit("XRP/EUR", t, t.now, 1.0, 0.0) == "crash_timeout"
    # Trend (auch alte Trades ohne Tag) endet erst, wenn der 4h-Kurs unter das Band faellt
    for tag in ("trend", "above_sma50d", None):
        t = FakeTrade(tag, 60 * 24 * 30)
        s.dp.analyzed = pd.DataFrame({"trend_down": [False]})
        assert s.custom_exit("BTC/EUR", t, t.now, 1.0, 0.2) is None
        s.dp.analyzed = pd.DataFrame({"trend_down": [True]})
        assert s.custom_exit("BTC/EUR", t, t.now, 1.0, 0.2) == "trend_end"


def test_fixed_stops():
    s = strategy(None)
    t = FakeTrade("crash", 5)
    assert abs(s.custom_stoploss("X", t, t.now, 1.0, 0.0, False) - 0.08) < 1e-6
    t = FakeTrade("trend", 5)
    assert abs(s.custom_stoploss("X", t, t.now, 1.0, 0.0, False) - 0.08) < 1e-6


def test_config_one_bot_dry_run():
    cfg = json.loads((ROOT / "user_data/config.json").read_text())
    assert cfg["dry_run"] is True
    assert cfg["strategy"] == "ComboV1"
    assert cfg["stake_amount"] * cfg["max_open_trades"] <= cfg["available_capital"]
    assert cfg["stake_amount"] <= 0.2 * cfg["available_capital"]
    assert "ComboV1" in (ROOT / "docker-compose.yml").read_text()


def test_watches_ten_big_coins():
    cfg = json.load(open(Path(__file__).parent.parent / "user_data" / "config.json"))
    pairs = cfg["exchange"]["pair_whitelist"]
    assert len(pairs) == 10
    assert {"BTC/EUR", "ETH/EUR"} <= set(pairs)
    assert all(p.endswith("/EUR") for p in pairs)
