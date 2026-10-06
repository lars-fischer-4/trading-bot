import numpy as np
import pandas as pd

from TrendFollowV1 import TrendFollowV1


def make_candles(n=600, seed=1):
    rng = np.random.default_rng(seed)
    # erst Abwaertstrend, dann kraeftiger Aufwaertstrend, dann wieder runter
    drift = np.r_[np.full(n // 3, -0.004), np.full(n // 3, 0.006), np.full(n - 2 * (n // 3), -0.006)]
    close = 30000 * np.exp(np.cumsum(drift + rng.normal(0, 0.004, n)))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC"),
        "open": open_,
        "high": np.maximum(open_, close) * 1.003,
        "low": np.minimum(open_, close) * 0.997,
        "close": close,
        "volume": rng.uniform(10, 100, n),
    })


def run(df):
    s = TrendFollowV1({"user_data_dir": "/tmp", "stake_currency": "EUR"})
    meta = {"pair": "BTC/EUR"}
    df = s.populate_indicators(df, meta)
    df = s.populate_entry_trend(df, meta)
    return s.populate_exit_trend(df, meta)


def test_buys_in_uptrend_and_exits_after():
    df = run(make_candles())
    entries = df.index[df["enter_long"] == 1]
    exits = df.index[df["exit_long"] == 1]
    assert len(entries) >= 1
    # Einstieg nur ueber dem EMA 200
    assert (df.loc[entries, "close"] > df.loc[entries, "ema_200"]).all()
    # nach dem letzten Einstieg kommt im Abwaertstrend ein Ausstiegssignal
    assert (exits > entries.max()).any()


def test_no_signal_during_warmup():
    df = run(make_candles())
    assert df["enter_long"].iloc[:TrendFollowV1.startup_candle_count].fillna(0).sum() == 0


def test_risk_settings():
    assert TrendFollowV1.stoploss == -0.08
    assert TrendFollowV1.max_total_loss == 0.15
    dd = [p for p in TrendFollowV1({}).protections if p["method"] == "MaxDrawdown"][0]
    assert dd["max_allowed_drawdown"] == 0.03


class FakeDP:
    def __init__(self, mode="dry_run"):
        self.runmode = type("RM", (), {"value": mode})()
        self.sent = []

    def send_msg(self, msg, always_send=False):
        self.sent.append(msg)


def live_strategy(tmp_path, monkeypatch, closed_profit=0.0, closed_trades=None):
    import TrendFollowV1 as mod

    s = TrendFollowV1({"user_data_dir": tmp_path, "stake_currency": "EUR", "dry_run": True,
                       "dry_run_wallet": 50, "available_capital": 50})
    s.dp = FakeDP()
    s.bot_start()
    s.market._fg_fetched_at = float("inf")
    monkeypatch.setattr(mod.Trade, "get_total_closed_profit", staticmethod(lambda: closed_profit))
    monkeypatch.setattr(mod.Trade, "get_open_trades", staticmethod(lambda: []))
    monkeypatch.setattr(mod.Trade, "get_trades_proxy", staticmethod(lambda **kw: closed_trades or []))
    monkeypatch.setattr(s.market, "new_headlines", lambda: [])
    return s


def entry(s, when):
    return s.confirm_trade_entry("BTC/EUR", "limit", 0.001, 30000, "GTC", when, "trend_start", "long")


def test_total_loss_creates_halt_and_blocks(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    now = datetime(2026, 11, 5, 10, tzinfo=UTC)
    s = live_strategy(tmp_path, monkeypatch, closed_profit=-7.6)  # > 15 % von 50
    assert entry(s, now) is True
    s.bot_loop_start(now)
    assert (tmp_path / "HALT").exists()
    assert any("NOTBREMSE" in m for m in s.dp.sent)
    assert entry(s, now) is False


def test_small_loss_no_halt(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    s = live_strategy(tmp_path, monkeypatch, closed_profit=-7.0)
    s.bot_loop_start(datetime(2026, 11, 5, 10, tzinfo=UTC))
    assert not (tmp_path / "HALT").exists()


def test_daily_report_once(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    s = live_strategy(tmp_path, monkeypatch)
    s.bot_loop_start(datetime(2026, 11, 5, 20, 0, tzinfo=UTC))  # 21:00 in Zuerich (Winterzeit)
    s.bot_loop_start(datetime(2026, 11, 5, 20, 30, tzinfo=UTC))
    reports = [m for m in s.dp.sent if m.startswith("Tagesbericht")]
    assert len(reports) == 1
    assert "Spielgeld" in reports[0]


def test_backtest_ignores_live_filters(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    s = live_strategy(tmp_path, monkeypatch)
    s.dp = FakeDP("backtest")
    (tmp_path / "HALT").write_text("x")
    assert entry(s, datetime(2026, 11, 5, tzinfo=UTC)) is True


def test_report_sums_periods(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    def closed(day, profit):
        return SimpleNamespace(close_date=datetime(2026, 11, day, 9), close_profit_abs=profit)

    # Do 5.11.2026: heute +1, diese Woche (ab Mo 2.11.) +1 +2, Monat zusaetzlich +3 am 1.11., Quartal +4 im Oktober
    trades = [closed(5, 1.0), closed(3, 2.0), closed(1, 3.0)]
    trades.append(SimpleNamespace(close_date=datetime(2026, 10, 20, 9), close_profit_abs=4.0))
    s = live_strategy(tmp_path, monkeypatch, closed_profit=10.0, closed_trades=trades)
    text = s.build_report(datetime(2026, 11, 5, 20, 0, tzinfo=UTC))
    assert "Kontostand: 60.00 EUR (+20.0% seit Start)" in text
    assert "Heute: +1.00 EUR, 1 Trades" in text
    assert "Woche +3.00 | Monat +6.00 | Quartal +10.00 | Gesamt +10.00" in text
