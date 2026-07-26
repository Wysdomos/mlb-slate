# SESSION STATUS - 2026-07-26 - Projected Mode header fix + withheld dropdown

Branch: `claude/projected-header-withheld`
Base:   `origin/main` @ `deb0120` (Chapter I)
Status: draft PR, not merged.

Targeted fix on main's shipped skin. **One file changed: `sync.py` (+193 / -2).**
The `claude/projected-overhaul` branch was not built on and is not revived.

---

## 1. THE WITHHELD COUNT IS 4, NOT 6 — AND THAT DISTINCTION MATTERS

The projected page carries **six** `unavailable-card` elements, but they say two
different things:

| section | card text | meaning |
|---|---|---|
| Matchup Spotlight | Unavailable without workbook | genuinely withheld |
| Pitcher's HR Risk Board | Unavailable without workbook | genuinely withheld |
| Conviction Board | Unavailable without workbook | genuinely withheld |
| Daily Skip List | Unavailable without workbook | genuinely withheld |
| Strikeout Stack | **No qualifying correlation stack** | board ran, nothing qualified |
| Anchor | **No qualifying correlation stack** | board ran, nothing qualified |

The last two are Chapter I's correlation parlay boards. They are **not**
withheld — they executed and produced no qualifying output today. Folding them
into "boards withheld today" would tell you a working board is missing because
of the workbook, which is false and is exactly the class of misinformation the
banner exists to prevent.

So: **only the four `projected-unavailable` sections are removed and counted.
The two "No qualifying correlation stack" cards are deliberately left in place.**
The disclosure reads **"4 boards withheld today"**, which also happens to match
the example in the brief.

---

## 2. WHAT I TOUCHED

Exactly three things in `sync.py`, all behind the `if not PROJECTED_MODE`
guard:

1. `.projected-mode-banner` — added safe-area padding and a negative bottom
   margin (the two header fixes).
2. Added 13 new `.pm-withheld*` CSS rules for the disclosure.
3. Added `PROJECTED_JS` (a 20-line vanilla toggle) and the markup/strip logic
   for the disclosure and the four placeholder sections.

Nothing else. Proof in (g).

---

## 3. VERIFICATION

### (a) Workbook-backed rendering byte-identical to main

```text
both rendered inside clock minute 17:16
  main   : 246,742 bytes  sha256=ea8d40c6fc8afde4bff2e60391fe7b3962fa357a064d93852fa863c27cabb742
  branch : 246,742 bytes  sha256=ea8d40c6fc8afde4bff2e60391fe7b3962fa357a064d93852fa863c27cabb742
  BYTE-IDENTICAL: True
  unified diff lines: 0  -> EMPTY

  workbook page contains 'pm-withheld'            : False
  workbook page contains 'PROJECTED MODE CSS START': False
  workbook page contains 'PROJECTED JS START'      : False
  workbook page contains 'PROJECTED CHROME START'  : False
  workbook page contains 'pmWithheldBtn'           : False
```

**The diff is empty.**

> Worth recording: my first run of this check reported a 281-line diff, and the
> bug was in the *test*, not the code. Main's committed `day_data.json` now
> carries `_mode: 'projected'` (Chapter I committed a projected build), so
> feeding it in was exercising the projected path twice rather than the
> workbook path at all. The harness now strips `_mode` first. The committed
> `index.html` is itself a projected build, so this check also proves the
> strip-and-rebuild path is idempotent: a projected page fed back through a
> workbook build comes out clean.

### (b) Diffstat shows nothing outside the presentation layer

```text
 sync.py | 195 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++-
 1 file changed, 193 insertions(+), 2 deletions(-)

M	sync.py
```

```text
  UNCHANGED  fetch_projected_mode.py     UNCHANGED  tools/
  UNCHANGED  extract_xlsx.py             UNCHANGED  backtest/
  UNCHANGED  shadow_chips.py             UNCHANGED  .github/
  UNCHANGED  parlay_rules.py
  UNCHANGED  build_day46.py
  UNCHANGED  build.py
  UNCHANGED  grade_results.py
```

`build_day46.py` untouched means no scoring and no `SLATE_PICKS` emission could
have moved. The withheld list is derived at render time from the sections'
own titles — no list is hard-coded and no build file was edited.

### (c) Banner clears the iOS status bar

Measured at 390 × 844 with a 59px top inset substituted (headless Chromium
*defines* the insets as 0, so `env()` fallbacks cannot test this):

```text
BEFORE (main)   bannerTextTop=14   appbarTop=136  brandTop=205  gap=69
AFTER  (fixed)  bannerTextTop=73   appbarTop=193  brandTop=262  gap=10

  banner text starts at y : 14px -> 73px   (status bar = 59px)
  clears the status bar   : False -> True
```

Screenshots: `before-safearea-dark.png` vs `after-safearea-dark.png`.

### (d) Dead gap closed — and what was producing it

The gap was **not** a stray margin. Diagnosed by measuring the header stack:

```text
  appbar  padding-top: 59px   min-height: 111px   position: sticky
```

The app bar reserves `env(safe-area-inset-top)` so its wordmark clears the
notch **once it is stuck to the top**. In Projected Mode the banner sits above
it, so at scroll 0 the bar is *not* stuck and that 59px reserve renders as a
blank band. It is dead only in that one state.

Fix, without touching the app bar and without JS: the banner overlaps the
reserve with `margin-bottom: calc(-1 * env(safe-area-inset-top, 0px))` and
`z-index: 61`. The reserve is empty by definition so nothing is occluded, and
the reserve still does its job the instant the bar pins and the banner has
scrolled away.

```text
  dead gap banner->brand : 69px -> 10px
```

The residual 10px is the wordmark's own 4px padding plus line leading — normal
spacing, not dead space. Before/after screenshots as above.

### (e) Withheld dropdown renders, counts, and expands

```text
  dropdown present : True
  count            : "4"
  label            : "boards withheld today"
  tap target       : 44px tall
  expanded         : aria-expanded="true", body .open
  names            : ["Matchup Spotlight", "Pitcher's HR Risk Board",
                      "Conviction Board", "Daily Skip List"]
  note             : "These need the workbook. They are held back rather than estimated."
  collapses again  : True
  page errors      : none
```

Placement is directly under the banner text and above the site header, as
specified. Styled with main's projected tokens — cyan on slate, 8px radii — not
the overhaul's palette.

### (f) Per-section cards removed; banner and dropdown both present

```text
                            main (before)   branch (after)
  projected-unavailable sections     4              0
  "Unavailable without workbook"     4              0
  "No qualifying correlation stack"  2              2   <- deliberately kept
  <section> count                   21             17
  banner present                  True           True
  dropdown present               False           True
```

The banner stays and the dropdown stays. Between them the page can never pass
as a graded slate, and the four missing boards are named on demand.

### (g) Nothing else about main's projected look changed

```text
  data rows            main=358  branch=358  identical=True
  <table>    main=  27  branch=  27   OK
  <td>       main=2917  branch=2917   OK
  <th>       main= 288  branch= 288   OK

  CSS rules in main's projected block   : 13
  CSS rules on this branch              : 27
  rules REMOVED from main's skin        : none
  main's rules all still present verbatim: True
  main rules whose declarations changed : ['.projected-mode-banner']

  rules ADDED (13, all the disclosure):
     .pm-withheld, .pm-withheld-btn, .pm-withheld-btn .pm-count,
     .pm-withheld-btn .pm-caret, .pm-withheld-btn[aria-expanded="true"] .pm-caret,
     .pm-withheld-body, .pm-withheld-body.open, .pm-withheld-body ul,
     .pm-withheld-body li, .pm-withheld-body li::before, .pm-withheld-note,
     @media (prefers-reduced-motion: reduce)

  sections removed : conviction, matchup-spotlight, skip, sp-vuln-board
  sections added   : none
```

**Zero of main's 13 projected CSS rules were removed, and all 13 are present
verbatim.** Exactly one — `.projected-mode-banner` — had its declarations
changed, and that change *is* the header fix. Every rendered value is identical:
all 358 data rows, all 2,917 cells.

No palette, card system, spine, hatch or search dock came across from the
scrapped branch.

### (h) Light and dark

The five new components, measured against composited backgrounds:

```text
                          dark   light   AA
withheld row              14.7    14.7   pass
count chip                10.6    10.6   pass
board name                14.0    14.0   pass
disclosure note           13.7    13.7   pass
caret                     13.7    13.7   pass
```

Identical in both themes, because the disclosure sits on the banner's own
gradient, which is theme-independent — the same reason the banner text itself
reads at 18.1 in both.

**Flagged, not fixed — a pre-existing defect in main's projected skin:**

```text
— brand wordmark —        16.5     1.1   FAIL
— hero h1 —               16.5     1.1   FAIL
— games chip —             9.8     1.4   FAIL
— table cell —            15.7     1.0   FAIL
```

In light mode main's `.projected-mode` block hard-codes dark surfaces at
specificity (0,1,0), so it also wins under `[data-theme="light"]` while text
stays near-black. Table cells sit at **1.0:1 — invisible** — on the page you
read in daylight. It is visible in `withheld-open-light.png` ("THE DAILY"
almost disappears).

I did **not** fix it: the brief says port only the two items and leave
everything else about main's look exactly as it is, and this would be a third
change. Flagging it so it is your call, not silently absorbed. It is a small
fix (scope the light values at `[data-theme="light"] .projected-mode`) whenever
you want it.

### (i) Preview file rebuilt and self-contained

`docs/preview/projected.html` — 250,693 bytes, committed with its own assets.

```text
  <script src=...>          : NONE
  inline <style> / <script> : 1 / 2
  games 15 | data rows 358
  banner: True | dropdown: True | projected-unavailable sections left: 0
  unresolved refs: k-report.html, record.html, scout.html, streaks.html  (sibling pages)
```

Loaded from its committed path with **networking disabled entirely**:

```text
OFFLINE LOAD: {"games":15,"rows":358,"banner":true,"dropdown":true,"count":"4","broken":[]}
dropdown expands -> ["Matchup Spotlight","Pitcher's HR Risk Board",
                     "Conviction Board","Daily Skip List"]
dock search "Aaron Judge": {"count":"1 match on the slate","visible":1,"allMatch":true}
after clear, filtering: False
page errors: none
```

Real Jul 26 slate — 15 games, 358 data rows, real players, no placeholders and
no invented values. Renders standalone, the dropdown works, the page's existing
dock search still works, zero broken images, zero page errors. The only request
the browser attempts is the Google Fonts stylesheet `index.html` already carries
on main.

### (j) ast.parse and py_compile

```text
  ast.parse(sync.py) OK -- 19,152 bytes, 489 lines
  py_compile sync.py OK
  curly quotes: none
  PROJECTED_CSS f-string: False | PROJECTED_JS f-string: False
  guard before CSS inject : True
  guard before JS inject  : True
  guard before card strip : True
```

AGENTS.md rules 3 and 5 hold — straight quotes only, and both injected blocks
are plain triple-quoted strings, so their single braces cannot crash the build.

---

## 4. SCREENSHOTS

390 × 844, mobile emulation, in `docs/projected-header-withheld/`.

| file | what |
|---|---|
| `before-safearea-dark.png` | main today, 59px inset — text under the status bar, 69px dead gap |
| `after-safearea-dark.png` | fixed — text clears the bar, gap closed |
| `after-safearea-light.png` | same, light |
| `top-dark.png` / `top-light.png` | top of page, disclosure collapsed |
| `withheld-open-dark.png` / `withheld-open-light.png` | disclosure expanded, naming the four boards |

---

## 5. NOTES

- **Withheld count is 4, not 6** — see section 1. The two "No qualifying
  correlation stack" cards belong to Chapter I's parlay boards and are a
  different statement; they were left alone.
- **The dead gap was the app bar's safe-area reserve**, not a margin — diagnosed
  by measurement before any change was made.
- **Main's light mode is broken independently of this work** — measured and
  flagged in (h), deliberately not fixed, since it is outside the two items.
- **Fonts:** the brief again asks for Rajdhani, which is not loaded; adding it
  would break "no new fonts". No font declarations were added at all this pass —
  the disclosure inherits the page's existing stack.
- Nothing merged. Draft PR only.
