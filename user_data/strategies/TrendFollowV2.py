"""
TrendFollowV2: Trendfilter mit 50-Tage-Durchschnitt auf 4-Stunden-Kerzen.

Kauf:     Schlusskurs steigt mehr als 2 % ueber den 50-Tage-Durchschnitt (SMA 300).
Verkauf:  Schlusskurs faellt mehr als 2 % unter den 50-Tage-Durchschnitt,
          oder der Stop-Loss greift.

Das 2-%-Band verhindert staendiges Hin und Her, wenn der Kurs um den
Durchschnitt pendelt. Nach einem Stop-Loss kauft der Bot erst wieder,
wenn der Kurs das Band erneut von unten durchbricht.

Alle Risikoregeln (Tages- und Gesamtverlust, Termine, Fear & Greed,
Telegram-Berichte) uebernimmt die Strategie unveraendert von TrendFollowV1.
"""

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import DecimalParameter, IntParameter
from TrendFollowV1 import TrendFollowV1


class TrendFollowV2(TrendFollowV1):
    startup_candle_count = 320

    trailing_stop = False

    sma_period = IntParameter(240, 450, default=300, space="buy", optimize=False)
    band = DecimalParameter(0.01, 0.04, default=0.02, decimals=2, space="buy", optimize=False)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma"] = ta.SMA(dataframe, timeperiod=self.sma_period.value)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        above = dataframe["close"] > dataframe["sma"] * (1 + self.band.value)
        dataframe.loc[
            above & ~above.shift(1, fill_value=False) & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "above_sma50d")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["sma"] * (1 - self.band.value)) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "below_sma50d")
        return dataframe
