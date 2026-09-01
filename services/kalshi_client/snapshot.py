"""Build read-only Kalshi MLB market snapshots."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .client import KALSHI_BASE_URL, KalshiClient
from .models import NormalizedMarket
from .normalize import (
    display_player_from_title,
    freshness_label,
    parse_event_ticker,
    parse_threshold,
    quote_age_seconds,
    settlement_note_for_series,
    side_mapping,
    slate_market_for_series,
)
from .pricing import price_quote, tradable_state
from .urls import market_url

KNOWN_SERIES = (
    "KXMLBHR",
    "KXMLBTOTAL",
    "KXMLBKS",
    "KXMLBHIT",
    "KXMLBTB",
    "KXMLBHRR",
    "KXMLBTEAMTOTAL",
    "KXMLBHA",
)
INTEREST_CHECKS = {
    "hits": ("KXMLBHIT", "KXMLBHITS"),
    "total_bases": ("KXMLBTB",),
    "hrr": ("KXMLBHRR",),
    "nrfi": ("KXMLBNRFI",),
    "team_totals": ("KXMLBTEAMTOTAL", "KXMLBTT"),
}


def discover_mlb_series(client: KalshiClient) -> list[dict[str, str]]:
    payload = client.series(category="Sports", tags="Baseball", limit=200)
    found = []
    for row in payload.get("series") or []:
        ticker = str(row.get("ticker") or "")
        title = str(row.get("title") or "")
        if ticker.startswith("KXMLB") or "Pro Baseball" in title or "MLB" in title:
            found.append({"series_ticker": ticker, "title": title})
    found.sort(key=lambda row: row["series_ticker"])
    return found


def check_interest_series(client: KalshiClient) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, tickers in INTEREST_CHECKS.items():
        matches = []
        for ticker in tickers:
            try:
                payload = client.series_detail(ticker)
            except Exception:
                continue
            series = payload.get("series") or {}
            if series:
                matches.append({"series_ticker": ticker, "title": series.get("title")})
        out[label] = matches
    return out


def build_snapshot(
    slate_date: str,
    *,
    client: Optional[KalshiClient] = None,
    series_tickers: tuple[str, ...] = KNOWN_SERIES,
) -> dict[str, Any]:
    client = client or KalshiClient()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    max_pages = _env_int("KALSHI_MAX_MARKET_PAGES", 3)
    max_orderbooks = _env_int("KALSHI_MAX_ORDERBOOK_CALLS", 25)
    quote_stale_seconds = _env_int("KALSHI_QUOTE_STALE_SECONDS", 180)
    records = []
    orderbook_calls = 0
    fetch_error = None
    try:
        for series in series_tickers:
            events = client.paged_events(series_ticker=series, max_pages=max_pages)
            slate_events = [event for event in events if _event_slate_date(event) == slate_date]
            for event in slate_events:
                event_ticker = str(event.get("event_ticker") or "")
                markets = client.paged_markets(
                    series_ticker=series,
                    event_ticker=event_ticker,
                    max_pages=max_pages,
                )
                for market in markets:
                    orderbook = None
                    if orderbook_calls < max_orderbooks:
                        try:
                            orderbook = client.orderbook(str(market.get("ticker") or ""))
                            orderbook_calls += 1
                        except Exception:
                            orderbook = None
                    records.append(
                        normalize_market(
                            market,
                            event=event,
                            orderbook=orderbook,
                            quote_stale_seconds=quote_stale_seconds,
                        ).as_dict()
                    )
    except Exception as exc:
        fetch_error = f"{type(exc).__name__}: {exc}"
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "base_url": KALSHI_BASE_URL,
        "slate_date": slate_date,
        "fetch_ok": fetch_error is None,
        "fetch_error": fetch_error,
        "request_count": client.request_count,
        "markets": records,
    }


def normalize_market(
    market: Mapping[str, Any],
    *,
    event: Optional[Mapping[str, Any]] = None,
    orderbook: Optional[Mapping[str, Any]] = None,
    quote_stale_seconds: int = 180,
    now_ts: Optional[float] = None,
) -> NormalizedMarket:
    event_ticker = str(market.get("event_ticker") or (event or {}).get("event_ticker") or "")
    parsed = parse_event_ticker(event_ticker)
    series = str(market.get("series_ticker") or parsed.get("series_ticker") or event_ticker.split("-", 1)[0])
    side = side_mapping(market, "over")
    quote = price_quote(market, orderbook, intended_side=side.kalshi_side)
    age = quote_age_seconds(market, now_ts)
    freshness = freshness_label(age, quote_stale_seconds)
    state = tradable_state(
        market,
        quote,
        quote_age_seconds=age,
        quote_stale_seconds=quote_stale_seconds,
        event_before_cutoff=True,
    )
    title = str(market.get("title") or "")
    threshold = market.get("floor_strike")
    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError):
        threshold_value = parse_threshold(title) or parse_threshold(market.get("rules_primary"))
    return NormalizedMarket(
        series_ticker=series,
        event_ticker=event_ticker,
        market_ticker=str(market.get("ticker") or ""),
        title=title,
        market_family=series,
        slate_date=str(parsed.get("slate_date") or ""),
        away_team=parsed.get("away_team"),
        home_team=parsed.get("home_team"),
        player_name=display_player_from_title(title),
        team=_team_from_market_ticker(market),
        threshold=threshold_value,
        slate_market=slate_market_for_series(series),
        slate_side=side.slate_side,
        kalshi_side=side.kalshi_side,
        yes_ask_reported=quote.yes_ask_reported,
        yes_ask_derived=quote.yes_ask_derived,
        ask_source=quote.ask_source,
        tradable_state=state,
        quote_age_seconds=age,
        freshness=freshness,
        fee_band=quote.fee_band,
        settlement_note=settlement_note_for_series(series),
        url=market_url(series, event_ticker),
        raw_status=str(market.get("status") or ""),
        rules_primary=str(market.get("rules_primary") or ""),
    )


def _event_slate_date(event: Mapping[str, Any]) -> str:
    parsed = parse_event_ticker(str(event.get("event_ticker") or ""))
    return str(parsed.get("slate_date") or "")


def _team_from_market_ticker(market: Mapping[str, Any]) -> Optional[str]:
    ticker = str(market.get("ticker") or "")
    event_ticker = str(market.get("event_ticker") or "")
    suffix = ticker[len(event_ticker):].lstrip("-") if event_ticker and ticker.startswith(event_ticker) else ""
    if len(suffix) >= 2:
        from .normalize import KNOWN_TEAMS, canonical_team

        for size in (3, 2):
            candidate = canonical_team(suffix[:size])
            if candidate in KNOWN_TEAMS:
                return candidate
    return None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value
