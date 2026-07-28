# Chapter O — Restore Headlines Navigation and Card Format

Branch: `codex/chapter-o-headlines`

## Scope

Restored the pre-Chapter-J headline section presentation and static navigation while keeping Chapter J's live-derived headline content. No hardcoded slate players, parks, team matchups, park figures, or stat values were reintroduced.

## Pre-Check: For The Record Reachability

`For The Record` was still reachable elsewhere on the page before this fix:

```text
index.html:2392: <a href="record.html" class="page-link"><span>💿 For The Record</span> <span class="arrow">›</span></a>
index.html:2428: <a class="more-row" href="record.html"><span class="mi">💿</span> For The Record <span class="arrow">›</span></a>
```

So it was not fully orphaned, but the top-of-page headline route was gone after Chapter J.

## Original Footer Source

Pulled original wording/destinations from `build_day46.py` at commit `5f14499`:

- `streaks.html`: `🔥 See Today's Hot Streaks →`
- `scout.html`: `⚡ SSJ (The Zone) — Matchup Intelligence →`
- SSJ sub-line: `Zone scores · DANGER tags · platoon · projections · Fusion parlays`
- `record.html`: `For The Record — yesterday's calls, graded.` with `See how they graded →`

## Implementation

Changed `build_day46.py` only:

- Added `headline_footer_links()` with the three restored static links.
- Restored original headline card treatment using `flag-row` and emoji icons:
  - `🌋` park leader
  - `🔥` stack opportunity
  - `⚡` K board leader
  - `🎯` pitcher HR risk
  - `🥶` fade parks
  - `📋` skip arms
- Kept the values derived from current slate data.
- Projected Mode keeps the links. `scout.html` gets an explicit note: `Projected Mode: opens the workbook-only unavailable page.`
- Added the requested guard comment above `build_headlines()`:
  - headline content must be slate-derived
  - static navigation must survive content rebuilds

Mapping note:
- The stack opportunity card is derived from the highest VulnScore starter plus current HR board top-50 bats from the opposing lineup. That preserves the original `🔥 stack` role without hardcoded names.

## Render Evidence

Workbook section build:

```text
Built 19 sections
  headlines: 2497 bytes
```

Projected section build:

```text
Built 19 sections
  headlines: 2779 bytes
```

Workbook synced page:

```text
OK #headlines
Done -- wrote 326,329 bytes to /tmp/chapter_o_workbook_index.html
```

Projected synced page:

```text
OK #headlines
Projected: 2 withheld board(s) -> one disclosure
Done -- wrote 276,940 bytes to /tmp/chapter_o_projected_index.html
```

Restored links and card format:

```text
workbook headline flag-row count: 7
workbook footer links: Hot Streaks=1, SSJ=1, For The Record=1
projected headline flag-row count: 7
projected footer links: Hot Streaks=1, SSJ=1, For The Record=1
projected scout unavailable note: 1
```

Rendered headline sample from workbook temp page:

```html
<section id="headlines">
  <h2>📅 Slate Headlines + Flags</h2>
  <div class="flag-row"><div class="icon">🌋</div><div>...</div></div>
  <div class="flag-row"><div class="icon">🔥</div><div>...</div></div>
  <div class="flag-row"><div class="icon">⚡</div><div>...</div></div>
  <div class="flag-row"><div class="icon">🎯</div><div>...</div></div>
  <div class="flag-row"><div class="icon">🥶</div><div>...</div></div>
  <div class="flag-row"><div class="icon">📋</div><div>...</div></div>
  ...static footer links...
</section>
```

## Hardcoded Slate Check

```text
rg -n "Mikolas|Skenes|Wheeler|De La Cruz|Urena|Perez|Sutter|May 12|Day 46" build_day46.py
# no output
```

## Final Checks

```text
BPP compliance OK (0 changed JSON/HTML files checked against 90a94b8c27ac)
ast.parse OK build_day46.py
ast.parse OK sync.py
python3 -m py_compile build_day46.py sync.py
```

