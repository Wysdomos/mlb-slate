"""Match slate-side candidates to normalized Kalshi market snapshots."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from .models import AskSource, TradableState
from .normalize import canonical_player_name, canonical_team, parse_event_ticker, quote_age_seconds, side_mapping
from .pricing import ASK_DISAGREE_TOLERANCE, parse_price

SCHEMA_VERSION = 1
SERIES_BY_MARKET = {
    "pitcher_strikeouts": "KXMLBKS",
    "batter_home_runs": "KXMLBHR",
    "batter_hrr": "KXMLBHRR",
    "batter_hits": "KXMLBHIT",
    "batter_total_bases": "KXMLBTB",
    "game_total": "KXMLBTOTAL",
    "run_first_inning": "KXMLBRFI",
}
EDGE_ALLOWED_PROBABILITY_KIND = "calibrated_probability"
PRE_FEE_PRICE_BASIS = "PRE_FEE"
DEFAULT_QUOTE_STALE_SECONDS = 180


@dataclass(frozen=True)
class MatchRecord:
    slate_id: str
    slate_market: str
    slate_signal: Any
    probability_kind: str
    edge_allowed: bool
    kalshi_ticker: Optional[str]
    event_ticker: Optional[str]
    series_ticker: Optional[str]
    match_confidence: int
    match_gates_passed: list[str]
    slate_side: Optional[str]
    kalshi_side: Optional[str]
    buy_price: Optional[float]
    price_basis: str
    ask_source: Optional[str]
    fee_band: Optional[str]
    available_strikes: list[float]
    tradable_state: str
    quote_ts: Optional[str]
    settlement_note: Optional[str]
    url: Optional[str]
    url_kind: str
    display: dict[str, str]
    ambiguous_survivors: Optional[list[dict[str, Any]]] = None
    reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def build_match_snapshot(
    candidates: Iterable[Mapping[str, Any]],
    kalshi_snapshot: Mapping[str, Any],
    *,
    slate_date: Optional[str] = None,
    quote_stale_seconds: int = DEFAULT_QUOTE_STALE_SECONDS,
    now_ts: Optional[float] = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    candidates_list = [candidate for candidate in candidates if isinstance(candidate, Mapping)]
    resolved_slate_date = slate_date or str(kalshi_snapshot.get("slate_date") or _first_candidate_date(candidates_list) or "")
    if not kalshi_snapshot.get("fetch_ok", False):
        return _failure_snapshot(
            generated_at,
            resolved_slate_date,
            f"kalshi_markets.json fetch_ok=false: {kalshi_snapshot.get('fetch_error') or 'unknown error'}",
        )
    if str(kalshi_snapshot.get("slate_date") or "") != str(resolved_slate_date):
        return _failure_snapshot(
            generated_at,
            resolved_slate_date,
            f"stale kalshi_markets.json: expected {resolved_slate_date}, found {kalshi_snapshot.get('slate_date')}",
        )
    markets = [market for market in kalshi_snapshot.get("markets") or [] if isinstance(market, Mapping)]
    matches = [
        match_candidate(candidate, markets, quote_stale_seconds=quote_stale_seconds, now_ts=now_ts).as_dict()
        for candidate in candidates_list
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "slate_date": resolved_slate_date,
        "fetch_ok": True,
        "fetch_error": None,
        "counts": count_matches(matches),
        "matches": matches,
    }


def match_candidate(
    candidate: Mapping[str, Any],
    markets: Iterable[Mapping[str, Any]],
    *,
    quote_stale_seconds: int = DEFAULT_QUOTE_STALE_SECONDS,
    now_ts: Optional[float] = None,
) -> MatchRecord:
    market_type = str(candidate.get("market_type") or "")
    slate_side = _candidate_side(candidate)
    edge_allowed = candidate.get("probability_kind") == EDGE_ALLOWED_PROBABILITY_KIND
    if not candidate.get("matchable"):
        return _not_listed(candidate, [], reason=str(candidate.get("reason") or "candidate_unmatchable"))
    expected_series = SERIES_BY_MARKET.get(market_type)
    if expected_series is None:
        return _not_listed(candidate, [], reason="no_kalshi_series")

    evaluated = [_evaluate_market(candidate, market, expected_series, quote_stale_seconds, now_ts) for market in markets]
    survivors = [row for row in evaluated if row["passes"]]
    if len(survivors) > 1:
        top_score = max(row["confidence"] for row in survivors)
        tied = [row for row in survivors if row["confidence"] == top_score]
        if len(tied) > 1:
            strikes = sorted({strike for row in tied for strike in row["available_strikes"]})
            return MatchRecord(
                slate_id=str(candidate.get("slate_id") or ""),
                slate_market=market_type,
                slate_signal=_slate_signal(candidate),
                probability_kind=str(candidate.get("probability_kind") or ""),
                edge_allowed=edge_allowed,
                kalshi_ticker=None,
                event_ticker=None,
                series_ticker=expected_series,
                match_confidence=top_score,
                match_gates_passed=tied[0]["gates"],
                slate_side=slate_side,
                kalshi_side=None,
                buy_price=None,
                price_basis=PRE_FEE_PRICE_BASIS,
                ask_source=None,
                fee_band=None,
                available_strikes=strikes,
                tradable_state=TradableState.MATCH_AMBIGUOUS.value,
                quote_ts=None,
                settlement_note=None,
                url=None,
                url_kind="none",
                display=_display(TradableState.MATCH_AMBIGUOUS.value, None, None),
                ambiguous_survivors=[_survivor_summary(row["market"], row["confidence"]) for row in tied],
                reason="multiple_equal_survivors",
            )

    if not survivors:
        strikes = available_strikes_for_candidate(candidate, evaluated)
        reason = "threshold_not_listed" if strikes else "not_listed"
        return _not_listed(candidate, strikes, reason=reason)

    row = survivors[0]
    market = row["market"]
    quote = _buy_quote(market, row["kalshi_side"])
    state = _tradable_state_for_match(market, quote, quote_stale_seconds=quote_stale_seconds, now_ts=now_ts)
    url = _market_url(market)
    return MatchRecord(
        slate_id=str(candidate.get("slate_id") or ""),
        slate_market=market_type,
        slate_signal=_slate_signal(candidate),
        probability_kind=str(candidate.get("probability_kind") or ""),
        edge_allowed=edge_allowed,
        kalshi_ticker=_market_ticker(market),
        event_ticker=str(market.get("event_ticker") or ""),
        series_ticker=row["series"],
        match_confidence=row["confidence"],
        match_gates_passed=row["gates"],
        slate_side=slate_side,
        kalshi_side=row["kalshi_side"],
        buy_price=quote["buy_price"],
        price_basis=PRE_FEE_PRICE_BASIS,
        ask_source=quote["ask_source"],
        fee_band=_fee_band(quote["buy_price"]),
        available_strikes=row["available_strikes"],
        tradable_state=state,
        quote_ts=_quote_ts(market),
        settlement_note=str(market.get("settlement_note") or ""),
        url=url,
        url_kind="direct" if url and url != "COPY TICKER" else "copy_ticker",
        display=_display(state, quote["buy_price"], _quote_age(market, now_ts)),
        reason=None,
    )


def available_strikes_for_candidate(candidate: Mapping[str, Any], evaluated: Iterable[Mapping[str, Any]]) -> list[float]:
    compatible = []
    for row in evaluated:
        gates = set(row["gates"])
        if {"sport", "date", "game", "family", "player"}.issubset(gates):
            compatible.extend(row["available_strikes"])
    return sorted(set(compatible))


def count_matches(matches: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"matched": 0, "live": 0, "tbd": 0, "no_quote": 0, "not_listed": 0, "ambiguous": 0}
    for row in matches:
        state = str(row.get("tradable_state") or "")
        if state == TradableState.NOT_LISTED.value:
            counts["not_listed"] += 1
        elif state == TradableState.MATCH_AMBIGUOUS.value:
            counts["ambiguous"] += 1
        else:
            counts["matched"] += 1
        if state == TradableState.OPEN_TRADABLE.value:
            counts["live"] += 1
        elif state in {TradableState.LISTED_TBD.value, TradableState.LISTED_UNOPENED.value}:
            counts["tbd"] += 1
        elif state == TradableState.OPEN_NO_QUOTE.value:
            counts["no_quote"] += 1
    return counts


def coverage_by_market(candidates: Iterable[Mapping[str, Any]], matches: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    by_id = {str(row.get("slate_id") or ""): row for row in matches}
    out: dict[str, dict[str, int]] = {}
    for candidate in candidates:
        if not candidate.get("matchable"):
            continue
        market = str(candidate.get("market_type") or "")
        bucket = out.setdefault(market, {"candidates": 0, "matched": 0, "live": 0, "not_listed": 0, "ambiguous": 0})
        bucket["candidates"] += 1
        match = by_id.get(str(candidate.get("slate_id") or ""))
        if not match:
            continue
        state = str(match.get("tradable_state") or "")
        if state == TradableState.NOT_LISTED.value:
            bucket["not_listed"] += 1
        elif state == TradableState.MATCH_AMBIGUOUS.value:
            bucket["ambiguous"] += 1
        else:
            bucket["matched"] += 1
        if state == TradableState.OPEN_TRADABLE.value:
            bucket["live"] += 1
    return out


def missing_exact_strikes(matches: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for match in matches:
        if match.get("tradable_state") != TradableState.NOT_LISTED.value:
            continue
        if match.get("reason") != "threshold_not_listed":
            continue
        rows.append(
            {
                "slate_id": match.get("slate_id"),
                "slate_market": match.get("slate_market"),
                "available_strikes": match.get("available_strikes") or [],
            }
        )
    return rows


def _evaluate_market(
    candidate: Mapping[str, Any],
    market: Mapping[str, Any],
    expected_series: str,
    quote_stale_seconds: int,
    now_ts: Optional[float],
) -> dict[str, Any]:
    del quote_stale_seconds
    del now_ts
    gates: list[str] = []
    confidence = 0
    series = _series_ticker(market)
    threshold = _market_threshold(market)
    available_strikes = [threshold] if threshold is not None else []
    if not _is_mlb_market(market, series):
        return _evaluation(market, False, confidence, gates, series, None, available_strikes)
    gates.append("sport")
    if _market_slate_date(market) != str(candidate.get("slate_date") or ""):
        return _evaluation(market, False, confidence, gates, series, None, available_strikes)
    gates.append("date")
    confidence += 10
    if _market_game_key(market) != str(candidate.get("game_key") or ""):
        return _evaluation(market, False, confidence, gates, series, None, available_strikes)
    gates.append("game")
    confidence += 30
    if series != expected_series:
        return _evaluation(market, False, confidence, gates, series, None, available_strikes)
    gates.append("family")
    confidence += 20
    if not _player_gate(candidate, market):
        return _evaluation(market, False, confidence, gates, series, None, available_strikes)
    gates.append("player")
    confidence += 25
    if not _thresholds_equal(candidate.get("threshold"), threshold):
        return _evaluation(market, False, confidence, gates, series, None, available_strikes)
    gates.append("threshold")
    confidence += 15
    mapped_side = _mapped_side(candidate, market)
    if mapped_side is None:
        return _evaluation(market, False, confidence, gates, series, None, available_strikes)
    gates.append("side")
    return _evaluation(market, True, confidence, gates, series, mapped_side, available_strikes)


def _evaluation(
    market: Mapping[str, Any],
    passes: bool,
    confidence: int,
    gates: list[str],
    series: str,
    kalshi_side: Optional[str],
    available_strikes: list[float],
) -> dict[str, Any]:
    return {
        "market": market,
        "passes": passes,
        "confidence": confidence,
        "gates": gates,
        "series": series,
        "kalshi_side": kalshi_side,
        "available_strikes": available_strikes,
    }


def _not_listed(candidate: Mapping[str, Any], available_strikes: list[float], *, reason: str) -> MatchRecord:
    return MatchRecord(
        slate_id=str(candidate.get("slate_id") or ""),
        slate_market=str(candidate.get("market_type") or ""),
        slate_signal=_slate_signal(candidate),
        probability_kind=str(candidate.get("probability_kind") or ""),
        edge_allowed=candidate.get("probability_kind") == EDGE_ALLOWED_PROBABILITY_KIND,
        kalshi_ticker=None,
        event_ticker=None,
        series_ticker=SERIES_BY_MARKET.get(str(candidate.get("market_type") or "")),
        match_confidence=0,
        match_gates_passed=[],
        slate_side=_candidate_side(candidate),
        kalshi_side=None,
        buy_price=None,
        price_basis=PRE_FEE_PRICE_BASIS,
        ask_source=None,
        fee_band=None,
        available_strikes=available_strikes,
        tradable_state=TradableState.NOT_LISTED.value,
        quote_ts=None,
        settlement_note=None,
        url=None,
        url_kind="none",
        display=_display(TradableState.NOT_LISTED.value, None, None),
        reason=reason,
    )


def _failure_snapshot(generated_at: str, slate_date: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "slate_date": slate_date,
        "fetch_ok": False,
        "fetch_error": message,
        "counts": {"matched": 0, "live": 0, "tbd": 0, "no_quote": 0, "not_listed": 0, "ambiguous": 0},
        "matches": [],
    }


def _survivor_summary(market: Mapping[str, Any], confidence: int) -> dict[str, Any]:
    return {
        "kalshi_ticker": _market_ticker(market),
        "event_ticker": str(market.get("event_ticker") or ""),
        "series_ticker": _series_ticker(market),
        "threshold": _market_threshold(market),
        "confidence": confidence,
    }


def _is_mlb_market(market: Mapping[str, Any], series: str) -> bool:
    sport = str(market.get("sport") or market.get("sport_name") or "").strip().upper()
    if sport:
        return sport == "MLB"
    return series.startswith("KXMLB")


def _series_ticker(market: Mapping[str, Any]) -> str:
    series = str(market.get("series_ticker") or "").strip().upper()
    if series:
        return series
    event_ticker = str(market.get("event_ticker") or "")
    return event_ticker.split("-", 1)[0].upper() if "-" in event_ticker else ""


def _market_slate_date(market: Mapping[str, Any]) -> str:
    value = str(market.get("slate_date") or "").strip()
    if value:
        return value[:10]
    parsed = parse_event_ticker(str(market.get("event_ticker") or ""))
    return str(parsed.get("slate_date") or "")


def _market_game_key(market: Mapping[str, Any]) -> Optional[str]:
    away = canonical_team(market.get("away_team"))
    home = canonical_team(market.get("home_team"))
    if away and home:
        return f"{away}@{home}"
    parsed = parse_event_ticker(str(market.get("event_ticker") or ""))
    away = canonical_team(parsed.get("away_team"))
    home = canonical_team(parsed.get("home_team"))
    return f"{away}@{home}" if away and home else None


def _market_threshold(market: Mapping[str, Any]) -> Optional[float]:
    value = market.get("threshold")
    if value is None:
        value = market.get("floor_strike")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _thresholds_equal(left: Any, right: Any) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


def _player_gate(candidate: Mapping[str, Any], market: Mapping[str, Any]) -> bool:
    if not _candidate_has_player(candidate):
        return True
    candidate_player = str(candidate.get("player_norm") or "")
    market_player = canonical_player_name(market.get("player_name") or _player_from_title(market))
    if candidate_player != market_player:
        return False
    candidate_team = _candidate_team(candidate)
    market_team = canonical_team(market.get("team"))
    if not candidate_team or not market_team:
        return False
    return candidate_team == market_team


def _candidate_has_player(candidate: Mapping[str, Any]) -> bool:
    return bool(candidate.get("player_norm"))


def _candidate_team(candidate: Mapping[str, Any]) -> Optional[str]:
    explicit = canonical_team(candidate.get("team"))
    if explicit:
        return explicit
    slate_id = str(candidate.get("slate_id") or "")
    player = _id_token(candidate.get("player_norm"))
    market = _id_token(candidate.get("market_type"))
    marker = f"_{player}_" if player else ""
    market_marker = f"_{market}_" if market else ""
    if not marker or not market_marker or marker not in slate_id or market_marker not in slate_id:
        return None
    after_player = slate_id.split(marker, 1)[1]
    team_token = after_player.split(market_marker, 1)[0].strip("_")
    team = canonical_team(team_token)
    return team or None


def _player_from_title(market: Mapping[str, Any]) -> Optional[str]:
    title = str(market.get("title") or "")
    if ":" not in title:
        return None
    return title.split(":", 1)[0].strip() or None


def _mapped_side(candidate: Mapping[str, Any], market: Mapping[str, Any]) -> Optional[str]:
    slate_side = _candidate_side(candidate)
    if not slate_side:
        return None
    if str(candidate.get("market_type") or "") == "run_first_inning":
        return "no" if slate_side == "no" else "yes"
    if slate_side in {"yes", "no"}:
        return slate_side
    mapping = side_mapping(market, slate_side)
    return mapping.kalshi_side


def _candidate_side(candidate: Mapping[str, Any]) -> Optional[str]:
    side = str(candidate.get("direction") or "").strip().lower()
    return side or None


def _buy_quote(market: Mapping[str, Any], kalshi_side: Optional[str]) -> dict[str, Any]:
    if kalshi_side == "yes":
        reported = _first_price(market, "yes_ask_reported", "yes_ask_dollars")
        derived = _first_price(market, "yes_ask_derived")
    elif kalshi_side == "no":
        reported = _first_price(market, "no_ask_reported", "no_ask_dollars")
        derived = _first_price(market, "no_ask_derived")
        if derived is None:
            yes_bid = _first_price(market, "yes_bid_reported", "yes_bid_dollars")
            if yes_bid is not None:
                derived = round(1.0 - yes_bid, 4)
    else:
        return {"buy_price": None, "ask_source": None}
    ask_source = _ask_source(reported, derived)
    if ask_source == AskSource.DISAGREE.value:
        return {"buy_price": None, "ask_source": ask_source}
    return {"buy_price": reported if reported is not None else derived, "ask_source": ask_source}


def _first_price(market: Mapping[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        price = parse_price(market.get(key))
        if price is not None:
            return price
    return None


def _ask_source(reported: Optional[float], derived: Optional[float]) -> Optional[str]:
    if reported is not None and derived is not None:
        return AskSource.AGREE.value if abs(reported - derived) <= ASK_DISAGREE_TOLERANCE else AskSource.DISAGREE.value
    if reported is not None:
        return AskSource.REPORTED_ONLY.value
    if derived is not None:
        return AskSource.DERIVED_ONLY.value
    return None


def _tradable_state_for_match(
    market: Mapping[str, Any],
    quote: Mapping[str, Any],
    *,
    quote_stale_seconds: int,
    now_ts: Optional[float],
) -> str:
    raw_state = str(market.get("tradable_state") or "")
    if raw_state in {
        TradableState.LISTED_UNOPENED.value,
        TradableState.LISTED_TBD.value,
        TradableState.CLOSED.value,
        TradableState.SETTLED.value,
        TradableState.STALE.value,
    }:
        return raw_state
    status = str(market.get("raw_status") or market.get("status") or "").strip().lower()
    result = str(market.get("result") or market.get("expiration_value") or "").strip()
    if result:
        return TradableState.SETTLED.value
    if status in {"closed", "finalized"}:
        return TradableState.CLOSED.value
    if status in {"initialized", "unopened"}:
        return TradableState.LISTED_UNOPENED.value
    if status in {"tbd", "pending"}:
        return TradableState.LISTED_TBD.value
    if quote.get("ask_source") == AskSource.DISAGREE.value:
        return TradableState.STALE.value
    age = _quote_age(market, now_ts)
    if age is not None and age > quote_stale_seconds:
        return TradableState.STALE.value
    if quote.get("buy_price") is None:
        return TradableState.OPEN_NO_QUOTE.value
    return TradableState.OPEN_TRADABLE.value


def _quote_age(market: Mapping[str, Any], now_ts: Optional[float]) -> Optional[float]:
    if market.get("quote_age_seconds") is not None:
        try:
            return float(market["quote_age_seconds"])
        except (TypeError, ValueError):
            return None
    return quote_age_seconds(market, now_ts)


def _quote_ts(market: Mapping[str, Any]) -> Optional[str]:
    value = market.get("updated_time") or market.get("last_updated_ts") or market.get("quote_ts")
    return str(value) if value else None


def _market_ticker(market: Mapping[str, Any]) -> str:
    return str(market.get("market_ticker") or market.get("ticker") or "")


def _market_url(market: Mapping[str, Any]) -> Optional[str]:
    value = market.get("url")
    return str(value) if value else None


def _fee_band(price: Optional[float]) -> Optional[str]:
    if price is None:
        return None
    return "extreme" if price <= 0.25 or price >= 0.75 else "mid"


def _display(state: str, buy_price: Optional[float], age_seconds: Optional[float]) -> dict[str, str]:
    badge = {
        TradableState.OPEN_TRADABLE.value: "LIVE",
        TradableState.OPEN_NO_QUOTE.value: "NO QUOTE",
        TradableState.NOT_LISTED.value: "NOT LISTED",
        TradableState.MATCH_AMBIGUOUS.value: "MATCH AMBIGUOUS",
        TradableState.LISTED_TBD.value: "TBD",
        TradableState.LISTED_UNOPENED.value: "UNOPENED",
        TradableState.STALE.value: "STALE",
        TradableState.CLOSED.value: "CLOSED",
        TradableState.SETTLED.value: "SETTLED",
    }.get(state, state or "UNKNOWN")
    if buy_price is None:
        price_label = "No executable quote"
    else:
        price_label = f"{PRE_FEE_PRICE_BASIS} {round(buy_price * 100):.0f}c"
    if age_seconds is None:
        age_label = "Quote age unknown"
    elif age_seconds <= 60:
        age_label = "Fresh"
    elif age_seconds <= DEFAULT_QUOTE_STALE_SECONDS:
        age_label = "Aging"
    else:
        age_label = "Stale"
    return {"badge": badge, "price_label": price_label, "age_label": age_label}


def _slate_signal(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {"consensus": candidate.get("consensus")}


def _first_candidate_date(candidates: Iterable[Mapping[str, Any]]) -> Optional[str]:
    for candidate in candidates:
        value = candidate.get("slate_date")
        if value:
            return str(value)
    return None


def _id_token(value: Any) -> str:
    import re

    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")
