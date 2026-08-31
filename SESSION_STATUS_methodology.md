# SESSION_STATUS — Methodology / Glossary Zone Removal (PR 2, docs slice)

Branch: `docs/methodology-bpp`
Base: `origin/main` at `d50a594` (`Fix/workflow 8x daily (#46)` — spec PR 1 already landed)
Status: pushed, branch only. No PR opened, per dispatch. Not merged.

## Scope

- Commit 1 `ce945d3` — `docs/BPP_REBUILD_SPEC.md`, verbatim copy of the
  architect spec. sha256 of the committed file equals the uploaded file:
  `5056499…677ef3` both sides.
- Commit 2 `75597f8` — `index.html` only. The five dispatched replacements in
  the hand-maintained methodology/glossary/alignment blocks, plus the four
  alignment tbody cells that item 5 conditionally covers.
- Commit 3 (this report + screenshots).

Deliberately not touched: the projected banner and method-intro (sync.py
generated), the projected-section-badges and the HR board `<th>Zone</th>`
(build_day46.py, PR 3), all three `scout.html`/SSJ links (PR 3), every CSS
token, the `.projected-mode` class (17 occurrences before and after), and every
`.py` file. `git diff --name-only` across the branch: `docs/*` and `index.html`
only.

## Deviation from dispatch: three commits, not two

The dispatch asked for two commits and also for this report on the branch. The
report cannot go into commit 1 (verbatim spec, no edits) nor commit 2
("index.html only") without contaminating one of them, so it is a third,
clearly-labelled commit. Both dispatched commits are exactly as specified.

## The one judgment call: HR Prob bands in the alignment tbody

Item 5 said: if the tbody rows carry Zone values, replace with the matching HR
Prob band; do not invent thresholds. The rows did carry Zone bands
(`≥7⚡ / 5–6⚡ / 3–4⚡ / <3`). **No matching HR Prob band exists anywhere in
the repo:**

```text
rg -n "hr_prob|HR Prob" build_day46.py
317:        'hr_prob',                      <- BPP field name in a list
1387:  <thead>...<th>HR Prob</th>...        <- column header
1634:  bpp_pct(c['nm'], 'hr_prob'),         <- shadow-chip input

tier banding in the projected HR board is by Score, not HR Prob:
1357:        if score >= 78: tier = 'row-tier0'
1358:        elif score >= 66: tier = 'row-tier1'

the only hr-prob-shaped thresholds are single consensus votes, not bands:
1614:        if score >= 70: votes += 1
1621:        if bpp_proj_hr >= 0.15: votes += 1
```

So the four cells take the missing-data em dash (`—`) — the same convention
the HR board already renders for Zone, per AGENTS.md rule 2 ("Missing data =
dash"). Nothing was invented. The column is in place with the Vuln column
beside it, ready for PR 3 to fill when `build_vuln.py` lands and real bands are
decided.

Found, not fixed (out of dispatch): the alignment Score bands read
`≥75 / 65–74 / 50–64 / <50`, but the projected HR board tiers at
`score >= 78` (T0) and `>= 66` (T1) in `build_day46.py:1357`. Pre-existing
mismatch, noted for the PR 3/PR 4 copy pass.

## Verification

### a. Five replacements applied, none silently skipped

Every replacement ran behind `assert OLD in src` and `assert count == 1`
(AGENTS.md rule 4); a drifted anchor would have raised, not skipped.

```text
applied 9: ['#1 key-num', '#2 key-item delete', '#3 glossary row',
            '#4 board cell', '#5 thead',
            '#5b T0 zone cell', '#5b T1 zone cell', '#5b T2 zone cell', '#5b SKIP zone cell']
bytes 269,337 -> 269,428  (delta +91)
```

Diff hunks vs `origin/main` — exactly the five dispatched regions:

```text
@@ -1665,7 +1665,7 @@    key-num
@@ -1791,7 +1791,6 @@    key-item delete
@@ -1834,7 +1833,9 @@    glossary row -> 3 rows
@@ -1890,7 +1891,7 @@    Top 25 HR Board cell
@@ -1918,12 +1919,12 @@  alignment thead + tbody cells
```

### b. Re-grep: only the 9 deferred Zone mentions remain

```text
grep -c "Zone\|ZONE" index.html  ->  9 lines, 9 occurrences

  line 1608  DEFERRED  projected-mode banner (sync.py)
  line 1650  DEFERRED  method-intro (sync.py)
  line 1829  DEFERRED  Danger #1-3 glossary row (PR 3 surfaces)
  line 1943  DEFERRED  scout link, headlines (PR 3)
  line 1944  DEFERRED  scout link caption (PR 3)
  line 2254  DEFERRED  projected-section-badge (build_day46, PR 3)
  line 2255  DEFERRED  HR board explainer (build_day46, PR 3)
  line 2257  DEFERRED  HR board <th>Zone</th> (build_day46, PR 3)
  line 2839  DEFERRED  More-sheet scout link (PR 3)

  lines NOT in the deferred list: none
```

Do-not-touch probes, byte-compared against `origin/main`:

```text
  UNTOUCHED  projected-mode banner        UNTOUCHED  scout link (headlines)
  UNTOUCHED  method-intro                 UNTOUCHED  More-sheet scout row
  UNTOUCHED  projected-section-badge      UNTOUCHED  CSS block <style>
  UNTOUCHED  HR board thead
  .projected-mode occurrences: 17 -> 17
```

### c. Mobile screenshots at 390px, dark and light

`docs/methodology-bpp/`: `keynum-{dark,light}.png` (the new "Look for" line),
`glossary-{dark,light}.png` (HR Prob / Barrel% / xwOBA rows),
`alignment-{dark,light}.png` (renamed headers, dashed HR Prob column, Vuln
kept). Rendered DOM checks behind them:

```text
--- dark ---                              --- light ---
key-num: 'Look for: Score 80+,            (identical)
  Barrel 12%+, xwOBA .350+'
Zone key-item: GONE (deleted)
glossary [HR Prob, Barrel%, xwOBA]: [True, True, True]
alignment thead: ['Tier','Score','HR Prob','Vuln','Park','Best Line','Verdict']
overflowX: False                          overflowX: False
page errors: none                         page errors: none
```

### d. All sections present; rail scrollspy works

```text
sections present : 20/20 in both themes
scrollspy        : scroll to #hr-board  -> active chip #hr-board
                   scroll to #conviction -> active chip #conviction
                   works=True (dark and light)
```

Note on the count: the dispatch's gate says 19; the page carries **20**
`<section>` elements (the 18 boards plus `methodology`, `alignment`,
`tip-jar` — the slate gained `tb-board` and the five parlay sections in
Chapters H/K). This diff neither adds nor removes any: 20 before, 20 after,
same ids.

## Not done

- No PR opened (dispatch: push branch only).
- HR Prob band values not filled in — no source to fill them from without
  inventing numbers; see the judgment call above.
- The 9 deferred Zone mentions left exactly as found, for PR 3.

## Addendum — duplicate glossary rows removed; HR Prob column dropped

Review caught a real miss in the first pass: the glossary already carried
xwOBA and Barrel% rows a few lines below my insert, with different thresholds
(`xwOBA ≥ .330 = T3 confirmer`; `Barrel% ≥ 8% = T3 confirmer; ≥12% = elite`).
My two added rows (`12%+ strong / 15%+ elite`, `.350+ strong / .400+ elite`)
were near-duplicates with conflicting numbers. I should have grepped the whole
glossary before inserting, not just the block I was editing.

Amendment commit, `index.html` plus the two re-shot alignment screenshots:

- Deleted the two duplicate rows I added. The pre-existing xwOBA and Barrel%
  rows are untouched; the new HR Prob row stays.
- Removed the HR Prob column from the alignment table entirely — header and
  the four dash cells — rather than leaving a column with no honest values.
  The SKIP row carries a second, pre-existing dash under Best Line, so the
  removal used full-row replacements to take only the third-column cell.

Confirmations (pasted):

```text
applied 7: ['#1a delete dup Barrel% row', '#1b delete dup xwOBA row',
            '#2 thead 7->6', '#2 T0 row', '#2 T1 row', '#2 T2 row', '#2 SKIP row']
  T0/T1/T2/SKIP cells = 6/6/6/6   thead cells = 6
  glossary rows: xwOBA=1 Barrel%=1 HR Prob=1
  page-wide <td><strong> row counts: xwOBA=1 Barrel%=1

rendered, 390px:  head = [Tier, Score, Vuln, Park, Best Line, Verdict]
                  rows = [6, 6, 6, 6]   overflowX = False   (dark and light)
```

This supersedes the earlier (a)/(c) evidence where the glossary showed three
new rows and the alignment table a 7th, dashed column. Zone re-grep is
unaffected: still the same 9 deferred mentions, none of these edits touch them.

## Addendum 2 — stale vendor attributions corrected in the glossary

Seven assert-guarded edits, `index.html` only, source/description text only —
every threshold, number and tier label byte-identical (verified: `80+ T0 row,
70+ T1 row, 60+ floor`, `V≥50 🔥`, `V32–49`, `V&lt;32` all intact):

```text
applied 7: ['Score row', 'SS row delete', 'Vuln row source', 'HR% row',
            '1+ Hit % row', '2+ Hits % row', 'K board row']
bytes 269,102 -> 268,971 (delta -131)
```

The Score row now reads "Daily Slate composite HR score / BallparkPal +
Savant", the SS row is gone, Vuln is sourced to "BallparkPal (ERA, HR/9, park
HR factor, BB rate)", the three probability rows to BallparkPal models, and
the K board row drops "Sweet Spot Ks + ". The two hit rows shared an identical
source cell, so both were anchored on their full row text.

### The check, corrected against reality

The dispatch expected zero "Sweet Spot"/"Dimers" hits outside the SSJ links at
~1940/1941/2882. **Those links contain neither term** — they say "SSJ (The
Zone)". The glossary and every other hand-maintained block are now clean; the
actual remainder is four lines, none resolvable inside this dispatch:

```text
line 1608  banner        sync.py-generated, re-stamped every build; an
                         index.html edit would silently revert on the next run
line 1650  method-intro  same — the source string lives in sync.py (PR 3/4)
line 2252  HR board      build_day46.py-generated section body ("does not
           explainer     reproduce Sweet Spot grades or Zone") — PR 3
line 2691  tip-jar       editorial: "…BallparkPal, Dimers, Sweet Spot data
           pitch         feeds, hosting…" — a factual claim about what the
                         owner pays for; whether Dimers/Sweet Spot are still
                         paid feeds is an owner decision, not a find/replace
```

Reported rather than guessed, per the dispatch. The first three go away when
PR 3/4 touch their generating .py files; the tip-jar line needs a one-word
answer from the owner.

