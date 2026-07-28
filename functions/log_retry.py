"""GitHub Actions log polling helpers for the Firebase healer."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

LOG_FINALIZE_INITIAL_DELAY_SECONDS = 120.0
LOG_RETRY_INITIAL_DELAY_SECONDS = 8.0


def fetch_github_log_archive(
    log_url: str,
    headers: Mapping[str, str],
    *,
    get: Callable[..., Any],
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    timeout_seconds: float = 180.0,
    initial_delay: float = LOG_RETRY_INITIAL_DELAY_SECONDS,
    max_delay: float = 45.0,
    finalize_delay: float = LOG_FINALIZE_INITIAL_DELAY_SECONDS,
    run_id: str | int | None = None,
) -> Any:
    """Poll GitHub's log archive endpoint until logs exist or timeout expires."""
    label = f"run {run_id}" if run_id is not None else "run log archive"
    if finalize_delay > 0:
        print(f"waiting {finalize_delay:.0f}s for {label} logs to finalize")
        sleep(finalize_delay)

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
            f"Logs not ready for {label} "
            f"(attempt {attempt}, elapsed {elapsed:.0f}s); waiting {wait:.0f}s."
        )
        if wait <= 0:
            return last_resp
        sleep(wait)
        delay = min(max_delay, delay * 1.7)
