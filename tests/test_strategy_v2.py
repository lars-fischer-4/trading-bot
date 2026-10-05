from test_strategy import make_candles

from TrendFollowV2 import TrendFollowV2


def run(df):
    s = TrendFollowV2({"user_data_dir": "/tmp", "stake_currency": "EUR"})
    meta = {"pair": "BTC/EUR"}
    df = s.populate_indicators(df, meta)
    df = s.populate_entry_trend(df, meta)
    return s.populate_exit_trend(df, meta)


def test_buys_above_band_and_exits_below():
    df = run(make_candles(n=1200))
    entries = df.index[df["enter_long"] == 1]
    exits = df.index[df["exit_long"] == 1]
    assert len(entries) >= 1
    assert (df.loc[entries, "close"] > df.loc[entries, "sma"] * 1.02).all()
    assert (df.loc[exits, "close"] < df.loc[exits, "sma"] * 0.98).all()
    assert (exits > entries.max()).any()


def test_entry_only_on_breakout():
    df = run(make_candles(n=1200))
    entries = df.index[df["enter_long"] == 1]
    # die Kerze davor lag noch nicht ueber dem Band
    prev = entries - 1
    assert (df.loc[prev, "close"] <= df.loc[prev, "sma"] * 1.02).all()


def test_no_signal_during_warmup():
    df = run(make_candles(n=1200))
    assert df["enter_long"].iloc[: TrendFollowV2.startup_candle_count].fillna(0).sum() == 0
    assert TrendFollowV2.startup_candle_count >= TrendFollowV2.sma_period.value


def test_keeps_v1_risk_rules():
    s = TrendFollowV2({})
    assert TrendFollowV2.stoploss == -0.08
    assert TrendFollowV2.trailing_stop is False
    assert TrendFollowV2.max_total_loss == 0.15
    assert {p["method"] for p in s.protections} == {"CooldownPeriod", "MaxDrawdown", "StoplossGuard"}
