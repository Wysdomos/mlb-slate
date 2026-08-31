# SESSION_STATUS — PR 3c: remove user-facing "Projected Mode" wording

Branch: `copy/remove-projected-wording`
Base: `origin/main` at `d8daa75` (`Refactor/tiers and ssj removal (#48)`)
Status: implemented, verified, pushed. Branch only — no PR opened, per dispatch.

## Scope

Three dispatched commits, copy only — BPP is the normal data source now, so the
page stops apologising for it:

1. `0754bbb` — `sync.py`. The ⚡ PROJECTED MODE banner text is gone; the
   `projected-mode-banner` div now renders only when the withheld disclosure is
   non-empty (today it is — the "2 boards withheld" dropdown rides inside it,
   unchanged). When the disclosure is empty the div is dropped but the CHROME
   markers still emit, so the strip regex keeps matching. Method-intro
   rewritten as a plain description of BallparkPal + Baseball Savant + MLB
   Stats API, keeping `Day N (date)`. Subtitle drops ` - Projected Mode`.
2. `5285581` — `sync.py`. The alignment title/tag swap removed from
   `apply_projected_theme()`: four variables and both `str.replace` pairs.
   The `if not PROJECTED_MODE: return html` guard is retained verbatim.
3. `fce9c3b` — `build_day46.py`. `projected_badge()` drops the
   `<span>PROJECTED MODE</span>`, keeping the container div and `<small>`
   provenance text. "· Projected Mode ·" removed from the HR-board and
   hits-board game-tags. HR badge text rewritten without mentioning Zone.

Deliberately not touched, per the keep-list and do-not-touch list:

- `PROJECTED_MODE` variable and every `if PROJECTED_MODE:` branch.
- CSS classes `.projected-mode` / `.projected-section-badge` /
  `.projected-mode-banner` / `.projected-unavailable`.
- All strip-regex marker comments (CSS START/END, CHROME START/END,
  JS START/END, `<!-- PROJECTED UNAVAILABLE -->` at `build_day46.py:1303`,
  matched by `sync.py:553`).
- `BUILD_STAMP` / `build-stamp.json` `mode` values; function names; log and
  print statements; every "projected" that means a forecast.
- The `projected_unavailable_section` calls for `sp-vuln-board` and
  `matchup-spotlight` (PR 3b runs in parallel) — including the reason string
  at `build_day46.py:3573` that still says "Projected Mode"; that surface
  belongs to 3b.
- Every `.py` file other than `sync.py` and `build_day46.py`; every
  threshold and CSS token. `git diff --name-only d8daa75..fce9c3b`:
  `build_day46.py`, `sync.py` only.

## Two dispatch premises, corrected against reality

- **The alignment title/tag swap is not entirely dead code.** The title
  replace pair is a true no-op (0 hits in `index.html`), but the tag OLD
  string `Tap to expand - tier thresholds + Aug 31 park notes` exists at
  `index.html:1915`, and the baseline build output contains its replacement
  ("reconstructed board boundaries") — the replace fires every build. Removing
  it therefore **changes output**: the alignment card tag reverts to the
  workbook wording, which is the desirable outcome for this PR (it drops a
  mode apology) and is recorded in commit 2's message rather than claimed as
  a no-op. Visible in verification (c)'s diff at hunk `@@ 1536`.
- **Zone is not "gone entirely."** `build_day46.py` still emits
  `<th>Zone</th>` and dash cells in the HR board. The badge rewrite therefore
  avoids mentioning Zone ("Score and tier are Daily Slate derived from live
  BallparkPal and Savant inputs.") rather than asserting its removal.

## Root cause of a failed check: stale baseline clone

The first A-vs-B content diff showed glossary rows, SSJ dock links and HR
board reordering that none of my commits could produce. Cause: cloning the
working repo locally maps the *source's local branches* to the clone's
`origin/*`, so the baseline clone's `origin/main` resolved to a stale local
`main`, not `d8daa75`. Fix: `git checkout -q d8daa75` in the baseline clone by
SHA, rebuild. All evidence below is from the corrected baseline. (Same trap
was hit and documented in July.)

## Verification

Letters follow the dispatch's check order.

### a. `ast.parse` both files

```bash
python3 - <<'PY'
import ast, pathlib
for f in ('sync.py', 'build_day46.py'):
    ast.parse(pathlib.Path(f).read_text(encoding='utf-8'))
print('ast.parse OK: sync.py, build_day46.py')
PY
python3 -m py_compile sync.py build_day46.py
```

```text
ast.parse OK: sync.py, build_day46.py
py_compile exit 0
```

Every edit in all three commits ran behind `assert OLD in src` and
`assert count == 1` (AGENTS.md rule 4); a drifted anchor would have raised.

### b. `build.py` in a temp clone

Two clones under the session scratchpad: `base_clone` pinned to `d8daa75`,
`b_clone` at branch head `fce9c3b`. Each ran `build.py` then `sync.py` twice
in a row (the second run consumes the first run's `index.html`, the real
idempotency path):

```text
base_clone @ d8daa75:  build.py exit: 0  sync.py exit: 0   (x2)
b_clone    @ fce9c3b:  build.py exit: 0  sync.py exit: 0   (x2)
-> /tmp/index_A1.html 265,306 B   /tmp/index_A2.html 265,308 B
   /tmp/index_B1.html 264,580 B   /tmp/index_B2.html 264,582 B
```

### c. Zero user-visible "Projected Mode"; all markers exactly once

Visible text = the page with comments, `<style>` and `<script>` stripped.
Marker counts are on the raw file:

```text
A1: visible "Projected Mode" = 16   markers(CSS s/e, CHROME s/e, JS s/e) = [1, 1, 1, 1, 1, 1]
A2: visible "Projected Mode" = 16   markers = [1, 1, 1, 1, 1, 1]
B1: visible "Projected Mode" =  0   markers = [1, 1, 1, 1, 1, 1]
B2: visible "Projected Mode" =  0   markers = [1, 1, 1, 1, 1, 1]
```

(`<!-- PROJECTED UNAVAILABLE -->` appears in no build on either side —
nothing renders a `projected-unavailable` section on this slate — but the
marker survives in source: `build_day46.py:1303`, consumed by `sync.py:553`.)

The normalized A1-vs-B1 unified diff (normalizing the build-stamp meta, the
last-updated clock, and the pre-existing blank-line accretion) is **16 hunks,
every one a dispatched change**:

```text
@@ 1255  banner: mode text gone; pm-withheld dropdown ("2 boards withheld") intact
@@ 1270  subtitle "12 Games - Day 157 - Projected Mode" -> "12 Games - Day 157"
         (+ 2:35->2:33 PM clock churn in the same hunk)
@@ 1292  method-intro rewritten (plain source description, Day 157 (Aug 31) kept)
@@ 1536  alignment game-tag reverts to workbook wording   <- commit 2 consequence
@@ 1556, 1573, 1609, 1815, 1863, 1932, 2000, 2049, 2080, 2110
         ten projected-section-badge divs lose the PROJECTED MODE span;
         <small> provenance text kept byte-identical (except @@ 1863, the
         dispatched HR badge rewrite)
@@ 1858  HR board tag drops "· Projected Mode ·"
@@ 1927  hits board tag drops "· Projected Mode ·"
```

Nothing else differs. The dispatch estimated ~9 badges; the page carries 10.

### d. CSS block exactly once after two consecutive builds

From the table in (c): `/* PROJECTED MODE CSS START */` count is 1 in `B1`
and still 1 in `B2` (second consecutive build over the first's output). The
banner-empty edge case cannot break this either: with no disclosure the CHROME
markers emit adjacent, and the strip regex
`\n?<!-- PROJECTED CHROME START -->[\s\S]*?<!-- PROJECTED CHROME END -->\s*`
still matches. B1-vs-B2 differ only in the build-stamp meta and the clock —
the same churn A1-vs-A2 shows.

### e. Mobile screenshots, 390px, dark and light

`docs/projected-copy/`: `header-{dark,light}.png` (withheld dropdown present,
no banner text, clean subtitle), `method-{dark,light}.png` (new intro,
methodology card expanded), `hrboard-{dark,light}.png` (badge without the
span, tag without "· Projected Mode ·"). Rendered-DOM checks behind them,
identical in both themes:

```text
subtitle: '12 Games - Day 157'
hr tag  : 'Tap to expand · derived rankings + Savant contact metrics'
hr badge: 'Score and tier are Daily Slate derived from live BallparkPal and Savant inputs.'
visible "projected mode" in innerText: 0    withheld count chip: '2'
overflowX: False    page errors: none
```

## Found, not fixed

- Each build appends two blank lines to `index.html` (A1→A2 grows +2 B,
  B1→B2 grows +2 B, same accretion in the untouched baseline). Pre-existing,
  not introduced or worsened here; noted for a future hygiene pass.
- `build_day46.py:3573` ("…no clean Projected Mode source.") is the last
  source string that could surface the phrase — it renders only inside a
  withheld-board section owned by PR 3b, which is why it was left alone.

## Not done

- No PR opened (dispatch: push branch only).
- sp-vuln-board / matchup-spotlight unavailable-section copy: PR 3b's.
