"""
functions/main.py
Autonomous Self-Healing Pipeline — Wysdomos/mlb-slate
Final production implementation — all patches applied.

Reviewed and finalized by Claude (Anthropic) — June 21, 2026

Patch history:
  V1 — Gemini initial build (4 bugs in spec)
  V2 — Fixed WEBHOOK_SECRET only (4 missed)
  V3 — Fixed null guard + YAML + runtime (3 still missed)
  FINAL — Claude applies remaining 3 patches + decorator fix
"""

import os
import re
import io
import zipfile
import hmac
import hashlib
import ast
import base64
import requests
from firebase_functions import https_fn, options
from google import genai

# ── ENVIRONMENT CONFIG ───────────────────────────────────────────
# These must all be set as Firebase environment variables.
# The Gemini client is created lazily inside the handler (the API key is a
# mounted secret, absent during deploy-time analysis).
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID")

# WEBHOOK_SECRET is validated per-request inside verify_signature()
# so that a missing secret fails closed (401) rather than open.


# ── SIGNATURE VERIFICATION ───────────────────────────────────────
def verify_signature(req: https_fn.Request) -> bool:
    """
    Validates that the incoming request was signed by GitHub Actions
    using the shared WEBHOOK_SECRET via HMAC-SHA256.
    Fails closed (returns False) if secret is not configured.
    """
    secret_str = os.environ.get("WEBHOOK_SECRET")
    if not secret_str:
        print("CRITICAL: WEBHOOK_SECRET environment variable is missing.")
        return False

    webhook_secret = secret_str.encode("utf-8")
    sig_header = req.headers.get("X-Hub-Signature-256", "")

    if not sig_header:
        return False

    body = req.get_data()
    expected = "sha256=" + hmac.new(
        webhook_secret, body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


# ── MOBILE NOTIFICATION ──────────────────────────────────────────
def notify_mobile(message: str):
    """Sends a push notification via Telegram Bot API. No-ops if not configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured — skipping notification.")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text":    message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
    except Exception as e:
        # Notification failure is non-fatal — log and continue
        print(f"Telegram notify failed: {e}")


# ── MAIN WEBHOOK HANDLER ─────────────────────────────────────────
@https_fn.on_request(
    timeout_sec=300,
    memory=options.MemoryOption.MB_512,
    secrets=[
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "WEBHOOK_SECRET",
    ],
)
def auto_heal_webhook(req: https_fn.Request) -> https_fn.Response:

    # ── STEP 1: AUTHENTICATE ─────────────────────────────────────
    if not verify_signature(req):
        return https_fn.Response(
            "Unauthorized or misconfigured webhook.", status=401
        )

    # ── STEP 2: VALIDATE PAYLOAD ─────────────────────────────────
    # PATCH 1: silent=True prevents crash on malformed body
    payload = req.get_json(silent=True)
    if not payload:
        return https_fn.Response(
            "Invalid or missing payload.", status=400
        )

    repo   = payload.get("repository")  # Wysdomos/mlb-slate
    run_id = payload.get("run_id")
    sha    = payload.get("sha")

    if not all([repo, run_id, sha]):
        return https_fn.Response(
            "Missing required fields: repository, run_id, sha.", status=400
        )

    # ── SELF-TEST: prove the Gemini key + model work (no repo touch) ──
    # Gated behind HMAC verification above; runs before any GitHub fetch.
    if payload.get("selftest") is True:
        try:
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            r = client.models.generate_content(
                model="gemini-3.5-flash",
                contents="Reply with exactly: OK",
            )
            msg = f"✅ Healer self-test passed. Gemini replied: {r.text.strip()[:40]}"
            notify_mobile(msg)
            return https_fn.Response(msg, status=200)
        except Exception as e:
            msg = f"❌ Healer self-test FAILED: {type(e).__name__}: {e}"
            print(msg)
            notify_mobile(msg)
            return https_fn.Response(msg, status=500)

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # ── STEP 3: FETCH AND PARSE ZIPPED LOGS ──────────────────────
    # GitHub /logs endpoint returns a 302 redirect to a zip archive.
    # Must follow redirect and unzip in memory — .text on binary = garbage.
    log_url = (
        f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
    )
    log_resp = requests.get(
        log_url, headers=headers, allow_redirects=True, timeout=30
    )

    if log_resp.status_code != 200:
        notify_mobile(
            f"⚠️ Healer could not fetch logs for run {run_id} "
            f"(HTTP {log_resp.status_code}). No action taken."
        )
        return https_fn.Response(
            f"Failed to fetch logs (HTTP {log_resp.status_code})", status=500
        )

    try:
        log_zip   = zipfile.ZipFile(io.BytesIO(log_resp.content))
        log_files = [f for f in log_zip.namelist() if f.endswith(".txt")]
        log_files.sort(
            key=lambda f: log_zip.getinfo(f).file_size, reverse=True
        )
        # Tail 8K chars — the traceback is always at the bottom
        error_log = log_zip.read(log_files[0]).decode(
            "utf-8", errors="replace"
        )[-8000:]
    except Exception as e:
        notify_mobile(f"⚠️ Healer could not parse logs for run {run_id}: {e}")
        return https_fn.Response(
            f"Error parsing log zip: {e}", status=500
        )

    # ── STEP 4: DYNAMIC CONTEXT RETRIEVAL ────────────────────────
    # Parse the failed Python filename from the traceback.
    match       = re.search(r'File "([^"]+\.py)"', error_log)
    failed_file = match.group(1).split("/")[-1] if match else None

    if not failed_file:
        print(f"Healer declined run {run_id}: no Python traceback in logs.")
        notify_mobile(
            f"🔍 Healer reviewed run {run_id} — no Python traceback "
            f"found, so there is no code to patch. No action taken. "
            f"(Likely a data/step failure, e.g. a missing workbook or "
            f"the freshness gate.)"
        )
        return https_fn.Response(
            "No Python file found in traceback.", status=200
        )

    # Fetch the full content of the broken file
    file_url  = (
        f"https://api.github.com/repos/{repo}/contents/{failed_file}"
    )
    file_resp = requests.get(
        file_url, headers=headers, timeout=30
    ).json()
    broken_code = base64.b64decode(
        file_resp.get("content", "")
    ).decode("utf-8")

    # Fetch AGENTS.md for project conventions context
    agents_url  = (
        f"https://api.github.com/repos/{repo}/contents/AGENTS.md"
    )
    agents_resp = requests.get(
        agents_url, headers=headers, timeout=30
    ).json()
    agents_md = base64.b64decode(
        agents_resp.get("content", "")
    ).decode("utf-8")[:3000]

    # ── STEP 5: GEMINI REASONING ──────────────────────────────────
    prompt = (
        f"You are fixing a Python script for The Daily Slate MLB pipeline.\n"
        f"Project conventions are in AGENTS.md below. "
        f"Output ONLY the corrected Python file.\n"
        f"No markdown fencing, no explanation, no preamble.\n\n"
        f"AGENTS.md (project conventions):\n{agents_md}\n\n"
        f"ERROR LOG (last 8000 chars):\n{error_log}\n\n"
        f"BROKEN FILE ({failed_file}):\n{broken_code}"
    )

    # PATCH 4: Wrap Gemini call — rate limits and API errors are real.
    # Uses the current google-genai SDK (the legacy google-generativeai
    # package is EOL and cannot reach gemini-3.5-flash).
    try:
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
        )
        raw_text = response.text
    except Exception as e:
        print(f"Gemini API error for {failed_file}: {type(e).__name__}: {e}")
        notify_mobile(
            f"⚠️ Auto-heal failed: Gemini API error for {failed_file}: {e}. "
            f"Manual intervention required."
        )
        return https_fn.Response("Gemini API call failed.", status=500)

    # ── STEP 6: STRIP MARKDOWN + AST GUARDRAIL ───────────────────
    # Strip any ```python or ``` fences Gemini adds despite instructions
    fixed_code = raw_text.strip()
    fixed_code = re.sub(r"^```python\s*", "", fixed_code)
    fixed_code = re.sub(r"^```\s*",       "", fixed_code)
    fixed_code = re.sub(r"```$",          "", fixed_code).strip()

    try:
        ast.parse(fixed_code)
    except SyntaxError as e:
        notify_mobile(
            f"🚨 Build failed in {failed_file}. "
            f"Generated fix has syntax error: {e}. "
            f"Manual intervention required."
        )
        return https_fn.Response(
            "Syntax check failed — aborting PR.", status=200
        )

    # ── STEP 7: CREATE BRANCH ────────────────────────────────────
    # PATCH 2 + 3: Timeouts on all calls + status code checks
    branch_name = f"auto-heal/{run_id}"

    branch_resp = requests.post(
        f"https://api.github.com/repos/{repo}/git/refs",
        headers=headers,
        json={
            "ref": f"refs/heads/{branch_name}",
            "sha": sha,
        },
        timeout=30,
    )
    # 201 = created, 422 = branch already exists (safe on retry)
    if branch_resp.status_code not in (201, 422):
        notify_mobile(
            f"⚠️ Auto-heal failed: could not create branch for {failed_file}. "
            f"GitHub status: {branch_resp.status_code}"
        )
        return https_fn.Response("Branch creation failed.", status=500)

    # ── STEP 8: PUSH FIXED FILE ──────────────────────────────────
    push_resp = requests.put(
        f"https://api.github.com/repos/{repo}/contents/{failed_file}",
        headers=headers,
        json={
            "message": f"Auto-heal: Fix {failed_file} errors",
            "content": base64.b64encode(
                fixed_code.encode("utf-8")
            ).decode("utf-8"),
            "sha":    file_resp.get("sha"),
            "branch": branch_name,
        },
        timeout=30,
    )
    if push_resp.status_code not in (200, 201):
        notify_mobile(
            f"⚠️ Auto-heal failed: could not push fix for {failed_file}. "
            f"GitHub status: {push_resp.status_code}"
        )
        return https_fn.Response("File push failed.", status=500)

    # ── STEP 9: OPEN PULL REQUEST ────────────────────────────────
    pr_resp = requests.post(
        f"https://api.github.com/repos/{repo}/pulls",
        headers=headers,
        json={
            "title": f"[Auto-Heal] Address failure in {failed_file}",
            "body": (
                "Automated reasoning applied via Firebase self-healer. "
                "Validated by `ast.parse()`. "
                "**Review logic carefully before merging.**"
            ),
            "head": branch_name,
            "base": "main",
        },
        timeout=30,
    ).json()

    pr_url = pr_resp.get("html_url")
    if not pr_url:
        notify_mobile(
            f"⚠️ Auto-heal: fix pushed for {failed_file} "
            f"but PR creation failed. Check GitHub manually."
        )
        return https_fn.Response("PR creation failed.", status=500)

    notify_mobile(f"✅ Auto-fix PR ready for {failed_file}: {pr_url}")
    return https_fn.Response("Self-healing sequence complete.")
