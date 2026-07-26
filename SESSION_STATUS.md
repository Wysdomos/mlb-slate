# SESSION STATUS - 2026-07-26 - Projected Mode skin bake-off (alternate)

Branch: `claude/projected-mode-skin-alt-keuhaf`
Scope: **skin only.** A competing visual treatment for the Projected Mode that
Chapter F already shipped to main. Nothing else changes. Loser's branch gets
deleted.

---

## 1. WHAT THIS IS

A second skin for the same feature, built so the owner can compare the two on
his phone and pick one. The data, the reconstruction, the freshness gate, the
section list, the row counts and every rendered value are identical to main.
The only thing that differs is how it looks.

### Design direction: **Cordon**

The page is a *reconstruction*, so it is **cordoned, not recolored**.

One hazard hatch is drawn at four scales:

| scale | where | why |
|---|---|---|
| 8px | fixed spine down the left edge of the viewport | on screen at every scroll position |
| inset | fills the iOS status-bar inset | first thing on the screen, above the wordmark |
| 4px | rule closing the sticky header stack | marks the chrome/content boundary |
| 5px | leading edge of every projected badge and held card | marks each reconstructed surface |

**Palette.** Violet carries the mode because nothing else on this page uses it
— green, gold, red and orange all already mean something about a *play*. Six
named values: Cordon Violet `#b98cff` / `#5b21b6`, Stamp Ground `#2a1152` /
`#4c1d95`, Blueprint Ink `#0a0713` / `#efeaf7`, Held Steel `#8ea6c8` /
`#3f5570`, Chalk `#f4eeff`, and the hatch (Cordon Violet at 58% on a 5px/11px
135 degree repeat).

**Type.** Existing stack only, no new fonts, no new dependencies. Bebas Neue
for the one stamp wordmark — the same display role `.brand .wordmark` and every
`.hero h1` already give it. DM Mono, uppercase and tracked, for every *mode*
label (badge label, held-section tags, status line): a machine voice for
machine-reconstructed surfaces. DM Sans for all prose. See section 5 for a note
on the brief's font line.

**Tiers.** `--tier0` / `--tier1` drop to violet + steel. These ranks are
*derived*; wearing the same green a Sweet Spot grade wears is exactly the
confusion the brief warns about. That is content-true, not decoration.

---

## 2. WHERE IT DELIBERATELY DIVERGES FROM MAIN

**1. The signal persists instead of scrolling away.**
Main's mark is a banner at the top of the body. Scroll past it and there is
nothing projected-looking left on screen — the page is a normal dark slate with
a cyan accent instead of a green one. That is a hue shift you have to *compare
against memory* to notice. This skin adds a fixed spine and a hatch rule in the
sticky header, so the mark is present at any scroll position. See
`docs/projected-skin-alt/compare-scrolled.png` — that pair is the whole
argument.

**2. Light mode works.**
Main's `.projected-mode` block hard-codes dark surfaces (`--bg: #0d1117`,
`--surface: #101720`, `.app-bar { background: rgba(13,17,23,0.9) }`) at
specificity (0,1,0) and is appended after `[data-theme="light"]`, so it wins in
*both* themes while `--text` stays the light theme's near-black. In daylight —
the owner's actual use case — the wordmark, the hero date, the games chip, the
install banner and the held-card headings all render near-invisible. Measured
below: **9 of 12 probes under WCAG AA, five of them at ~1.1:1.** This skin
scopes the light values under `[data-theme="light"] .projected-mode`
(specificity (0,2,0), so it wins regardless of source order). All 12 probes
clear AA in both themes.

**3. The banner clears the notch.**
Main's banner is `padding: 13px 18px` with no `env(safe-area-inset-top)`, and
it sits above the app bar — so on a real iPhone its first line runs under the
status bar / Dynamic Island. This skin pads by
`calc(env(safe-area-inset-top, 0px) + 13px)` and fills the inset with the
hatch. `docs/projected-skin-alt/alt-dark-safearea.png` is rendered with the
insets substituted (59px top / 34px bottom).

**4. Held-back sections stop looking broken.**
Main uses a dashed amber border on `.unavailable-card` — the universal
warning/error idiom. Nothing is wrong: the workbook simply is not there. This
skin uses a solid, fully built panel carrying the same cordon edge as every
other reconstructed surface, in normal text colours, no dash and no amber. The
panel field is deliberately left un-hatched — hatching *inside* the box would
read as struck through rather than reserved.

**5. Banner hierarchy is inverted; the wording is not.**
Main leads with four lines of bold body copy you have to read. This skin leads
with a stamp you *recognise* (`PROJECTED` / `MODE`, then a tracked mono
`RECONSTRUCTED · NOT GRADED`), and demotes the same facts to small print
underneath, ending on the one action that fixes it. Every fact main states is
still stated; only the emphasis moved. The `⚡ PROJECTED MODE —` prefix was
dropped because the stamp above it now carries that. **No data value changed**
— proven in (a) below, where all 4,263 visible text nodes in `<main>` are
byte-identical.

**6. Kept on purpose:** the house corner radius. Main flattens
`.collapsible` / `.game` from the site's 18px to 8px. This skin leaves the
product's form language alone so that only the *mode* chrome differs. The
distinction is carried by the cordon and the stamp, which are stronger signals
than a corner radius.

**7. No animation.** No glow, no pulse, no drift. The one bold move is the
cordon; everything around it stays quiet.

---

## 3. VERIFICATION

### (a) Projected page differs from main VISUALLY ONLY

Both branches rendered through the same pipeline (`build_day46.py` -> `sync.py`)
from the same `day_data.json` with `_mode: projected`.

```text
sections in main : 21
sections in alt  : 21
section ids identical : True
sections byte-identical: 21/21  (all)

structural element counts   main / alt
  OK  <section           21 /     21
  OK  <table             27 /     27
  OK  <tr               385 /    385
  OK  <td              2917 /   2917
  OK  <th               288 /    288
  OK  collapsible        18 /     18

visible text nodes in <main>  main=4263  alt=4263  identical=True

HTML with <style>, banner and build-clock masked out:
  main sha=c67c3943e7e5c0c4  alt sha=c67c3943e7e5c0c4  identical=True
```

All 21 `<section>` blocks are byte-identical, every structural count matches,
and every one of the 4,263 rendered text values in `<main>` matches. With the
`<style>` block, the mode banner and the build clock masked out, the two
documents hash the same. The entire difference between the two renders is the
CSS block and the banner chrome.

### (b) Workbook-backed (non-projected) rendering is byte-identical to main

Same pristine `index.html`, same `built_sections.json`, same `day_data.json`
(no `_mode` key), both runs inside the same clock minute so the build timestamp
matches:

```text
both renders inside clock minute 05:43
  main : 340,598 bytes  sha256=449c50e8c415789f726f9a36470f7491f8e7955f005cbfbf653ec36a3dc75c33
  alt  : 340,598 bytes  sha256=449c50e8c415789f726f9a36470f7491f8e7955f005cbfbf653ec36a3dc75c33
  BYTE-IDENTICAL: True
  unified diff lines: 0   -> EMPTY
  "projected" string occurrences: main=10 alt=10
```

**The diff is empty.** On a normal workbook day this branch produces the same
bytes as main. All new CSS is gated behind `PROJECTED_MODE`.

### (c) No file outside the presentation layer is modified

```text
$ git diff --stat origin/main
 sync.py | 369 +++++++++++++++++++++++++++++++++++++++++++++++++++++-----------
 1 file changed, 305 insertions(+), 64 deletions(-)

$ git diff --name-status origin/main
M	sync.py
```

One file. Every off-limits path confirmed untouched:

```text
  UNCHANGED  fetch_projected_mode.py
  UNCHANGED  extract_xlsx.py
  UNCHANGED  tools/projected_publish_guard.py
  UNCHANGED  tools/check_bpp_compliance.py
  UNCHANGED  build_day46.py
  UNCHANGED  build.py
  UNCHANGED  grade_results.py
  UNCHANGED  .github/workflows/*
```

The three changed hunks in `sync.py` are all inside the presentation layer:
`PROJECTED_CSS` (the `.projected-mode` block), and two hunks in
`apply_projected_theme()` (the banner strip regex and the banner markup).

Also added: `docs/projected-skin-alt/*.png` — the screenshot deliverables. New
files only, not on any code path.

> Note for the record: `build_day46.py` writes `slate_picks.json` /
> `slate_picks_7-25.json` as a side effect, so an early render run dirtied them.
> They were restored from `origin/main` and the render harness was moved to an
> isolated clone. The re-render is identical to the one screenshotted (verified
> after masking the build clock). Working tree is clean apart from `sync.py`,
> this file, and the new `docs/` images.

### (d) 390px width, safe areas respected

```text
  main dark   scrollWidth=390px  horizontal overflow=False  3 smallest tap targets=[28, 30, 30]px
  main light  scrollWidth=390px  horizontal overflow=False  3 smallest tap targets=[28, 30, 30]px
  ALT  dark   scrollWidth=390px  horizontal overflow=False  3 smallest tap targets=[28, 30, 30]px
  ALT  light  scrollWidth=390px  horizontal overflow=False  3 smallest tap targets=[28, 30, 30]px
```

Measured with every collapsible expanded. No horizontal overflow; tap-target
sizes are unchanged from main (they come from base CSS this skin does not
touch).

Safe areas — the skin uses `env(safe-area-inset-*)` in three new places: the
banner's top padding, the banner's inset hatch, and the left offset of the
fixed spine (so the cordon sits inside the notch cutout in landscape).
Headless Chromium *defines* the insets as `0`, so `env()` fallbacks never fire
and cannot be used to test this; the proof render substitutes the literals
(59px top / 34px bottom, iPhone 14 Pro portrait) instead —
`docs/projected-skin-alt/alt-dark-safearea.png`.

One bug found and fixed during this pass: the hatch was originally also applied
to `.app-bar`'s inset reserve, which painted a stray band mid-page at scroll 0
because the bar is not pinned to the top until you scroll. Removed — the fixed
spine already covers that region.

### (e) Light and dark both work

Text contrast against its **composited** background (every translucent layer
from the element up to an opaque ancestor is alpha-composited; a naive
`backgroundColor` read gives garbage on this page's glass surfaces).
Thresholds are WCAG AA: 3.0 for large text, 4.5 otherwise.

```text
                      main dark  main light   ALT dark  ALT light   verdict
------------------------------------------------------------------------------
brand wordmark             16.5         1.1       17.4       15.7   AA restored in light
hero h1                    16.5         1.1       17.4       15.2   AA restored in light
hero games chip             9.8         1.4       11.2       10.9   AA restored in light
last updated                6.2         3.6        6.6        5.2   AA restored in light
install banner             14.1         1.1       16.1       17.2   AA restored in light
section title              15.6         7.2       16.5       16.9
section tag                 5.9         2.1        6.2        5.8   AA restored in light
badge label                11.0         1.8        6.8        7.6   AA restored in light
badge detail                9.7         4.3       10.5        9.7   AA restored in light
held card title             9.2         1.4       16.2       16.0   AA restored in light
held card body              9.3         4.7       11.3       10.1
banner body                18.1        18.1       14.2       10.0

  main dark   below WCAG AA -> none
  main light  below WCAG AA -> brand wordmark (1.1), hero h1 (1.1), hero games chip (1.4),
                               last updated (3.6), install banner (1.1), section tag (2.1),
                               badge label (1.8), badge detail (4.3), held card title (1.4)
  ALT  dark   below WCAG AA -> none
  ALT  light  below WCAG AA -> none
```

Dark mode is fine on both. Light mode is where they part: main fails 9 of 12
probes, five at roughly 1.1:1 (invisible). This skin clears AA on all 12 in
both themes. `--text-dim` is nudged one step darker (`#5d6e79` -> `#55646e`) in
projected light mode only, because the projected ground is slightly deeper than
the stock light theme's.

### (f) ast.parse and py_compile

```text
ast.parse(sync.py)      OK  -- 21049 bytes, 539 lines
py_compile sync.py      OK
curly quotes in sync.py: none
PROJECTED_CSS is an f-string: False (single braces are safe)
```

Last two lines cover AGENTS.md rules 5 and 3 — straight quotes only, and the
CSS block is a plain triple-quoted string, not an f-string, so its single
braces cannot crash the build.

---

## 4. SCREENSHOTS

All rendered at **390 x 844, device pixel ratio 2, mobile emulation on**.

| file | what |
|---|---|
| `docs/projected-skin-alt/compare-top.png` | **main vs this branch, dark and light, top of page** |
| `docs/projected-skin-alt/compare-scrolled.png` | **main vs this branch, scrolled 2,600px in** |
| `docs/projected-skin-alt/alt-dark-390.png` | this branch, dark |
| `docs/projected-skin-alt/alt-light-390.png` | this branch, light |
| `docs/projected-skin-alt/alt-dark-scrolled.png` | this branch, scrolled deep |
| `docs/projected-skin-alt/alt-dark-safearea.png` | this branch with iPhone 14 Pro insets applied |

---

## 5. NOTES / JUDGEMENT CALLS

- **The brief's font line.** It asks to keep "Bebas Neue for zone and rank
  numbers only, Rajdhani for stats and labels". The live `index.html` does not
  work that way: it loads Bebas Neue + DM Sans + DM Mono, has no Rajdhani, and
  already uses Bebas for the wordmark, every `.hero h1` and every rail chip.
  Adding Rajdhani would have violated the binding constraint ("no new fonts"),
  so this skin keeps the stack that actually ships and uses Bebas only in the
  role the page already gives it — a display wordmark. Flagging it rather than
  quietly picking one reading.

- **Banner height.** 219px vs main's 136px at 390px wide. That is the cost of
  leading with a stamp instead of a paragraph. It scrolls away either way, and
  the persistent signal is the cordon, not the banner.

- **Colour is not the load-bearing signal.** The hatch is a *pattern*, so the
  distinction survives for a colour-blind reader and in washed-out direct
  sunlight, where a hue shift would not.

- Nothing was merged. Draft PR only, per the brief.
