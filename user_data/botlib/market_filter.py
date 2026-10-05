"""
Markt- und Newsfilter fuer den Trading-Bot.

Liefert drei Dinge, alle bewusst fehlertolerant (faellt eine Quelle aus,
wird normal weitergehandelt und nur geloggt):

- Fear & Greed Index (alternative.me), stuendlich gecacht
- Sperrfenster rund um wichtige Termine (US-Zinsentscheide, US-Inflation)
- Neue Schlagzeilen aus RSS-Feeds, gefiltert nach Stichworten

Die Einstellungen stehen in user_data/market_filter.json.
"""

from __future__ import annotations

import json
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests


logger = logging.getLogger(__name__)

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
HTTP_TIMEOUT = 10
USER_AGENT = "trading-bot (Raspberry Pi)"


@dataclass
class Event:
    name: str
    time: datetime


@dataclass
class Headline:
    title: str
    link: str
    source: str


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


class MarketFilter:
    def __init__(self, settings_path: Path, state_path: Path | None = None):
        self.settings_path = settings_path
        self.state_path = state_path
        self.settings = self._load_settings()
        self._fg_value: int | None = None
        self._fg_label: str | None = None
        self._fg_fetched_at = 0.0
        self._seen_links: list[str] = self._load_seen()

    # --- Einstellungen -------------------------------------------------

    def _load_settings(self) -> dict:
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.warning("market_filter.json nicht lesbar (%s), nutze Standardwerte", e)
            return {}

    @property
    def events(self) -> list[Event]:
        out = []
        for e in self.settings.get("events", []):
            try:
                out.append(Event(e["name"], _parse_time(e["time"])))
            except (KeyError, ValueError):
                logger.warning("Ungueltiger Termin in market_filter.json: %s", e)
        return out

    # --- Fear & Greed --------------------------------------------------

    def fear_greed(self) -> tuple[int | None, str | None]:
        """Aktueller Index (0 = extreme Angst, 100 = extreme Gier), max. 1x pro Stunde geladen."""
        if time.time() - self._fg_fetched_at < 3600:
            return self._fg_value, self._fg_label
        self._fg_fetched_at = time.time()
        try:
            r = requests.get(FEAR_GREED_URL, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            data = r.json()["data"][0]
            self._fg_value = int(data["value"])
            self._fg_label = data.get("value_classification")
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            logger.warning("Fear & Greed nicht abrufbar: %s", e)
        return self._fg_value, self._fg_label

    # --- Termine ---------------------------------------------------------

    def blocking_event(self, now: datetime) -> Event | None:
        """Termin, in dessen Sperrfenster `now` liegt, sonst None."""
        before = timedelta(hours=self.settings.get("event_blackout_hours_before", 12))
        after = timedelta(hours=self.settings.get("event_blackout_hours_after", 2))
        for e in self.events:
            if e.time - before <= now <= e.time + after:
                return e
        return None

    def upcoming_events(self, now: datetime, days: int = 7) -> list[Event]:
        horizon = now + timedelta(days=days)
        return sorted((e for e in self.events if now <= e.time <= horizon), key=lambda e: e.time)

    # --- Einstiegsfilter ---------------------------------------------

    def entry_block_reason(self, now: datetime) -> str | None:
        """Grund, warum gerade kein neuer Kauf erfolgen soll, oder None."""
        event = self.blocking_event(now)
        if event:
            return f"Sperrfenster wegen {event.name} ({event.time:%d.%m. %H:%M} UTC)"
        limit = self.settings.get("fear_greed_max_entry")
        if limit is not None:
            value, label = self.fear_greed()
            if value is not None and value >= limit:
                return f"Fear & Greed bei {value} ({label}), Grenze {limit}"
        return None

    # --- Schlagzeilen ---------------------------------------------------

    def new_headlines(self) -> list[Headline]:
        """Neue, relevante Schlagzeilen seit dem letzten Aufruf."""
        keywords = [k.lower() for k in self.settings.get("news_keywords", [])]
        found: list[Headline] = []
        for feed in self.settings.get("news_feeds", []):
            for h in self._fetch_feed(feed.get("name", "?"), feed.get("url", "")):
                if h.link in self._seen_links:
                    continue
                self._seen_links.append(h.link)
                if not keywords or any(k in h.title.lower() for k in keywords):
                    found.append(h)
        self._seen_links = self._seen_links[-500:]
        self._save_seen()
        return found

    def _fetch_feed(self, name: str, url: str) -> list[Headline]:
        if not url:
            return []
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            return parse_rss(r.content, name)
        except (requests.RequestException, ET.ParseError) as e:
            logger.warning("Feed %s nicht abrufbar: %s", name, e)
            return []

    def _load_seen(self) -> list[str]:
        if not self.state_path:
            return []
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _save_seen(self) -> None:
        if not self.state_path:
            return
        try:
            self.state_path.write_text(json.dumps(self._seen_links), encoding="utf-8")
        except OSError as e:
            logger.warning("Konnte gesehene News nicht speichern: %s", e)


def parse_rss(content: bytes, source: str) -> list[Headline]:
    """Liest RSS 2.0 und Atom."""
    root = ET.fromstring(content)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:
            out.append(Headline(title, link, source))
    atom = "{http://www.w3.org/2005/Atom}"
    for entry in root.iter(f"{atom}entry"):
        title = (entry.findtext(f"{atom}title") or "").strip()
        link_el = entry.find(f"{atom}link")
        link = link_el.get("href", "").strip() if link_el is not None else ""
        if title and link:
            out.append(Headline(title, link, source))
    return out
