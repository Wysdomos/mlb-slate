# The Daily Slate — BPP-Powered Rebuild

**Spec for review. No code written, no branch created.**
Repo inspected at `bdc2acea6ce7a716f3843270d363beddd44c9479` (2026-08-29)
Reviewer: Claude (architect lane)

**Goal:** BallparkPal becomes the sole data spine. Projected Mode becomes the only mode. Cordon skin becomes permanent. 8 builds/day. Kalshi deferred.

---

## 0. CRITICAL FINDING — READ FIRST

**Projected Mode is currently running by accident, not by design.**

`daily.yml` step "Find slate file":

```bash
XLSX=$(python3 extract_xlsx.py --which)
if [ -z "$XLSX" ]; then echo "No xlsx found" && exit 1; fi
```

With no workbook, `--which` returns `None` under `ALLOW_PROJECTED_MODE=1`, `$XLSX` is empty, and **the build hard-exits 1.**

It has not been failing because exactly one stale workbook is sitting in the repo:

```
MLB Slate 7-29-26.xlsx     (dated July 29 — one month old)
```

`--which` finds it, `extract_xlsx.py` sees the date is stale, logs `stale workbook dated … ignored; entering Projected Mode`, and writes the projected marker. Verified live: `day_data.json` reads `_mode: projected`, `_slate_date: 2026-08-29`, 15 tabs.

**Delete that file today and every build fails.** A month-old spreadsheet is the only thing keeping the pipeline alive. Fixing this is the real content of PR 1 — the mode flip is almost a side effect.

---

## 1. SSJ DECISION — DELETE

The condition was: keep SSJ if BPP can backfill HR. It cannot, and the reason is structural rather than a coverage gap.

### The formula

From `build_scout.py`:

```
SSJ Score = (Zone × 3) + (VulnScore/100 × 20) + (ISO × 30)
          + (wOBA × 20) + (HR × 0.2) + streak bonuses + DANGER/grade bonuses
```

Zone carries the heaviest weight. Both Zone and VulnScore come from workbook Sweet Spot tabs.

### VulnScore survives. Zone does not.

`VulnScore` is defined as ERA trend + HR/9 + park HR factor + walk rate. **BPP supplies all four.** It is cleanly reconstructable.

`Zone` is defined as a composite of ISO + wOBA + HR output + pitcher vulnerability + platoon advantage. Every input is available from BPP + Savant + MLB Stats API — which is exactly the problem.

Rebuild Zone from those inputs and substitute back:

```
SSJ = 3 × (ISO + wOBA + HR + Vuln + platoon)
    + Vuln + ISO + wOBA + HR
```

ISO, wOBA, HR and Vuln each get counted **four times**. The composite stops meaning anything. A reconstructed Zone would be a different model wearing the old name, and the page would keep teaching a glossary that no longer describes it.

### Verdict

**Delete SSJ. Harvest VulnScore.**

- `build_scout.py` — deleted
- `scout.html` — deleted, link removed from headlines and rail
- `VulnScore` — rebuilt from BPP as `build_vuln.py`, feeding **Matchup Spotlight** and the **Pitcher's HR Risk Board** on the main slate

This trades a standalone page for two boards that were going dark anyway. The DANGER tag survives, which matters because it is the intended gate for Anchor parlays.

**Dependency check clean:** `parlay_rules.py` has zero references to Zone, Vuln, or DANGER. No parlay logic breaks. Remaining consumers of Zone/Vuln are `build_day46.py` and `build_streaks.py` only.

---

## 2. NEW `daily.yml`

Replaces the trigger block, adds concurrency, drops the xlsx path.

```yaml
name: Daily MLB Slate Build

on:
  schedule:
    - cron: '0 7 * * *'    #  3:00 AM ET - new slate, overnight grading
    - cron: '0 13 * * *'   #  9:00 AM ET - BPP posts the day's sims
    - cron: '0 16 * * *'   # 12:00 PM ET - day-game lineups
    - cron: '0 19 * * *'   #  3:00 PM ET - early lineup window
    - cron: '0 21 * * *'   #  5:00 PM ET - final pre-lock, 6:40/7:05 games
    - cron: '0 23 * * *'   #  7:00 PM ET - early games lock
    - cron: '0 1 * * *'    #  9:00 PM ET - West Coast 9:40 lineups
    - cron: '0 3 * * *'    # 11:00 PM ET - last call
  workflow_dispatch:

concurrency:
  group: daily-build
  cancel-in-progress: false

permissions:
  contents: write
```

**Removed:** `push: paths: ['**.xlsx']`. No workbooks means no upload trigger.

**Concurrency is a prerequisite, not a nice-to-have.** `daily.yml` currently has *no* concurrency group — only `grade.yml` does. At 4 builds across 13 hours that survives. At 8 builds plus manual dispatches, two runs race on the push. Queue rather than cancel: builds take minutes, and cancelling mid-push is worse than waiting.

**Cron is UTC.** These times shift one hour when EDT ends in November. Either accept the drift or split into seasonal schedules.

### Steps to delete

```yaml
- name: Find slate file        # DELETE — the exit-1 trap
- name: Extract slate data     # DELETE
```

### Step to replace them

```yaml
- name: Initialize slate day
  env:
    DATA_FILE: day_data.json
  run: python3 init_slate_day.py
```

`init_slate_day.py` is new and small: resolve today's date in ET, write the projected marker into `day_data.json`, exit 0. It is what `extract_xlsx.py` already does on the stale path, minus the workbook detour and the exit-1 trap.

Everything downstream — `fetch_projected_mode.py`, `fetch_bpp_tabs.py`, `check_critical_tabs.py`, `build.py`, `sync.py` — is unchanged.

---

## 3. REQUEST BUDGET

`fetch_bpp_tabs.py` already encodes `BPP_MONTHLY_BUDGET = 15000` and logs per-run counts.

Per run: `games` + `parkfactors` + 15 × `projection_averages` + 15 × `probabilities` ≈ **32 BPP calls**.

| Builds/day | Calls/month (31d) | % of budget |
|---|---|---|
| 4 (current) | 3,968 | 26% |
| **8 (target)** | **7,936** | **53%** |
| 10 | 9,920 | 66% |
| 12 | 11,904 | 79% |
| 15 | 14,880 | 99% — no headroom |

8/day leaves 47% for retries, `grade.yml`, and manual dispatches. Ten is the ceiling.

**Verify the 32-call estimate on the first run** — `fetch_bpp_tabs.py` prints `calls/run BPP=N`. If N is materially above 32, drop to 6 builds and revisit.

**Recommend notifying Aaron.** Written permission covers access, not volume. Going from 4 to 8 daily runs doubles call volume against his infrastructure. A short heads-up email costs nothing and protects the relationship the whole platform depends on.

---

## 4. CORDON SKIN — PERMANENT

One line in `sync.py::apply_projected_theme()`:

```python
# before
if not PROJECTED_MODE:
    html = re.sub(r'<body class="projected-mode">', '<body>', html, count=1)
    ...
    return html
html = re.sub(r'<body(?: class="[^"]*")?>', '<body class="projected-mode">', html, count=1)

# after — unconditional
html = re.sub(r'<body(?: class="[^"]*")?>', '<body class="projected-mode">', html, count=1)
```

**Every token survives untouched.** No CSS edits:

```
--bg #0d1117      --surface #101720     --surface-2 #14202b
--accent #22d3ee  --accent-soft rgba(34,211,238,0.14)
--gold #fbbf24    --tier0 #67e8f9       --tier1 #fbbf24
--glass rgba(103,232,249,0.08)          --border rgba(125,211,252,0.2)
```

Plus the `.projected-mode .app-bar / .hero / .game-header / .collapsible` rules and the full `[data-theme="light"] .projected-mode` override block.

**Do not rename the class in this PR.** `.projected-mode` appears ~40 times across 280 lines of CSS in `sync.py`. Rename to `.cordon` later as a pure find/replace with no other change in the diff.

---

## 5. COPY REWRITE

The skin stays; the apology goes. Current copy frames the mode as degraded and temporary.

| Location | Now | Becomes |
|---|---|---|
| Top banner | "PROJECTED MODE — no workbook uploaded… Upload the workbook to restore the full slate" | **Delete.** The normal state does not announce itself. |
| Per-section badges | `PROJECTED MODE` on each section | **Delete.** Meaningless when universal. |
| Withheld notice | "2 boards withheld today — held back rather than estimated" | **Delete.** Boards are rebuilt or removed, not withheld. |
| Alignment table | "Projected Mode Alignment" / "reconstructed board boundaries" | "Board Alignment" / "tap to expand — board boundaries" |
| Methodology | Teaches `ZONE ⚡5+` and `Vuln 50+` as core signals | Rewrite: BPP HR probability, park factor, HRA, platoon, consensus lenses |
| Glossary | Defines Zone, VulnScore, Sweet Spot grades | Remove Zone; keep VulnScore with a BPP-sourced definition |

The methodology rewrite matters most. It is the onboarding document, and it currently instructs readers to look at columns that render `—` on every row.

### Dead columns

- HR Board `Zone` → `—` on all 50 rows. **Remove.**
- K Board `Vuln` → `V—` on all 30 rows. **Restore** from `build_vuln.py`.

---

## 6. DEAD CODE

| File | Action |
|---|---|
| `MLB Slate 7-29-26.xlsx` | Delete — but **only after** PR 1 removes the exit-1 trap |
| `extract_xlsx.py` | Replace with `init_slate_day.py` |
| `build_editorial.py` | Already skipped in Projected Mode. Delete + remove Step 3 from `build.py` |
| `build_scout.py` | Delete (§1) |
| `scout.html` | Delete; remove headline link and rail chip |
| `tools/check_critical_tabs.py` | **Keep.** `Park_Factors` and `SP_Projections` are now BPP-sourced and more critical, not less |

**Ordering is load-bearing.** Deleting the xlsx before the workflow fix takes the site down.

---

## 7. PR SEQUENCE

Four PRs. Not one. A four-day outage in this repo traced to a single unstaged file; a bundled diff makes a red build uninformative.

### PR 1 — Workflow (Codex)
`init_slate_day.py`; remove the two xlsx steps; add concurrency; 8-cron schedule; drop the push trigger.
**Gate:** one full day of green builds at all 8 slots. Confirm `calls/run BPP=N` ≈ 32.
**Do not delete the xlsx yet.**

### PR 2 — Permanent Cordon + copy (Claude Code)
Unconditional body class; banner, badges, withheld notice, alignment strings, methodology, glossary.
**Gate:** mobile screenshots at 390px, dark and light. All 19 sections present. Rail scrollspy intact.

### PR 3 — SSJ removal + Vuln rebuild (Codex)
Delete `build_scout.py` and `scout.html`; new `build_vuln.py`; restore Matchup Spotlight and Pitcher's HR Risk; remove the Zone column.
**Gate:** `parlay_rules.py` tests pass unchanged. `tools/test_parlay_rules.py` green.

### PR 4 — Dead code sweep (Codex)
Delete the stale xlsx, `extract_xlsx.py`, `build_editorial.py`. Refresh `AGENTS.md` — its file map is stale (`build_day46.py` listed at ~1,673 lines; actual is 3,636).

**Kalshi is PR 5+**, per `KALSHI_V1_SPEC.md`, after this stack is green for a week.

---

## 8. RISKS

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | xlsx deleted before PR 1 merges → total outage | **Critical** | Ordering in §7; call it out in the PR description |
| R2 | BPP calls/run exceeds 32 → budget overrun | High | Verify on first run; fall back to 6 builds |
| R3 | Two builds race on push at 8×/day | High | Concurrency group in PR 1 |
| R4 | BPP outage now has no workbook fallback | High | `check_critical_tabs.py` + Telegram already fire; consider a "last good build" banner |
| R5 | Methodology still teaches Zone after removal | Medium | PR 2 gate includes a full read of the methodology section |
| R6 | Rebuilt Vuln ≠ old Vuln, same name | Medium | Label it `Vuln (BPP)` in the glossary; do not imply continuity with workbook scores |
| R7 | Cron drifts an hour at DST | Low | Accept, or split seasonal schedules |
| R8 | BPP rate-limits at doubled volume | Medium | `BPP_MIN_GAP: '6.2'` already set; notify Aaron |

---

## 9. OPEN QUESTIONS

1. **Notify Aaron before or after PR 1?** Recommend before.
2. **BPP outage behavior** — hold the last good build with a staleness banner, or render unavailable cards? Currently the latter.
3. **`Vuln (BPP)` weights** — reuse the workbook's ERA/HR9/park/BB blend, or refit? Recommend reuse initially so the DANGER threshold at 70 stays interpretable.
4. **Streaks** — `build_streaks.py` reads Zone. Confirm it degrades cleanly or needs the same treatment.
5. **Rename `.projected-mode` → `.cordon`** — separate cosmetic PR, or leave permanently?

---

## 10. NOT DONE

No branch. No code. No commit. Nothing pushed.

On approval: PR 1 and PR 3 to Codex (data/logic/infra lane), PR 2 to Claude Code (presentation lane), PR 4 either.
