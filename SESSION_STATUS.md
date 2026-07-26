# SESSION STATUS - 2026-07-26 - Projected Mode overhaul, revision pass

Branch: `claude/projected-overhaul` (pushed onto, not re-branched)
Base:   `origin/main` @ `2cbdcb5` (Chapter E)
Status: draft PR #25, not merged.

---

## 0. ONE PREMISE IN THE BRIEF WAS INVERTED — PLEASE READ

The brief's central colour constraint says:

> "The site's normal brand accent is ALREADY cyan. 'THE DAILY SLATE' renders
> with a cyan 'SLATE'."

**That is not what the code does.** Measured from `index.html` on main:

```text
  :root                --accent: #2de38f     <- green
  [data-theme="light"] --accent: #0c9d5f     <- green
  .brand .wordmark em { color: var(--accent); }
```

The wordmark renders **green** on the normal workbook page. It renders cyan
only on **main's Projected Mode page**, because main's projected skin overrides
`--accent: #22d3ee`. So the cyan you are seeing *is already the mode signal*,
not the brand.

The consequence matters: adopting an icy blue does **not** collide with the
brand accent. But a real adjacent collision does exist, and I designed against
that one instead:

```text
  --info: #56a8ff   --cold: #56a8ff     <- blue, and these carry meaning in cells
```

So the icy key was pushed **colder and less saturated than `#56a8ff`** so the
two read as different materials, and — exactly as instructed — **the mode
signal is carried structurally, not by hue**. Details in (c).

---

## 1. WHAT CHANGED IN THIS PASS

Everything structural and behavioural from the previous revision is kept: the
layout, card system, elevation model, search dock, withheld disclosure and
interaction model are unchanged. What changed is the material, plus four
corrections.

### 1. Palette: icy blue material adopted

| token | dark | light |
|---|---|---|
| mode key | `#6fd7e9` | `#0b6981` |
| key lift | `#a8e9f5` | `#085466` |
| steel companion | `#8fa6bd` | `#3d5468` |
| page ground | `#0a1016` | `#eaf1f5` |
| data plate | `#0d1621` | `#ffffff` |
| header lip | `#14232f` | `#eef4f8` |
| frost edge light | `rgba(190,235,250,.09)` | `#ffffff` |

Cold surfaces, frost edge light, machined steps — main's material language,
kept on this branch's structure. `--good`, `--bad`, `--hot`, `--warn`,
`--cold`, `--info` are still **never redefined**: green, gold, red and orange
stay reserved for tier and park semantics.

Derived ranks still deliberately carry less weight than a graded grade: ice +
steel instead of green + gold, **and** a hairline rail instead of a filled row
band.

### 2. Emoji restored on Top 50 HR and Hits

Worth flagging: **this was not a regression introduced by the overhaul.**
`build_day46.py` has always emitted different titles per mode —
`build_hr_board()` produces `🏆 Top 50 HR Board` while
`build_projected_hr_board()` produces a bare `Top 50 HR Board`. Main's
projected page has the same gap.

Restored in `sync.py`, under the projected guard, to match the workbook boards
exactly: **🏆 Top 50 HR Board** and **☄️ Top 50 Hits Board**.

### 3. SSJ / Zone: withheld message + back link

SSJ is not a section on the slate — it is the dock and More-sheet link to
`scout.html`, whose Projected Mode page is written by `build.py`. That page was
rebuilt to match this branch's withheld treatment exactly: the same
`PROJECTED MODE` chip, the same hatched cordon spine and card edge, the same
ice palette in both colour schemes, and the same language as the withheld
disclosure ("held back rather than estimated").

Added a **44px back link** — "← Back to the top of the slate" → `index.html`.

### 4. Row cap removed — you were right

The 12-row cap was wrong for this brief, and worse than I realised when I built
it. The data plate is *already* a scroll container with its own `max-height`,
so capping shrank the container **and** added a tap: it showed strictly less.

The cap is gone entirely. Density is bought structurally instead — a taller
plate (`min(78vh, 760px)`) and a tighter row rhythm (cell padding 7px → 5px,
header padding 10px → 7px, line-height 1.3 → 1.26) with **no reduction in font
size** (still 13px). Measured in (f): more rows on screen *and* nothing hidden.

### 5. Provenance now reads before the numbers

`tuckNotes()` still moves the long explainer below the plate, but it now first
**lifts the compact `PROJECTED MODE` chip out of the board body and into the
board header**, above the data. That is real DOM moved from the page — not
generated content — so it is announced by screen readers.

This replaced the previous revision's CSS `::before` eyebrow
(`DERIVED RANKING` / `STARTERS` / `CONTEXT`), which would otherwise have been a
second label stacked on the first. Board family is still distinguishable at a
glance from the rail: solid ice = derived, split ice/steel = pitcher, solid
steel = context.

### 6. Preview rebuilt

`docs/preview/projected.html` regenerated from the same real 15-game slate, and
`docs/preview/scout.html` added so the SSJ page and its back link are tappable
in the preview too.

---

## 2. VERIFICATION

### (a) Workbook-backed rendering byte-identical to main

```text
both rendered inside clock minute 16:06
  base     : 340,599 bytes  sha256=7f4527bbba8b90b392b761845f63ea59c922566715e746cd3f94a2c405684c85
  overhaul : 340,599 bytes  sha256=7f4527bbba8b90b392b761845f63ea59c922566715e746cd3f94a2c405684c85
  BYTE-IDENTICAL: True
  unified diff lines: 0  -> EMPTY

  workbook page contains 'pm-searchbar'            : False
  workbook page contains 'PROJECTED MODE CSS START': False
  workbook page contains 'PROJECTED JS START'      : False
  workbook page contains 'pm-withheld'             : False
  workbook page contains 'data-board'              : False
```

The guard still protects everything, asserted mechanically — including the new
emoji fix, which also sits after it:

```text
guard before CSS inject: True
guard before JS inject : True
guard before emoji fix : True
```

`build.py`'s change is confined to the `if PROJECTED_MODE:` branch of the scout
step; the workbook branch still calls `build_scout.py` untouched:

```text
scout write sits inside 'if PROJECTED_MODE:' before 'else:': True
workbook branch still calls build_scout.py: True
```

### (b) Diffstat shows nothing outside the presentation layer

```text
 sync.py   | 921 ++++++++++++++++++++++++++++++++++++++++++++++++++--
 build.py  |  66 +++++++++++--
```

Two code files. `build.py` is new to the diff this pass: it owns the Projected
Mode `scout.html` page, which is where item 3 lives. That block is pure inline
presentation and is gated behind `if PROJECTED_MODE:`.

Every off-limits path confirmed untouched:

```text
  UNCHANGED  fetch_projected_mode.py
  UNCHANGED  extract_xlsx.py
  UNCHANGED  shadow_chips.py
  UNCHANGED  build_day46.py
  UNCHANGED  grade_results.py
  UNCHANGED  tools/
  UNCHANGED  backtest/
  UNCHANGED  .github/
```

No data, no scoring, no reconstruction, no pick emission. `build_day46.py`
untouched means no `SLATE_PICKS.append` could have moved.

### (c) Projected Mode is still unmistakable — given the accent is also blue

The palette can no longer carry the signal, so it doesn't. Four structural
marks do, none of which any colour choice can dilute:

1. **A fixed hatched spine** down the left edge of the viewport — `position:
   fixed`, so it is on screen at *every* scroll position, not just at the top.
   Diagonal hatch, 8px. Visible in every screenshot.
2. **The stamp**, which always inverts against the ground: a lifted ice-to-slate
   gradient block on dark, a deep one on light. The inversion, not the hue, is
   the half-second signal.
3. **A hatch rule closing the sticky header stack**, so the cordon reads as an
   L even once the banner has scrolled away.
4. **A `PROJECTED MODE` chip in every board header**, above the data.

Two supporting facts: the hatch is a **pattern**, so it survives colour
blindness and blown-out sunlight where a hue shift would not; and the mode key
`#6fd7e9` is 24° of hue away from `--info`/`--cold` `#56a8ff` with a large
saturation and lightness gap, so the material reads cold-cyan rather than
info-blue.

Derived rankings still never wear a graded grade's weight: hairline rail, no
filled band, ice and steel instead of green and gold.

### (d) Emoji present on Top 50 HR and Hits

```text
  #hr-board  title: "🏆 Top 50 HR Board"
  #oo5-board title: "☄️ Top 50 Hits Board"
```

These are the only two rendered-text changes in the whole branch, and they are
intentional per item 2. The value-equality check confirms nothing else moved:

```text
  strings present in overhaul but not in base: 2
     + 🏆 Top 50 HR Board
     + ☄️ Top 50 Hits Board
```

### (e) SSJ shows the withheld message and a working back link

Rendered offline, both colour schemes, zero errors:

```text
dark  {"chip": "PROJECTED MODE", "h1": "SSJ The Zone is withheld today",
       "backText": "← Back to the top of the slate", "backHref": "index.html",
       "backH": 44, "backW": 235, "spine": "8px"}   errors: none
light {... identical ...}                            errors: none
```

Round-tripped inside the preview bundle with networking disabled:

```text
SSJ: "SSJ The Zone is withheld today"
BACK LINK round-trip -> {"file": "projected.html", "searchBar": true, "rows": 358}
errors: none
```

Note: the **shipped** `scout.html` links to `index.html`, which is correct in
production where the two sit side by side. The **preview** copy links to
`projected.html`, because that is what the slate is called inside
`docs/preview/`. Without that one-line difference the preview's back link would
have 404'd — it did, and was caught by testing the round trip rather than
assuming it.

### (f) Row cap decision, with the numbers

**Decision: removed entirely.** Justification is that the cap failed on its own
terms — the plate is already a scroll container, so capping shrank the visible
container *and* gated the rest behind a tap.

Measured on the same three boards, 390 × 844:

| | previous revision (12-row cap) | this revision (no cap) |
|---|---|---|
| plate height | 608px | **658px** |
| row height | 49px | **45px** |
| **rows on screen** | **11** | **13** |
| **rows reachable with no tap** | **12** | **50** (all) |
| extra tap required | yes | **no** |

**+18% more rows visible per screen, and every row reachable without a tap.**
Font size did not shrink — it is still 13px, up from the base page's 12.5px.

### (g) Provenance apparent without scrolling past the data

```text
  PROJECTED MODE chips lifted into board headers : 10
  long explainers tucked below the plate         : 11
  leftover badges still sitting above data       : 1  (combos-k, no table)
  headlines badge                                : in place, top of section
```

All 12 provenance markers on the page sit at or above the data. Two notes:

- The 1 "leftover" is `combos-k`, which has no table — its badge stays at the
  top of the body, which is already above its content.
- Only 1 of the 15 game cards carries a chip, because `with_projected_badge()`
  in `build_day46.py` inserts the badge with `count=1` — so only the first game
  card has ever had one, on this branch and on main alike. I did not
  manufacture 14 more; the fixed spine and the banner cover those cards.

### (h) Light and dark both fully designed

Contrast against composited backgrounds; WCAG AA (3.0 large / 4.5 otherwise):

```text
                      base dark  base light   NEW dark  NEW light   verdict
------------------------------------------------------------------------------
brand wordmark             16.5         1.1       16.6       16.1   AA restored in light
hero h1                    16.5         1.1       16.6       15.7   AA restored in light
hero games chip             9.8         1.4       10.6       11.1   AA restored in light
last updated                6.2         3.6        6.3        5.8   AA restored in light
install banner             14.1         1.1       15.2       17.4   AA restored in light
section title              15.6         7.2       13.9       16.2
section tag                 5.9         2.1        5.3        6.0   AA restored in light
board eyebrow              14.6        13.1       10.8        6.3
provenance tag             11.0         1.8        8.9        4.8   AA restored in light
provenance body             9.7         4.3       11.6       10.0   AA restored in light
note paragraph               --          --       10.2       11.4
rank numeral                 --          --        8.9        5.5
table cell                 15.7         1.0       15.7       17.9   AA restored in light
table header                5.4         3.1        5.3        6.0   AA restored in light
header chip                  --          --        7.1        4.9
search input                 --          --       15.8       17.9
withheld line                --          --       16.6       14.4
withheld item                --          --       16.6       14.4
banner body                  --          --       15.5       13.0

  base dark   below WCAG AA -> none
  base light  below WCAG AA -> 10 probes, five of them at ~1.1:1 (invisible)
  NEW  dark   below WCAG AA -> none
  NEW  light  below WCAG AA -> none
```

All 19 probes clear AA in both themes. A sweep also confirmed **zero** values
from the previous palette survive anywhere in the projected CSS.

### (i) 390px, safe areas respected

```text
--- dark --- scrollWidth=390 overflowX=False
--- light -- scrollWidth=390 overflowX=False
    search input     n=1   minH=44   minW=366   >=44px: yes
    withheld toggle  n=1   minH=45   minW=355   >=44px: yes
    board header     n=12  minH=87   minW=360   >=44px: yes
    rail chip        n=15  minH=44   minW=44    >=44px: yes
    icon button      n=1   minH=44   minW=44    >=44px: yes
    dock button      n=7   minH=49   minW=47    >=44px: yes
```

16 `env(safe-area-inset-*)` uses on the page. Headless Chromium *defines* the
insets as `0`, so `env()` fallbacks never fire and cannot test this — the proof
render substitutes literals (59px top / 34px bottom):
`docs/projected-overhaul/safearea-dark.png`.

### (j) Preview rebuilt, self-contained, search works in it

`docs/preview/projected.html` — 275,219 bytes, plus `scout.html` and the page's
own assets.

```text
  <script src=...>          : NONE
  inline <style> / <script> : 1 / 2
  games 15 · data rows 358
  emoji titles: ['🏆 Top 50 HR Board', '☄️ Top 50 Hits Board']
  unresolved refs: k-report.html, record.html, streaks.html   (sibling pages)
```

Loaded from its committed path with **networking disabled entirely**:

```text
OFFLINE LOAD: {"games":15,"rows":358,"chips":10,"caps":0,"withheld":6,"broken":[]}
OFFLINE SEARCH "Hunter Greene": {"hits":"8","visible":8,"all":true}
after clear, filtering: False
SSJ round trip: withheld page -> back link -> projected.html (358 rows, search bar live)
page errors: none
```

Renders standalone, search works, zero broken images, zero page errors. The
only request the browser attempts is the Google Fonts stylesheet `index.html`
already carries on main; offline the display face falls back to Arial Narrow
and the layout is unchanged.

### (k) ast.parse and py_compile

```text
  ast.parse(sync.py)  OK -- 44,068 bytes, 1063 lines
  ast.parse(build.py) OK --  6,649 bytes,  137 lines
  py_compile sync.py build.py OK
  curly quotes: none
  PROJECTED_CSS f-string: False | PROJECTED_JS f-string: False
```

AGENTS.md rules 3 and 5 hold: straight quotes only, and both injected blocks
are plain triple-quoted strings, so their single braces cannot crash the build.

---

## 3. SCREENSHOTS

390 × 844, device pixel ratio 2, mobile emulation, in `docs/projected-overhaul/`.

| file | what |
|---|---|
| `top-dark.png` / `top-light.png` | top of page |
| `mid-dark.png` / `mid-light.png` | mid-scroll, HR board open |
| `search-dark.png` / `search-light.png` | search active, filtered |
| `withheld-open-dark.png` / `withheld-open-light.png` | disclosure expanded |
| `ssj-dark.png` / `ssj-light.png` | SSJ withheld page + back link |
| `safearea-dark.png` | iPhone 14 Pro insets applied |

The search shots show HR ranks **1, 3, 5, 20, 34** — non-contiguous, which is
the proof there is no longer any cap between the filter and row 34.

---

## 4. NOTES

- **The brand accent is green, not cyan** — see section 0. The cyan you have
  been looking at is main's projected skin, i.e. the mode signal itself.
- **The emoji were never removed by this branch** — `build_day46.py` has always
  emitted different titles per mode. Restored to match the workbook boards.
- **The row cap was my error**, and the numbers in (f) say so plainly.
- **Fonts:** the brief again asks for Rajdhani, which is not loaded; adding it
  would break "no new fonts". Bebas is used for rank numerals only, DM Mono
  carries every stat label and header — the role the brief gives Rajdhani.
- **Preview caveat, unchanged:** a genuine no-workbook day needs live fetches,
  so the preview forces `_mode: projected` onto the committed workbook slate.
  That is what makes the values real; the consequence is that a few columns
  (e.g. Zone) show workbook values that would be dashes on a true projected day.
- Nothing merged. Draft PR #25, same branch.
