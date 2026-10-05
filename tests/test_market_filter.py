import json
from datetime import UTC, datetime

import pytest

from market_filter import MarketFilter, parse_rss


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "market_filter.json"
    path.write_text(json.dumps({
        "fear_greed_max_entry": 85,
        "event_blackout_hours_before": 12,
        "event_blackout_hours_after": 2,
        "events": [{"name": "FOMC", "time": "2026-10-28T18:00:00Z"}],
        "news_feeds": [],
        "news_keywords": ["hack"],
    }))
    return path


def test_blackout_window(settings):
    mf = MarketFilter(settings)
    mf._fg_fetched_at = float("inf")  # kein Netz im Test
    assert mf.entry_block_reason(datetime(2026, 10, 28, 6, 0, tzinfo=UTC)) is not None
    assert mf.entry_block_reason(datetime(2026, 10, 28, 19, 59, tzinfo=UTC)) is not None
    assert mf.entry_block_reason(datetime(2026, 10, 28, 5, 59, tzinfo=UTC)) is None
    assert mf.entry_block_reason(datetime(2026, 10, 28, 20, 1, tzinfo=UTC)) is None


def test_fear_greed_limit(settings):
    mf = MarketFilter(settings)
    mf._fg_fetched_at = float("inf")
    now = datetime(2026, 11, 5, tzinfo=UTC)
    mf._fg_value, mf._fg_label = 90, "Extreme Greed"
    assert "Fear & Greed" in mf.entry_block_reason(now)
    mf._fg_value = 60
    assert mf.entry_block_reason(now) is None
    mf._fg_value = None  # Quelle ausgefallen -> nicht blockieren
    assert mf.entry_block_reason(now) is None


def test_missing_settings_file(tmp_path):
    mf = MarketFilter(tmp_path / "fehlt.json")
    mf._fg_fetched_at = float("inf")
    assert mf.entry_block_reason(datetime.now(UTC)) is None


def test_parse_rss_and_atom():
    rss = b"""<rss><channel>
      <item><title>Exchange hack drains funds</title><link>https://a/1</link></item>
      <item><title>Quiet day</title><link>https://a/2</link></item>
    </channel></rss>"""
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Atom title</title><link href="https://b/1"/></entry>
    </feed>"""
    assert [h.link for h in parse_rss(rss, "A")] == ["https://a/1", "https://a/2"]
    assert parse_rss(atom, "B")[0].title == "Atom title"


def test_headlines_keyword_filter_and_dedup(settings, tmp_path, monkeypatch):
    state = tmp_path / "seen.json"
    mf = MarketFilter(settings, state)
    mf.settings["news_feeds"] = [{"name": "A", "url": "https://a/rss"}]
    rss = b"""<rss><channel>
      <item><title>Exchange HACK drains funds</title><link>https://a/1</link></item>
      <item><title>Quiet day</title><link>https://a/2</link></item>
    </channel></rss>"""
    monkeypatch.setattr(mf, "_fetch_feed", lambda name, url: parse_rss(rss, name))
    assert [h.link for h in mf.new_headlines()] == ["https://a/1"]
    assert mf.new_headlines() == []
    # nach Neustart bleiben gesehene News gemerkt
    assert MarketFilter(settings, state)._seen_links == ["https://a/1", "https://a/2"]
