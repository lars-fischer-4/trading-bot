"""
ComboV1: ein Bot fuer alles, was sich im Test gelohnt hat.

Laeuft auf 5-Minuten-Kerzen und beobachtet die 10 umsatzstaerksten Coins auf Bitvavo laufend
(BTC, ETH, XRP, SOL, ADA, SUI, DOGE, LINK, FET, TAO; Liste in config.json).
Zwei Arten von Trades (enter_tag):

  trend  Trendfolge wie TrendFollowV2, nur BTC und ETH: im Trend sein, solange der 4-Stunden-
         Schlusskurs mehr als 2 % ueber den 50-Tage-Durchschnitt gestiegen und seither nicht mehr
         als 2 % darunter gefallen ist. Verkaufen, wenn er mehr als 2 % darunter faellt. Stop 12 %;
         nach einem Stop erst beim naechsten Trend wieder kaufen.
  crash  Schneller Abprall-Kauf: Der Kurs liegt mehr als 7 % unter dem Hoch der letzten Stunde.
         Ziel +8 %, Stop -8 %, nach spaetestens 4 Stunden raus.

Weggelassen, weil sie im Test nach Gebuehren verloren haben: kurze Ruecksetzer-Kaeufe,
Ausbrueche, Scalping und kleinere Coins. Mit 20 Coins sank der Gewinn auf +6 %, mit 40 Coins
lag er bei -37 % (siehe docs/daytrading-research.md).

Risikoregeln, Notbremse, News, Tagesbericht und 10-Minuten-Status kommen von TrendFollowV1.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

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
    trend_stop = 0.12

    crash_drop = 0.07
    crash_target = 0.08
    crash_stop = 0.08
    crash_max_hold = timedelta(hours=4)

    # Einsatz als Anteil am aktuellen Kontostand (waechst mit Gewinnen mit); None = stake_amount aus config
    # Backtest 01.2025-10.2026: 50 % / 35 % brachte 50 -> 153 bei 15 % groesstem Rueckgang,
    # 10 EUR fest (vorher) +67 % bei 9 % (docs/daytrading-research.md)
    # Trendkauf nimmt den ganzen freien Betrag, solange nur ein Coin im Trend ist (meistens der Fall),
    # und die Haelfte, wenn BTC und ETH gleichzeitig im Trend sind.
    # Backtest 01.2025-10.2026: 50 -> 168 statt 153, Durchschnitt 30 Tage +7.0 % statt +5.9 %,
    # groesster Rueckgang 18 % statt 15 % (docs/daytrading-research.md)
    trend_stake: float | None = 0.50
    trend_stake_solo: float | None = 1.00
    crash_stake: float | None = 0.35

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
        dataframe["trend_on"] = False
        dataframe["trend_since"] = 0.0
        if metadata["pair"] in self.trend_pairs:
            big = self.dp.get_pair_dataframe(metadata["pair"], self.trend_timeframe)
            if big is not None and len(big) > self.trend_sma:
                big = big.copy()
                sma = ta.SMA(big, timeperiod=self.trend_sma)
                big["up"] = (big["close"] > sma * (1 + self.trend_band)).astype(int)
                big["down"] = (big["close"] < sma * (1 - self.trend_band)).astype(int)
                # Trend gilt ab dem ersten Schluss ueber dem Band, bis ein Schluss unter dem Band liegt
                state = big["up"].where(big["up"] == 1, -big["down"]).replace(0, np.nan).ffill()
                big["on"] = (state == 1).astype(int)
                start = (big["on"] == 1) & (big["on"].shift(1, fill_value=0) == 0)
                since = big["date"].where(start).ffill()
                big["since"] = since.map(lambda d: d.timestamp() if pd.notna(d) else 0.0)
                dataframe = merge_informative_pair(
                    dataframe, big[["date", "up", "down", "on", "since"]], self.timeframe, self.trend_timeframe,
                    ffill=True,
                )
                tf = self.trend_timeframe
                dataframe["trend_up"] = dataframe[f"up_{tf}"].fillna(0).astype(bool)
                dataframe["trend_down"] = dataframe[f"down_{tf}"].fillna(0).astype(bool)
                dataframe["trend_on"] = dataframe[f"on_{tf}"].fillna(0).astype(bool)
                dataframe["trend_since"] = dataframe[f"since_{tf}"].fillna(0.0)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        has_volume = dataframe["volume"] > 0
        crash = dataframe["drop_1h"] < -self.crash_drop
        dataframe.loc[crash & has_volume, ["enter_long", "enter_tag"]] = (1, "crash")
        # Trend hat Vorrang: laengere Haltedauer. Kauft auch mitten in einem laufenden Trend
        # (z. B. nach einem Neustart); nach einem Stop-Loss erst beim naechsten Trend (confirm_trade_entry).
        dataframe.loc[dataframe["trend_on"] & has_volume, ["enter_long", "enter_tag"]] = (1, "trend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float, proposed_stake: float,
                            min_stake: float | None, max_stake: float, leverage: float, entry_tag: str | None,
                            side: str, **kwargs) -> float:
        if entry_tag == "trend":
            share = self.trend_stake_solo if self._trend_coins_on() <= 1 else self.trend_stake
        else:
            share = self.crash_stake
        if share is None:
            return proposed_stake
        return min(max_stake, self.wallets.get_total_stake_amount() * share)

    def _trend_coins_on(self) -> int:
        """Wie viele der Trend-Coins (BTC, ETH) gerade im Trend sind."""
        on = 0
        for p in self.trend_pairs:
            df, _ = self.dp.get_analyzed_dataframe(p, self.timeframe)
            if df is not None and len(df) and "trend_on" in df and bool(df["trend_on"].iloc[-1]):
                on += 1
        return on

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, time_in_force: str,
                            current_time: datetime, entry_tag: str | None, side: str, **kwargs) -> bool:
        if entry_tag == "trend" and self._stopped_in_current_trend(pair):
            return False
        return super().confirm_trade_entry(pair, order_type, amount, rate, time_in_force, current_time,
                                           entry_tag, side, **kwargs)

    def _stopped_in_current_trend(self, pair: str) -> bool:
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df is None or not len(df) or "trend_since" not in df:
            return False
        since = datetime.fromtimestamp(float(df["trend_since"].iloc[-1]), tz=timezone.utc)
        for t in Trade.get_trades_proxy(pair=pair, is_open=False):
            if (t.enter_tag != "crash" and t.exit_reason in ("stop_loss", "trailing_stop_loss")
                    and t.close_date_utc >= since):
                return True
        return False

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
