#!/usr/bin/env python3
"""Skip publishing degenerate Projected Mode builds."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping


def main() -> int:
    data_path = Path(os.environ.get("DATA_FILE", "day_data.json"))
    data = read_json(data_path)
    mode = data.get("_mode")
    slate_date = str(data.get("_slate_date") or "unknown")

    if mode != "projected":
        print("[projected-guard] workbook-backed build; publish guard not applied")
        return 0

    hr_count = row_count(data, "HR_Leaderboard")
    hits_count = row_count(data, "Hit_Probabilities")
    min_hr = env_int("PROJECTED_MIN_HR", 50)
    min_hits = env_int("PROJECTED_MIN_HITS", 50)

    print(
        "[projected-guard] "
        f"slate_date={slate_date} hr_rows={hr_count} hits_rows={hits_count} "
        f"min_hr={min_hr} min_hits={min_hits}"
    )

    if hr_count < min_hr or hits_count < min_hits:
        print(
            "[projected-guard] skipping commit/push: Projected Mode reconstruction "
            "is below non-degenerate publish thresholds"
        )
        set_github_value("GITHUB_ENV", "SKIP_PROJECTED_PUBLISH", "1")
        set_github_value("GITHUB_OUTPUT", "skip_publish", "1")
    else:
        print("[projected-guard] projected reconstruction meets publish thresholds")
        set_github_value("GITHUB_ENV", "SKIP_PROJECTED_PUBLISH", "0")
        set_github_value("GITHUB_OUTPUT", "skip_publish", "0")

    return 0


def read_json(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def row_count(data: Mapping[str, Any], key: str) -> int:
    rows = data.get(key)
    return len(rows) if isinstance(rows, list) else 0


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def set_github_value(env_var: str, name: str, value: str) -> None:
    path = os.environ.get(env_var)
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


if __name__ == "__main__":
    raise SystemExit(main())
