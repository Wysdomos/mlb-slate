# SESSION STATUS - 2026-07-25 - Codex

## 0. CHAPTER G ADD-ON - PICK PROVENANCE
- Stayed on `codex/chapter-g-early-build`; this is an add-on for the existing PR #22.
- Added `PICK_SOURCE = 'projected' if PROJECTED_MODE else 'workbook'` in `build_day46.py`.
- Added `pick_source` to all 8 `SLATE_PICKS.append({...})` payloads.
- Added historical compatibility in `backtest/backfill_grades.py`: missing `pick_source` defaults to `workbook` when new graded rows are written.
- Added calibration segmentation in `backtest/calibration.py`: `build(store, source_filter=...)` and CLI `--pick-source workbook|projected`, with missing historical values treated as `workbook`.
- Did not modify any existing `slate_picks*.json`, `backtest/graded_picks.json`, or generated public HTML/JSON files.

### Add-On Verification

a. Workbook-backed build -> every pick record has `pick_source == 'workbook'`; count matches total picks:
```text
python3 extract_xlsx.py MLB_Slate_7-25-26.xlsx /tmp/chapterg-addon-current-day_data.json
HR_Leaderboard: 270 rows
Hit_Probabilities: 258 rows
Done. 1508 total rows -> /tmp/chapterg-addon-current-day_data.json

build_day46.py temp-output execution
Wrote 205 pick records -> /tmp/chapterg-addon-current-picks.json (+ slate_picks_7-25.json)

workbook picks=205 pick_source_workbook=205 missing=0
```

b. Projected build -> every pick record has `pick_source == 'projected'`; count matches total picks:
```text
ALLOW_PROJECTED_MODE=1 python3 extract_xlsx.py /tmp/chapterg-addon-projected-day_data.json
Projected Mode marker written for 2026-07-25 because no workbook was uploaded and ALLOW_PROJECTED_MODE=1.
Done. 14 total rows -> /tmp/chapterg-addon-projected-day_data.json

DATA_FILE=/tmp/chapterg-addon-projected-day_data.json STREAKS_OUT=streaks_live.json BPP_MIN_GAP=0.1 python3 fetch_projected_mode.py
[projected] rebuilt 2026-07-25: HR=270, Hits=270, Savant=573 batters
[projected] calls/run BPP=33, MLB=5; 3 runs/day BPP ~= 99; 4 runs/day BPP ~= 132; monthly budget 15000
Projected Mode BPP API calls this run: 33

build_day46.py temp-output execution
Wrote 99 pick records -> /tmp/chapterg-addon-projected-picks.json (+ slate_picks_7-25.json)

projected picks=99 pick_source_projected=99 missing=0 other=[]
```

c. Upload-day HR and Hits HTML section diffs still empty vs `origin/main`:
```text
main hr-board 25735
main oo5-board 18954
current hr-board 25735
current oo5-board 18954

diff -u /tmp/chapterg-addon-main-hr.html /tmp/chapterg-addon-current-hr.html
exit 0, empty

diff -u /tmp/chapterg-addon-main-hits.html /tmp/chapterg-addon-current-hits.html
exit 0, empty
```

d. `slate_picks.json` diff vs main shows the added key and nothing else:
```text
workbook picks=205 pick_source_workbook=205 missing=0
stripped_equals_main True
main_has_pick_source False
current_keys_delta_only_pick_source True
```

e. `calibration.py` and `backfill_grades.py` run clean against existing historical `graded_picks.json` with no `pick_source` present:
```text
historical graded rows 2660
pick_source present before 0

python3 backtest/calibration.py
wrote /private/tmp/chapterg-addon-backtest/backtest/CALIBRATION.md (3299 bytes)

python3 backtest/calibration.py --pick-source workbook
wrote /private/tmp/chapterg-addon-backtest/backtest/CALIBRATION.md (3299 bytes)

python3 backtest/calibration.py --pick-source projected
wrote /private/tmp/chapterg-addon-backtest/backtest/CALIBRATION.md (1206 bytes)

python3 backtest/backfill_grades.py
1 slate files · 11 date(s) already backfilled
wrote /private/tmp/chapterg-addon-backtest/backtest/graded_picks.json: 2660 rows, 2443 gradable, 11 dates

historical graded rows after 2660
pick_source present after 0
```

Additional backtest mock:
```text
python3 backtest/test_backtest_mock.py
ALL TESTS PASSED
```

f. BPP compliance:
```text
python3 tools/check_bpp_compliance.py --base origin/main
BPP compliance OK (0 changed JSON/HTML files checked against eb82870cec59)
```

g. `ast.parse` and `py_compile`:
```text
ast OK extract_xlsx.py
ast OK fetch_projected_mode.py
ast OK build.py
ast OK build_day46.py
ast OK sync.py
ast OK backtest/calibration.py
ast OK backtest/backfill_grades.py
ast OK tools/check_bpp_compliance.py
ast OK tools/projected_publish_guard.py

python3 -m py_compile extract_xlsx.py fetch_projected_mode.py build.py build_day46.py sync.py backtest/calibration.py backtest/backfill_grades.py tools/check_bpp_compliance.py tools/projected_publish_guard.py
exit 0
```

## 1. WHAT I DID
- Branch: `codex/chapter-g-early-build` from `origin/main` after Chapter F PR #21 was merged as `eb82870 Add Chapter F Projected Mode (#21)`.
- Changed stale workbook handling in `extract_xlsx.py`:
  - With `ALLOW_PROJECTED_MODE=1`, a stale newest workbook is left untouched and treated like an absent workbook.
  - With the flag unset, existing hard-fail behavior and messages are unchanged.
  - A same-day workbook still extracts normally.
- Added `tools/projected_publish_guard.py` for non-degenerate Projected Mode publishing:
  - Workbook-backed builds are never guarded.
  - Projected builds log slate date, HR rows, Hits rows, and thresholds.
  - Projected builds below `PROJECTED_MIN_HR` or `PROJECTED_MIN_HITS` set `SKIP_PROJECTED_PUBLISH=1` and exit 0.
- Updated `.github/workflows/daily.yml`:
  - Added `0 7 * * *` early cron for 3:00 AM ET.
  - Inserted the publish guard after `sync.py`.
  - Skips compliance and commit/push when the guard marks a thin Projected Mode run.

## 2. INTENTIONAL REQUIREMENT REVERSAL
- Chapter F required stale workbooks to hard-fail even with Projected Mode enabled.
- Chapter G deliberately reverses that owner-approved requirement: stale workbooks are now treated as absent only when `ALLOW_PROJECTED_MODE=1`.
- Commit message must say this is owner-approved.

## 3. RAW VERIFICATION OUTPUT

a. Stale workbook present, `ALLOW_PROJECTED_MODE=1` -> projected marker written, exit 0, stale file untouched:
```text
ALLOW_PROJECTED_MODE=1 python3 extract_xlsx.py --which
allow which exit=0
__PROJECTED_MODE__
stale workbook dated 2026-07-24 ignored; entering Projected Mode for 2026-07-25

ALLOW_PROJECTED_MODE=1 python3 extract_xlsx.py day_data.json
allow extract exit=0
stale workbook dated 2026-07-24 ignored; entering Projected Mode for 2026-07-25
Done. 14 total rows -> day_data.json
projected 2026-07-25 0 0

shasum -a 256 /tmp/chapterg-stale-allow/MLB_Slate_7-24-26.xlsx
b1987229e0b1ecd570e0d2598ab72e8ae897afc6292f896ca123fbe78b23ed56
```

b. Stale workbook present, flag unset -> exit 1, messages unchanged:
```text
python3 extract_xlsx.py --which
unset which exit=1
ERROR: newest available slate file is dated 2026-07-24 but today (ET) is 2026-07-25 -- no fresh upload found. Refusing to build a stale slate.

python3 extract_xlsx.py day_data.json
unset extract exit=1
ERROR: slate file is dated 2026-07-24 but today (ET) is 2026-07-25 -- refusing stale workbook.
```

c. Today's workbook present -> HR and Hits section diffs empty vs `origin/main`:
```text
python3 extract_xlsx.py MLB_Slate_7-25-26.xlsx day_data.json
HR_Leaderboard: 270 rows
Hit_Probabilities: 258 rows
Done. 1508 total rows -> day_data.json

origin/main hr-board 25735
origin/main oo5-board 18954
chapter-g hr-board 25735
chapter-g oo5-board 18954

diff -u /tmp/chapterg-main-hr.html /tmp/chapterg-current-hr.html
exit 0, empty

diff -u /tmp/chapterg-main-hits.html /tmp/chapterg-current-hits.html
exit 0, empty
```

d. Simulated thin reconstruction (`HR=4`) -> no commit, exit 0, counts logged:
```text
GITHUB_ENV=/tmp/chapterg-guard/thin.env GITHUB_OUTPUT=/tmp/chapterg-guard/thin.out DATA_FILE=/tmp/chapterg-guard/thin.json PROJECTED_MIN_HR=50 PROJECTED_MIN_HITS=50 python3 tools/projected_publish_guard.py
[projected-guard] slate_date=2026-07-25 hr_rows=4 hits_rows=60 min_hr=50 min_hits=50
[projected-guard] skipping commit/push: Projected Mode reconstruction is below non-degenerate publish thresholds
thin guard exit=0
SKIP_PROJECTED_PUBLISH=1
skip_publish=1
thin simulated commit step: skipped, workflow remains success
```

e. Simulated full reconstruction -> commits normally:
```text
GITHUB_ENV=/tmp/chapterg-guard/full.env GITHUB_OUTPUT=/tmp/chapterg-guard/full.out DATA_FILE=/tmp/chapterg-guard/full.json PROJECTED_MIN_HR=50 PROJECTED_MIN_HITS=50 python3 tools/projected_publish_guard.py
[projected-guard] slate_date=2026-07-25 hr_rows=51 hits_rows=50 min_hr=50 min_hits=50
[projected-guard] projected reconstruction meets publish thresholds
full guard exit=0
SKIP_PROJECTED_PUBLISH=0
skip_publish=0
full simulated commit step: would run normally

GITHUB_ENV=/tmp/chapterg-guard/workbook.env GITHUB_OUTPUT=/tmp/chapterg-guard/workbook.out DATA_FILE=/tmp/chapterg-guard/workbook.json PROJECTED_MIN_HR=50 PROJECTED_MIN_HITS=50 python3 tools/projected_publish_guard.py
[projected-guard] workbook-backed build; publish guard not applied
workbook guard exit=0
workbook simulated commit step: would run normally
```

f. Syntax and compliance:
```text
python3 - <<'PY'
import ast
from pathlib import Path
for path in [
    'extract_xlsx.py',
    'fetch_projected_mode.py',
    'build.py',
    'build_day46.py',
    'sync.py',
    'tools/check_bpp_compliance.py',
    'tools/projected_publish_guard.py',
]:
    ast.parse(Path(path).read_text(encoding='utf-8'), filename=path)
    print(f'ast OK {path}')
PY
ast OK extract_xlsx.py
ast OK fetch_projected_mode.py
ast OK build.py
ast OK build_day46.py
ast OK sync.py
ast OK tools/check_bpp_compliance.py
ast OK tools/projected_publish_guard.py

python3 -m py_compile extract_xlsx.py fetch_projected_mode.py build.py build_day46.py sync.py tools/check_bpp_compliance.py tools/projected_publish_guard.py
exit 0

python3 tools/check_bpp_compliance.py --base origin/main
BPP compliance OK (0 changed JSON/HTML files checked against eb82870cec59)
```

Projected Mode measurement logging:
```text
fetch_projected_mode.py already prints the BPP call count and reconstructed HR/Hits rows in Projected Mode:
[projected] rebuilt <slate-date>: HR=<count>, Hits=<count>, Savant=<count> batters
[projected] calls/run BPP=<count>, MLB=<count>; ...
Projected Mode BPP API calls this run: <count>

tools/projected_publish_guard.py additionally logs slate_date, hr_rows, hits_rows, and thresholds before any commit/push decision, including skip cases.
```

## 4. EXACT FINAL DAILY.YML

```yaml
name: Daily MLB Slate Build

on:
  push:
    paths:
      - '**.xlsx'
  schedule:
    - cron: '0 7 * * *'    # 3:00 AM ET - early build
    - cron: '30 10 * * *'   # 6:30 AM ET  - morning build
    - cron: '0 15 * * *'    # 11:00 AM ET - mid-morning line posts
    - cron: '0 20 * * *'    # 4:00 PM ET  - late lines + confirmed lineups
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install openpyxl

      - name: Find slate file
        env:
          ALLOW_PROJECTED_MODE: '1'
        run: |
          XLSX=$(python3 extract_xlsx.py --which)
          if [ -z "$XLSX" ]; then echo "No xlsx found" && exit 1; fi
          echo "XLSX_FILE=$XLSX" >> $GITHUB_ENV
          echo "Using newest slate by date: $XLSX"

      - name: Extract slate data
        env:
          ALLOW_PROJECTED_MODE: '1'
        run: python3 extract_xlsx.py "$XLSX_FILE" day_data.json

      - name: Rebuild Projected Mode data
        timeout-minutes: 8
        continue-on-error: true
        env:
          ALLOW_PROJECTED_MODE: '1'
          BPP_API_KEY: ${{ secrets.BPP_API_KEY }}
          DATA_FILE: day_data.json
          STREAKS_OUT: streaks_live.json
        run: python3 fetch_projected_mode.py

      - name: Fetch BallparkPal tab overrides
        timeout-minutes: 6
        continue-on-error: true
        env:
          BPP_API_KEY: ${{ secrets.BPP_API_KEY }}
          DATA_FILE: day_data.json
        run: python3 fetch_bpp_tabs.py

      - name: Fetch real K lines
        timeout-minutes: 4
        continue-on-error: true
        env:
          BDL_KEY: ${{ secrets.BDL_KEY }}
          ODDS_API_KEY: ${{ secrets.ODDS_API_KEY }}
          K_PROPS_FILE: k_props.json
          DATA_FILE: day_data.json
        run: python3 fetch_props.py

      - name: Fetch Phase 2 metrics
        timeout-minutes: 8
        continue-on-error: true
        env:
          BDL_KEY: ${{ secrets.BDL_KEY }}
          K_SAVANT_FILE: k_savant_data.json
          DATA_FILE: day_data.json
          BDL_MIN_GAP: '0.1'
        run: python3 fetch_phase2.py

      - name: Fetch BallparkPal projections
        timeout-minutes: 5
        continue-on-error: true
        env:
          BPP_API_KEY: ${{ secrets.BPP_API_KEY }}
          DATA_FILE: day_data.json
        run: python3 fetch_bpp.py

      - name: Fetch live streaks
        timeout-minutes: 6
        continue-on-error: true
        env:
          BDL_KEY: ${{ secrets.BDL_KEY }}
          STREAKS_OUT: streaks_live.json
          STREAK_DAYS: '10'
          BDL_MIN_GAP: '0.2'
        run: python3 fetch_streaks.py

      - name: Build slate
        env:
          DATA_FILE: day_data.json
          SECTIONS_FILE: built_sections.json
          K_REPORT_FILE: k-report.html
          K_PROPS_FILE: k_props.json
          K_SAVANT_FILE: k_savant_data.json
          BPP_SUMMARY_FILE: bpp_summary.json
          BDL_KEY: ${{ secrets.BDL_KEY }}
          STREAKS_OUT: streaks_live.json
          STREAK_DAYS: '10'
        run: python3 build.py

      - name: Sync to HTML
        run: python3 sync.py

      - name: Guard projected publish
        id: projected_publish_guard
        env:
          DATA_FILE: day_data.json
          PROJECTED_MIN_HR: '50'
          PROJECTED_MIN_HITS: '50'
        run: python3 tools/projected_publish_guard.py

      - name: Fetch compliance baseline
        if: steps.projected_publish_guard.outputs.skip_publish != '1'
        run: git fetch origin +main:refs/remotes/origin/main

      - name: BPP public-output compliance
        if: steps.projected_publish_guard.outputs.skip_publish != '1'
        run: python3 tools/check_bpp_compliance.py --base origin/main

      - name: Commit and push
        if: steps.projected_publish_guard.outputs.skip_publish != '1'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          git config user.email "mrwwright9@gmail.com"
          git config user.name "Wysdomos"
          git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/Wysdomos/mlb-slate.git"
          git add index.html k-report.html streaks.html day_data.json built_sections.json
          git add scout.html 2>/dev/null || true
          git add streaks_live.json 2>/dev/null || true
          git add slate_picks*.json 2>/dev/null || true
          git add k_props.json 2>/dev/null || true
          git add k_savant_data.json 2>/dev/null || true
          git add bpp_summary.json 2>/dev/null || true
          if ! git diff --staged --quiet; then
            git commit -m "Auto-update: $XLSX_FILE"
            # Generated files (index.html etc.) can't be line-merged with a parallel build,
            # so merge the remote keeping OUR freshly-built versions, and retry the push.
            pushed=0
            for i in 1 2 3 4 5; do
              git fetch origin main || true
              git merge -X ours --no-edit origin/main || git merge --abort || true
              if git push origin main; then pushed=1; echo "pushed on attempt $i"; break; fi
              echo "push rejected, retrying ($i)"; sleep $((RANDOM % 4 + 2))
            done
            [ "$pushed" = 1 ] || { echo "push failed after retries"; exit 1; }
          else
            echo "No changes to commit"
          fi

      - name: Telegram alert on failure
        if: failure()
        run: |
          curl -s -X POST "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
            -d chat_id="${{ secrets.TELEGRAM_CHAT_ID }}" \
            --data-urlencode text="🚨 Daily Slate FAILED: ${{ github.workflow }} — https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}"

      - name: Notify Firebase Auto-Healer on Failure
        if: failure()
        run: |
          PAYLOAD=$(printf '{"repository":"%s","run_id":"%s","sha":"%s"}' \
            "${{ github.repository }}" \
            "${{ github.run_id }}" \
            "${{ github.sha }}")
          SIG=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 \
            -hmac "${{ secrets.WEBHOOK_SECRET }}" | awk '{print $2}')
          HTTP=$(curl -s -o /tmp/heal_resp.txt -w '%{http_code}' \
            -X POST "${{ secrets.FIREBASE_WEBHOOK_URL }}" \
            -H "Content-Type: application/json" \
            -H "X-Hub-Signature-256: sha256=$SIG" \
            -d "$PAYLOAD")
          echo "healer responded HTTP $HTTP"
          cat /tmp/heal_resp.txt || true
          if [ "$HTTP" -lt 200 ] || [ "$HTTP" -ge 300 ]; then
            curl -s -X POST \
              "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
              -d chat_id="${{ secrets.TELEGRAM_CHAT_ID }}" \
              --data-urlencode text="⚠️ Auto-healer webhook returned HTTP $HTTP — the safety net may be down."
          fi
```

## 5. LOCAL STATE
- Branch: `codex/chapter-g-early-build`.
- Intended files:
  - `.github/workflows/daily.yml`
  - `extract_xlsx.py`
  - `tools/projected_publish_guard.py`
  - `SESSION_STATUS.md`
- Temporary verification files:
  - `/tmp/chapterg-stale-allow`
  - `/tmp/chapterg-stale-unset`
  - `/tmp/chapterg-guard`
  - `/tmp/chapterg-main-hr.html`
  - `/tmp/chapterg-current-hr.html`
  - `/tmp/chapterg-main-hits.html`
  - `/tmp/chapterg-current-hits.html`
