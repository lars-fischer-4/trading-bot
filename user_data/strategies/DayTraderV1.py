"""
DayTraderV1: aktiver Daytrader auf 5-Minuten-Kerzen ueber die umsatzstaerksten Bitvavo-Coins.

Laeuft als zweiter Bot neben TrendFollowV2, nur mit Spielgeld, und dient als Live-Experiment:
Im Backtest ueber 21 Monate hat keine haeufig handelnde Variante die Gebuehren
(rund 0.5 % pro Kauf und Verkauf) zuverlaessig verdient. Siehe docs/daytrading-research.md.

Zwei Einstiegsarten (enter_tag):
  dip    Kurzer Ruecksetzer im Aufwaertstrend: RSI(14) unter 25, Kurs ueber dem
         ~50-Stunden-Durchschnitt, BTC ueber seinem 50-Stunden-Durchschnitt.
         Ziel +3 %, Stop -4 %, nach 3 Stunden raus.
  crash  Starker Einbruch: Kurs mehr als 7 % unter dem Hoch der letzten Stunde, RSI unter 30.
         Ziel +8 %, Stop -10 %, nach 2 Stunden raus.

Risikoregeln, Tagesbericht und Gesamtverlust-Limit kommen von TrendFollowV1.
Das Gesamtverlust-Limit schreibt hier user_data/HALT_daytrader und stoppt nur diesen Bot.
"""

from datetime import datetime, timedelta
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import merge_informative_pair, stoploss_from_open
from TrendFollowV1 import TrendFollowV1


class DayTraderV1(TrendFollowV1):
    timeframe = "5m"
    startup_candle_count = 700

    minimal_roi = {"0": 100}
    stoploss = -0.10
    trailing_stop = False
    use_custom_stoploss = True
    use_exit_signal = True  # noetig, damit custom_exit (Ziel und Zeitlimit) aufgerufen wird

    # pro Einstiegsart: (Ziel, Stop, maximale Haltedauer)
    exits = {
        "dip": (0.03, 0.04, timedelta(hours=3)),
        "crash": (0.08, 0.10, timedelta(hours=2)),
    }
    report_title = "Tagesbericht Daytrader"
    dip_rsi = 25
    crash_drop = 0.07
    crash_rsi = 30

    @property
    def protections(self):
        return [
            # nach einem Verkauf 10 Minuten Pause fuer dieses Paar
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
            # Tagesverlust-Limit: mehr als 3 % Verlust in 24 h -> 24 h keine neuen Kaeufe
            {
                "method": "MaxDrawdown",
                "calculation_mode": "equity",
                "lookback_period_candles": 288,
                "trade_limit": 1,
                "stop_duration_candles": 288,
                "max_allowed_drawdown": 0.03,
            },
            # Markt kippt: 3 Stop-Losses in 2 Stunden -> 2 Stunden Pause
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 24,
                "trade_limit": 3,
                "stop_duration_candles": 24,
                "only_per_pair": False,
            },
            # Coin laeuft schlecht: 2 Trades mit zusammen mehr als 2 % Verlust in 24 h -> 12 h Sperre
            {
                "method": "LowProfitPairs",
                "lookback_period_candles": 288,
                "trade_limit": 2,
                "stop_duration_candles": 144,
                "required_profit": -0.02,
            },
        ]

    def bot_start(self, **kwargs) -> None:
        super().bot_start(**kwargs)
        self.halt_file = Path(self.config["user_data_dir"]) / "HALT_daytrader"

    def informative_pairs(self):
        return [(f"BTC/{self.config['stake_currency']}", "1h")]

    # --- Indikatoren und Signale -----------------------------------

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=600)  # ~50 Stunden
        dataframe["high_1h"] = dataframe["high"].rolling(12).max().shift(1)
        dataframe["drop_1h"] = dataframe["close"] / dataframe["high_1h"] - 1

        btc = self.dp.get_pair_dataframe(f"BTC/{self.config['stake_currency']}", "1h")
        if btc is not None and not btc.empty:
            btc = btc.copy()
            btc["ema50"] = ta.EMA(btc, timeperiod=50)
            btc["ok"] = (btc["close"] > btc["ema50"]).astype(int)
            dataframe = merge_informative_pair(dataframe, btc[["date", "close", "ema50", "ok"]], self.timeframe, "1h", ffill=True)
            dataframe["btc_ok"] = dataframe["ok_1h"].fillna(0).astype(bool)
        else:
            dataframe["btc_ok"] = False
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        has_volume = dataframe["volume"] > 0
        dip = (
            (dataframe["rsi"] < self.dip_rsi)
            & (dataframe["close"] > dataframe["ema_trend"])
            & dataframe["btc_ok"]
            & has_volume
        )
        crash = (dataframe["drop_1h"] < -self.crash_drop) & (dataframe["rsi"] < self.crash_rsi) & has_volume
        dataframe.loc[dip, ["enter_long", "enter_tag"]] = (1, "dip")
        # crash hat Vorrang: groesseres Ziel
        dataframe.loc[crash, ["enter_long", "enter_tag"]] = (1, "crash")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    # --- Ausstieg pro Einstiegsart -----------------------------------

    def _exit_rule(self, trade: Trade):
        return self.exits.get(trade.enter_tag or "dip", self.exits["dip"])

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                        current_profit: float, after_fill: bool, **kwargs) -> float | None:
        # fester Stop relativ zum Einstiegspreis (nicht nachgezogen)
        return stoploss_from_open(-self._exit_rule(trade)[1], current_profit, is_short=trade.is_short, leverage=trade.leverage) or None

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> str | None:
        target, _, max_hold = self._exit_rule(trade)
        if current_profit >= target:
            return f"{trade.enter_tag}_target"
        if current_time - trade.open_date_utc >= max_hold:
            return f"{trade.enter_tag}_timeout"
        return None

    # Schlagzeilen schickt schon der Haupt-Bot
    def _send_news(self, now: datetime) -> None:
        return
