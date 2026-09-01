"""Build slate-side candidate contracts before Kalshi matching.

This module normalizes The Daily Slate picks into a stable, matchable contract
shape. It does not call Kalshi and does not attempt market matching.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from .normalize import canonical_player_name, canonical_team

MATCHABLE_MARKETS = {
    "K": ("pitcher_strikeouts", "projection_only"),
    "HR": ("batter_home_runs", "model_probability_unvalidated"),
    "HRR": ("batter_hrr", "calibrated_probability"),
    "HIT": ("batter_hits", "model_probability_unvalidated"),
    "TB": ("batter_total_bases", "model_probability_unvalidated"),
    "TOTAL": ("game_total", "projection_only"),
    "NRFI": ("run_first_inning", "model_probability_unvalidated"),
}

NO_SERIES_MARKETS = {
    "SB",
    "2B",
    "OUTS_ALT",
    "H_ALLOWED",
    "H_ALLOWED_ALT",
    "ER_ALLOWED",
}

UNIT_SUFFIX_RE = re.compile(
    r"\s*(?:outs?|h\s+allowed|hits?\s+allowed|er|hrr|tb|hrs?|hits?|h|k|strikeouts?)\s*$",
    re.I,
)
NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")
PLUS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+")
TOTAL_PROB_RE = re.compile(r"^p_over_(\d+)(?:_(\d+))?$")


@dataclass(frozen=True)
class Candidate:
    slate_id: str
    slate_date: str
    game_key: Optional[str]
    away_team: Optional[str]
    home_team: Optional[str]
    player: Optional[str]
    player_norm: Optional[str]
    market_type: str
    direction: Optional[str]
    threshold: Optional[float]
    display_line: Optional[str]
    probability_kind: str
    consensus: Any
    matchable: bool
    reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def build_candidates_from_files(
    slate_picks_path: str | Path = "slate_picks.json",
    day_data_path: str | Path = "day_data.json",
) -> list[dict[str, Any]]:
    slate = load_json(slate_picks_path)
    day_data = load_json(day_data_path)
    return [candidate.as_dict() for candidate in build_candidates(slate, day_data)]


def build_candidates(slate: Mapping[str, Any], day_data: Mapping[str, Any]) -> list[Candidate]:
    slate_date = str(slate.get("slate_date") or day_data.get("_slate_date") or "")
    games = GameResolver(day_data)
    candidates = []
    for pick in slate.get("picks") or []:
        if isinstance(pick, Mapping):
            candidates.append(candidate_for_pick(pick, slate_date=slate_date, games=games))
    return candidates


def candidate_for_pick(pick: Mapping[str, Any], *, slate_date: str, games: "GameResolver") -> Candidate:
    raw_market = str(pick.get("market") or "").strip().upper()
    market_type, probability_kind = _market_and_probability(raw_market)
    player = None if raw_market in {"TOTAL", "NRFI"} else _clean_player(pick.get("name"))
    player_norm = canonical_player_name(player) if player else None
    game = games.resolve(pick)
    display_line = pick.get("line")
    direction = None
    threshold = None
    reason = None
    if raw_market == "NRFI":
        direction = "no"
    elif raw_market == "TOTAL":
        direction = _total_direction(pick)
        threshold, reason = resolve_total_threshold(pick)
    else:
        parsed = parse_display_line(display_line)
        direction = parsed.get("direction")
        threshold = parsed.get("threshold")
        reason = parsed.get("reason")

    matchable = True
    if raw_market in NO_SERIES_MARKETS or raw_market not in MATCHABLE_MARKETS:
        matchable = False
        reason = "no_kalshi_series"
    elif game.reason:
        matchable = False
        reason = game.reason
    elif raw_market != "NRFI" and threshold is None:
        matchable = False
        reason = reason or "missing_threshold"
    elif direction not in {"over", "under", "yes", "no"}:
        matchable = False
        reason = reason or "missing_direction"

    game_key = game.game_key
    slate_id = make_slate_id(
        slate_date=slate_date,
        game_key=game_key,
        player_norm=player_norm,
        market_type=market_type,
        direction=direction,
        threshold=threshold,
        team=pick.get("team"),
    )
    return Candidate(
        slate_id=slate_id,
        slate_date=slate_date,
        game_key=game_key,
        away_team=game.away_team,
        home_team=game.home_team,
        player=player,
        player_norm=player_norm,
        market_type=market_type,
        direction=direction,
        threshold=threshold,
        display_line=display_line,
        probability_kind=probability_kind,
        consensus=pick.get("consensus"),
        matchable=matchable,
        reason=reason if not matchable else None,
    )


def parse_display_line(line: Any) -> dict[str, Any]:
    if line is None:
        return {"direction": None, "threshold": None, "reason": "missing_line"}
    original = str(line).strip()
    if not original:
        return {"direction": None, "threshold": None, "reason": "missing_line"}
    text = UNIT_SUFFIX_RE.sub("", original).strip()
    lower = text.lower()
    if lower.startswith(("under", "u ")):
        direction = "under"
    elif lower.startswith(("over", "ov", "o ")):
        direction = "over"
    elif lower in {"yes", "no"}:
        return {"direction": lower, "threshold": None, "reason": None}
    else:
        return {"direction": None, "threshold": None, "reason": "missing_direction"}

    plus = PLUS_RE.search(text)
    if plus:
        return {"direction": direction, "threshold": float(plus.group(1)) - 0.5, "reason": None}
    number = NUMBER_RE.search(text)
    if not number:
        return {"direction": direction, "threshold": None, "reason": "missing_threshold"}
    return {"direction": direction, "threshold": float(number.group(1)), "reason": None}


def resolve_total_threshold(pick: Mapping[str, Any]) -> tuple[Optional[float], Optional[str]]:
    ref_line = pick.get("ref_line")
    if isinstance(ref_line, (int, float)) and not isinstance(ref_line, bool):
        return float(ref_line), None
    for key in pick.keys():
        match = TOTAL_PROB_RE.match(str(key))
        if not match:
            continue
        whole = match.group(1)
        decimal = match.group(2)
        text = f"{whole}.{decimal}" if decimal else whole
        return float(text), None
    parsed = parse_display_line(pick.get("line"))
    if parsed.get("threshold") is not None:
        return float(parsed["threshold"]), None
    return None, "missing_total_threshold"


def make_slate_id(
    *,
    slate_date: str,
    game_key: Optional[str],
    player_norm: Optional[str],
    market_type: str,
    direction: Optional[str],
    threshold: Optional[float],
    team: Any = None,
) -> str:
    pieces = [slate_date or "unknown-date", game_key or "UNKNOWN_GAME"]
    if player_norm:
        pieces.append(_id_token(player_norm))
        team_token = _id_token(canonical_team(team))
        if team_token:
            pieces.append(team_token)
    pieces.extend([_id_token(market_type), _id_token(direction or "none")])
    if threshold is not None:
        pieces.append(_threshold_token(threshold))
    return "_".join(piece for piece in pieces if piece)


@dataclass(frozen=True)
class GameResolution:
    game_key: Optional[str]
    away_team: Optional[str]
    home_team: Optional[str]
    reason: Optional[str] = None


class GameResolver:
    def __init__(self, day_data: Mapping[str, Any]) -> None:
        self._by_pair: dict[frozenset[str], GameResolution] = {}
        for game in day_data.get("BP_Games") or []:
            if not isinstance(game, Mapping):
                continue
            away = canonical_team(game.get("AwayTeam"))
            home = canonical_team(game.get("HomeTeam"))
            if not away or not home:
                continue
            resolution = GameResolution(game_key=f"{away}@{home}", away_team=away, home_team=home)
            self._by_pair[frozenset({away, home})] = resolution

    def resolve(self, pick: Mapping[str, Any]) -> GameResolution:
        pair = _teams_from_pick(pick)
        if pair is None:
            return GameResolution(None, None, None, "missing_game_teams")
        found = self._by_pair.get(frozenset(pair))
        if found is None:
            return GameResolution(None, None, None, "game_not_found")
        return found


def report(candidates: list[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(candidates)
    matchable = sum(1 for candidate in candidates if candidate.get("matchable"))
    by_market: dict[str, dict[str, int]] = {}
    failed = []
    for candidate in candidates:
        market = str(candidate.get("market_type") or "")
        bucket = by_market.setdefault(market, {"total": 0, "matchable": 0})
        bucket["total"] += 1
        if candidate.get("matchable"):
            bucket["matchable"] += 1
        else:
            failed.append(
                {
                    "slate_id": candidate.get("slate_id"),
                    "market_type": candidate.get("market_type"),
                    "reason": candidate.get("reason"),
                    "display_line": candidate.get("display_line"),
                }
            )
    return {"total": total, "matchable": matchable, "by_market": by_market, "failed": failed}


def _market_and_probability(raw_market: str) -> tuple[str, str]:
    mapped = MATCHABLE_MARKETS.get(raw_market)
    if mapped:
        return mapped
    if raw_market in NO_SERIES_MARKETS:
        return raw_market.lower(), "not_applicable"
    return raw_market.lower() or "unknown", "not_applicable"


def _total_direction(pick: Mapping[str, Any]) -> Optional[str]:
    lean = str(pick.get("lean") or "").strip().lower()
    if lean == "over":
        return "over"
    if lean == "under":
        return "under"
    text = str(pick.get("pick") or "").lower()
    if " over " in f" {text} ":
        return "over"
    if " under " in f" {text} ":
        return "under"
    return None


def _teams_from_pick(pick: Mapping[str, Any]) -> Optional[tuple[str, str]]:
    team = canonical_team(pick.get("team"))
    opp = canonical_team(pick.get("opp"))
    if team and opp:
        return team, opp
    game = pick.get("game")
    if game:
        parts = str(game).replace(" vs ", "@").replace(" VS ", "@").split("@")
        if len(parts) == 2:
            return canonical_team(parts[0]), canonical_team(parts[1])
    return None


def _clean_player(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _id_token(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")


def _threshold_token(value: float) -> str:
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text.replace(".", "_")
