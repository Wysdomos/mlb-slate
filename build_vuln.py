"""BPP-derived Sweet_Spot_Slate vulnerability reconstruction."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Mapping


VULN_FIT_DATE = "2026-07-29"
VULN_FIT_SAMPLE_N = 32
VULN_SCORE_CEILING = 72

# Fitted against MLB Slate 7-29-26.xlsx Sweet_Spot_Slate using runtime-style
# BPP inputs. Each component is clipped at zero; the original score saturates
# around 72, so the reconstructed score keeps the same ceiling.
VULN_BASE_SCORE = 23.0
VULN_ERA_BASE = 3.0
VULN_ERA_SCALE = 5.5
VULN_ERA_WEIGHT = 36.0
VULN_HR9_BASE = 0.65
VULN_HR9_SCALE = 1.6
VULN_HR9_WEIGHT = 10.0
VULN_PARK_BASE = 0.92
VULN_PARK_SCALE = 0.4
VULN_PARK_WEIGHT = 20.0
VULN_BB9_BASE = 1.8
VULN_BB9_SCALE = 3.4
VULN_BB9_WEIGHT = 4.0

TEAM_ALIASES = {
    "WAS": "WSH",
    "WSN": "WSH",
    "SFG": "SF",
    "SDP": "SD",
    "TBR": "TB",
    "KCR": "KC",
    "CHW": "CHW",
}


def canonical_team(value: Any) -> str:
    text = str(value or "").strip().upper()
    return TEAM_ALIASES.get(text, text)


def normalized_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.strip().lower().split())


def normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(float(value)):
            return float(value)
        return None
    text = str(value).strip().replace("%", "").replace("+", "")
    if not text or text in {"-", "--", "—"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def required_row_value(row: Mapping[str, Any], accepted_keys: tuple[str, ...], context: str) -> Any:
    normalized = {normalized_key(key): key for key in row.keys()}
    for key in accepted_keys:
        actual = normalized.get(normalized_key(key))
        if actual is not None:
            return row.get(actual)
    joined = ", ".join(accepted_keys)
    available = ", ".join(str(key) for key in row.keys())
    raise KeyError(f"{context}: missing required column ({joined}); available: {available}")


def rounded(value: float | None, places: int) -> float | str:
    if value is None or not math.isfinite(value):
        return "—"
    return round(value, places)


def park_multiplier(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and "%" in value:
        pct = as_float(value)
        if pct is None:
            return None
        return round(1.0 + (pct / 100.0), 2)
    num = as_float(value)
    if num is None:
        return None
    if -100 <= num <= 100 and abs(num) > 3:
        return round(1.0 + (num / 100.0), 2)
    return round(num, 2)


def teams_from_game(game: Any) -> set[str]:
    text = str(game or "").upper()
    parts = [canonical_team(part) for part in re.split(r"\s+(?:@|VS\.?|V)\s+", text) if part.strip()]
    return {part for part in parts if part}


def park_factor_for_pitcher(
    pitcher_team: Any,
    opponent: Any,
    parks: list[Mapping[str, Any]],
) -> float | None:
    team = canonical_team(pitcher_team)
    opp = canonical_team(opponent)
    for park in parks:
        game_teams = teams_from_game(park.get("Game"))
        if team in game_teams and opp in game_teams:
            return park_multiplier(park.get("HR %"))
    return None


def projected_iso(row: Mapping[str, Any]) -> float | None:
    at_bats = as_float(required_row_value(row, ("AtBats", "At Bats", "AB"), "BP_Batters"))
    hits = as_float(required_row_value(row, ("Hits", "H"), "BP_Batters"))
    bases = as_float(required_row_value(row, ("Bases", "TotalBases", "Total Bases", "TB"), "BP_Batters"))
    if at_bats is None or at_bats <= 0 or hits is None or bases is None:
        return None
    return max(0.0, (bases - hits) / at_bats)


def danger_batters(opponent: Any, batters: list[Mapping[str, Any]]) -> list[str]:
    opp = canonical_team(opponent)
    ranked: list[tuple[float, str]] = []
    for batter in batters:
        if canonical_team(batter.get("Team")) != opp:
            continue
        name = str(batter.get("FullName") or "").strip()
        if not name:
            continue
        iso = projected_iso(batter)
        if iso is None:
            continue
        ranked.append((iso, name))
    ranked.sort(key=lambda item: (-item[0], normalized_name(item[1])))
    return [f"{name} (ISO .{int(round(iso * 1000)):03d})" for iso, name in ranked[:3]]


def vuln_score(era: float | None, hr9: float | None, park: float | None, bb9: float | None) -> int | str:
    if era is None or hr9 is None or park is None or bb9 is None:
        return "—"
    def component(value: float, base: float, scale: float) -> float:
        return max(0.0, (value - base) / scale)

    score = (
        VULN_BASE_SCORE
        + VULN_ERA_WEIGHT * component(era, VULN_ERA_BASE, VULN_ERA_SCALE)
        + VULN_HR9_WEIGHT * component(hr9, VULN_HR9_BASE, VULN_HR9_SCALE)
        + VULN_PARK_WEIGHT * component(park, VULN_PARK_BASE, VULN_PARK_SCALE)
        + VULN_BB9_WEIGHT * component(bb9, VULN_BB9_BASE, VULN_BB9_SCALE)
    )
    return int(round(max(0.0, min(float(VULN_SCORE_CEILING), score))))


def derive_vuln_row(
    sp_row: Mapping[str, Any],
    *,
    parks: list[Mapping[str, Any]] | None = None,
    batters: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    pitcher = str(required_row_value(sp_row, ("Pitcher", "FullName", "Full Name"), "SP_Projections")).strip()
    if not pitcher or pitcher.upper() == "TBD":
        return None

    team = canonical_team(required_row_value(sp_row, ("Team",), f"SP_Projections[{pitcher}]"))
    opponent = canonical_team(required_row_value(sp_row, ("Opp", "Opponent"), f"SP_Projections[{pitcher}]"))
    throws = str(sp_row.get("Throws") or sp_row.get("PitcherHand") or "").strip()
    era = as_float(required_row_value(sp_row, ("ERA",), f"SP_Projections[{pitcher}]"))
    try:
        inn_raw = required_row_value(sp_row, ("Inn", "Innings"), f"SP_Projections[{pitcher}]")
    except KeyError:
        inn_raw = None
    inn = as_float(inn_raw)

    dangers = danger_batters(opponent, batters or [])
    while len(dangers) < 3:
        dangers.append("—")

    if inn is None or inn <= 0:
        return {
            "Pitcher": pitcher,
            "Team": team,
            "Throws": throws,
            "Opponent": opponent,
            "ERA": rounded(era, 2),
            "WHIP": "—",
            "K9": "—",
            "BB9": "—",
            "ParkFactor": "—",
            "VulnScore": "—",
            "DangerBatter1": dangers[0],
            "DangerBatter2": dangers[1],
            "DangerBatter3": dangers[2],
        }

    hits = as_float(required_row_value(sp_row, ("H", "Hits", "HitsAllowed", "Hits Allowed"), f"SP_Projections[{pitcher}]"))
    home_runs = as_float(required_row_value(sp_row, ("HR", "HomeRuns", "HomeRunsAllowed", "Home Runs"), f"SP_Projections[{pitcher}]"))
    strikeouts = as_float(required_row_value(sp_row, ("K", "Strikeouts", "Strike outs"), f"SP_Projections[{pitcher}]"))
    walks = as_float(required_row_value(sp_row, ("BB", "Walks"), f"SP_Projections[{pitcher}]"))
    if hits is None or home_runs is None or strikeouts is None or walks is None:
        raise ValueError(f"SP_Projections[{pitcher}]: H/HR/K/BB values must be numeric")

    whip = (hits + walks) / inn
    k9 = (strikeouts / inn) * 9.0
    bb9 = (walks / inn) * 9.0
    hr9 = (home_runs / inn) * 9.0
    park = park_factor_for_pitcher(team, opponent, parks or [])

    return {
        "Pitcher": pitcher,
        "Team": team,
        "Throws": throws,
        "Opponent": opponent,
        "ERA": rounded(era, 2),
        "WHIP": rounded(whip, 2),
        "K9": rounded(k9, 1),
        "BB9": rounded(bb9, 1),
        "ParkFactor": rounded(park, 2),
        "VulnScore": vuln_score(era, hr9, park, bb9),
        "DangerBatter1": dangers[0],
        "DangerBatter2": dangers[1],
        "DangerBatter3": dangers[2],
    }


def build_vuln_by_name(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    parks = list(data.get("Park_Factors") or [])
    batters = list(data.get("BP_Batters") or [])
    for sp_row in data.get("SP_Projections") or []:
        row = derive_vuln_row(sp_row, parks=parks, batters=batters)
        if not row:
            continue
        rows[str(row["Pitcher"]).strip().lower()] = row
    return rows


def workbook_vuln_by_name(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        pitcher = str(row.get("Pitcher") or "").strip()
        if not pitcher or pitcher == "TBD":
            continue
        copied = dict(row)
        copied["source"] = "workbook"
        out[pitcher.lower()] = copied
    return out


def vuln_by_name(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    workbook_rows = workbook_vuln_by_name(list(data.get("Sweet_Spot_Slate") or []))
    if workbook_rows:
        return workbook_rows
    bpp_rows = build_vuln_by_name(data)
    for row in bpp_rows.values():
        row["source"] = "bpp"
    return bpp_rows
