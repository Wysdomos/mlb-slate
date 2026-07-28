"""GitHub Actions log archive parsing helpers for the Firebase healer."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping


FAILED_CONCLUSIONS = {"failure", "timed_out", "cancelled", "action_required"}
IGNORED_CONCLUSIONS = {"success", "skipped", "neutral"}
FAILURE_SIGNATURES = (
    "Traceback (most recent call last)",
    "Process completed with exit code",
    "::error",
    "##[error]",
    "Error:",
    "Exception",
    "failed",
)


@dataclass(frozen=True)
class LogSelection:
    entry: str | None
    reason: str
    names: list[str]


@dataclass(frozen=True)
class ExtractedLog:
    error_log: str | None
    entry: str | None
    reason: str
    names: list[str]


def log_text_entries(names: list[str]) -> list[str]:
    return [name for name in names if name.endswith(".txt") and not name.endswith("/")]


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _is_failed(conclusion: object) -> bool:
    value = str(conclusion or "").lower()
    return bool(value) and value not in IGNORED_CONCLUSIONS


def fetch_failed_jobs(
    repo: str,
    run_id: str | int,
    headers: Mapping[str, str],
    *,
    get: Callable[..., Any],
) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    resp = get(url, headers=headers, timeout=30)
    if getattr(resp, "status_code", None) != 200:
        print(
            f"Could not fetch job metadata for run {run_id} "
            f"(HTTP {getattr(resp, 'status_code', 'unknown')}); falling back to log scan."
        )
        return []
    payload = resp.json() if hasattr(resp, "json") else {}
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    failed = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        steps = [step for step in job.get("steps", []) if isinstance(step, dict)]
        failed_steps = [step for step in steps if _is_failed(step.get("conclusion"))]
        if _is_failed(job.get("conclusion")) or failed_steps:
            failed.append({**job, "failed_steps": failed_steps})
    return failed


def _score_entry_for_job(entry: str, job: Mapping[str, Any]) -> int:
    normalized_entry = _norm(entry)
    score = 0
    job_name = _norm(job.get("name"))
    if job_name and job_name in normalized_entry:
        score += 100
    for step in job.get("failed_steps", []):
        step_name = _norm(step.get("name"))
        if step_name and step_name in normalized_entry:
            score += 50
        number = str(step.get("number") or "")
        if number and re.search(rf"(^|[/_-])0*{re.escape(number)}([_-]|$)", entry):
            score += 10
    return score


def _signature_score(text: str) -> int:
    lower = text.lower()
    score = 0
    for idx, signature in enumerate(FAILURE_SIGNATURES):
        if signature.lower() in lower:
            score += max(1, len(FAILURE_SIGNATURES) - idx)
    return score


def select_log_entry(
    log_zip: Any,
    names: list[str],
    *,
    failed_jobs: list[dict[str, Any]] | None = None,
) -> LogSelection:
    entries = log_text_entries(names)
    if not entries:
        return LogSelection(None, "empty", names)

    failed_jobs = failed_jobs or []
    scored = []
    for entry in entries:
        score = max((_score_entry_for_job(entry, job) for job in failed_jobs), default=0)
        if score:
            scored.append((score, log_zip.getinfo(entry).file_size, entry))
    if scored:
        score, _size, entry = max(scored)
        return LogSelection(entry, f"failed job metadata match score={score}", names)

    scanned = []
    for entry in entries:
        text = log_zip.read(entry).decode("utf-8", errors="replace")
        score = _signature_score(text)
        if score:
            scanned.append((score, log_zip.getinfo(entry).file_size, entry))
    if scanned:
        score, _size, entry = max(scanned)
        return LogSelection(entry, f"failure signature scan score={score}", names)

    entry = max(entries, key=lambda item: log_zip.getinfo(item).file_size)
    return LogSelection(entry, "largest readable .txt fallback", names)


def extract_error_log(
    log_zip: Any,
    repo: str,
    run_id: str | int,
    headers: Mapping[str, str],
    *,
    get: Callable[..., Any],
    tail_chars: int = 8000,
) -> ExtractedLog:
    names = list(log_zip.namelist())
    if not log_text_entries(names):
        return ExtractedLog(None, None, "empty", names)

    failed_jobs = fetch_failed_jobs(repo, run_id, headers, get=get)
    selection = select_log_entry(log_zip, names, failed_jobs=failed_jobs)
    if not selection.entry:
        return ExtractedLog(None, None, selection.reason, selection.names)

    text = log_zip.read(selection.entry).decode("utf-8", errors="replace")
    return ExtractedLog(text[-tail_chars:], selection.entry, selection.reason, selection.names)
