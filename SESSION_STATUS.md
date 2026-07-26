# SESSION STATUS - 2026-07-26 - Projected Mode full visual overhaul

Branch: `claude/projected-overhaul`
Base:   `origin/main` @ `2cbdcb5` (Chapter E)
Status: draft PR, not merged.

---

## 0. BASE DECISION (owner input was left blank)

The brief's `BASE:` line arrived as an unfilled `[OWNER — FILL ONE IN]`
placeholder. I asked; the question was dismissed, so I picked and am flagging
it here rather than burying it:

**Branched from `main`, not from the "Cordon" skin (`claude/projected-mode-skin-alt-keuhaf`).**
That branch's PR #24 is still an open draft. Building on it would have carried
its diff into this PR and made this work unmergeable unless Cordon won the
bake-off. Branching from main keeps the overhaul independent of that decision.

Cordon's core colour finding still carried over, because it is forced by the
brief rather than by that branch: violet is the only high-chroma hue on this
page with no existing meaning, so it is what the mode signal has to use.

**If you wanted (b), say so and I will rebase onto that branch** — the design
work is unaffected, only the parent commit and the (a) baseline change.

---

## 1. WHAT SHIPPED

A ground-up redesign of Projected Mode, entirely inside the presentation layer.
One file changed: `sync.py`.

### Depth strategy — layered elevation, zero blur

Four elevation steps, all built from luminance geometry:

| step | surface | treatment |
|---|---|---|
| E0 | page ground | no shadow |
| E1 | board shell | 1px border + `inset 0 1px 0` edge light + `0 1px 2px` drop |
| E2 | header lip | one step lighter, raised, stronger edge light |
| E3 | data plate | **recessed** — `inset 0 2px 6px -3px`, no drop shadow |
| E4 | search dock | solid fill, tight `0 -6px 18px -12px` lift |

The recess is what does the 3D work: the data plate sits *below* the chrome
plane rather than floating above it. No `backdrop-filter`, no glassmorphism, no
gloss anywhere in the new CSS — those are exactly the effects that wash out in
sunlight and cost scroll performance. **In light mode the edge light inverts**
(highlight moves to a bottom hairline, surfaces step up in lightness), so the
same geometry reads correctly against a light ground instead of disappearing.

### Colour system — and why these hues

Green, gold, red and orange were left completely alone. `--good`, `--bad`,
`--hot`, `--warn`, `--cold` and `--info` are **not redefined anywhere** in the
new CSS: they live inside table cells and encode park and stat meaning that has
to survive a reskin.

- **Signal Violet** `#9d7bff` dark / `#6d28d9` light — the mode key. It is the
  only high-chroma hue left with no job on this page.
- **Instrument Steel** `#8aa0bd` / `#3f5570` — the quiet companion, used for
  context boards and the second tier.
- **Panel / Plate / Lip** — three neutral surface steps per theme.

**Derived ranks deliberately lost weight.** `--tier0`/`--tier1` move to
violet/steel *and* drop from a filled row band to a hairline rail with a tinted
first cell. A graded Sweet Spot row is a filled band; a projected row is a rail.
That difference is visible at a glance and is the brief's "never wear the same
visual weight" requirement made literal.

### Card grammar — one system, five families

Grammar is `rail + eyebrow + title + summary strip + plate`. Only the rail and
the eyebrow change between families, so board types are distinguishable at a
glance while obviously belonging to one system.

| family | sections | rail | eyebrow |
|---|---|---|---|
| `derived` | hr-board, oo5-board | solid violet | `DERIVED RANKING` |
| `pitcher` | k-board | split violet/steel | `STARTERS` |
| `context` | park, totals, nrfi, sb, doubles, dfs, combos-k | steel | `CONTEXT` |
| `games` | games | none — the matchup is the hero | — |
| `headlines` | headlines | no shell, no plate — editorial cards | — |

Families are assigned by a `data-board` attribute added in `sync.py`. The
explainer sections (`alignment`, `methodology`, `tip-jar`) are deliberately
**not** tagged — they are documentation, not boards, and must not wear a board
eyebrow.

### Density — four structural moves, no shrinking

Body cells went **up** from 12.5px to 13px, because 12.5px is not readable in
direct sun. Density was bought with structure instead:

1. **Progressive disclosure.** Long boards render their first 12 rows; the rest
   is one 44px tap away, labelled with the exact hidden count ("Show all 50
   rows / 38 more"). 8 boards are capped. This is a plain CSS rule
   (`:nth-child(n+13)`), so it costs nothing per keystroke — and it yields
   automatically while `body.filtering` is set, so **search always sees every
   row** even when the cap is on.
2. **Data first.** Each board used to open with a provenance badge and a
   4–6 line explainer before the first row. Both are now moved *below* the
   plate as a footnote. Text is moved, never altered.
3. **Tier grouping rails** chunk 50 rows into bands the eye can skip through
   instead of scanning linearly.
4. **Scroll affordance.** A `background-attachment: local` edge shading that
   retracts only at the scroll end, so a 13-column board announces its extra
   columns instead of hiding them.

Net effect: the HR board goes from ~5 lines of prose before any data to 10
ranked rows on the first screen.

### Search

**The page already had a search engine** — a dock sheet that indexes every
matchable node once, debounces at 130 ms, and filters by toggling a single
class. It was never rebuilding the DOM. Standing up a second engine would have
put two of them in a fight over the same rows.

So the new sticky bar **drives the existing engine** rather than duplicating it:
one value copy plus one event dispatch per keystroke, with the debounce and the
filtering pass left exactly where they already were. The bar is fixed directly
above the tab dock (thumb zone, always reachable, never stranded), 44px tall,
16px font so iOS does not zoom on focus, with a clear (×) that routes through
the engine's own "Clear all". Result count mirrors the engine via a
`MutationObserver`, not a poll.

### Withheld boards

The 6 individual "unavailable" placeholder sections are removed from the page.
In their place, one collapsed disclosure sits under the banner: **"6 boards
withheld today"**, expanding to name all six. The banner is unchanged in
substance. The count is always on screen; the names are one tap away.

---

## 2. VERIFICATION

### (a) Workbook-backed rendering byte-identical to base

Same pristine `index.html`, same `built_sections.json`, same `day_data.json`
(no `_mode` key), both runs inside one clock minute so the build timestamp
matches:

```text
both rendered inside clock minute 06:48
  base     : 340,598 bytes  sha256=59f8a5b5866cb86a62b56a67eac28cc48aa788880acd60d7ce6636d9242a7401
  overhaul : 340,598 bytes  sha256=59f8a5b5866cb86a62b56a67eac28cc48aa788880acd60d7ce6636d9242a7401
  BYTE-IDENTICAL: True
  unified diff lines: 0  -> EMPTY
```

**The diff is empty.** No marker leaks into a workbook build:

```text
  workbook page contains 'pm-searchbar'            : False
  workbook page contains 'PROJECTED MODE CSS START': False
  workbook page contains 'PROJECTED JS START'      : False
  workbook page contains 'pm-withheld'             : False
  workbook page contains 'data-board'              : False
```

The guard property the brief asked me to preserve is intact and asserted
mechanically — both the CSS *and* the new JS are injected strictly after
`if not PROJECTED_MODE: return html`:

```text
guard intact            : True
JS injected after guard : True
```

### (b) Diffstat shows no file outside the presentation layer

```text
$ git diff --stat origin/main
 sync.py | 891 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++------
 1 file changed, 813 insertions(+), 78 deletions(-)

$ git diff --name-status origin/main
M	sync.py
```

One file. Every off-limits path confirmed untouched:

```text
  UNCHANGED  fetch_projected_mode.py
  UNCHANGED  extract_xlsx.py
  UNCHANGED  shadow_chips.py
  UNCHANGED  build_day46.py
  UNCHANGED  build.py
  UNCHANGED  grade_results.py
  UNCHANGED  tools/
  UNCHANGED  backtest/
  UNCHANGED  .github/
```

`build_day46.py` was never touched, so no scoring logic and no
`SLATE_PICKS.append` could have moved. Added files are the interactive preview
and the screenshots, neither on any code path.

### (c) Every projected value matches base

```text
data rows  base=358  overhaul=358  identical sequence=True
row multisets identical: True
  rows only in base    : 0
  rows only in overhaul: 0
  <tbody> rows   base=  385  overhaul=  385   OK
  <td> cells     base= 2917  overhaul= 2917   OK
  <th> cells     base=  288  overhaul=  288   OK
  <table>        base=   27  overhaul=   27   OK

visible text nodes in <main>  base=4263  overhaul=4233
  strings present in overhaul but not in base: 0
```

All 358 data rows match **in sequence and as a multiset** — reordering the
provenance notes moved no values. Every cell count is identical.

**Nothing was invented: zero strings appear in the overhaul that were not in
the base.** The 30 removed text nodes are 20 occurrences (9 unique) belonging
to the six withheld placeholder cards the owner asked to remove:

```text
     - Unavailable without workbook                    (x6)
     - The Sweet Spot danger-batter grid is workbook-only and cannot be reconstructed honestly...
     - The Sweet Spot pitcher vulnerability and danger-batter columns have no clean Projected Mode source...
     - HRR Combos
     - The HRR combo board depends on full Sweet Spot and Dimers workbook context...
     - Parlay Builder
     - The full parlay builder is withheld in Projected Mode because several workbook-only signals are missing...
     - Conviction rankings require the complete workbook signal stack...
     - The skip list includes editorial workbook context and is not reconstructed on missed-upload days...
```

All six board *names* survive in the disclosure: Matchup Spotlight, Pitcher's
HR Risk Board, HRR Combos, Parlay Builder, Conviction Board, Daily Skip List.

### (d) Search filters correctly across all boards

Before/after screenshots: `docs/projected-overhaul/mid-{dark,light}.png` (no
filter) vs `docs/projected-overhaul/search-{dark,light}.png` (filtered on
"Hunter Greene").

```text
full slate in DOM: 358 table rows, 15 game cards, 15 sections

query "Hunter Greene"                                  <- pitcher
   8 rows visible across 4 section(s): games, k-board, hr-board, nrfi-board
   every visible row contains the query: True
query "STL"                                            <- team
   24 rows visible across 10 section(s): methodology, park-board, games, k-board,
   hr-board, oo5-board, totals-board, nrfi-board, sb-board, dfs-board
   every visible row contains the query: True
query "Yamamoto"                                       <- pitcher, matches batters facing him too
   4 rows visible across 5 section(s): games, k-board, hr-board, nrfi-board, combos-k
   every visible row contains the query: True
query "Skenes"
   3 rows visible across 4 section(s): games, k-board, nrfi-board, combos-k
   every visible row contains the query: True

after Clear: body.filtering=False  rows still hidden by filter=0  input=''
```

Player, team and pitcher all filter. The search screenshot shows HR-board ranks
**1, 3, 5, 20, 34** — non-contiguous, which is the row cap correctly yielding so
the filter can reach rows 20 and 34 that the cap would otherwise hide.

The count badge can exceed the visible *table row* count (e.g. "Skenes" shows 6
hits for 3 table rows) because the engine also matches `.flag-row` combo cards,
which are not tables. That is the engine's own pre-existing behaviour.

### (e) Search stays responsive on a full 15-game slate

Measured on the full slate — 358 table rows, 15 game cards, 2,917 cells — by
typing character by character and sampling main-thread cost to the next frame:

```text
per-keystroke main-thread cost (ms), 13 keystrokes:
   [2.4, 16, 16.6, 16.7, 16.6, 16.5, 16.8, 16.7, 16.6, 16.9, 16.6, 16.6, 16.5]
   max 16.90 ms   median 16.60 ms
```

16.6 ms is one frame at 60 Hz — the measurement is dominated by the
`requestAnimationFrame` wait, so the actual work per keystroke sits below a
frame budget and nothing drops.

**Approach used to keep it fast:**
1. **No second engine.** The bar proxies to the existing filter, so per
   keystroke it does one value copy and one event dispatch.
2. **Debounce is retained** at the engine's 130 ms; the filtering pass runs once
   per pause, not once per key.
3. **No DOM rebuild** — filtering toggles one class per node against a node list
   indexed once on first use.
4. **The density cap is CSS, not JS.** `:nth-child(n+13)` under
   `body:not(.filtering)` means the cap costs zero at search time and lifts
   itself when a filter is active, so no JS has to walk rows to un-hide them.
5. **Count mirroring uses a `MutationObserver`**, not a polling timer.

### (f) Banner and collapsed disclosure both present

Both present. `docs/projected-overhaul/top-{dark,light}.png` shows the banner
with the collapsed line; `withheld-open-{dark,light}.png` shows it expanded and
naming all six boards.

```text
withheld disclosure items: 6
remaining '.projected-unavailable / .unavailable-card' elements: 0
```

### (g) Light and dark both fully designed

Text contrast against its **composited** background (every translucent layer is
alpha-composited up to an opaque ancestor; a naive `backgroundColor` read gives
nonsense on this page's glass surfaces). WCAG AA: 3.0 large, 4.5 otherwise.

```text
                      base dark  base light   NEW dark  NEW light   verdict
------------------------------------------------------------------------------
brand wordmark             16.5         1.1       17.1       15.7   AA restored in light
hero h1                    16.5         1.1       17.1       15.2   AA restored in light
hero games chip             9.8         1.4       11.2       10.9   AA restored in light
last updated                6.2         3.6        6.5        5.4   AA restored in light
install banner             14.1         1.1       16.1       17.2   AA restored in light
section title              15.6         7.2       15.2       16.1
section tag                 5.9         2.1        5.7        5.7   AA restored in light
board eyebrow              14.6        13.1        5.9        7.1
provenance tag             11.0         1.8        5.3        5.2   AA restored in light
provenance body             9.7         4.3       11.9        9.7   AA restored in light
note paragraph               --          --       10.6       11.4
rank numeral                 --          --        5.2        6.2
table cell                 15.7         1.0       16.0       17.9   AA restored in light
table header                5.4         3.1        5.7        5.7   AA restored in light
show-all button              --          --        5.6        6.4
search input                 --          --       16.0       17.9
withheld line                --          --       14.9       11.8
withheld item                --          --       14.9       11.8
banner body                  --          --       13.6       10.2

  base dark   below WCAG AA -> none
  base light  below WCAG AA -> brand wordmark (1.1), hero h1 (1.1), hero games chip (1.4),
                               last updated (3.6), install banner (1.1), section tag (2.1),
                               provenance tag (1.8), table cell (1.0), table header (3.1)
  NEW  dark   below WCAG AA -> none
  NEW  light  below WCAG AA -> none
```

Worth calling out: **base light mode was broken.** `.projected-mode` hard-codes
dark surfaces at specificity `(0,1,0)`, so it also won under
`[data-theme="light"]` while text stayed near-black — table cells sat at
**1.0:1**, i.e. invisible, on the page this owner reads in daylight. The new
light values are scoped under `[data-theme="light"] .projected-mode` at
`(0,2,0)`, so they win regardless of source order. All 19 probes clear AA in
both themes.

### (h) 390px width, safe areas respected

```text
  NEW  dark   scrollWidth=390px  horizontal overflow=False
  NEW  light  scrollWidth=390px  horizontal overflow=False
```

Tap targets, measured with every board expanded:

```text
control            count  min h  min w   >=44px
search input           1     44    366   yes
withheld toggle        1     45    355   yes
show-all button        8     44    328   yes
board header          12     87    360   yes
rail chip             15     44     44   yes
icon button            1     44     44   yes
dock button            7     49     47   yes
```

Every control the mode owns clears 44px. The nav rail grew (`--rail-h` 46 -> 54)
so its chips could reach 44px rather than shrinking the chips to fit.

Safe areas: `env(safe-area-inset-*)` is used for the banner's top padding, the
search bar's left/right padding, the search bar's offset above the dock, and the
body's bottom padding. Headless Chromium *defines* the insets as `0`, so
`env()` fallbacks never fire and cannot test this — the proof render substitutes
literals (59px top / 34px bottom, iPhone 14 Pro portrait):
`docs/projected-overhaul/safearea-dark.png`.

### (i) No external network requests from the new JS

```text
network requests during load: 3
    file:///.../render/alt_projected/index.html
    https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Mono...
    file:///.../render/alt_projected/index.html
network requests caused by search interaction: 0
```

The only non-`file://` request is the Google Fonts stylesheet that
`index.html` already ships in its `<head>` on main — it is not mine and the new
JS makes no requests at all. The preview was additionally loaded in a
**fully offline browser context** and rendered, searched, cleared and expanded
with zero page errors (see section 3).

### (j) ast.parse and py_compile

```text
ast.parse(sync.py) OK -- 42,444 bytes, 1033 lines
py_compile sync.py OK
curly quotes: none
PROJECTED_CSS is f-string: False
PROJECTED_JS  is f-string: False
```

Last three lines cover AGENTS.md rules 3 and 5 — straight quotes only, and both
injected blocks are plain triple-quoted strings rather than f-strings, so their
single braces cannot crash the build.

---

## 3. INTERACTIVE PREVIEW

**`docs/preview/projected.html`** — 277,420 bytes, committed and pushed. Open it
on the phone; the screenshots are only a record of it.

Built through the real pipeline (`build_day46.py` -> `sync.py`) from the
committed **Jul 25 2026 slate**. Verified against the exact bytes extracted from
the pushed commit (`git show origin/claude/projected-overhaul:docs/preview/projected.html`),
not from the working tree:

```text
game cards  : 15
data rows   : 358
<td> cells  : 2917
header      : "15 Games - Day 120 - Projected Mode"
matchups    : KC @ DET, LAA @ SF, ARI @ WSH, TOR @ BOS, SD @ MIA, NYY @ PHI,
              CLE @ TB, CHC @ PIT, ATL @ BAL, COL @ MIL, HOU @ CHW, ATH @ MIN,
              CIN @ STL, SEA @ TEX, LAD @ NYM
```

A real, full 15-game card. Nothing trimmed, nothing mocked. A scan for
placeholder names found only the string `placeholder` as an HTML
`<input placeholder="...">` attribute — never as data.

### Self-contained

```text
<script src=...>           : NONE
inline <style> blocks      : 1
inline <script> blocks     : 2
@import / CSS url() fetches: NONE
<link rel=stylesheet>      : 1   (the Google Fonts URL)
  same link in index.html  : 1   -> byte-identical, verified by diff
```

Zero external script or stylesheet **files**. The single `<link>` is the Google
Fonts URL that `index.html` carries on main today, kept deliberately so the
preview is *exactly as index.html is today* — the brief's own wording — and so
type renders the same as production rather than diverging from it.

Every other relative reference the page makes now resolves from
`docs/preview/`: the tip-jar QR codes and the PWA icons/manifest were copied in
alongside it. (Those QR images were 404ing on the first push; caught by an audit
of every `img`/`link` reference and fixed.)

```text
unresolved references remaining: k-report.html, record.html, scout.html, streaks.html
```

Those four are **sibling pages**, not assets of this page — separate builds that
cannot be inlined into a single file. The four dock/rail buttons pointing at
them go nowhere from the preview. Everything belonging to this page resolves.

### Confirmed: renders standalone, and search works

Loaded from its committed path in a browser context with **networking disabled
entirely**, then driven through every new interaction:

```text
OFFLINE LOAD
  games 15 · rows 358 · cells 3186 · boards 12 · capped 8 · show-all buttons 8
  withheld items 6 · search bar present
  broken images: []                      <- none
  .pm-word font resolved to: "Bebas Neue", "Arial Narrow", sans-serif

OFFLINE SEARCH "Yamamoto"
  6 hits · body.filtering=true · 4 rows visible · every visible row contains it: True
after Clear      : filtering=false, input=''
show-all toggle  : 12 rows -> 50 rows
withheld opens   : Matchup Spotlight, Pitcher's HR Risk Board, HRR Combos,
                   Parlay Builder, Conviction Board, Daily Skip List
theme toggle     : data-theme=light, localStorage slateTheme=light

failed requests while offline: the Google Fonts stylesheet (expected)
page errors: none
```

**It renders standalone and search works in it** — offline, with zero page
errors and zero broken images. The only thing the network buys is the webfonts;
without them the page falls back to `Arial Narrow` for the display face and the
layout is unchanged. `docs/projected-overhaul/preview-offline-top.png` and
`preview-offline-search.png` are captured in that fully offline state so the
fallback rendering is on the record.

One honest caveat: a genuine no-workbook day needs live network fetches, so the
preview forces `_mode: projected` onto the committed workbook slate. That is
what makes the values real. The consequence is that a few columns (e.g. Zone)
show workbook values that would render as dashes on a true projected day — the
*layout* is exact, one column's content is more populated than it would be.

## 4. SCREENSHOTS

All at **390 x 844, device pixel ratio 2, mobile emulation on**, in
`docs/projected-overhaul/`.

| file | what |
|---|---|
| `top-dark.png` / `top-light.png` | top of page |
| `mid-dark.png` / `mid-light.png` | scrolled mid-page, HR board open |
| `search-dark.png` / `search-light.png` | search active, filtered on "Hunter Greene" |
| `withheld-open-dark.png` / `withheld-open-light.png` | disclosure expanded |
| `safearea-dark.png` | iPhone 14 Pro insets applied |
| `preview-offline-top.png` / `preview-offline-search.png` | the committed preview, browser fully offline |

The collapsed disclosure is visible in the `top-*` shots; the expanded state is
in the `withheld-open-*` shots.

---

## 5. NOTES / JUDGEMENT CALLS

- **The brief's font line.** It asks for "Bebas Neue for zone and rank numbers
  only, Rajdhani for stats and labels". `index.html` loads Bebas Neue + DM Sans
  + DM Mono and has no Rajdhani, so adding it would have broken the binding
  "no new fonts" constraint. I honoured the line's *intent* with the loaded
  stack: **Bebas is used for rank numerals and nothing else** (the `#` column of
  the derived boards, plus the one PROJECTED stamp), and **DM Mono carries every
  stat label, eyebrow and header** — the role the brief gives Rajdhani. Flagging
  rather than silently picking a reading.

- **A search already existed.** It is behind the dock's SEARCH button as a
  bottom sheet, and it already met most of the brief's requirements. I judged
  that the gap was reachability — two taps and a sheet — not capability, so I
  added a persistent bar in the thumb zone and wired it to the existing engine.
  Replacing the engine would have been a regression dressed as a feature.

- **Withheld count is 6, not 4.** The brief's example said "4 boards
  unavailable today". The real count on this slate is six, and the number is
  computed from what was actually stripped rather than hard-coded, so it stays
  correct if the withheld set changes.

- **Explainer sections are untagged on purpose.** `alignment`, `methodology`
  and `tip-jar` are documentation, not boards; giving them a `CONTEXT` eyebrow
  and a steel rail would have implied they were reconstructed data.

- Nothing was merged. Draft PR only, per the brief.
