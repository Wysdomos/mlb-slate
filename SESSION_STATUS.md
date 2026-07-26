# SESSION STATUS - 2026-07-26 - Projected Mode: header fix, withheld dropdown, light/dark

Branch: `claude/projected-header-withheld`
Base:   `origin/main` @ `deb0120` (Chapter I)
Status: draft PR, not merged.

Targeted fix on main's shipped skin. **One file changed: `sync.py` (+280 / -2).**
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
4. Added a full light theme for the projected skin, scoped
   `[data-theme="light"] .projected-mode` (section 6).

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
 sync.py | 282 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++-
 1 file changed, 280 insertions(+), 2 deletions(-)

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
  CSS rules on this branch              : 34
  rules REMOVED from main's skin        : none
  main's rules all still present verbatim: True
  main rules whose declarations changed : ['.projected-mode-banner']

  rules ADDED: 21  ->  12 disclosure (.pm-withheld*, reduced-motion)
                       9 light-theme ([data-theme="light"] .projected-mode ...)

  sections removed : conviction, matchup-spotlight, skip, sp-vuln-board
  sections added   : none
```

**Zero of main's 13 projected CSS rules were removed, and all 13 are present
verbatim.** Exactly one — `.projected-mode-banner` — had its declarations
changed, and that change *is* the header fix. Every rendered value is identical:
all 358 data rows, all 2,917 cells.

The 21 added rules are purely additive: 12 for the disclosure and 9 for the
light theme. The light-theme rules are all scoped `[data-theme="light"]`, so
they are inert in dark mode — dark is byte-for-byte the skin main ships.

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
  ast.parse(sync.py) OK -- 22,943 bytes, 576 lines
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
| `theme-dark.png` / `theme-light.png` | both themes after the light/dark fix |
| `theme-light-mid.png` | light, mid-scroll with a board open |

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

---

## 6. LIGHT / DARK — PROJECTED CSS HAD NO THEME SUPPORT

### Root cause, confirmed in the code

```text
  [data-theme= selectors in PROJECTED_CSS : 0
  prefers-color-scheme blocks             : 0
  variables overridden on one fixed palette: 22
```

`.projected-mode` (specificity 0,1,0) is injected *after* `[data-theme="light"]`
(also 0,1,0), so it won the cascade in **both** themes. Toggling to light
flipped the site's text to near-black while these overrides held the surfaces
dark. Measured before the fix: page background `rgb(13,17,23)` in light mode,
table cells at **1.0:1 — invisible**, 12 elements below AA.

Ten further rules hard-coded colours rather than reading a variable
(`.app-bar` background, `.projected-section-badge span`, `.unavailable-card
strong`, the hero and game-header gradients, the card shadows), so each needed
its own light value too.

### The fix

A full light palette scoped `[data-theme="light"] .projected-mode` (0,2,0), so
it beats the dark block regardless of source order, driven by the same
attribute the in-app toggle writes.

**No `prefers-color-scheme` anywhere** — verified against the shipped page with
comments stripped, so the one textual occurrence (this rationale) is not
counted:

```text
  data-theme selectors in shipped CSS : 10
  prefers-color-scheme @media rules   : 0
```

**Designed, not auto-inverted.** An inversion of the dark values produces muddy
greys and loses the icy character. The light ground is a cold blue-white — the
blue channel runs 10-32 above red across the three ground tones — and the
accents deepen rather than desaturate:

| role | dark | light | contrast vs white / paper |
|---|---|---|---|
| accent, tier0 | `#22d3ee` / `#67e8f9` | `#0e7490` | 5.36 / 4.73 |
| tier1, gold | `#fbbf24` | `#8a5406` (text), `#a16207` (fills) | 6.27 / 5.53 |
| badge label | `#67e8f9` | `#0b5f78` | 7.19 / 6.35 |
| page ground | `#0d1117` | `#eaf2f7` | — |
| surface | `#101720` | `#ffffff` | — |
| text-dim | inherited | `#4e5f6b` (deepened for sun) | 6.62 / 5.84 |

The banner and its disclosure keep the same deep teal block in **both** themes.
That is deliberate: it inverts against the light page exactly as it stands out
on the dark one, so the loudest "this is Projected Mode" mark never changes
character when the theme is toggled.

### Result

```text
                      main dk  main lt   NEW dk   NEW lt   verdict
brand wordmark           16.5      1.1     16.5     15.8   FIXED in light
hero h1                  16.5      1.1     16.5     15.8   FIXED in light
games chip                9.8      1.4      9.8      9.3   FIXED in light
last updated              6.2      3.6      6.2      5.8   FIXED in light
install banner           14.1      1.1     14.1     14.7   FIXED in light
section title            15.6      7.2     15.6     17.2
section tag               5.9      2.1      5.9      6.3   FIXED in light
table cell               15.7      1.0     15.7     17.9   FIXED in light
table header              5.4      3.1      5.4      6.1   FIXED in light
rail chip                 6.2      4.5      6.2      6.3   FIXED in light
badge label              11.0      1.8     11.0      6.2   FIXED in light
badge detail              9.7      4.3      9.7      9.8   FIXED in light
unavailable strong        9.2      1.4      9.2      5.4   FIXED in light
unavailable body          9.3      4.7      9.3      9.7
method intro             10.8      4.6     10.8     10.9
count chip                 --       --     10.6     10.6

  main light : 12 elements below AA
  NEW  light : none
  NEW  dark  : none

  page background   main light = rgb(13, 17, 23)     <- the bug
                    NEW  light = rgb(234, 242, 247)
```

The banner, its `<small>` and the withheld row initially read as failures here.
That was a measurement artifact, not a regression: their background is a CSS
**gradient**, which `getComputedStyle().backgroundColor` reports as
transparent, so the probe composited the text against the page behind it.
Re-measured from rendered pixels, sampling the banner's background at
text-free points:

```text
  dark   banner bg (28,41,58)   text 14.1   small 13.1
  light  banner bg (37,50,67)   text 12.4   small 11.6
```

Both themes clear AA on every probe.

### The page follows the in-app toggle, not the OS

Tested all four combinations of stored `slateTheme` against the OS
`prefers-color-scheme`. Rows 2 and 3 are the decisive ones — OS set opposite to
the toggle:

```text
slateTheme  OS scheme   data-theme  page bg                 reads as follows
dark        dark        dark        rgb(13, 17, 23)         dark     YES
dark        light       dark        rgb(13, 17, 23)         dark     YES
light       dark        light       rgb(234, 242, 247)      light    YES
light       light       light       rgb(234, 242, 247)      light    YES

page follows the in-app toggle in all 4 combinations: True

live toggle with OS=dark: ['light', 'rgb(234,242,247)'] -> ['dark', 'rgb(13,17,23)', 'dark']
toggle flips the page and persists to localStorage: True
```

The rebuilt preview was re-checked the same way, offline:

```text
OFFLINE preview  toggle=light  OS=dark  -> theme light, bg rgb(234,242,247), dropdown 4, 0 broken, no errors
OFFLINE preview  toggle=dark   OS=light -> theme dark,  bg rgb(13,17,23),    dropdown 4, 0 broken, no errors
```

Screenshots: `theme-dark.png`, `theme-light.png`, `theme-light-mid.png`.

### Note on (h) above

Section (h) recorded these four light failures as "flagged, not fixed" because
they were outside the two items in that brief. Item 3 put them in scope and
they are now fixed; the table in this section supersedes that note.
