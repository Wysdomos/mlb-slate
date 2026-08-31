# PR 1 — Workflow Fix, 8x Daily Cadence, Permanent Theme

Branch: `fix/workflow-8x-daily`

## Required Context Reads

- Read `AGENTS.md`.
- `docs/BPP_REBUILD_SPEC.md` was requested but is not present in the current checkout.

```text
sed: docs/BPP_REBUILD_SPEC.md: No such file or directory
rg --files -g '*BPP*' -g '*REBUILD*' -g '*SPEC*'
# no output
```

## Commits

1. `bbd60e9 Fix daily workflow no-workbook cadence`
2. `3242427 Keep Cordon theme on workbook builds`
3. Report-only commit: `SESSION_STATUS_workflow.md`

The two code files requested by the task were changed in two separate commits. This status file is separate because the task also required it on the branch.

## Commit 1 — `.github/workflows/daily.yml`

Changes:
- Kept push trigger on `**.xlsx`.
- Replaced four cron entries with the exact eight requested entries.
- Added `concurrency` above `permissions`.
- Added `ref: main` to `actions/checkout`.
- Removed the no-workbook `exit 1` trap in `Find slate file`.
- Added the empty-`XLSX_FILE` path in `Extract slate data`.
- Left existing generated-output staging/stash/fail-fast push-loop hardening intact.

PyYAML validation, using `d.get('on', d.get(True))`:

```text
yaml parsed OK
push paths: ['**.xlsx']
cron count: 8
crons: ['0 7 * * *', '0 13 * * *', '0 16 * * *', '0 19 * * *', '0 21 * * *', '0 23 * * *', '0 1 * * *', '0 3 * * *']
concurrency: {'group': 'daily-build', 'cancel-in-progress': False}
checkout ref: main
find contains fallback: True
find no exit trap: True
extract handles empty: True
```

Relevant final YAML:

```yaml
on:
  push:
    paths:
      - '**.xlsx'
  schedule:
    - cron: '0 7 * * *'
    - cron: '0 13 * * *'
    - cron: '0 16 * * *'
    - cron: '0 19 * * *'
    - cron: '0 21 * * *'
    - cron: '0 23 * * *'
    - cron: '0 1 * * *'
    - cron: '0 3 * * *'
  workflow_dispatch:

concurrency:
  group: daily-build
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0

      - name: Find slate file
        env:
          ALLOW_PROJECTED_MODE: '1'
        run: |
          XLSX=$(python3 extract_xlsx.py --which || echo "")
          if [ -z "$XLSX" ]; then echo "No workbook - BPP-only build"; fi
          echo "XLSX_FILE=$XLSX" >> $GITHUB_ENV
          echo "Using newest slate by date: $XLSX"

      - name: Extract slate data
        env:
          ALLOW_PROJECTED_MODE: '1'
        run: |
          if [ -z "$XLSX_FILE" ]; then
            python3 extract_xlsx.py day_data.json
          else
            python3 extract_xlsx.py "$XLSX_FILE" day_data.json
          fi
```

## Commit 2 — `sync.py`

Changes:
- `apply_projected_theme()` now always injects the Cordon CSS block.
- `apply_projected_theme()` now always sets `<body class="projected-mode">`.
- Removed the workbook branch body-class stripping.
- Kept workbook text reversal, so workbook builds still show workbook wording.
- Kept projected banner/withheld disclosure projected-only.

Workbook-mode temp sync evidence:

```text
Done -- wrote 294,786 bytes to /tmp/workflow_workbook_real_index.html
Wrote build stamp -> /tmp/workflow_workbook_real_stamp.json: 2026-08-30|workbook|2026-08-31T14:19:43+00:00

/tmp/workflow_workbook_real_index.html:1295:/* PROJECTED MODE CSS START */
/tmp/workflow_workbook_real_index.html:1608:<body class="projected-mode">
/tmp/workflow_workbook_real_index.html:1913:<div class="game-title">📊 Alignment — Sweet Spot Tier Logic</div>
```

Projected-mode temp sync evidence:

```text
Done -- wrote 277,445 bytes to /tmp/workflow_projected_index.html
Wrote build stamp -> /tmp/workflow_projected_stamp.json: 2026-08-30|projected|2026-08-31T14:19:03+00:00

/tmp/workflow_projected_index.html:1295:/* PROJECTED MODE CSS START */
/tmp/workflow_projected_index.html:1608:<body class="projected-mode">
/tmp/workflow_projected_index.html:1914:<div class="game-title">📊 Projected Mode Alignment</div>
```

## Final Checks

```text
ast.parse OK sync.py
python3 -m py_compile sync.py
python3 -m py_compile build_day46.py sync.py
```

