"""Kalshi pricing normalization.

Kalshi orderbooks expose bid arrays. A YES ask can be derived from the best
NO bid, and a NO ask can be derived from the best YES bid.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .models import AskSource, PricingQuote, TradableState

ASK_DISAGREE_TOLERANCE = 0.01


def parse_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price <= 0.0 or price >= 1.0:
        return None
    return round(price, 4)


def best_bid(book_side: Any) -> Optional[float]:
    if not isinstance(book_side, list):
        return None
    bids = []
    for row in book_side:
        if not isinstance(row, (list, tuple)) or not row:
            continue
        price = parse_price(row[0])
        if price is not None:
            bids.append(price)
    return max(bids) if bids else None


def ask_from_orderbook(orderbook: Mapping[str, Any], side: str) -> Optional[float]:
    book = orderbook.get("orderbook_fp") if isinstance(orderbook, Mapping) else None
    if not isinstance(book, Mapping):
        return None
    if side == "yes":
        no_bid = best_bid(book.get("no_dollars"))
        return round(1.0 - no_bid, 4) if no_bid is not None else None
    if side == "no":
        yes_bid = best_bid(book.get("yes_dollars"))
        return round(1.0 - yes_bid, 4) if yes_bid is not None else None
    raise ValueError("side must be yes or no")


def fee_band(price: Optional[float]) -> Optional[str]:
    if price is None:
        return None
    return "extreme" if price <= 0.25 or price >= 0.75 else "mid"


def price_quote(market: Mapping[str, Any], orderbook: Optional[Mapping[str, Any]] = None, *, intended_side: str = "yes") -> PricingQuote:
    yes_reported = parse_price(market.get("yes_ask_dollars"))
    no_reported = parse_price(market.get("no_ask_dollars"))
    orderbook = orderbook or {}
    yes_derived = ask_from_orderbook(orderbook, "yes")
    no_derived = ask_from_orderbook(orderbook, "no")
    reported = yes_reported
    derived = yes_derived
    if reported is not None and derived is not None:
        ask_source = AskSource.AGREE if abs(reported - derived) <= ASK_DISAGREE_TOLERANCE else AskSource.DISAGREE
    elif reported is not None:
        ask_source = AskSource.REPORTED_ONLY
    elif derived is not None:
        ask_source = AskSource.DERIVED_ONLY
    else:
        ask_source = AskSource.REPORTED_ONLY if no_reported is not None else AskSource.DERIVED_ONLY if no_derived is not None else AskSource.REPORTED_ONLY

    if intended_side == "yes":
        intended = _side_price(yes_reported, yes_derived, ask_source)
    elif intended_side == "no":
        intended = _side_price(no_reported, no_derived, ask_source)
    else:
        raise ValueError("intended_side must be yes or no")

    return PricingQuote(
        yes_ask_reported=yes_reported,
        yes_ask_derived=yes_derived,
        no_ask_reported=no_reported,
        no_ask_derived=no_derived,
        ask_source=ask_source.value,
        intended_side_price=intended,
        fee_band=fee_band(intended),
    )


def tradable_state(
    market: Mapping[str, Any],
    quote: PricingQuote,
    *,
    quote_age_seconds: Optional[float],
    quote_stale_seconds: int,
    event_before_cutoff: bool = True,
    match_ambiguous: bool = False,
) -> str:
    if match_ambiguous:
        return TradableState.MATCH_AMBIGUOUS.value
    status = str(market.get("status") or "").strip().lower()
    result = str(market.get("result") or market.get("expiration_value") or "").strip()
    if result:
        return TradableState.SETTLED.value
    if status in {"closed", "finalized"}:
        return TradableState.CLOSED.value
    if status in {"initialized", "unopened"}:
        return TradableState.LISTED_UNOPENED.value
    if status in {"tbd", "pending"}:
        return TradableState.LISTED_TBD.value
    if status not in {"open", "active"}:
        return TradableState.LISTED_UNOPENED.value
    if quote.ask_source == AskSource.DISAGREE.value:
        return TradableState.STALE.value
    if quote_age_seconds is not None and quote_age_seconds > quote_stale_seconds:
        return TradableState.STALE.value
    if not event_before_cutoff:
        return TradableState.CLOSED.value
    if quote.intended_side_price is None:
        return TradableState.OPEN_NO_QUOTE.value
    return TradableState.OPEN_TRADABLE.value


def _side_price(reported: Optional[float], derived: Optional[float], ask_source: AskSource) -> Optional[float]:
    if ask_source == AskSource.DISAGREE:
        return None
    if reported is not None:
        return reported
    return derived
