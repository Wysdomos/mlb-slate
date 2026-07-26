#!/usr/bin/env python3
"""Guard public JSON/HTML against raw BallparkPal values.

The repo has historical generated JSON on main. This check is intentionally
baseline-aware so a Chapter F PR does not rewrite history, while still failing
new raw field names and simple raw-value renames.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

RAW_FIELD_MARKERS = (
    "matchup_advantage",
    "matchupAdvantage",
    "homeRunProbability",
    "singleProbability",
    "homeRunVsTypical",
    "runsCreatedVsTypical",
    "VsTypical",
    "requestId",
    "marketKey",
    "asOf",
)

RAW_MATCHUP_KEY = "bpp_matchup_advantage"
SUSPICIOUS_KEY_PARTS = ("calibration", "matchup", "advantage", "signal")
BASE_SENTINEL = object()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args(argv)

    base = merge_base(args.base)
    failures: List[str] = []
    files = changed_public_files(base)
    failures.extend(check_added_raw_markers(base, files))
    failures.extend(check_pick_value_renames(base, files))

    if failures:
        print("BPP compliance check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f"BPP compliance OK ({len(files)} changed JSON/HTML files checked against {base[:12]})")
    return 0


def run_git(args: Sequence[str], *, text: bool = True) -> str:
    return subprocess.check_output(["git", *args], text=text)


def merge_base(base_ref: str) -> str:
    return run_git(["merge-base", "HEAD", base_ref]).strip()


def changed_public_files(base: str) -> List[str]:
    out = run_git(["diff", "--name-only", base, "--", "*.json", "*.html"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def check_added_raw_markers(base: str, files: Sequence[str]) -> List[str]:
    if not files:
        return []
    diff = run_git(["diff", "-U0", base, "--", *files])
    failures = []
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for marker in RAW_FIELD_MARKERS:
            if marker in line:
                failures.append(f"added raw BPP marker `{marker}` in public JSON/HTML")
    return sorted(set(failures))


def check_pick_value_renames(base: str, files: Sequence[str]) -> List[str]:
    failures = []
    for file_name in files:
        path = Path(file_name)
        if not path.name.startswith("slate_picks") or path.suffix != ".json":
            continue
        before = read_json_at(base, file_name)
        after = read_json_file(path)
        before_picks = picks(before)
        after_picks = picks(after)
        raw_sequence = [pick.get(RAW_MATCHUP_KEY, BASE_SENTINEL) for pick in before_picks]
        if not before_picks or all(value is BASE_SENTINEL for value in raw_sequence):
            continue
        current_keys = sorted({key for pick in after_picks for key in pick})
        for key in current_keys:
            if key == RAW_MATCHUP_KEY:
                continue
            sequence = [pick.get(key, BASE_SENTINEL) for pick in after_picks]
            if sequence == raw_sequence:
                failures.append(
                    f"{file_name}: `{key}` is byte-for-byte the old raw BPP matchup vector"
                )
            elif suspicious_raw_integer_vector(key, sequence):
                failures.append(
                    f"{file_name}: `{key}` looks like an untransformed BPP matchup integer vector"
                )
    return failures


def suspicious_raw_integer_vector(key: str, sequence: Sequence[Any]) -> bool:
    if not any(part in key.lower() for part in SUSPICIOUS_KEY_PARTS):
        return False
    values = [value for value in sequence if value is not BASE_SENTINEL and value is not None]
    if len(values) < 10:
        return False
    return all(isinstance(value, int) and -10 <= value <= 10 for value in values)


def read_json_at(base: str, file_name: str) -> Any:
    try:
        text = run_git(["show", f"{base}:{file_name}"])
    except subprocess.CalledProcessError:
        return {}
    return json.loads(text)


def read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def picks(payload: Any) -> List[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    rows = payload.get("picks")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


if __name__ == "__main__":
    raise SystemExit(main())
