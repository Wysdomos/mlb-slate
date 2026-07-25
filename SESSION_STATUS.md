# SESSION STATUS - 2026-07-25 - Codex

## 0. ARCHITECT REVIEW FIXES - 2026-07-25
- Restored `slate_picks.json`, `slate_picks_7-24.json`, and `slate_picks_7-25.json` to their `origin/main` tree state. The 2026-07-24 and 2026-07-25 historical slate-pick files are no longer modified by Chapter F.
- Removed the raw-value rename for future generation. `build_day46.py` now emits `calibration_tier` as a derived label (`plus`, `lean-plus`, `neutral`, `lean-minus`, `minus`) instead of writing the raw BPP matchup integer under another key.
- Added committed compliance test `tools/check_bpp_compliance.py` and CI workflow `.github/workflows/ci.yml`. The test is value-aware for `slate_picks*.json`: renaming the old raw `bpp_matchup_advantage` vector to another key fails even when the forbidden key name is gone.
- Added the compliance check to the daily workflow after HTML sync and before committing generated public outputs.
- Updated `daily.yml` so `Rebuild Projected Mode data` has `continue-on-error: true` and the same `ALLOW_PROJECTED_MODE: '1'` gate as the Find/Extract steps.
- Because workflow edits must be applied by the repo owner through the GitHub web UI, use the final YAML in `.github/workflows/daily.yml` from this branch. The relevant final block is:

```yaml
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Rebuild Projected Mode data
        timeout-minutes: 8
        continue-on-error: true
        env:
          ALLOW_PROJECTED_MODE: '1'
          BPP_API_KEY: ${{ secrets.BPP_API_KEY }}
          DATA_FILE: day_data.json
          STREAKS_OUT: streaks_live.json
        run: python3 fetch_projected_mode.py

      - name: Sync to HTML
        run: python3 sync.py

      - name: Fetch compliance baseline
        run: git fetch origin +main:refs/remotes/origin/main

      - name: BPP public-output compliance
        run: python3 tools/check_bpp_compliance.py --base origin/main
```

Review-fix verification:
```text
python3 tools/check_bpp_compliance.py --base origin/main
BPP compliance OK (0 changed JSON/HTML files checked against 7cf48ada4454)

python3 -m py_compile extract_xlsx.py fetch_projected_mode.py build.py build_day46.py sync.py tools/check_bpp_compliance.py
exit 0

negative compliance test: renaming bpp_matchup_advantage to calibration_signal in slate_picks_7-25.json
BPP compliance check failed:
  - slate_picks_7-25.json: `calibration_signal` is byte-for-byte the old raw BPP matchup vector
```

## 1. WHAT I DID
- Branch: `codex/chapter-f-projected-mode` off current `origin/main`.
- Added Projected Mode for cleanly absent workbook days, gated by `ALLOW_PROJECTED_MODE=1`.
- Preserved stale-workbook hard failure: wrong-date workbook still exits 1.
- Added `fetch_projected_mode.py` to rebuild missed-upload data from:
  - BallparkPal live games, park factors, matchups, projection averages, and projection probabilities.
  - MLB Stats API schedule and handedness.
  - Baseball Savant custom CSV for batter barrel rate and xwOBA.
- Added Projected Mode rendering:
  - Top-of-page disclosure banner.
  - Scoped `.projected-mode` visual identity.
  - Per-section Projected Mode badges on reconstructed boards.
  - Honest unavailable cards for workbook-only Sweet Spot / Dimers / Zone surfaces.
  - HR board uses Daily Slate derived score/tier, real BPP-derived HR probabilities, Savant barrel/xwOBA, real pitcher/park context, and `Zone` shown as `—`.
- Added PR review artifact: `docs/projected-mode-sample.png`.
- Superseded by architect review fix: committed pick JSON files are restored to `origin/main`, and future generation uses derived `calibration_tier`.

## 2. RAW VERIFICATION OUTPUT

Syntax gates:
```text
ast OK extract_xlsx.py
ast OK fetch_projected_mode.py
ast OK build.py
ast OK build_day46.py
ast OK sync.py

python3 -m py_compile extract_xlsx.py fetch_projected_mode.py build.py build_day46.py sync.py -> exit 0
```

Upload-day regression, same real 2026-07-25 workbook and same BPP inputs:
```text
diff -u /tmp/chapterf-before-hr-board.html /tmp/chapterf-after-hr-board.html -> exit 0, empty
diff -u /tmp/chapterf-before-oo5-board.html /tmp/chapterf-after-oo5-board.html -> exit 0, empty
```

Projected Mode absent-workbook gate:
```text
ALLOW_PROJECTED_MODE=1 python3 extract_xlsx.py day_data.json
Projected Mode marker written for 2026-07-25 because no workbook was uploaded and ALLOW_PROJECTED_MODE=1.
Done. 14 total rows -> day_data.json
```

Projected Mode live reconstruction:
```text
[projected] rebuilt 2026-07-25: HR=270, Hits=270, Savant=573 batters
[projected] calls/run BPP=33, MLB=4; 3 runs/day BPP ~= 99; 4 runs/day BPP ~= 132; monthly budget 15000
Projected Mode BPP API calls this run: 33
```

Projected Mode build/sync:
```text
Built 18 sections
  hr-board: 17831 bytes
  oo5-board: 13912 bytes
build_editorial: skipped in Projected Mode
build_scout: wrote Projected Mode unavailable page
Done -- wrote 250,181 bytes to index.html
```

Projected Mode content checks:
```text
PROJECTED MODE banner present
projected-section-badge present on reconstructed boards
Unavailable without workbook cards present
HR first 5 Zone cells are all —
```

BPP HR spot checks:
```text
Yordan Alvarez BPP HR percent 4.1 HTML 4.10% rank 1 score 98
James Wood BPP HR percent 4.8 HTML 4.80% rank 3 score 94
Tyler Locklear BPP HR percent 2 HTML 2.00% rank 4 score 92
```

Savant spot checks:
```text
1 Yordan Alvarez score 98 HR 4.10% Zone — Savant 19 .476 HTML 19.0% 0.476
3 James Wood score 94 HR 4.80% Zone — Savant 21.9 .423 HTML 21.9% 0.423
4 Tyler Locklear score 92 HR 2.00% Zone — Savant 23.1 .475 HTML 23.1% 0.475
```

Stale workbook hard-fail:
```text
ALLOW_PROJECTED_MODE=1 python3 extract_xlsx.py --which
ERROR: newest available slate file is dated 2026-07-24 but today (ET) is 2026-07-25 -- no fresh upload found. Refusing to build a stale slate.
exit 1
```

Absent workbook without flag:
```text
python3 extract_xlsx.py --which
ERROR: No .xlsx file found.
exit 1
```

Compliance grep:
```text
git ls-files '*.json' '*.html' | xargs rg -n "matchup_advantage|homeRunProbability|singleProbability|homeRunVsTypical|runsCreatedVsTypical|VsTypical|requestId|marketKey|asOf"
-> exit 1, no matches
```

Rendered sample:
```text
qlmanage -t -s 1440 -o /tmp/chapterf-projected /tmp/chapterf-projected/index.html
* /tmp/chapterf-projected/index.html produced one thumbnail
docs/projected-mode-sample.png written
```

## 3. WHERE I STOPPED AND WHY
- Implementation and verification are complete on the feature branch.
- Stopping after draft PR creation per request.

## 4. SURPRISES AND DEVIATIONS
- The in-app browser runtime was available, but no browser backend was listed, so the rendered sample was produced with macOS Quick Look (`qlmanage`) instead.
- BPP `/matchups` probability fields are percent-point values, while `/projections/probabilities` uses normalized probabilities. The projected fetcher now treats those endpoint units separately.
- Baseball Savant names do not always match BPP names exactly, but the board fills metrics by MLB player id where available, avoiding name-matching for actual reconstruction.

## 5. LOCAL STATE
- Branch: `codex/chapter-f-projected-mode`.
- Intended changed files:
  - `.github/workflows/daily.yml`
  - `extract_xlsx.py`
  - `fetch_projected_mode.py`
  - `build.py`
  - `build_day46.py`
  - `sync.py`
  - `SESSION_STATUS.md`
  - `docs/projected-mode-sample.png`
  - `slate_picks.json`
  - `slate_picks_7-24.json`
  - `slate_picks_7-25.json`
- Generated verification files are under `/tmp/chapterf-*`.

## 6. OPEN QUESTIONS
- Visual approval is pending on `docs/projected-mode-sample.png`.
