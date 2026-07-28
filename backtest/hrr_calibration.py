"""Empirical HRR calibration measurement.

Reads backtest/graded_picks.json without modifying it. Current historical
graded rows predate the hrr_pct copy field, so --recover-from-slate-picks can
join read-only slate_picks_*.json archives to recover the emitted prediction.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics
from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STORE = os.path.join(HERE, "graded_picks.json")
REPO = os.path.dirname(HERE)
APPLIED_OFFSET_POINTS = 8.9
APPLIED_GREEN_CUT = 73.0
APPLIED_ORANGE_CUT = 70.0


def norm_name(value: object) -> str:
    return str(value or "").strip().lower()


def load_json(path: str) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def recovered_predictions() -> Dict[Tuple[str, str], float]:
    out: Dict[Tuple[str, str], float] = {}
    for path in glob.glob(os.path.join(REPO, "slate_picks_*.json")):
        payload = load_json(path)
        if not isinstance(payload, Mapping):
            continue
        date = str(payload.get("slate_date") or "")
        for pick in payload.get("picks", []) or []:
            if not isinstance(pick, Mapping):
                continue
            if pick.get("market") != "HRR" or pick.get("hrr_pct") is None:
                continue
            out[(date, norm_name(pick.get("name")))] = float(pick["hrr_pct"])
    return out


def load_hrr_rows(store_path: str, recover: bool = False) -> List[dict]:
    store = load_json(store_path)
    if not isinstance(store, Mapping):
        return []
    recovery = recovered_predictions() if recover else {}
    rows: List[dict] = []
    for row in store.get("graded", []) or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("market") != "HRR" or row.get("win") is None:
            continue
        pred = row.get("hrr_pct")
        if pred is None:
            pred = recovery.get((str(row.get("date") or ""), norm_name(row.get("name"))))
        if pred is None:
            continue
        rows.append(
            {
                "date": str(row.get("date") or ""),
                "name": str(row.get("name") or ""),
                "pred": float(pred),
                "win": 1 if row.get("win") else 0,
                "got": row.get("got"),
            }
        )
    return rows


def brier(rows: Iterable[Mapping[str, float]], transform: Callable[[float], float]) -> float:
    items = list(rows)
    if not items:
        return math.nan
    return sum(((transform(float(row["pred"])) / 100.0) - float(row["win"])) ** 2 for row in items) / len(items)


def metrics(rows: List[dict], transform: Callable[[float], float] = lambda value: value) -> dict:
    preds = [max(0.0, min(99.0, transform(float(row["pred"])))) for row in rows]
    wins = [int(row["win"]) for row in rows]
    mean_pred = sum(preds) / len(preds) if preds else math.nan
    actual = 100.0 * sum(wins) / len(wins) if wins else math.nan
    return {
        "n": len(rows),
        "mean_pred": mean_pred,
        "actual": actual,
        "gap": abs(mean_pred - actual),
        "brier": brier(rows, transform),
    }


def five_point_bands(rows: Iterable[dict]) -> List[dict]:
    grouped: Dict[Tuple[int, int], List[dict]] = defaultdict(list)
    for row in rows:
        lo = int(float(row["pred"]) // 5 * 5)
        grouped[(lo, lo + 5)].append(row)
    out = []
    for (lo, hi), band in sorted(grouped.items()):
        stat = metrics(band)
        out.append({"band": f"{lo}-{hi}", **stat, "signed_gap": stat["mean_pred"] - stat["actual"]})
    return out


def date_split(rows: List[dict], test_dates: int = 3) -> Tuple[List[dict], List[dict]]:
    dates = sorted({row["date"] for row in rows if row.get("date")})
    if len(dates) <= test_dates:
        return rows, []
    held_out = set(dates[-test_dates:])
    train = [row for row in rows if row["date"] not in held_out]
    test = [row for row in rows if row["date"] in held_out]
    return train, test


def color_share(rows: List[dict], transform: Callable[[float], float], green: float, orange: float) -> List[dict]:
    groups = [
        ("green", lambda value: value >= green),
        ("orange", lambda value: orange <= value < green),
        ("base", lambda value: value < orange),
    ]
    out = []
    for label, predicate in groups:
        band = [row for row in rows if predicate(max(0.0, min(99.0, transform(float(row["pred"])))))]
        actual = 100.0 * sum(row["win"] for row in band) / len(band) if band else math.nan
        out.append({"label": label, "n": len(band), "share": len(band) / len(rows) if rows else 0.0, "actual": actual})
    return out


def report(rows: List[dict]) -> str:
    lines = []
    lines.append(f"HRR rows with prediction + outcome: {len(rows)}")
    lines.append("")
    lines.append("| Predicted band | n | Mean predicted | Actual hit rate | Gap |")
    lines.append("|---|---:|---:|---:|---:|")
    bands = five_point_bands(rows)
    for band in bands:
        lines.append(
            f"| {band['band']} | {band['n']} | {band['mean_pred']:.2f}% | "
            f"{band['actual']:.2f}% | {band['signed_gap']:.2f} pts |"
        )
    usable = [band for band in bands if band["n"] >= 30]
    gaps = [band["signed_gap"] for band in usable]
    if gaps and max(gaps) - min(gaps) <= 5:
        lines.append("")
        lines.append(
            "Gap shape: roughly constant across usable bands; a flat offset is the simplest supported correction."
        )
    else:
        lines.append("")
        lines.append("Gap shape: varies materially across usable bands; a flat offset may be insufficient.")

    train, test = date_split(rows)
    if test:
        train_stat = metrics(train)
        offset = train_stat["mean_pred"] - train_stat["actual"]
        scale = train_stat["actual"] / train_stat["mean_pred"] if train_stat["mean_pred"] else 1.0
        lines.append("")
        lines.append(f"Date split: train n={len(train)}, holdout n={len(test)}")
        lines.append(f"Flat offset fit from train: {offset:.2f} points")
        lines.append(f"Scale fit from train: {scale:.4f}")
        lines.append("")
        lines.append("| Shape | Split | Mean predicted | Actual | Gap | Brier |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for label, transform in (
            ("raw", lambda value: value),
            ("offset", lambda value, offset=offset: value - offset),
            ("scale", lambda value, scale=scale: value * scale),
        ):
            for split_label, split_rows in (("train", train), ("holdout", test)):
                stat = metrics(split_rows, transform)
                lines.append(
                    f"| {label} | {split_label} | {stat['mean_pred']:.2f}% | "
                    f"{stat['actual']:.2f}% | {stat['gap']:.2f} pts | {stat['brier']:.4f} |"
                )

    lines.append("")
    lines.append("Old color cuts on calibrated offset values: green >=82, orange >=75")
    for share in color_share(rows, lambda value: value - APPLIED_OFFSET_POINTS, 82.0, 75.0):
        lines.append(f"- {share['label']}: n={share['n']} share={share['share']:.1%} actual={share['actual']:.1f}%")
    lines.append("")
    lines.append("Candidate color cuts on calibrated offset values: green >=73, orange >=70")
    for share in color_share(rows, lambda value: value - APPLIED_OFFSET_POINTS, APPLIED_GREEN_CUT, APPLIED_ORANGE_CUT):
        lines.append(f"- {share['label']}: n={share['n']} share={share['share']:.1%} actual={share['actual']:.1f}%")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--recover-from-slate-picks", action="store_true")
    args = parser.parse_args()
    rows = load_hrr_rows(args.store, recover=args.recover_from_slate_picks)
    if not rows:
        print("No HRR rows with both prediction and outcome were found.")
        return 1
    print(report(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
