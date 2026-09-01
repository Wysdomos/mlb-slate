"""Data models for normalized Kalshi market snapshots."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


class TradableState(str, Enum):
    NOT_LISTED = "NOT_LISTED"
    LISTED_UNOPENED = "LISTED_UNOPENED"
    LISTED_TBD = "LISTED_TBD"
    OPEN_NO_QUOTE = "OPEN_NO_QUOTE"
    OPEN_TRADABLE = "OPEN_TRADABLE"
    STALE = "STALE"
    CLOSED = "CLOSED"
    SETTLED = "SETTLED"
    MATCH_AMBIGUOUS = "MATCH_AMBIGUOUS"


class AskSource(str, Enum):
    AGREE = "agree"
    REPORTED_ONLY = "reported_only"
    DERIVED_ONLY = "derived_only"
    DISAGREE = "disagree"


@dataclass(frozen=True)
class SideMapping:
    slate_side: str
    kalshi_side: str
    yes_slate_side: str
    no_slate_side: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PricingQuote:
    yes_ask_reported: Optional[float]
    yes_ask_derived: Optional[float]
    no_ask_reported: Optional[float]
    no_ask_derived: Optional[float]
    ask_source: str
    intended_side_price: Optional[float]
    fee_band: Optional[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedMarket:
    series_ticker: str
    event_ticker: str
    market_ticker: str
    title: str
    market_family: str
    slate_date: str
    away_team: Optional[str]
    home_team: Optional[str]
    player_name: Optional[str]
    team: Optional[str]
    threshold: Optional[float]
    slate_market: str
    slate_side: str
    kalshi_side: str
    yes_ask_reported: Optional[float]
    yes_ask_derived: Optional[float]
    ask_source: str
    tradable_state: str
    quote_age_seconds: Optional[float]
    freshness: str
    fee_band: Optional[str]
    settlement_note: str
    url: str
    raw_status: str
    rules_primary: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
