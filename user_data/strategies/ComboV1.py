"""
ComboV1: ein Bot fuer alles, was sich im Test gelohnt hat.

Laeuft auf 5-Minuten-Kerzen und beobachtet die 10 umsatzstaerksten Coins auf Bitvavo laufend
(BTC, ETH, XRP, SOL, ADA, SUI, DOGE, LINK, FET, TAO; Liste in config.json).
Zwei Arten von Trades (enter_tag):

  trend  Trendfolge wie TrendFollowV2, nur BTC und ETH: kaufen, wenn der 4-Stunden-Schlusskurs
         mehr als 2 % ueber den 50-Tage-Durchschnitt steigt; verkaufen, wenn er mehr als 2 %
         darunter faellt. Stop 8 %.
  crash  Schneller Abprall-Kauf: Der Kurs liegt mehr als 7 % unter dem Hoch der letzten Stunde.
         Ziel +8 %, Stop -8 %, nach spaetestens 4 Stunden raus.

Weggelassen, weil sie im Test nach Gebuehren verloren haben: kurze Ruecksetzer-Kaeufe,
Ausbrueche, Scalping und kleinere Coins. Mit 20 Coins sank der Gewinn auf +6 %, mit 40 Coins
lag er bei -37 % (siehe docs/daytrading-research.md).

Risikoregeln, Notbremse, News, Tagesbericht und 10-Minuten-Status kommen von TrendFollowV1.
"""

from datetime import datetime, timedelta

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import merge_informative_pair, stoploss_from_open
from TrendFollowV1 import TrendFollowV1


class ComboV1(TrendFollowV1):
    timeframe = "5m"
    trend_timeframe = "4h"
    startup_candle_count = 320

    minimal_roi = {"0": 100}
    stoploss = -0.10
    trailing_stop = False
    use_custom_stoploss = True
    use_exit_signal = True  # noetig, damit custom_exit aufgerufen wird

    trend_pairs = ("BTC/EUR", "ETH/EUR")
    trend_sma = 300  # 4h-Kerzen = 50 Tage
    trend_band = 0.02
    trend_stop = 0.08

    crash_drop = 0.07
    crash_target = 0.08
    crash_stop = 0.08
    crash_max_hold = timedelta(hours=4)

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration": 30},
            # Tagesverlust-Limit: mehr als 3 % Verlust in 24 h -> 24 h keine neuen Kaeufe
            {
                "method": "MaxDrawdown",
                "calculation_mode": "equity",
                "lookback_period": 1440,
                "trade_limit": 1,
                "stop_duration": 1440,
                "max_allowed_drawdown": 0.03,
            },
            # zwei Stop-Losses in 2 Tagen -> 2 Tage Pause
            {
                "method": "StoplossGuard",
                "lookback_period": 2880,
                "trade_limit": 2,
                "stop_duration": 2880,
                "only_per_pair": False,
            },
        ]

    def informative_pairs(self):
        return [(p, self.trend_timeframe) for p in self.trend_pairs]

    # --- Indikatoren und Signale -----------------------------------

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["high_1h"] = dataframe["high"].rolling(12).max().shift(1)
        dataframe["drop_1h"] = dataframe["close"] / dataframe["high_1h"] - 1

        dataframe["trend_up"] = False
        dataframe["trend_down"] = False
        if metadata["pair"] in self.trend_pairs:
            big = self.dp.get_pair_dataframe(metadata["pair"], self.trend_timeframe)
            if big is not None and len(big) > self.trend_sma:
                big = big.copy()
                sma = ta.SMA(big, timeperiod=self.trend_sma)
                big["up"] = (big["close"] > sma * (1 + self.trend_band)).astype(int)
                big["down"] = (big["close"] < sma * (1 - self.trend_band)).astype(int)
                dataframe = merge_informative_pair(
                    dataframe, big[["date", "up", "down"]], self.timeframe, self.trend_timeframe, ffill=True
                )
                dataframe["trend_up"] = dataframe[f"up_{self.trend_timeframe}"].fillna(0).astype(bool)
                dataframe["trend_down"] = dataframe[f"down_{self.trend_timeframe}"].fillna(0).astype(bool)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        has_volume = dataframe["volume"] > 0
        trend_start = dataframe["trend_up"] & ~dataframe["trend_up"].shift(1, fill_value=False)
        crash = dataframe["drop_1h"] < -self.crash_drop
        dataframe.loc[crash & has_volume, ["enter_long", "enter_tag"]] = (1, "crash")
        # Trend hat Vorrang: laengere Haltedauer
        dataframe.loc[trend_start & has_volume, ["enter_long", "enter_tag"]] = (1, "trend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    # --- Ausstieg pro Trade-Art --------------------------------------

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                        current_profit: float, after_fill: bool, **kwargs) -> float | None:
        stop = self.crash_stop if trade.enter_tag == "crash" else self.trend_stop
        # fester Stop relativ zum Einstiegspreis
        return stoploss_from_open(-stop, current_profit, is_short=trade.is_short, leverage=trade.leverage) or None

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> str | None:
        # alles ausser Crash-Kaeufen (auch alte Trades von TrendFollowV2) laeuft als Trend
        if trade.enter_tag != "crash":
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(df) and bool(df["trend_down"].iloc[-1]):
                return "trend_end"
            return None
        if current_profit >= self.crash_target:
            return "crash_target"
        if current_time - trade.open_date_utc >= self.crash_max_hold:
            return "crash_timeout"
        return None
