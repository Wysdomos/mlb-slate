# PR Preview Deploys

Branch: `infra/pr-previews`

## Scope

- Added `.github/workflows/preview.yml`.
- Did not modify `daily.yml`, `grade.yml`, `ci.yml`, or any builder.
- Checked `tools/projected_publish_guard.py`: it reads only `DATA_FILE` and does not glob generated output, so no preview exclusion was needed there.
- The preview workflow does not call `extract_xlsx.py`, `fetch_projected_mode.py`, `fetch_bpp_tabs.py`, or any BPP fetch path.

## Workflow Summary

- Triggers on `pull_request` opened, synchronize, reopened, and closed.
- Same-repo PRs only; fork PRs are skipped.
- Concurrency group: `preview-${{ github.event.number }}` with `cancel-in-progress: true`.
- Build job checks out the PR head, copies source to `$RUNNER_TEMP`, uses `origin/main:day_data.json`, and runs `build.py` / `sync.py` with temp output env vars.
- Publishes only to `preview/<sanitized-branch>/` on main.
- Cleanup job deletes only `preview/<sanitized-branch>/` on main.
- Preview URL format: `https://wysdomos.github.io/mlb-slate/preview/<sanitized-branch>/`.
- Existing preview PR comment is updated using marker `<!-- mlb-slate-pr-preview -->`.

## Local Validation

```text
$ /tmp/mlb-preview-yaml-venv/bin/python - <<'PY'
import yaml
from pathlib import Path
path = Path('.github/workflows/preview.yml')
data = yaml.safe_load(path.read_text())
on = data.get('on', data.get(True))
assert on and 'pull_request' in on, on
assert on['pull_request']['types'] == ['opened', 'synchronize', 'reopened', 'closed']
assert data['concurrency']['group'] == 'preview-${{ github.event.number }}'
assert data['concurrency']['cancel-in-progress'] is True
assert set(data['jobs']) == {'build-preview', 'cleanup-preview'}
print('preview.yml yaml ok')
print('pull_request types:', ', '.join(on['pull_request']['types']))
print('permissions:', data['permissions'])
PY
preview.yml yaml ok
pull_request types: opened, synchronize, reopened, closed
permissions: {'contents': 'write', 'pull-requests': 'write'}

$ rg -n "fetch_bpp|fetch_projected|BPP_API_KEY|extract_xlsx" .github/workflows/preview.yml || true
# no output
```

PyYAML was not available in the system Python, so validation used a throwaway venv at `/tmp/mlb-preview-yaml-venv`.

## Smoke PR

Throwaway PR: `https://github.com/Wysdomos/mlb-slate/pull/54`

Preview URL:

```text
https://wysdomos.github.io/mlb-slate/preview/test-pr-preview-smoke/
```

Build run:

```text
PR Preview run 33468213232
build-preview: success in 1m56s
Publish preview to main: pushed on attempt 1
Comment preview URL: updated PR comment
```

Published tree check:

```text
$ git fetch origin main && git ls-tree -r --name-only origin/main preview/test-pr-preview-smoke
preview/test-pr-preview-smoke/apple-touch-icon.png
preview/test-pr-preview-smoke/build-stamp.json
preview/test-pr-preview-smoke/icon-192.png
preview/test-pr-preview-smoke/icon-512.png
preview/test-pr-preview-smoke/icon.svg
preview/test-pr-preview-smoke/index.html
preview/test-pr-preview-smoke/k-report.html
preview/test-pr-preview-smoke/manifest.webmanifest
preview/test-pr-preview-smoke/qr-paypal.png
preview/test-pr-preview-smoke/qr-venmo.png
preview/test-pr-preview-smoke/record.html
preview/test-pr-preview-smoke/streaks.html
```

HTTP check after publish:

```text
HTTP/2 200
content-type: text/html; charset=utf-8
content-length: 312213
```

390px viewport render:

```text
$ npx --yes playwright@latest screenshot --viewport-size=390,844 https://wysdomos.github.io/mlb-slate/preview/test-pr-preview-smoke/ /tmp/pr-preview-390.png
Navigating to https://wysdomos.github.io/mlb-slate/preview/test-pr-preview-smoke/
Capturing screenshot into /tmp/pr-preview-390.png
```

Visual result at 390px: rendered correctly. Header, top chips, accordion blocks, headline cards, and bottom dock were visible with no obvious horizontal overflow.

## Cleanup Verification

The first cleanup smoke run found a real defect: `git rm` staged deletions, then `git add -A "$PREVIEW_PATH"` failed because the removed path no longer existed. Fixed by making the explicit preview-path staging helper tolerate absent paths:

```text
git add -A -- "$PREVIEW_PATH" 2>/dev/null || true
```

Re-run cleanup:

```text
PR Preview run 33468351239
cleanup-preview: success in 9s
Delete preview from main: pushed on attempt 1
cleanup commit on main: b048488
```

Main tree check after cleanup:

```text
$ git fetch origin main && git ls-tree -r --name-only origin/main preview/test-pr-preview-smoke | wc -l
0
```

Important note: immediately after cleanup, GitHub Pages still returned HTTP 200 for the old preview URL because the previous page was cached with `cache-control: max-age=600`. The authoritative GitHub tree has zero files under `preview/test-pr-preview-smoke`, and the cleanup workflow pushed the deletion commit successfully.

## Commits

- `d2ec41c` - Add pull request preview deployment workflow
- `66cd46f` - Harden preview cleanup staging
