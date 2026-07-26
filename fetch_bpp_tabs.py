#!/usr/bin/env python3
"""
fetch_bpp_tabs.py -- live BallparkPal workbook-tab overrides.

This step runs after extract_xlsx.py writes day_data.json and before build.py.
It updates only the Chapter D owned surfaces:

* SP_Projections: fully rebuilt from BPP projection averages plus MLB handedness.
* Park_Factors: consumed columns rebuilt from BPP park factors plus MLB venue lookup.
* BP_Batters/BP_Pitchers: existing workbook rows are preserved, with API-available
  projection columns refreshed in place.

Any failure leaves day_data.json untouched and exits 0.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from services.bpp_client import BppApiError, BppClient

DATA_FILE = os.environ.get("DATA_FILE", "day_data.json")
BPP_MIN_GAP = float(os.environ.get("BPP_MIN_GAP", "6.2"))
BPP_TABS_MAX_RETRIES = int(os.environ.get("BPP_TABS_MAX_RETRIES", "3"))
BPP_RATE_LIMIT_BACKOFF = float(os.environ.get("BPP_RATE_LIMIT_BACKOFF", "20"))
BPP_MONTHLY_BUDGET = 15000
MLB_BASE = "https://statsapi.mlb.com/api/v1"

OWNED_TABS = ("SP_Projections", "Park_Factors", "BP_Batters", "BP_Pitchers")

REQUIRED_OUTPUT_COLUMNS = {
    "SP_Projections": {"Team", "Pitcher", "Throws", "Opp", "Inn", "BF", "R", "H", "HR", "K", "BB"},
    "Park_Factors": {"Venue", "Game", "Time", "Date", "Runs %", "HR %", "2B/3B %"},
    "BP_Batters": {
        "FullName",
        "BatterStand",
        "Team",
        "Opponent",
        "Doubles",
        "StolenBaseAttempts",
        "StolenBaseProbability",
        "PointsDK",
        "PointsFD",
        "HomeRunProbability",
        "HitProbability",
    },
    "BP_Pitchers": {
        "FullName",
        "PitcherHand",
        "Team",
        "Opponent",
        "Innings",
        "QualityStart",
        "RunsAllowed",
        "HitsAllowed",
        "Strikeouts",
        "Walks",
        "HomeRunsAllowed",
    },
}

TEAM_FIX = {
    "WAS": "WSH",
    "WSH": "WSH",
    "SFG": "SF",
    "SF": "SF",
    "CWS": "CHW",
    "CHW": "CHW",
    "AZ": "ARI",
    "ARI": "ARI",
}


class CallCounter:
    def __init__(self, client: BppClient) -> None:
        self.client = client
        self.bpp_count = 0
        self.mlb_count = 0

    def bpp(self, label: str, func: Any) -> Dict[str, Any]:
        for attempt in range(1, BPP_TABS_MAX_RETRIES + 1):
            self.bpp_count += 1
            print(
                f"[bpp-tabs] BPP call {self.bpp_count} "
                f"(monthly budget {BPP_MONTHLY_BUDGET}): {label}"
                f"{'' if attempt == 1 else f' retry {attempt}/{BPP_TABS_MAX_RETRIES}'}",
                file=sys.stderr,
            )
            try:
                return func()
            except BppApiError as exc:
                if not is_rate_limit_error(exc) or attempt >= BPP_TABS_MAX_RETRIES:
                    raise
                wait = BPP_RATE_LIMIT_BACKOFF * attempt
                print(
                    f"[bpp-tabs] rate limited while fetching {label}; "
                    f"sleeping {wait:.0f}s before retry",
                    file=sys.stderr,
                )
                time.sleep(wait)
        raise RuntimeError(f"unreachable BPP retry state for {label}")

    def mlb_json(self, label: str, url: str) -> Dict[str, Any]:
        self.mlb_count += 1
        print(f"[bpp-tabs] MLB call {self.mlb_count}: {label}", file=sys.stderr)
        with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    if not os.environ.get("BPP_API_KEY"):
        print("[bpp-tabs] skipped: BPP_API_KEY is not set; day_data.json left untouched")
        print("BPP tab API calls this run: 0")
        return 0

    counter: Optional[CallCounter] = None
    try:
        path = Path(DATA_FILE)
        original = json.loads(path.read_text(encoding="utf-8"))
        slate_date = requested_date(original)
        client = BppClient(use_cache=False, min_gap=BPP_MIN_GAP)
        counter = CallCounter(client)
        updated = build_overrides(original, slate_date, counter)
        assert_schema_parity(updated)
        write_json_atomic(path, updated)
        print_schema_summary(updated)
        print(
            f"[bpp-tabs] calls/run BPP={counter.bpp_count}, MLB={counter.mlb_count}; "
            f"3 runs/day BPP ~= {counter.bpp_count * 3}; "
            f"4 runs/day BPP ~= {counter.bpp_count * 4}; "
            f"monthly budget {BPP_MONTHLY_BUDGET}",
            file=sys.stderr,
        )
        print(f"BPP tab API calls this run: {counter.bpp_count}")
        return 0
    except Exception as exc:
        count = counter.bpp_count if counter is not None else 0
        print(f"[bpp-tabs] non-fatal failure: {exc}", file=sys.stderr)
        print("[bpp-tabs] day_data.json left untouched", file=sys.stderr)
        print(f"BPP tab API calls this run: {count}")
        return 0


def requested_date(data: Mapping[str, Any]) -> str:
    override = os.environ.get("BPP_TABS_DATE", "").strip()
    if override:
        print(f"[bpp-tabs] using BPP_TABS_DATE override: {override}", file=sys.stderr)
        return override[:10]
    for tab, field in (("BP_Games", "GameDate"), ("Park_Factors", "Date")):
        for row in data.get(tab, []) or []:
            value = str(row.get(field) or "")[:10]
            if value:
                return value
    raise RuntimeError("could not determine slate date from day_data.json")


def build_overrides(
    original: Mapping[str, Any],
    slate_date: str,
    counter: CallCounter,
) -> Dict[str, Any]:
    updated = copy.deepcopy(original)
    games_payload = counter.bpp(
        f"games({slate_date})",
        lambda: counter.client.games(date=slate_date, force_refresh=True),
    )
    park_payload = counter.bpp(
        f"parkfactors({slate_date})",
        lambda: counter.client.parkfactors(slate_date, force_refresh=True),
    )
    game_meta = index_games(games_payload)
    park_rows = list(iter_items(park_payload))
    apply_park_rows(updated, slate_date, park_rows, game_meta, counter)

    averages_by_game: Dict[int, Mapping[str, Any]] = {}
    for game_id in sorted(game_meta):
        averages_by_game[game_id] = counter.bpp(
            f"projection_averages({game_id})",
            lambda game_id=game_id: counter.client.projection_averages(game_id, force_refresh=True),
        )

    hands = fetch_handedness(collect_player_ids(averages_by_game), counter)
    updated["SP_Projections"] = build_sp_rows(averages_by_game, game_meta, hands)
    apply_pitcher_overrides(updated, averages_by_game, hands)

    probabilities_by_game: Dict[int, Mapping[str, Any]] = {}
    for game_id in sorted(game_meta):
        try:
            probabilities_by_game[game_id] = counter.bpp(
                f"projection_probabilities({game_id})",
                lambda game_id=game_id: counter.client.projection_probabilities(
                    game_id,
                    force_refresh=True,
                ),
            )
        except BppApiError as exc:
            print(
                f"[bpp-tabs] warning: optional projection_probabilities({game_id}) "
                f"failed after critical tabs were rebuilt: {exc}",
                file=sys.stderr,
            )
            break
    apply_batter_overrides(updated, averages_by_game, probabilities_by_game, hands)
    return updated


def index_games(payload: Mapping[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in iter_items(payload):
        game_id = as_int(row.get("gameId"))
        if game_id is None:
            continue
        out[game_id] = {
            "game_id": game_id,
            "game_date": str(row.get("gameDate") or "")[:10],
            "game_time": row.get("gameTime"),
            "game_time_full": row.get("gameTimeFull"),
            "team_away_id": as_int(row.get("teamAwayId")),
            "team_home_id": as_int(row.get("teamHomeId")),
            "venue_id": as_int(row.get("venueId")),
        }
    if not out:
        raise RuntimeError("BPP games payload had no games")
    return out


def apply_park_rows(
    data: MutableMapping[str, Any],
    slate_date: str,
    park_rows: Iterable[Mapping[str, Any]],
    game_meta: MutableMapping[int, Dict[str, Any]],
    counter: CallCounter,
) -> None:
    schedule = fetch_schedule(slate_date, counter)
    existing = index_existing_parks(data.get("Park_Factors", []))
    rows = []
    for row in park_rows:
        game_id = as_int(row.get("gameId"))
        if game_id is None:
            continue
        away = canonical_team(row.get("teamAway"))
        home = canonical_team(row.get("teamHome"))
        game = f"{away} @ {home}"
        prior = existing.get((away, home), {})
        meta = game_meta.setdefault(game_id, {"game_id": game_id})
        meta["away"] = away
        meta["home"] = home
        venue = schedule.get(game_id, {}).get("venue") or prior.get("Venue")
        if not venue:
            raise RuntimeError(f"missing Venue for gameId {game_id}")
        out = dict(prior)
        out.update(
            {
                "Date": slate_date,
                "Venue": venue,
                "Game": game,
                "Time": row.get("gameTime") or meta.get("game_time") or prior.get("Time"),
                "HR %": fmt_pct(row.get("homeRunsPercent")),
                "2B/3B %": fmt_pct(row.get("doublesTriplesPercent")),
                "Runs %": fmt_pct(row.get("runsPercent")),
            }
        )
        rows.append(out)
    if not rows:
        raise RuntimeError("BPP parkfactors payload had no rows")
    rows.sort(key=lambda row: time_sort_key(row.get("Time")))
    data["Park_Factors"] = rows


def fetch_schedule(slate_date: str, counter: CallCounter) -> Dict[int, Dict[str, Any]]:
    params = urllib.parse.urlencode({"sportId": 1, "date": slate_date})
    payload = counter.mlb_json("schedule", f"{MLB_BASE}/schedule?{params}")
    out: Dict[int, Dict[str, Any]] = {}
    for date_row in payload.get("dates", []) or []:
        for game in date_row.get("games", []) or []:
            game_id = as_int(game.get("gamePk"))
            if game_id is None:
                continue
            venue = game.get("venue") or {}
            out[game_id] = {"venue": venue.get("name"), "venue_id": venue.get("id")}
    return out


def index_existing_parks(rows: Iterable[Mapping[str, Any]]) -> Dict[Tuple[str, str], Mapping[str, Any]]:
    out: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    for row in rows or []:
        parsed = parse_game(row.get("Game"))
        if parsed:
            out[parsed] = row
    return out


def build_sp_rows(
    averages_by_game: Mapping[int, Mapping[str, Any]],
    game_meta: Mapping[int, Mapping[str, Any]],
    hands: Mapping[int, Mapping[str, Optional[str]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for game_id in sorted(averages_by_game, key=lambda gid: time_sort_key(game_meta.get(gid, {}).get("game_time"))):
        data = averages_by_game[game_id].get("data") or {}
        meta = game_meta.get(game_id, {})
        for pitcher in data.get("pitchers", []) or []:
            if not pitcher.get("isStarter"):
                continue
            team = canonical_team(pitcher.get("team"))
            opp = opponent_for(team, meta)
            player_id = as_int(pitcher.get("playerId"))
            rows.append(
                {
                    "Team": team,
                    "Pitcher": pitcher.get("playerName"),
                    "Throws": (hands.get(player_id or -1) or {}).get("pitch"),
                    "Opp": opp,
                    "Inn": round_num(pitcher.get("innings")),
                    "BF": round_num(pitcher.get("battersFaced")),
                    "R": round_num(pitcher.get("runsAllowed")),
                    "H": round_num(pitcher.get("hitsAllowed")),
                    "HR": round_num(pitcher.get("homeRunsAllowed")),
                    "K": round_num(pitcher.get("strikeouts")),
                    "BB": round_num(pitcher.get("walks")),
                }
            )
    if not rows:
        raise RuntimeError("no starting pitchers found in BPP projection averages")
    return rows


def apply_batter_overrides(
    data: MutableMapping[str, Any],
    averages_by_game: Mapping[int, Mapping[str, Any]],
    probabilities_by_game: Mapping[int, Mapping[str, Any]],
    hands: Mapping[int, Mapping[str, Optional[str]]],
) -> None:
    averages: Dict[Tuple[int, int], Mapping[str, Any]] = {}
    for game_id, payload in averages_by_game.items():
        for row in (payload.get("data") or {}).get("batters", []) or []:
            player_id = as_int(row.get("playerId"))
            if player_id is not None:
                averages[(game_id, player_id)] = row
    probabilities = index_batter_probabilities(probabilities_by_game)
    for row in data.get("BP_Batters", []) or []:
        game_id = as_int(row.get("GamePk"))
        player_id = as_int(row.get("PlayerId"))
        if game_id is None or player_id is None:
            continue
        avg = averages.get((game_id, player_id))
        if avg:
            row["BatterStand"] = (hands.get(player_id) or {}).get("bat") or row.get("BatterStand")
            set_if_number(row, "BattingPosition", avg.get("battingPosition"), digits=0)
            set_if_number(row, "PlateAppearances", avg.get("plateAppearances"))
            set_if_number(row, "AtBats", avg.get("atBats"))
            set_if_number(row, "Hits", avg.get("hits"))
            set_if_number(row, "Bases", avg.get("totalBases"))
            set_if_number(row, "Strikeouts", avg.get("strikeouts"))
            set_if_number(row, "Walks", avg.get("walks"))
            set_if_number(row, "Singles", avg.get("singles"))
            set_if_number(row, "Doubles", avg.get("doubles"))
            set_if_number(row, "Triples", avg.get("triples"))
            set_if_number(row, "HomeRuns", avg.get("homeRuns"))
            set_if_number(row, "RBIs", avg.get("rbis"))
            set_if_number(row, "Runs", avg.get("runs"))
            set_if_number(row, "StolenBaseSuccesses", avg.get("stolenBaseSuccesses"))
            set_if_number(row, "PointsDK", avg.get("fantasyPointsDK"))
            set_if_number(row, "PointsFD", avg.get("fantasyPointsFD"))
        probs = probabilities.get((game_id, player_id))
        if probs:
            for col, value in probs.items():
                set_if_number(row, col, value, digits=4)


def apply_pitcher_overrides(
    data: MutableMapping[str, Any],
    averages_by_game: Mapping[int, Mapping[str, Any]],
    hands: Mapping[int, Mapping[str, Optional[str]]],
) -> None:
    averages: Dict[Tuple[int, int], Mapping[str, Any]] = {}
    for game_id, payload in averages_by_game.items():
        for row in (payload.get("data") or {}).get("pitchers", []) or []:
            player_id = as_int(row.get("playerId"))
            if player_id is not None:
                averages[(game_id, player_id)] = row
    for row in data.get("BP_Pitchers", []) or []:
        game_id = as_int(row.get("GamePk"))
        player_id = as_int(row.get("PlayerId"))
        if game_id is None or player_id is None:
            continue
        avg = averages.get((game_id, player_id))
        if not avg:
            continue
        row["PitcherHand"] = (hands.get(player_id) or {}).get("pitch") or row.get("PitcherHand")
        set_if_number(row, "BattersFaced", avg.get("battersFaced"))
        set_if_number(row, "Innings", avg.get("innings"))
        set_if_number(row, "WinPct", avg.get("winProbability"), digits=4)
        set_if_number(row, "LossPct", avg.get("lossProbability"), digits=4)
        win = as_float(row.get("WinPct"))
        loss = as_float(row.get("LossPct"))
        if win is not None and loss is not None:
            row["NdPct"] = round(max(0.0, 1.0 - win - loss), 4)
        set_if_number(row, "QualityStart", avg.get("qualityStartProbability"), digits=4)
        set_if_number(row, "PointsDK", avg.get("fantasyPointsDK"))
        set_if_number(row, "PointsFD", avg.get("fantasyPointsFD"))
        set_if_number(row, "RunsAllowed", avg.get("runsAllowed"))
        set_if_number(row, "HitsAllowed", avg.get("hitsAllowed"))
        set_if_number(row, "Strikeouts", avg.get("strikeouts"))
        set_if_number(row, "Walks", avg.get("walks"))
        set_if_number(row, "HomeRunsAllowed", avg.get("homeRunsAllowed"))


def index_batter_probabilities(
    probabilities_by_game: Mapping[int, Mapping[str, Any]]
) -> Dict[Tuple[int, int], Dict[str, float]]:
    market_to_col = {
        "Batter Home Runs": "HomeRunProbability",
        "Batter Hits": "HitProbability",
        "Batter Stolen Bases": "StolenBaseProbability",
    }
    out: Dict[Tuple[int, int], Dict[str, float]] = {}
    for game_id, payload in probabilities_by_game.items():
        for row in iter_items(payload):
            col = market_to_col.get(str(row.get("displayName") or ""))
            if not col:
                continue
            subject = row.get("subject") if isinstance(row.get("subject"), Mapping) else {}
            player_id = as_int(subject.get("id"))
            if player_id is None:
                continue
            if str(row.get("side") or "").lower() != "over":
                continue
            line = as_float(row.get("line"))
            if line != 0.5:
                continue
            prob = as_float(row.get("probability"))
            if prob is None:
                continue
            out.setdefault((game_id, player_id), {})[col] = prob
    return out


def collect_player_ids(averages_by_game: Mapping[int, Mapping[str, Any]]) -> List[int]:
    ids = set()
    for payload in averages_by_game.values():
        data = payload.get("data") or {}
        for group in ("batters", "pitchers"):
            for row in data.get(group, []) or []:
                player_id = as_int(row.get("playerId"))
                if player_id is not None:
                    ids.add(player_id)
    return sorted(ids)


def fetch_handedness(ids: Iterable[int], counter: CallCounter) -> Dict[int, Dict[str, Optional[str]]]:
    out: Dict[int, Dict[str, Optional[str]]] = {}
    ids = list(ids)
    for chunk in chunks(ids, 100):
        params = urllib.parse.urlencode({"personIds": ",".join(str(i) for i in chunk)})
        payload = counter.mlb_json("people handedness", f"{MLB_BASE}/people?{params}")
        for person in payload.get("people", []) or []:
            player_id = as_int(person.get("id"))
            if player_id is None:
                continue
            bat_side = person.get("batSide") or {}
            pitch_hand = person.get("pitchHand") or {}
            out[player_id] = {
                "bat": bat_side.get("code"),
                "pitch": pitch_hand.get("code"),
                "name": person.get("fullName"),
            }
    return out


def assert_schema_parity(data: Mapping[str, Any]) -> None:
    missing_by_tab = {}
    for tab, required in REQUIRED_OUTPUT_COLUMNS.items():
        rows = data.get(tab, []) or []
        present = set()
        for row in rows:
            if isinstance(row, Mapping):
                present.update(row.keys())
        missing = sorted(required - present)
        if missing:
            missing_by_tab[tab] = missing
    if missing_by_tab:
        details = "; ".join(f"{tab}: {', '.join(cols)}" for tab, cols in missing_by_tab.items())
        raise RuntimeError(f"schema parity failed: {details}")


def print_schema_summary(data: Mapping[str, Any]) -> None:
    for tab in OWNED_TABS:
        rows = data.get(tab, []) or []
        present = set()
        for row in rows:
            if isinstance(row, Mapping):
                present.update(row.keys())
        print(
            f"[bpp-tabs] schema parity OK: {tab} "
            f"rows={len(rows)} required={len(REQUIRED_OUTPUT_COLUMNS[tab])}",
            file=sys.stderr,
        )


def iter_items(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    data = payload.get("data") if isinstance(payload, Mapping) else None
    if isinstance(data, Mapping) and isinstance(data.get("items"), list):
        for row in data["items"]:
            if isinstance(row, Mapping):
                yield row
    elif isinstance(data, list):
        for row in data:
            if isinstance(row, Mapping):
                yield row


def is_rate_limit_error(exc: BppApiError) -> bool:
    blob = f"{exc.status or ''} {exc.code or ''} {exc}".lower()
    return "429" in blob or "rate limit" in blob or "too many requests" in blob


def opponent_for(team: str, meta: Mapping[str, Any]) -> str:
    away = canonical_team(meta.get("away"))
    home = canonical_team(meta.get("home"))
    if team == away:
        return home
    if team == home:
        return away
    return ""


def parse_game(value: Any) -> Optional[Tuple[str, str]]:
    text = str(value or "")
    if "@" not in text:
        return None
    away, home = text.split("@", 1)
    return canonical_team(away), canonical_team(home)


def canonical_team(value: Any) -> str:
    team = str(value or "").strip().upper()
    return TEAM_FIX.get(team, team)


def fmt_pct(value: Any) -> str:
    num = as_float(value)
    if num is None:
        return ""
    rounded = int(round(num))
    sign = "+" if rounded > 0 else ""
    return f"{sign}{rounded}%"


def round_num(value: Any, digits: int = 2) -> Optional[float]:
    num = as_float(value)
    if num is None:
        return None
    if digits == 0:
        return int(round(num))
    return round(num, digits)


def set_if_number(row: MutableMapping[str, Any], key: str, value: Any, digits: int = 3) -> None:
    num = round_num(value, digits=digits)
    if num is not None:
        row[key] = num


def as_int(value: Any) -> Optional[int]:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def time_sort_key(value: Any) -> Tuple[int, int]:
    text = str(value or "")
    try:
        hour, minute = text.split(":", 1)
        return int(hour), int(minute[:2])
    except (TypeError, ValueError):
        return 99, 99


def chunks(values: List[int], size: int) -> Iterable[List[int]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")
    tmp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
