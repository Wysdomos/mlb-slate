"""GitHub Actions log polling helpers for the Firebase healer."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping


def fetch_github_log_archive(
    log_url: str,
    headers: Mapping[str, str],
    *,
    get: Callable[..., Any],
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    timeout_seconds: float = 180.0,
    initial_delay: float = 8.0,
    max_delay: float = 45.0,
) -> Any:
    """Poll GitHub's log archive endpoint until logs exist or timeout expires."""
    started = monotonic()
    delay = initial_delay
    attempt = 0
    last_resp = None

    while True:
        attempt += 1
        last_resp = get(log_url, headers=headers, allow_redirects=True, timeout=30)
        if getattr(last_resp, "status_code", None) != 404:
            return last_resp

        elapsed = monotonic() - started
        if elapsed >= timeout_seconds:
            return last_resp

        wait = min(delay, max(0.0, timeout_seconds - elapsed))
        print(
            f"Logs not ready for run log archive "
            f"(attempt {attempt}, elapsed {elapsed:.0f}s); waiting {wait:.0f}s."
        )
        if wait <= 0:
            return last_resp
        sleep(wait)
        delay = min(max_delay, delay * 1.7)
