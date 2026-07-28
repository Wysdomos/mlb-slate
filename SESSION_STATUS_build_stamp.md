# SESSION STATUS - Build Stamp Staging

Branch: `codex/fix-build-stamp-staging`

## Summary

Fixed the daily push loop root cause:

- `build-stamp.json` is now explicitly staged with the generated artifacts in `.github/workflows/daily.yml`.
- The retry loop now stashes unstaged/untracked files before each merge retry, so a forgotten generated artifact cannot abort `git merge -X ours origin/main`.
- A real merge abort now fails immediately with a GitHub `::error::` naming the blocking files instead of burning all five retries.

No blanket `git add -A` was added.

## Verification

### a. Full daily build runs and pushes green

Production `main` was not pushed from this feature branch. The commit/push loop was verified with a local bare `origin` simulation that exercises the same staging, merge, and push behavior.

Relevant output:

```text
To /var/folders/vt/jgcq4b4s0qz5_xh9nt07jpkc0000gn/T/tmp.88whmAtWNJ/origin.git
   061084b..e940b1d  main -> main
pushed on attempt 1
```

### b. Dirty unstaged generated file no longer aborts merge

Simulation deliberately dirtied a tracked generated file that is not in the explicit stage list: `extra-generated.json`.

Output:

```text
::warning::Stashing unstaged/untracked files before merge retry so generated artifacts cannot abort the merge
 M extra-generated.json
Saved working directory and index state On main: daily-build-unstaged-before-merge-local
To /var/folders/vt/jgcq4b4s0qz5_xh9nt07jpkc0000gn/T/tmp.88whmAtWNJ/origin.git
   061084b..e940b1d  main -> main
pushed on attempt 1
```

### c. Unresolvable merge fails fast naming file

Simulation created a directory/file conflict. The loop exited on the first merge failure.

Output:

```text
::error::Merge aborted during push retry; blocking file(s): conflict-path~origin_main
CONFLICT (file/directory): directory in the way of conflict-path from origin/main; moving it to conflict-path~origin_main instead.
Automatic merge failed; fix conflicts and then commit the result.
```

### d. build-stamp.json updates on main after success

Simulation confirmed `build-stamp.json` reached the target `main`.

```text
build-stamp on main: runner stamp
extra-generated on main: initial
```

`extra-generated.json` stayed unchanged on main, proving the dirty forgotten generated file was not accidentally committed.

### e. No untracked or BPP-derived file newly staged

Before adding this report, repo status showed only the workflow change:

```text
 M .github/workflows/daily.yml
```

### f. Compliance, ast.parse, py_compile

```bash
ruby -e "require 'yaml'; YAML.load_file('.github/workflows/daily.yml'); puts 'YAML OK'"
```

```text
YAML OK
```

```bash
bash -n /tmp/daily_commit_push_block.sh
```

```text
OK
```

```bash
python3 tools/check_bpp_compliance.py
```

```text
BPP compliance OK (0 changed JSON/HTML files checked against fbfaffb76dbd)
```

```bash
python3 -m py_compile sync.py build.py build_day46.py
```

```text
OK
```

```bash
python3 - <<'PY'
import ast, pathlib
for root in ['.', 'tools', 'backtest', 'functions']:
    for path in pathlib.Path(root).glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('ast.parse OK')
PY
```

```text
ast.parse OK
```

## Exact Final YAML

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
          BPP_MIN_GAP: '6.2'
          DATA_FILE: day_data.json
        run: python3 fetch_bpp_tabs.py

      - name: Alert on empty critical tabs
        if: always()
        env:
          DATA_FILE: day_data.json
          CRITICAL_TABS: Park_Factors,SP_Projections
          GITHUB_RUN_URL: https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python3 tools/check_critical_tabs.py

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

          stage_generated_outputs() {
            git add index.html k-report.html streaks.html day_data.json built_sections.json build-stamp.json
            git add scout.html 2>/dev/null || true
            git add streaks_live.json 2>/dev/null || true
            git add slate_picks*.json 2>/dev/null || true
            git add k_props.json 2>/dev/null || true
            git add k_savant_data.json 2>/dev/null || true
            git add bpp_summary.json 2>/dev/null || true
          }

          clean_unstaged_before_merge() {
            if [ -n "$(git status --porcelain)" ]; then
              echo "::warning::Stashing unstaged/untracked files before merge retry so generated artifacts cannot abort the merge"
              git status --short
              git stash push --include-untracked --keep-index -m "daily-build-unstaged-before-merge-${GITHUB_RUN_ID:-local}" >/tmp/daily-build-stash.log
              cat /tmp/daily-build-stash.log
            fi
          }

          fail_fast_merge_abort() {
            merge_log="$1"
            conflicts="$(git diff --name-only --diff-filter=U | tr '\n' ' ')"
            if [ -z "$conflicts" ]; then
              conflicts="$(git status --porcelain | sed 's/^...//' | tr '\n' ' ')"
            fi
            echo "::error::Merge aborted during push retry; blocking file(s): ${conflicts:-unknown}"
            cat "$merge_log"
            git merge --abort 2>/dev/null || true
            exit 1
          }

          stage_generated_outputs
          if ! git diff --staged --quiet; then
            git commit -m "Auto-update: $XLSX_FILE"
            # Generated files (index.html etc.) can't be line-merged with a parallel build,
            # so merge the remote keeping OUR freshly-built versions, and retry the push.
            pushed=0
            for i in 1 2 3 4 5; do
              git fetch origin main || true
              clean_unstaged_before_merge
              merge_log="$(mktemp)"
              if ! git merge -X ours --no-edit origin/main >"$merge_log" 2>&1; then
                fail_fast_merge_abort "$merge_log"
              fi
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
