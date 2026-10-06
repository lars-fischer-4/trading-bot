import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from DayTraderV1 import DayTraderV1

ROOT = Path(__file__).resolve().parent.parent


def candles(n, freq, start="2026-01-01", drift=0.0005, seed=2):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.002, n)))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({
        "date": pd.date_range(start, periods=n, freq=freq, tz="UTC"),
        "open": open_, "high": np.maximum(open_, close) * 1.001, "low": np.minimum(open_, close) * 0.999,
        "close": close, "volume": rng.uniform(10, 100, n),
    })


class FakeDP:
    def __init__(self, btc):
        self.btc = btc
        self.runmode = type("RM", (), {"value": "backtest"})()

    def get_pair_dataframe(self, pair, timeframe):
        return self.btc


def strategy(btc_drift=0.002):
    s = DayTraderV1({"user_data_dir": "/tmp", "stake_currency": "EUR"})
    s.dp = FakeDP(candles(200, "1h", start="2025-12-25", drift=btc_drift))
    return s


def run(s, df):
    meta = {"pair": "SOL/EUR"}
    df = s.populate_indicators(df, meta)
    return s.populate_entry_trend(df, meta)


def test_crash_entry():
    df = candles(1000, "5min")
    df.loc[900:905, "close"] = df.loc[899, "close"] * np.linspace(0.97, 0.88, 6)  # Absturz um 12 %
    df["open"] = np.r_[df["close"].iloc[0], df["close"].iloc[:-1]]
    df["low"] = np.minimum(df["open"], df["close"]) * 0.999
    out = run(strategy(), df)
    tags = out.loc[900:910, "enter_tag"].dropna()
    assert "crash" in set(tags)
    assert out["enter_long"].iloc[: DayTraderV1.startup_candle_count].fillna(0).sum() == 0


def test_dip_needs_btc_uptrend():
    df = candles(1000, "5min")
    df.loc[950:960, "close"] = df.loc[949, "close"] * np.linspace(0.995, 0.97, 11)  # kurzer Ruecksetzer
    df["open"] = np.r_[df["close"].iloc[0], df["close"].iloc[:-1]]
    up = run(strategy(btc_drift=0.002), df.copy())
    down = run(strategy(btc_drift=-0.002), df.copy())
    assert (up["enter_tag"] == "dip").any()
    assert not (down["enter_tag"] == "dip").any()


class FakeTrade:
    def __init__(self, tag, minutes):
        self.enter_tag = tag
        self.open_date_utc = datetime(2026, 1, 1, tzinfo=UTC)
        self.now = self.open_date_utc + timedelta(minutes=minutes)
        self.is_short = False
        self.leverage = 1.0


def test_exit_rules_per_tag():
    s = strategy()
    t = FakeTrade("dip", 30)
    assert s.custom_exit("X/EUR", t, t.now, 1.0, 0.031) == "dip_target"
    assert s.custom_exit("X/EUR", t, t.now, 1.0, 0.01) is None
    t = FakeTrade("dip", 181)
    assert s.custom_exit("X/EUR", t, t.now, 1.0, 0.0) == "dip_timeout"
    t = FakeTrade("crash", 60)
    assert s.custom_exit("X/EUR", t, t.now, 1.0, 0.05) is None
    assert s.custom_exit("X/EUR", t, t.now, 1.0, 0.081) == "crash_target"


def test_fixed_stop_from_entry():
    s = strategy()
    t = FakeTrade("dip", 10)
    # bei +2 % Gewinn liegt der Stop weiterhin 4 % unter dem Einstieg, also ~5.9 % unter dem aktuellen Kurs
    stop = s.custom_stoploss("X/EUR", t, t.now, 1.0, 0.02, False)
    assert abs(stop - (1 - 0.96 / 1.02)) < 1e-6
    t = FakeTrade("crash", 10)
    assert abs(s.custom_stoploss("X/EUR", t, t.now, 1.0, 0.0, False) - 0.10) < 1e-6


def test_own_halt_file(tmp_path):
    s = DayTraderV1({"user_data_dir": tmp_path, "stake_currency": "EUR"})
    s.bot_start()
    assert s.halt_file == tmp_path / "HALT_daytrader"


def test_configs_stay_in_dry_run():
    for cfg in ROOT.glob("user_data/config*.json"):
        assert json.loads(cfg.read_text()).get("dry_run", True) is True, cfg
    dt = json.loads((ROOT / "user_data/config-daytrader.json").read_text())
    assert dt["telegram"]["enabled"] is False  # Telegram-Befehle bleiben beim Haupt-Bot
    assert dt["stake_amount"] * dt["max_open_trades"] <= 50
