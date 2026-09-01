"""Sole owner of Kalshi web URL construction."""

from __future__ import annotations

import re
from typing import Any, Mapping

KALSHI_WEB_BASE = "https://kalshi.com/markets"


def market_url(series_ticker: str, event_ticker: str) -> str:
    series = str(series_ticker or "").strip().lower()
    event = str(event_ticker or "").strip()
    if not series or not event or not re.fullmatch(r"[A-Z0-9-]+", event):
        return "COPY TICKER"
    return f"{KALSHI_WEB_BASE}/{series}/{_slug_for_series(series)}/{event}"


def market_url_for_record(record: Mapping[str, Any]) -> str:
    return market_url(str(record.get("series_ticker") or ""), str(record.get("event_ticker") or ""))


def _slug_for_series(series_ticker: str) -> str:
    return {
        "kxmlbhr": "pro-baseball-home-runs",
        "kxmlbtotal": "pro-baseball-total-runs",
        "kxmlbks": "pro-baseball-strikeouts",
        "kxmlbhit": "pro-baseball-hits",
        "kxmlbtb": "pro-baseball-total-bases",
        "kxmlbhrr": "pro-baseball-hits-runs-rbis",
        "kxmlbteamtotal": "pro-baseball-team-total",
        "kxmlbha": "pro-baseball-hits-allowed",
    }.get(series_ticker, series_ticker)
