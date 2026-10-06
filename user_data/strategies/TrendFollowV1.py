"""
TrendFollowV1: einfache Trendfolge auf 4-Stunden-Kerzen.

Kauf:     sobald gleichzeitig der schnelle EMA ueber dem langsamen liegt,
          der Kurs ueber dem EMA 200 (langfristiger Aufwaertstrend)
          und der ADX einen echten Trend zeigt.
Verkauf:  schneller EMA kreuzt den langsamen nach unten,
          oder Stop-Loss bzw. nachgezogener Stop greift.

Risikoregeln (zusaetzlich zur Konfiguration):
- Kein neuer Kauf im Sperrfenster vor/nach US-Zinsentscheid und US-Inflation
- Kein neuer Kauf bei extremer Gier (Fear & Greed)
- Tagesverlust-Limit ueber die MaxDrawdown-Protection
- Gesamtverlust-Limit: ab 15 % Verlust des Startkapitals wird die Datei
  user_data/HALT angelegt; solange sie existiert, kauft der Bot nichts mehr.
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, IntParameter
from technical import qtpylib


sys.path.append(str(Path(__file__).parent.parent / "botlib"))
from market_filter import MarketFilter  # noqa: E402


logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Europe/Zurich")


class TrendFollowV1(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "4h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 220

    # Gewinne laufen lassen: kein festes Gewinnziel, Ausstieg ueber Signal/Stop
    minimal_roi = {"0": 100}
    stoploss = -0.08
    trailing_stop = True
    trailing_stop_positive = 0.04
    trailing_stop_positive_offset = 0.08
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    exit_profit_only = False

    ema_fast = IntParameter(10, 30, default=21, space="buy", optimize=False)
    ema_slow = IntParameter(40, 80, default=55, space="buy", optimize=False)
    adx_min = IntParameter(15, 30, default=20, space="buy", optimize=False)

    # Gesamtverlust-Limit in Anteilen des Startkapitals
    max_total_loss = 0.15
    news_interval = timedelta(minutes=60)
    daily_report_hour = 21  # Uhrzeit (Schweiz) fuer den Tagesbericht
    report_title = "Tagesbericht"
    status_interval = timedelta(minutes=15)  # kurzer Status per Telegram

    @property
    def protections(self):
        return [
            # Nach einem Verkauf 1 Kerze (4 h) Pause fuer dieses Paar
            {"method": "CooldownPeriod", "stop_duration_candles": 1},
            # Tagesverlust-Limit: mehr als 3 % Verlust in 24 h -> 24 h keine neuen Kaeufe
            {
                "method": "MaxDrawdown",
                "calculation_mode": "equity",
                "lookback_period_candles": 6,
                "trade_limit": 1,
                "stop_duration_candles": 6,
                "max_allowed_drawdown": 0.03,
            },
            # Zwei Stop-Losses innerhalb von 2 Tagen -> 2 Tage Pause
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 12,
                "trade_limit": 2,
                "stop_duration_candles": 12,
                "only_per_pair": False,
            },
        ]

    def bot_start(self, **kwargs) -> None:
        user_data = Path(self.config["user_data_dir"])
        self.halt_file = user_data / "HALT"
        self.market = MarketFilter(user_data / "market_filter.json", user_data / "seen_news.json")
        self._last_news = datetime.min
        self._last_report_day = None
        self._last_status = datetime.min
        self._halt_announced = False

    # --- Indikatoren und Signale -----------------------------------

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        for n in set(self.ema_fast.range) | set(self.ema_slow.range) | {200}:
            dataframe[f"ema_{n}"] = ta.EMA(dataframe, timeperiod=n)
        dataframe["adx"] = ta.ADX(dataframe)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe[f"ema_{self.ema_fast.value}"]
        slow = dataframe[f"ema_{self.ema_slow.value}"]
        # Kauf, sobald alle Trendbedingungen gemeinsam erfuellt sind (und es vorher nicht waren).
        # So zaehlt auch ein Kreuzen, das noch unter dem EMA 200 passiert ist.
        trend = (fast > slow) & (dataframe["close"] > dataframe["ema_200"]) & (dataframe["adx"] > self.adx_min.value)
        dataframe.loc[
            trend & ~trend.shift(1, fill_value=False) & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "trend_start")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe[f"ema_{self.ema_fast.value}"]
        slow = dataframe[f"ema_{self.ema_slow.value}"]
        dataframe.loc[
            qtpylib.crossed_below(fast, slow) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "ema_cross_down")
        return dataframe

    # --- Risikoregeln ---------------------------------------------------

    def _is_live(self) -> bool:
        return self.dp.runmode.value in ("live", "dry_run")

    def _starting_capital(self) -> float:
        return float(self.config.get("available_capital") or self.config.get("dry_run_wallet") or 0)

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        if not self._is_live():
            # Im Backtest gibt es keine historischen News/Termine: nur die reine Strategie testen
            return True
        if self.halt_file.exists():
            logger.info("Kauf %s abgelehnt: HALT-Datei vorhanden", pair)
            return False
        reason = self.market.entry_block_reason(current_time)
        if reason:
            logger.info("Kauf %s abgelehnt: %s", pair, reason)
            self.dp.send_msg(f"Kaufsignal {pair} ignoriert: {reason}")
            return False
        return True

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        if not self._is_live():
            return
        self._check_total_loss()
        self._send_news(current_time)
        self._send_daily_report(current_time)
        self._send_status(current_time)

    def _check_total_loss(self) -> None:
        capital = self._starting_capital()
        if capital <= 0:
            return
        closed = Trade.get_total_closed_profit()
        if closed <= -self.max_total_loss * capital and not self.halt_file.exists():
            self.halt_file.write_text(f"Gesamtverlust {closed:.2f} am {datetime.now(LOCAL_TZ):%d.%m.%Y %H:%M}\n")
            self.dp.send_msg(
                f"NOTBREMSE: Gesamtverlust {closed:.2f} {self.config['stake_currency']} "
                f"(mehr als {self.max_total_loss:.0%} von {capital:.0f}). "
                "Keine neuen Kaeufe mehr. Offene Positionen laufen mit Stop-Loss weiter. "
                "Freigabe nach Pruefung mit: rm user_data/HALT",
                always_send=True,
            )

    def _send_news(self, now: datetime) -> None:
        if now.replace(tzinfo=None) - self._last_news < self.news_interval:
            return
        self._last_news = now.replace(tzinfo=None)
        for h in self.market.new_headlines()[:5]:
            self.dp.send_msg(f"News ({h.source}): {h.title}\n{h.link}", always_send=True)

    def _last_price(self, pair: str) -> float | None:
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            return float(df["close"].iloc[-1]) if len(df) else None
        except Exception:
            return None

    def _period_profits(self, local: datetime) -> dict[str, float]:
        """Abgeschlossener Gewinn seit Tagesbeginn, Wochenbeginn, Monatsbeginn, Quartalsbeginn (Schweizer Zeit)."""
        day = local.replace(hour=0, minute=0, second=0, microsecond=0)
        starts = {
            "Heute": day,
            "Woche": day - timedelta(days=day.weekday()),
            "Monat": day.replace(day=1),
            "Quartal": day.replace(month=(day.month - 1) // 3 * 3 + 1, day=1),
        }
        closed = Trade.get_trades_proxy(is_open=False)
        out = {}
        for name, since in starts.items():
            since_utc = since.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            out[name] = sum(
                (t.close_profit_abs or 0.0) for t in closed
                if t.close_date and t.close_date.replace(tzinfo=None) >= since_utc
            )
        out["trades_today"] = sum(
            1 for t in closed
            if t.close_date and t.close_date.replace(tzinfo=None) >= starts["Heute"].astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        )
        return out

    def build_report(self, now: datetime) -> str:
        local = now.astimezone(LOCAL_TZ)
        cur = self.config["stake_currency"]
        start = self._starting_capital()
        closed = Trade.get_total_closed_profit()
        open_trades = Trade.get_open_trades()
        unrealized = 0.0
        open_lines = []
        for t in open_trades:
            price = self._last_price(t.pair)
            pct = ""
            if price:
                unrealized += t.calc_profit(price)
                pct = f" {t.calc_profit_ratio(price):+.1%}"
            open_lines.append(f"  {t.pair} ({t.enter_tag or '-'}){pct}, seit {t.open_date:%d.%m. %H:%M}")
        equity = start + closed + unrealized
        p = self._period_profits(local)
        mode = "Spielgeld" if self.config.get("dry_run") else "ECHTGELD"
        lines = [
            f"{self.report_title} {local:%d.%m.%Y} ({mode})",
            f"Kontostand: {equity:.2f} {cur} ({(equity / start - 1) if start else 0:+.1%} seit Start)",
            f"Heute: {p['Heute']:+.2f} {cur}, {p['trades_today']} Trades abgeschlossen",
            f"Woche {p['Woche']:+.2f} | Monat {p['Monat']:+.2f} | Quartal {p['Quartal']:+.2f} | Gesamt {closed:+.2f}",
        ]
        lines.append(f"Offen: {len(open_trades)}" + ("" if open_trades else " (nichts investiert)"))
        lines += open_lines
        fg, fg_label = self.market.fear_greed()
        events = self.market.upcoming_events(now)
        extra = []
        if fg is not None:
            extra.append(f"Fear & Greed {fg}")
        if events:
            e = events[0]
            extra.append(f"naechster Termin {e.time.astimezone(LOCAL_TZ):%a %d.%m. %H:%M} {e.name}")
        if extra:
            lines.append(" | ".join(extra))
        if self.halt_file.exists():
            lines.append("ACHTUNG: Notbremse aktiv, keine neuen Kaeufe.")
        return "\n".join(lines)

    def _send_daily_report(self, now: datetime) -> None:
        local = now.astimezone(LOCAL_TZ)
        if local.hour != self.daily_report_hour or self._last_report_day == local.date():
            return
        self._last_report_day = local.date()
        self.dp.send_msg(self.build_report(now), always_send=True)

    def build_status(self, now: datetime) -> str:
        local = now.astimezone(LOCAL_TZ)
        cur = self.config["stake_currency"]
        start = self._starting_capital()
        closed = Trade.get_total_closed_profit()
        parts = []
        unrealized = 0.0
        for t in Trade.get_open_trades():
            price = self._last_price(t.pair)
            if price:
                unrealized += t.calc_profit(price)
                parts.append(f"{t.pair.split('/')[0]} {t.calc_profit_ratio(price):+.1%}")
            else:
                parts.append(t.pair.split("/")[0])
        equity = start + closed + unrealized
        today = self._period_profits(local)["Heute"]
        line2 = "Offen: " + (", ".join(parts) if parts else "nichts, wartet auf Signal")
        if self.halt_file.exists():
            line2 += " | Notbremse aktiv"
        return (f"Status {local:%H:%M}: {equity:.2f} {cur} ({(equity / start - 1) if start else 0:+.1%}), "
                f"heute {today:+.2f}\n{line2}")

    def _send_status(self, now: datetime) -> None:
        if now.replace(tzinfo=None) - self._last_status < self.status_interval:
            return
        self._last_status = now.replace(tzinfo=None)
        self.dp.send_msg(self.build_status(now), always_send=True)
