#!/usr/bin/env python3
"""Regression test for healer log polling on fresh failed runs."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))

from log_retry import fetch_github_log_archive


class Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def main() -> int:
    statuses = [404, 404, 200]
    sleeps = []
    now = [0.0]

    def fake_get(*args, **kwargs):
        return Response(statuses.pop(0))

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    resp = fetch_github_log_archive(
        "https://api.github.com/repos/example/repo/actions/runs/1/logs",
        {},
        get=fake_get,
        sleep=fake_sleep,
        monotonic=lambda: now[0],
        timeout_seconds=60,
        initial_delay=5,
        max_delay=30,
    )
    assert resp.status_code == 200
    assert len(sleeps) == 2
    print(f"healer log retry OK: final_status={resp.status_code}, sleeps={sleeps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
