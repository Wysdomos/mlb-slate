# Session Report Standard

How a builder writes up a piece of work in this repo.

This is not a new format. It is the format the reports on `main` already use,
written down so it stops being folklore. It was derived by reading the ten
`SESSION_STATUS_*.md` files on `main` as of 2026-07-28 — Chapters H, K, L, M,
the render fix, the build stamp, the two healer reports, the satellite removal
and the parlay scoreboard.

---

## The one rule that is not negotiable

**Write to `SESSION_STATUS_<topic>.md`. Never to the shared `SESSION_STATUS.md`.**

Concurrent branches all writing the same `SESSION_STATUS.md` produced merge
conflicts in a file that carries no code, and blocked two PRs until someone
hand-resolved a document nobody needed to merge. One file per topic, named for
the work:

```text
SESSION_STATUS_chapter_h.md
SESSION_STATUS_render_fix.md
SESSION_STATUS_healer_initial_delay.md
```

Pick the topic slug from the branch name. If your branch is
`codex/chapter-n-widgets`, the report is `SESSION_STATUS_chapter_n.md`. Two
builders should never be able to collide.

---

## Structure

### 1. Title and header block

```markdown
# SESSION_STATUS — Chapter H Market Expansion

Branch: `codex/chapter-h-markets`
Base: `origin/main` at `d6115cc`
Status: implemented, verified, pushed as draft PR.
```

Base is a **commit SHA**, not "main". Reviewers need to know which main you
built on, because main moves under you. State PR status plainly — draft, do not
merge, merged, whatever is true.

### 2. Scope — what changed, and what deliberately did not

`## Scope` or `## Summary`. A short list of what the branch does. Then, just as
importantly, what it does **not** touch. Real examples from the repo:

```text
No parlay selection thresholds, nesting rules, forbidden markets, pitcher-side
rules, or grading data were changed.

Thresholds and consensus counts were intentionally left unchanged pending
calibration review.
```

If you considered something and rejected it, say so and say why. A reviewer
cannot tell "decided against" from "forgot" unless you write it down.

`## Ordered commits` is worth adding when the branch has more than a couple of
commits and the order matters for review.

### 3. Root cause — when you are fixing a defect

`## Root Cause: <thing>`. Required for any bug fix. Show the evidence that
identifies the cause, not just the symptom. From `SESSION_STATUS_render_fix.md`:

```text
`oo5-board` was not removed by `sync.py` directly. It disappeared in merge commit:

2e437ab Merge remote-tracking branch 'origin/main'
Parents: f68d884 0fcabdb

Both parents still contained <section id="oo5-board">:
```

That is a root cause. "The board was missing so I added it back" is not.

### 4. Verification — lettered, and matching the dispatch

`## Verification`, then one `### a.`, `### b.`, `### c.` per item, **using the
same letters the dispatch used**. If the brief asked for a–j, the report has
a–j in that order. A reviewer should be able to read the two side by side
without mapping anything.

Each item pastes the command and its real output:

````markdown
### a. 2B/SB absent from rendered HTML; still emitted

Command:

```bash
python3 -c "import json, collections; ..."
```

Output:

```text
rendered id=sb-board False
nav href #sb-board False
shadow SB picks 41
```
````

**Paste output. Do not assert.** "Verified byte-identical" is worth nothing;
the sha256 of both files is worth something. If a check produced a number, the
number goes in the report. This is the single biggest difference between a
report that can be trusted and one that cannot.

If a check failed, or passed only after you fixed something, that belongs in
the report too. A verification section where everything passed first try is
usually a verification section that did not look very hard.

### 5. Anything not shipped

State it explicitly, with the reason. Also state anything you found but did not
fix, and why it was out of scope — a defect you noticed and silently left is a
defect the next person rediscovers from scratch.

`## Historical-file safety` is the established heading when the point is that
committed pick/grade JSON was left alone.

### 6. Addenda

If something turns up after the main write-up, append `## Addendum — <thing>`
rather than editing the earlier sections. The report is a record of what
happened, in the order it happened.

---

## Conventions worth keeping

- Backtick every filename, branch, commit SHA, and identifier.
- Fence command blocks as ` ```bash ` and output blocks as ` ```text `.
- Quote real values — sizes, sha256s, row counts, pixel measurements, timings.
- When a measurement needs a caveat to be honest, give it the caveat. If a
  value was produced under simulation rather than on device, say so.
- Keep the prose plain. This is a record for whoever picks the work up next,
  which is often the same person three weeks later.

## Checklist before pushing

- [ ] File is `SESSION_STATUS_<topic>.md`, not `SESSION_STATUS.md`
- [ ] Branch, base commit SHA and PR status at the top
- [ ] Scope says what changed **and** what deliberately did not
- [ ] Root cause section present if this is a fix
- [ ] Verification letters match the dispatch letters, in order
- [ ] Every verification item pastes real output
- [ ] Anything not shipped, or found-but-not-fixed, is stated with a reason
