"""Normalization helpers for Kalshi baseball markets."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, Mapping, Optional

from .models import SideMapping

TEAM_ALIASES = {
    "WAS": "WSH",
    "WSH": "WSH",
    "SFG": "SF",
    "SF": "SF",
    "ATH": "ATH",
    "OAK": "ATH",
    "CHW": "CHW",
    "CWS": "CHW",
    "ARI": "AZ",
    "AZ": "AZ",
    "TBR": "TB",
    "TB": "TB",
    "KCR": "KC",
    "KC": "KC",
    "SDP": "SD",
    "SD": "SD",
}

KNOWN_TEAMS = {
    "ARI", "AZ", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL",
    "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY",
    "ATH", "OAK", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEX",
    "TOR", "WSH",
}

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

EVENT_RE = re.compile(
    r"^(?P<series>[A-Z0-9]+)-(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<dd>\d{2})(?P<hhmm>\d{4})(?P<teams>[A-Z]+)$"
)


def canonical_team(value: Any) -> str:
    text = str(value or "").strip().upper()
    return TEAM_ALIASES.get(text, text)


def canonical_player_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", text, flags=re.I)
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())


def display_player_from_title(title: Any) -> Optional[str]:
    text = str(title or "")
    if ":" not in text:
        return None
    name = text.split(":", 1)[0].strip()
    return name or None


def parse_threshold(text: Any) -> Optional[float]:
    raw = str(text or "")
    plus = re.search(r"(\d+(?:\.\d+)?)\s*\+", raw)
    if plus:
        return float(plus.group(1)) - 0.5
    over = re.search(r"(?:over|more than|more)\s+(\d+(?:\.\d+)?)", raw, re.I)
    if over:
        return float(over.group(1))
    under = re.search(r"(?:under|fewer than|less than)\s+(\d+(?:\.\d+)?)", raw, re.I)
    if under:
        return float(under.group(1))
    return None


def parse_event_ticker(event_ticker: str) -> dict[str, Any]:
    match = EVENT_RE.match(str(event_ticker or "").upper())
    if not match:
        return {}
    yy = int(match.group("yy"))
    year = 2000 + yy
    month = MONTHS.get(match.group("mon"))
    if month is None:
        return {}
    slate_date = date(year, month, int(match.group("dd"))).isoformat()
    teams = split_event_team_codes(match.group("teams"))
    return {
        "series_ticker": match.group("series"),
        "slate_date": slate_date,
        "first_pitch_et": match.group("hhmm"),
        "away_team": teams[0] if teams else None,
        "home_team": teams[1] if teams else None,
    }


def split_event_team_codes(value: str) -> Optional[tuple[str, str]]:
    text = str(value or "").upper()
    for idx in range(2, len(text) - 1):
        left = canonical_team(text[:idx])
        right = canonical_team(text[idx:])
        if left in KNOWN_TEAMS and right in KNOWN_TEAMS:
            return left, right
    return None


def slate_market_for_series(series_ticker: str) -> str:
    return {
        "KXMLBHR": "HR",
        "KXMLBTOTAL": "TOTAL_RUNS",
        "KXMLBKS": "K",
        "KXMLBHIT": "HIT",
        "KXMLBTB": "TB",
        "KXMLBHRR": "HRR",
        "KXMLBTEAMTOTAL": "TEAM_TOTAL",
        "KXMLBHA": "H_ALLOWED",
    }.get(series_ticker, series_ticker)


def settlement_note_for_series(series_ticker: str) -> str:
    if series_ticker == "KXMLBKS":
        return (
            "Scratched or non-starting pitcher resolves to last fair price; "
            "relief appearances do not count."
        )
    if series_ticker in {"KXMLBHR", "KXMLBTOTAL", "KXMLBHIT", "KXMLBTB", "KXMLBHRR", "KXMLBTEAMTOTAL", "KXMLBHA"}:
        return "Market references the originally scheduled game datetime for settlement."
    return ""


def side_mapping(market: Mapping[str, Any], intended_slate_side: str = "over") -> SideMapping:
    rules = f"{market.get('rules_primary') or ''} {market.get('title') or ''}".lower()
    yes_side = "over"
    if re.search(r"\b(under|fewer than|less than|no more than)\b", rules):
        yes_side = "under"
    elif re.search(r"\b(over|more than|\d+\+|records? \d+)\b", rules):
        yes_side = "over"
    no_side = "under" if yes_side == "over" else "over"
    slate = intended_slate_side.lower()
    kalshi = "yes" if slate == yes_side else "no"
    return SideMapping(
        slate_side=slate,
        kalshi_side=kalshi,
        yes_slate_side=yes_side,
        no_slate_side=no_side,
    )


def quote_age_seconds(market: Mapping[str, Any], now_ts: Optional[float] = None) -> Optional[float]:
    updated = market.get("updated_time") or market.get("last_updated_ts")
    if not updated:
        return None
    from datetime import datetime, timezone

    text = str(updated).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now_ts is None:
        now_ts = datetime.now(timezone.utc).timestamp()
    return max(0.0, now_ts - dt.timestamp())


def freshness_label(age_seconds: Optional[float], stale_seconds: int) -> str:
    if age_seconds is None:
        return "UNKNOWN"
    if age_seconds <= 60:
        return "FRESH"
    if age_seconds <= stale_seconds:
        return "AGING"
    return "STALE"
