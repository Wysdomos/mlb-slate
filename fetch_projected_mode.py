#!/usr/bin/env python3
"""
fetch_projected_mode.py -- rebuild workbook-missing slate tabs from live sources.

This runs only when extract_xlsx.py wrote {"_mode": "projected"}. It persists
only app-facing workbook-shaped fields and derived ranks/scores; raw BPP
response envelopes and internal field names are never written to JSON.
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from services.bpp_client import BppClient
from fetch_bpp_tabs import (
    BPP_MONTHLY_BUDGET,
    CallCounter,
    as_float,
    as_int,
    canonical_team,
    fetch_handedness,
    fetch_schedule,
    fmt_pct,
    iter_items,
    round_num,
    time_sort_key,
    write_json_atomic,
)

DATA_FILE = os.environ.get("DATA_FILE", "day_data.json")
BPP_MIN_GAP = float(os.environ.get("BPP_MIN_GAP", "1.0"))

PROJECTED_TABS = [
    "HR_Leaderboard",
    "Hit_Probabilities",
    "Sweet_Spot_Analyzer",
    "Pitcher_Projections",
    "SP_Projections",
    "Park_Factors",
    "Sweet_Spot_Slate",
    "BP_Batters",
    "BP_Pitchers",
    "BP_Teams",
    "BP_Games",
    "Streaks",
    "Scout",
    "Best_Spots",
]


def main() -> int:
    path = Path(DATA_FILE)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("_mode") != "projected":
        print("[projected] skipped: day_data.json is workbook-backed")
        return 0
    if not os.environ.get("BPP_API_KEY"):
        print("[projected] BPP_API_KEY is required in Projected Mode", file=sys.stderr)
        return 1

    slate_date = str(data.get("_slate_date") or os.environ.get("PROJECTED_DATE") or "")[:10]
    if not slate_date:
        print("[projected] could not determine projected slate date", file=sys.stderr)
        return 1

    client = BppClient(use_cache=False, min_gap=BPP_MIN_GAP)
    counter = CallCounter(client)

    games_payload = counter.bpp(
        f"games({slate_date})",
        lambda: client.games(date=slate_date, force_refresh=True),
    )
    parks_payload = counter.bpp(
        f"parkfactors({slate_date})",
        lambda: client.parkfactors(slate_date, force_refresh=True),
    )
    matchups_payload = counter.bpp(
        f"matchups({slate_date}, starters=True)",
        lambda: client.matchups(slate_date, starters=True, force_refresh=True),
    )

    game_meta = index_games(games_payload)
    park_rows = list(iter_items(parks_payload))
    apply_park_meta(game_meta, park_rows)
    schedule = fetch_schedule(slate_date, counter)

    averages_by_game: Dict[int, Mapping[str, Any]] = {}
    probabilities_by_game: Dict[int, Mapping[str, Any]] = {}
    for game_id in sorted(game_meta):
        averages_by_game[game_id] = counter.bpp(
            f"projection_averages({game_id})",
            lambda game_id=game_id: client.projection_averages(game_id, force_refresh=True),
        )
        probabilities_by_game[game_id] = counter.bpp(
            f"projection_probabilities({game_id})",
            lambda game_id=game_id: client.projection_probabilities(game_id, force_refresh=True),
        )

    hands = fetch_handedness(collect_player_ids(averages_by_game, matchups_payload), counter)
    savant = fetch_savant_batter_metrics(slate_date[:4])
    streaks = load_streaks()

    rebuilt: Dict[str, Any] = {tab: [] for tab in PROJECTED_TABS}
    rebuilt.update({k: v for k, v in data.items() if str(k).startswith("_")})
    rebuilt["_mode"] = "projected"
    rebuilt["_slate_date"] = slate_date
    rebuilt["Park_Factors"] = build_park_rows(slate_date, park_rows, game_meta, schedule)
    rebuilt["BP_Games"] = build_game_rows(slate_date, game_meta, averages_by_game, probabilities_by_game)
    rebuilt["SP_Projections"] = build_sp_rows(averages_by_game, game_meta, hands)
    rebuilt["BP_Pitchers"] = build_pitcher_rows(slate_date, averages_by_game, game_meta, hands)
    rebuilt["BP_Batters"] = build_batter_rows(slate_date, averages_by_game, game_meta, hands, probabilities_by_game)
    rebuilt["Hit_Probabilities"] = build_hit_rows(
        matchups_payload,
        averages_by_game,
        probabilities_by_game,
    )
    rebuilt["HR_Leaderboard"] = build_hr_rows(
        matchups_payload,
        averages_by_game,
        rebuilt["BP_Pitchers"],
        rebuilt["Park_Factors"],
        hands,
        savant,
        streaks,
    )
    rebuilt["INDEX"] = index_rows(rebuilt)

    write_json_atomic(path, rebuilt)
    print(
        f"[projected] rebuilt {slate_date}: "
        f"HR={len(rebuilt['HR_Leaderboard'])}, Hits={len(rebuilt['Hit_Probabilities'])}, "
        f"Savant={len(savant)} batters",
        file=sys.stderr,
    )
    print(
        f"[projected] calls/run BPP={counter.bpp_count}, MLB={counter.mlb_count}; "
        f"3 runs/day BPP ~= {counter.bpp_count * 3}; "
        f"4 runs/day BPP ~= {counter.bpp_count * 4}; monthly budget {BPP_MONTHLY_BUDGET}",
        file=sys.stderr,
    )
    print(f"Projected Mode BPP API calls this run: {counter.bpp_count}")
    return 0


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
            "team_away_id": as_int(row.get("teamAwayId")),
            "team_home_id": as_int(row.get("teamHomeId")),
            "venue_id": as_int(row.get("venueId")),
        }
    if not out:
        raise RuntimeError("BPP games response had no slate games")
    return out


def apply_park_meta(game_meta: MutableMapping[int, Dict[str, Any]], rows: Iterable[Mapping[str, Any]]) -> None:
    for row in rows:
        game_id = as_int(row.get("gameId"))
        if game_id is None:
            continue
        meta = game_meta.setdefault(game_id, {"game_id": game_id})
        meta["away"] = canonical_team(row.get("teamAway"))
        meta["home"] = canonical_team(row.get("teamHome"))
        meta["game_time"] = row.get("gameTime") or meta.get("game_time")


def build_park_rows(
    slate_date: str,
    park_rows: Iterable[Mapping[str, Any]],
    game_meta: Mapping[int, Mapping[str, Any]],
    schedule: Mapping[int, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    rows = []
    for row in park_rows:
        game_id = as_int(row.get("gameId"))
        if game_id is None:
            continue
        meta = game_meta.get(game_id, {})
        away = canonical_team(row.get("teamAway") or meta.get("away"))
        home = canonical_team(row.get("teamHome") or meta.get("home"))
        rows.append(
            {
                "Date": slate_date,
                "Venue": (schedule.get(game_id) or {}).get("venue") or "",
                "Game": f"{away} @ {home}",
                "Time": row.get("gameTime") or meta.get("game_time"),
                "HR %": fmt_pct(row.get("homeRunsPercent")),
                "2B/3B %": fmt_pct(row.get("doublesTriplesPercent")),
                "Runs %": fmt_pct(row.get("runsPercent")),
            }
        )
    rows.sort(key=lambda row: time_sort_key(row.get("Time")))
    return rows


def build_game_rows(
    slate_date: str,
    game_meta: Mapping[int, Mapping[str, Any]],
    averages_by_game: Mapping[int, Mapping[str, Any]],
    probabilities_by_game: Mapping[int, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    rows = []
    for game_id in sorted(game_meta, key=lambda gid: time_sort_key(game_meta[gid].get("game_time"))):
        meta = game_meta[game_id]
        teams = (averages_by_game.get(game_id, {}).get("data") or {}).get("teams") or []
        team_rows = {canonical_team(t.get("team")): t for t in teams}
        away = canonical_team(meta.get("away"))
        home = canonical_team(meta.get("home"))
        away_row = team_rows.get(away, {})
        home_row = team_rows.get(home, {})
        runs_away = round_num(away_row.get("runs")) or 0
        runs_home = round_num(home_row.get("runs")) or 0
        f5_away = round_num(away_row.get("runsFirstFive")) or round(runs_away * 0.55, 3)
        f5_home = round_num(home_row.get("runsFirstFive")) or round(runs_home * 0.55, 3)
        probs = game_probabilities(probabilities_by_game.get(game_id, {}))
        total = runs_away + runs_home
        row = {
            "GamePk": game_id,
            "GameDate": slate_date,
            "GameTime": meta.get("game_time"),
            "AwayTeam": away,
            "HomeTeam": home,
            "RunsAway": runs_away,
            "RunsHome": runs_home,
            "RunsFirstInningPct": probs.get("yrfi", poisson_over(total * 0.12, 0)),
            "RunsFirst5Away": f5_away,
            "RunsFirst5Home": f5_home,
            "AwayWinFirst5": round_num(away_row.get("winFirstFiveProbability"), 3) or 0,
            "HomeWinFirst5": round_num(home_row.get("winFirstFiveProbability"), 3) or 0,
        }
        row.update(poisson_total_distribution(total))
        rows.append(row)
    return rows


def game_probabilities(payload: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for row in iter_items(payload):
        display = str(row.get("displayName") or "")
        side = str(row.get("side") or "").lower()
        line = as_float(row.get("line"))
        prob = as_float(row.get("probability"))
        if prob is None:
            continue
        if display == "Runs First Inning" and side == "over" and line == 0.5:
            out["yrfi"] = round(prob, 3)
        if display == "Total Runs" and side == "over" and line == 8.5:
            out["over_8_5"] = round(prob, 3)
    return out


def build_sp_rows(
    averages_by_game: Mapping[int, Mapping[str, Any]],
    game_meta: Mapping[int, Mapping[str, Any]],
    hands: Mapping[int, Mapping[str, Optional[str]]],
) -> List[Dict[str, Any]]:
    rows = []
    for game_id in sorted(averages_by_game, key=lambda gid: time_sort_key(game_meta.get(gid, {}).get("game_time"))):
        meta = game_meta.get(game_id, {})
        for pitcher in (averages_by_game[game_id].get("data") or {}).get("pitchers", []) or []:
            if not pitcher.get("isStarter"):
                continue
            team = canonical_team(pitcher.get("team"))
            player_id = as_int(pitcher.get("playerId"))
            rows.append(
                {
                    "Team": team,
                    "Pitcher": pitcher.get("playerName"),
                    "Throws": (hands.get(player_id or -1) or {}).get("pitch"),
                    "Opp": opponent_for(team, meta),
                    "Inn": round_num(pitcher.get("innings")),
                    "BF": round_num(pitcher.get("battersFaced")),
                    "R": round_num(pitcher.get("runsAllowed")),
                    "H": round_num(pitcher.get("hitsAllowed")),
                    "HR": round_num(pitcher.get("homeRunsAllowed")),
                    "K": round_num(pitcher.get("strikeouts")),
                    "BB": round_num(pitcher.get("walks")),
                    "ERA": projected_era(pitcher),
                }
            )
    return rows


def build_pitcher_rows(
    slate_date: str,
    averages_by_game: Mapping[int, Mapping[str, Any]],
    game_meta: Mapping[int, Mapping[str, Any]],
    hands: Mapping[int, Mapping[str, Optional[str]]],
) -> List[Dict[str, Any]]:
    rows = []
    for game_id, payload in averages_by_game.items():
        meta = game_meta.get(game_id, {})
        for row in (payload.get("data") or {}).get("pitchers", []) or []:
            player_id = as_int(row.get("playerId"))
            team = canonical_team(row.get("team"))
            win = round_num(row.get("winProbability"), 4) or 0
            loss = round_num(row.get("lossProbability"), 4) or 0
            rows.append(
                {
                    "GamePk": game_id,
                    "GameDate": slate_date,
                    "GameTime": meta.get("game_time"),
                    "PlayerId": player_id,
                    "FullName": row.get("playerName"),
                    "LastName": last_name(row.get("playerName")),
                    "PitcherHand": (hands.get(player_id or -1) or {}).get("pitch"),
                    "Side": side_for(team, meta),
                    "Team": team,
                    "Opponent": opponent_for(team, meta),
                    "BattersFaced": round_num(row.get("battersFaced")),
                    "Innings": round_num(row.get("innings")),
                    "WinPct": win,
                    "LossPct": loss,
                    "NdPct": round(max(0, 1 - win - loss), 4),
                    "QualityStart": round_num(row.get("qualityStartProbability"), 4),
                    "PointsDK": round_num(row.get("fantasyPointsDK")),
                    "PointsFD": round_num(row.get("fantasyPointsFD")),
                    "RunsAllowed": round_num(row.get("runsAllowed")),
                    "HitsAllowed": round_num(row.get("hitsAllowed")),
                    "Strikeouts": round_num(row.get("strikeouts")),
                    "Walks": round_num(row.get("walks")),
                    "HomeRunsAllowed": round_num(row.get("homeRunsAllowed")),
                }
            )
    return rows


def build_batter_rows(
    slate_date: str,
    averages_by_game: Mapping[int, Mapping[str, Any]],
    game_meta: Mapping[int, Mapping[str, Any]],
    hands: Mapping[int, Mapping[str, Optional[str]]],
    probabilities_by_game: Mapping[int, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    probs = batter_probabilities(probabilities_by_game)
    rows = []
    for game_id, payload in averages_by_game.items():
        meta = game_meta.get(game_id, {})
        for row in (payload.get("data") or {}).get("batters", []) or []:
            player_id = as_int(row.get("playerId"))
            team = canonical_team(row.get("team"))
            player_probs = probs.get((game_id, player_id or -1), {})
            rows.append(
                {
                    "GamePk": game_id,
                    "GameDate": slate_date,
                    "GameTime": meta.get("game_time"),
                    "PlayerId": player_id,
                    "FullName": row.get("playerName"),
                    "LastName": last_name(row.get("playerName")),
                    "BatterStand": (hands.get(player_id or -1) or {}).get("bat"),
                    "Side": side_for(team, meta),
                    "Team": team,
                    "Opponent": opponent_for(team, meta),
                    "BattingPosition": round_num(row.get("battingPosition"), 0),
                    "PlateAppearances": round_num(row.get("plateAppearances")),
                    "AtBats": round_num(row.get("atBats")),
                    "Hits": round_num(row.get("hits")),
                    "Bases": round_num(row.get("totalBases")),
                    "Strikeouts": round_num(row.get("strikeouts")),
                    "Walks": round_num(row.get("walks")),
                    "Singles": round_num(row.get("singles")),
                    "Doubles": round_num(row.get("doubles")),
                    "Triples": round_num(row.get("triples")),
                    "HomeRuns": round_num(row.get("homeRuns")),
                    "RBIs": round_num(row.get("rbis")),
                    "Runs": round_num(row.get("runs")),
                    "StolenBaseSuccesses": round_num(row.get("stolenBaseSuccesses")),
                    "PointsDK": round_num(row.get("fantasyPointsDK")),
                    "PointsFD": round_num(row.get("fantasyPointsFD")),
                    "HomeRunProbability": player_probs.get("hr", probability_from_mean(row.get("homeRuns"))),
                    "HitProbability": player_probs.get("hit", probability_from_mean(row.get("hits"))),
                    "StolenBaseProbability": player_probs.get("sb", probability_from_mean(row.get("stolenBaseSuccesses"))),
                }
            )
    return rows


def batter_probabilities(
    probabilities_by_game: Mapping[int, Mapping[str, Any]]
) -> Dict[Tuple[int, int], Dict[str, float]]:
    market_map = {
        "Batter Home Runs": "hr",
        "Batter Hits": "hit",
        "Batter Stolen Bases": "sb",
    }
    out: Dict[Tuple[int, int], Dict[str, float]] = {}
    for game_id, payload in probabilities_by_game.items():
        for row in iter_items(payload):
            key = market_map.get(str(row.get("displayName") or ""))
            if not key or str(row.get("side") or "").lower() != "over":
                continue
            if as_float(row.get("line")) != 0.5:
                continue
            subject = row.get("subject") if isinstance(row.get("subject"), Mapping) else {}
            player_id = as_int(subject.get("id"))
            prob = as_float(row.get("probability"))
            if player_id is not None and prob is not None:
                out.setdefault((game_id, player_id), {})[key] = round(prob, 4)
    return out


def build_hit_rows(
    matchups_payload: Mapping[str, Any],
    averages_by_game: Mapping[int, Mapping[str, Any]],
    probabilities_by_game: Mapping[int, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    averages = batter_average_index(averages_by_game)
    probs = batter_probabilities(probabilities_by_game)
    rows = []
    for row in iter_items(matchups_payload):
        name = str(row.get("batterName") or "").strip()
        if not name:
            continue
        first, last = split_name(name)
        game_id = as_int(row.get("gameId"))
        player_id = as_int(row.get("batterId"))
        avg = averages.get((game_id or -1, player_id or -1), {})
        player_probs = probs.get((game_id or -1, player_id or -1), {})
        hit_mean = as_float(avg.get("hits"))
        rows.append(
            {
                "First Name": first,
                "Last Name": last,
                "Team": canonical_team(row.get("batterTeam")),
                "Matchup": f"{canonical_team(row.get('batterTeam'))} vs. {canonical_team(row.get('pitcherTeam'))}",
                "1+ Hit": pct(player_probs.get("hit", probability_from_mean(hit_mean))),
                "2+ Hits": pct(poisson_at_least_two(hit_mean)),
                "To Get RBI": pct(probability_from_mean(avg.get("rbis"))),
                "To Hit HR": pct(player_probs.get("hr", matchup_percent_probability(row.get("homeRunProbability")))),
                "Last Updated": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            }
        )
    rows.sort(key=lambda r: parse_pct(r.get("1+ Hit")), reverse=True)
    return rows


def build_hr_rows(
    matchups_payload: Mapping[str, Any],
    averages_by_game: Mapping[int, Mapping[str, Any]],
    pitcher_rows: Iterable[Mapping[str, Any]],
    parks: Iterable[Mapping[str, Any]],
    hands: Mapping[int, Mapping[str, Optional[str]]],
    savant: Mapping[int, Mapping[str, Any]],
    streaks: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    averages = batter_average_index(averages_by_game)
    pitchers = {(str(r.get("FullName") or "").lower(), canonical_team(r.get("Team"))): r for r in pitcher_rows}
    park_by_team = index_parks(parks)
    rows = []
    for row in iter_items(matchups_payload):
        batter = str(row.get("batterName") or "").strip()
        pitcher = str(row.get("pitcherName") or "").strip()
        if not batter:
            continue
        game_id = as_int(row.get("gameId"))
        batter_id = as_int(row.get("batterId"))
        pitcher_team = canonical_team(row.get("pitcherTeam"))
        batter_team = canonical_team(row.get("batterTeam"))
        avg = averages.get((game_id or -1, batter_id or -1), {})
        sv = savant.get(batter_id or -1, {})
        pit = pitchers.get((pitcher.lower(), pitcher_team), {})
        park = park_by_team.get(batter_team) or {}
        hr_prob_raw = row.get("homeRunProbability")
        hr_prob = matchup_percent_probability(hr_prob_raw)
        if hr_prob is None:
            hr_prob = probability_from_mean(avg.get("homeRuns"))
        barrel = as_float(sv.get("barrel"))
        xwoba = as_float(sv.get("xwoba"))
        park_hr = parse_pct(park.get("HR %"))
        era = projected_era(pit)
        score = projected_hr_score(hr_prob, barrel, xwoba, park_hr, pit, streaks.get(batter.lower(), {}))
        rows.append(
            {
                "Batter": batter,
                "Team": batter_team,
                "Bats": (hands.get(batter_id or -1) or {}).get("bat"),
                "Pitcher": pitcher,
                "Pitcher Team": pitcher_team,
                "ERA": era if era is not None else "—",
                "Grade": projected_grade(score),
                "Score": score,
                "Streak": streak_label(streaks.get(batter.lower(), {})),
                "Zone": "—",
                "Barrel%": f"{barrel:.1f}%" if barrel is not None else "—",
                "HH%": "—",
                "xwOBA": f"{xwoba:.3f}" if xwoba is not None else "—",
                "Launch Ang": "—",
                "Pull%": "—",
                "Park": park.get("HR %") or "—",
                "HR": pct(hr_prob),
            }
        )
    rows.sort(key=lambda r: (-as_float(r.get("Score")) if as_float(r.get("Score")) is not None else 0, r.get("Batter") or ""))
    for idx, row in enumerate(rows, 1):
        row["Rank"] = idx
    return rows


def fetch_savant_batter_metrics(year: str) -> Dict[int, Dict[str, float]]:
    params = {
        "year": year,
        "type": "batter",
        "filter": "",
        "min": "10",
        "selections": "xwoba,barrel_batted_rate",
        "csv": "true",
    }
    url = "https://baseballsavant.mlb.com/leaderboard/custom?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8-sig", errors="replace")
    out: Dict[int, Dict[str, float]] = {}
    for row in csv.DictReader(text.splitlines()):
        player_id = as_int(row.get("player_id"))
        if player_id is None:
            continue
        out[player_id] = {
            "xwoba": as_float(row.get("xwoba")),
            "barrel": as_float(row.get("barrel_batted_rate")),
        }
    return out


def load_streaks() -> Dict[str, Mapping[str, Any]]:
    path = Path(os.environ.get("STREAKS_OUT", "streaks_live.json"))
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, Mapping):
        return {}
    return {str(k).strip().lower(): v for k, v in data.items() if isinstance(v, Mapping)}


def collect_player_ids(
    averages_by_game: Mapping[int, Mapping[str, Any]],
    matchups_payload: Mapping[str, Any],
) -> List[int]:
    ids = set()
    for payload in averages_by_game.values():
        data = payload.get("data") or {}
        for group in ("batters", "pitchers"):
            for row in data.get(group, []) or []:
                player_id = as_int(row.get("playerId"))
                if player_id is not None:
                    ids.add(player_id)
    for row in iter_items(matchups_payload):
        for key in ("batterId", "pitcherId"):
            player_id = as_int(row.get(key))
            if player_id is not None:
                ids.add(player_id)
    return sorted(ids)


def batter_average_index(payloads: Mapping[int, Mapping[str, Any]]) -> Dict[Tuple[int, int], Mapping[str, Any]]:
    out: Dict[Tuple[int, int], Mapping[str, Any]] = {}
    for game_id, payload in payloads.items():
        for row in (payload.get("data") or {}).get("batters", []) or []:
            player_id = as_int(row.get("playerId"))
            if player_id is not None:
                out[(game_id, player_id)] = row
    return out


def index_parks(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        game = str(row.get("Game") or "")
        if "@" not in game:
            continue
        away, home = [canonical_team(part) for part in game.split("@", 1)]
        out[away] = row
        out[home] = row
    return out


def opponent_for(team: str, meta: Mapping[str, Any]) -> str:
    away = canonical_team(meta.get("away"))
    home = canonical_team(meta.get("home"))
    if team == away:
        return home
    if team == home:
        return away
    return ""


def side_for(team: str, meta: Mapping[str, Any]) -> str:
    away = canonical_team(meta.get("away"))
    home = canonical_team(meta.get("home"))
    if team == away:
        return "A"
    if team == home:
        return "H"
    return ""


def projected_era(row: Mapping[str, Any]) -> Any:
    innings = as_float(row.get("innings") or row.get("Innings"))
    runs = as_float(row.get("runsAllowed") or row.get("RunsAllowed"))
    if innings is None or innings <= 0 or runs is None:
        return "—"
    return f"{runs / innings * 9:.2f}"


def projected_hr_score(
    hr_prob: Optional[float],
    barrel: Optional[float],
    xwoba: Optional[float],
    park_hr: int,
    pitcher: Mapping[str, Any],
    streak: Mapping[str, Any],
) -> int:
    hr_component = (hr_prob or 0) * 300
    barrel_component = (barrel or 0) * 1.25
    xwoba_component = max(0.0, (xwoba or 0) - 0.300) * 120
    park_component = max(-8, min(12, park_hr * 0.22))
    pitcher_component = (as_float(pitcher.get("HomeRunsAllowed")) or 0) * 8
    streak_component = (as_float(streak.get("hrStreak")) or as_float(streak.get("HR Streak")) or 0) * 3
    score = round(30 + hr_component + barrel_component + xwoba_component + park_component + pitcher_component + streak_component)
    return max(1, min(100, int(score)))


def projected_grade(score: int) -> str:
    if score >= 78:
        return "PRIME"
    if score >= 66:
        return "CORE"
    if score >= 54:
        return "LIVE"
    return "WATCH"


def streak_label(row: Mapping[str, Any]) -> str:
    hr = as_int(row.get("hrStreak") or row.get("HR Streak")) or 0
    hit = as_int(row.get("hitStreak") or row.get("Hit Streak")) or 0
    if hr >= 1:
        return f"HR{hr}"
    if hit >= 5:
        return f"H{hit}"
    return ""


def probability_from_mean(value: Any) -> float:
    mean = as_float(value)
    if mean is None or mean <= 0:
        return 0.0
    return round(1 - math.exp(-mean), 4)


def normalize_probability(value: Any) -> Optional[float]:
    num = as_float(value)
    if num is None:
        return None
    if num > 1:
        num /= 100
    return max(0.0, min(1.0, round(num, 4)))


def matchup_percent_probability(value: Any) -> Optional[float]:
    num = as_float(value)
    if num is None:
        return None
    return max(0.0, min(1.0, round(num / 100, 4)))


def poisson_at_least_two(mean: Optional[float]) -> float:
    if mean is None or mean <= 0:
        return 0.0
    return round(1 - math.exp(-mean) * (1 + mean), 4)


def poisson_over(mean: float, line: int) -> float:
    if mean <= 0:
        return 0.0
    cumulative = 0.0
    for k in range(0, line + 1):
        cumulative += math.exp(-mean) * (mean ** k) / math.factorial(k)
    return round(max(0.0, min(1.0, 1 - cumulative)), 4)


def poisson_total_distribution(mean: float) -> Dict[str, float]:
    out = {}
    probs = []
    for k in range(20):
        prob = math.exp(-mean) * (mean ** k) / math.factorial(k) if mean > 0 else 0
        probs.append(prob)
        out[f"Runs{k}"] = round(prob, 4)
    out["Runs20"] = round(max(0.0, 1 - sum(probs)), 4)
    return out


def pct(value: Any) -> str:
    num = as_float(value)
    if num is None:
        return "—"
    if 0 <= num <= 1:
        num *= 100
    return f"{num:.2f}%"


def parse_pct(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(str(value).replace("+", "").replace("%", "").strip()))
    except (TypeError, ValueError):
        return 0


def split_name(name: str) -> Tuple[str, str]:
    parts = name.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def last_name(name: Any) -> str:
    return split_name(str(name or ""))[1]


def index_rows(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for key in PROJECTED_TABS:
        values = data.get(key, [])
        columns = set()
        for row in values:
            if isinstance(row, Mapping):
                columns.update(row.keys())
        rows.append({"Sheet": key, "Rows": len(values), "Cols": len(columns)})
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
