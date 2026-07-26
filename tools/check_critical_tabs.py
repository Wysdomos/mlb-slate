#!/usr/bin/env python3
"""Warn and alert when non-fatal fetch steps leave critical slate tabs empty."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable, Mapping

DEFAULT_CRITICAL_TABS = ("Park_Factors", "SP_Projections")


def main() -> int:
    data_file = Path(os.environ.get("DATA_FILE", "day_data.json"))
    critical_tabs = tuple(split_csv(os.environ.get("CRITICAL_TABS"))) or DEFAULT_CRITICAL_TABS
    run_url = os.environ.get("GITHUB_RUN_URL", "")

    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    except Exception as exc:
        message = f"critical tab check could not read {data_file}: {exc}"
        warn(message)
        send_telegram(f"Daily Slate warning: {message}", run_url)
        return 0

    empty = [tab for tab in critical_tabs if row_count(data, tab) == 0]
    if not empty:
        counts = ", ".join(f"{tab}={row_count(data, tab)}" for tab in critical_tabs)
        print(f"Critical slate tabs OK: {counts}")
        return 0

    counts = ", ".join(f"{tab}={row_count(data, tab)}" for tab in critical_tabs)
    message = (
        "critical slate tab(s) empty after non-fatal fetch: "
        f"{', '.join(empty)} ({counts})"
    )
    warn(message)
    send_telegram(f"Daily Slate warning: {message}", run_url)
    return 0


def split_csv(value: str | None) -> Iterable[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def row_count(data: Mapping[str, object], tab: str) -> int:
    rows = data.get(tab)
    return len(rows) if isinstance(rows, list) else 0


def warn(message: str) -> None:
    print(f"::warning title=Critical slate tab empty::{message}")
    print(f"[critical-tabs] WARNING: {message}", file=sys.stderr)


def send_telegram(message: str, run_url: str = "") -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    text = f"{message}\n{run_url}".strip()
    if os.environ.get("TELEGRAM_DRY_RUN") == "1":
        print(f"[critical-tabs] Telegram dry run: {text}")
        return
    if not bot_token or not chat_id:
        print("[critical-tabs] Telegram not configured; alert not sent", file=sys.stderr)
        return
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=body,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[critical-tabs] Telegram alert sent HTTP {resp.status}")
    except Exception as exc:
        print(f"[critical-tabs] Telegram alert failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
