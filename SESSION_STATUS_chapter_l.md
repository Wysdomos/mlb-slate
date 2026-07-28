# Chapter L — Funnel Diagnostics, Cache, HRR

Branch: `codex/chapter-l-fixes`  
Base: `main` at `9be294174c54`  
Status: implemented, built, verified locally. Draft PR opened; not merged.

## 1. Funnel Logging First

First commit: `Chapter L add parlay funnel logging`.

Projected baseline from logging-only commit:

```text
[two-way-ks] pool=32 -> after lens>=3=0 -> after tier 0-1=0 -> after same-game pairing=0 -> after alt margin=0 -> emitted=0
[traffic-jam] pool=132 -> after same-lineup pairing=14 -> after structure match=5 -> after validation=5 -> emitted=5
[double-barrel] pool=288 -> after hit>=65=100 -> after park>=0+opp_sp=53 -> after contact vuln=5 -> after same-lineup pairing=1 -> after validation=1 -> emitted=1
[cruise-control] details_key=1 -> pool=79 -> after streak>=3=79 -> after supported non-HR market=79 -> after leg build=79 -> after validation=1 -> emitted=1
[yard-sale] pool=288 -> after park>=8+opp_sp=144 -> after driver threshold=130 -> after same-game pairing=14 -> after validation=12 -> emitted=12
```

Workbook baseline from logging-only commit using 7/27 workbook-backed `day_data.json` from `a5729dd`:

```text
[two-way-ks] pool=24 -> after lens>=3=1 -> after tier 0-1=1 -> after same-game pairing=0 -> after alt margin=0 -> emitted=0
[traffic-jam] pool=38 -> after same-lineup pairing=8 -> after structure match=3 -> after validation=3 -> emitted=3
[double-barrel] pool=237 -> after hit>=65=2 -> after park>=0+opp_sp=2 -> after contact vuln=0 -> after same-lineup pairing=0 -> after validation=0 -> emitted=0
[cruise-control] details_key=1 -> pool=79 -> after streak>=3=79 -> after supported non-HR market=79 -> after leg build=79 -> after validation=1 -> emitted=1
[yard-sale] pool=216 -> after park>=8+opp_sp=57 -> after driver threshold=57 -> after same-game pairing=10 -> after validation=10 -> emitted=10
```

Collapse points:

- `two-way-ks`: projected collapsed at independent lens count; workbook collapsed at same-game pairing after lens/tier.
- `double-barrel`: collapsed at contact-vulnerability filter.
- `cruise-control`: initial full run showed validation collapse from selecting two legs for the same player; this was a bug, not a threshold issue.
- `traffic-jam` and `yard-sale`: no supply collapse.

## 2. Loosen/Fix Based On Funnel

Threshold changes:

```text
TWO_WAY_K_MIN_FAMILIES: 3 -> 1
Reason: projected had 0/32 at three families; probe showed two families still produced zero same-game pairs, while one family preserved same-game structure and emitted.

DOUBLE_BARREL_CONTACT_VULN_MIN: 60.0 -> 50.0
CONTACT_HITS_ALLOWED_MIN: 5.5 -> 5.0
Reason: projected had 100 hit-qualified hitters and 53 with nonnegative park/opposing SP, but only 5 survived contact vulnerability.
```

Bug fixed:

```text
Cruise Control was selecting the top three streak legs by (player, market), which allowed the same player to appear twice and then fail validate_parlay().
Fix: select at most one leg per player before validation.
```

Runtime hot-streak verification:

```text
build.py runs build_streaks.py before build_day46.py.
[streaks] ✓ Wrote hot_streaks.json — 4 HR streakers, 79 hot batters
[cruise-control] details_key=1 -> pool=116 -> after streak>=3=116 -> after supported non-HR market=116 -> after leg build=115 -> after validation=1 -> emitted=1
```

Note: current 7/28 data logs 79 hot batters, not 44. I did not alter the count; the file does carry `details`, and Cruise reads it successfully.

Final projected build funnels:

```text
[two-way-ks] pool=32 -> after lens>=1=15 -> after tier 0-1=15 -> after same-game pairing=5 -> after alt margin=2 -> emitted=1
[traffic-jam] pool=132 -> after same-lineup pairing=14 -> after structure match=5 -> after validation=5 -> emitted=5
[double-barrel] pool=288 -> after hit>=65=100 -> after park>=0+opp_sp=53 -> after contact vuln=30 -> after same-lineup pairing=7 -> after validation=7 -> emitted=7
[cruise-control] details_key=1 -> pool=116 -> after streak>=3=116 -> after supported non-HR market=116 -> after leg build=115 -> after validation=1 -> emitted=1
[yard-sale] pool=288 -> after park>=8+opp_sp=144 -> after driver threshold=130 -> after same-game pairing=14 -> after validation=12 -> emitted=12
```

Emission verification:

```text
two-way-ks empty=False cards=1 pick legs=2
double-barrel empty=False cards=5 pick legs=10
cruise-control empty=False cards=1 pick legs=3
```

## 3. HRR Column

Root cause:

- Workbook mode had the formula but read park Runs% with `_sf('+30%')`, which parsed to `0`.
- Projected Mode had a separate Hits builder that omitted the HRR column entirely.

Fix:

- Added shared `hrr_probability_for_hit_row()` and `hrr_cell_for_pct()`.
- Workbook and Projected Mode both use the same formula: `1+ Hit`, `To Get RBI`, opposing starter `ERA`, and park `Runs %`.
- Projected Mode now renders the existing Hits board with an HRR column, not a duplicate column.

Verification:

```text
workbook rows 50 HRR populated 50 sample ['79.2%', '82.5%', '81.4%', '79.3%', '79.0%']
projected rows 50 HRR populated 50 sample ['92.0%', '90.7%', '86.7%', '92.3%', '86.3%']
```

Screenshots:

- `artifacts/chapter_l_hrr_workbook.png`
- `artifacts/chapter_l_hrr_projected.png`

## 4. iOS Stale Page

Implemented in `sync.py`:

- Adds bottom-dock refresh control with `44px` minimum tap target.
- Refresh uses `location.pathname + '?v=' + Date.now()`.
- Writes `build-stamp.json` every sync run.
- Bakes the same stamp into `index.html`.
- On load, fetches `build-stamp.json?v=...` with `cache: 'no-store'`; if the remote stamp differs, shows a dismissible banner.
- No service worker added.

Generated stamp:

```json
{
  "stamp": "2026-07-28|projected|2026-07-28T10:56:38+00:00",
  "slate_date": "2026-07-28",
  "mode": "projected",
  "built_at_utc": "2026-07-28T10:56:38+00:00"
}
```

Refresh/stale mock:

```text
match {"shown":false,"refreshHref":"/index.html?v=1785236223115"}
stale {"shown":true,"refreshHref":"/index.html?v=1785236223119"}
```

Static no-service-worker check:

```bash
rg -n "serviceWorker|navigator\\.serviceWorker" index.html sync.py
```

Output: no matches.

## 5. Checks

Compliance:

```text
BPP compliance OK (4 changed JSON/HTML files checked against 9be294174c54)
```

AST:

```text
ast ok build_day46.py
ast ok sync.py
```

py_compile:

```bash
python3 -m py_compile build_day46.py sync.py
```

Output: no errors.
