# SESSION STATUS - Firebase Functions Deploy Automation

Branch: `codex/functions-deploy`

## Summary

Added a dedicated GitHub Actions workflow that deploys Firebase Functions after a merge to `main` changes `functions/**`.

Files:

- `.github/workflows/functions-deploy.yml`
- `docs/FIREBASE_FUNCTIONS_DEPLOY.md`

The workflow deploys only Functions:

```bash
firebase deploy --only functions --project "${{ steps.auth.outputs.project_id }}" --non-interactive
```

No Hosting, Pages, Firestore rules, Storage rules, or other Firebase resources are deployed.

## Secret Setup

Documented in `docs/FIREBASE_FUNCTIONS_DEPLOY.md`.

Create one GitHub Actions repository secret:

- Name: `FIREBASE_FUNCTIONS_DEPLOY_SA`
- Location: GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret
- Value: complete Google Cloud service-account key JSON for the deployer account, preferably minified to one line

Firebase/GCP console setup:

1. Go to the Firebase project's Google Cloud console.
2. IAM & Admin -> Service Accounts.
3. Create `github-functions-deployer`.
4. Grant it:
   - Cloud Functions Admin: `roles/cloudfunctions.admin`
   - Service Account User: `roles/iam.serviceAccountUser` on the function runtime service account(s), usually `PROJECT_NUMBER-compute@developer.gserviceaccount.com` for 2nd gen; also `PROJECT_ID@appspot.gserviceaccount.com` if a 1st gen function exists.
5. Confirm the active Cloud Build service account has Cloud Build Service Account: `roles/cloudbuild.builds.builder`.
6. Create a JSON key for `github-functions-deployer`.
7. Paste the key JSON into the GitHub secret `FIREBASE_FUNCTIONS_DEPLOY_SA`.

Existing Telegram secrets are reused:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

References checked:

- Firebase CLI partial deploy: https://firebase.google.com/docs/cli
- Firebase Functions deploy command: https://firebase.google.com/docs/functions/manage-functions
- Firebase Functions IAM requirements: https://firebase.google.com/docs/projects/iam/permissions
- Cloud Functions IAM deploy requirements: https://docs.cloud.google.com/functions/docs/reference/iam/roles
- Google GitHub auth service-account JSON input: https://github.com/google-github-actions/auth

## Verification

### a. Workflow triggers only on push to main touching functions/**

Workflow trigger:

```yaml
on:
  push:
    branches:
      - main
    paths:
      - 'functions/**'
```

Static check:

```text
has pull_request: False
push main: True
functions path filter: True
only functions deploy: True
telegram failure alert: True
```

### b. Change outside functions/** does not trigger it

The only path filter is:

```yaml
paths:
  - 'functions/**'
```

A docs-only, workflow-only, root-file, workbook, or generated-site change does not match this filter and will not trigger this workflow.

### c. Deploy failure alerts and fails the job

The deploy step has no `continue-on-error`, so a Firebase CLI deploy failure fails the job:

```yaml
- name: Deploy functions only
  run: firebase deploy --only functions --project "${{ steps.auth.outputs.project_id }}" --non-interactive
```

The failure alert follows the existing Telegram pattern:

```yaml
- name: Telegram alert on deploy failure
  if: failure()
  run: |
    curl -s -X POST "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
      -d chat_id="${{ secrets.TELEGRAM_CHAT_ID }}" \
      --data-urlencode text="🚨 Firebase Functions deploy FAILED: ${{ github.workflow }} — https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

### d. Exact setup instructions written down

Setup instructions are committed in `docs/FIREBASE_FUNCTIONS_DEPLOY.md` and summarized above.

### e. Final YAML

```yaml
name: Deploy Firebase Functions

on:
  push:
    branches:
      - main
    paths:
      - 'functions/**'

permissions:
  contents: read

jobs:
  deploy-functions:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'

      - id: auth
        name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v3
        with:
          credentials_json: ${{ secrets.FIREBASE_FUNCTIONS_DEPLOY_SA }}

      - name: Install Firebase CLI
        run: npm install -g firebase-tools

      - name: Deploy functions only
        run: firebase deploy --only functions --project "${{ steps.auth.outputs.project_id }}" --non-interactive

      - name: Telegram alert on deploy failure
        if: failure()
        run: |
          curl -s -X POST "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
            -d chat_id="${{ secrets.TELEGRAM_CHAT_ID }}" \
            --data-urlencode text="🚨 Firebase Functions deploy FAILED: ${{ github.workflow }} — https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

## Checks

```bash
ruby -e "require 'yaml'; YAML.load_file('.github/workflows/functions-deploy.yml'); puts 'functions-deploy YAML OK'"
```

```text
functions-deploy YAML OK
```

```bash
python3 tools/check_bpp_compliance.py
```

```text
BPP compliance OK (0 changed JSON/HTML files checked against f59cf0f23026)
```

```bash
python3 -m py_compile functions/main.py functions/log_retry.py functions/archive_logs.py
```

```text
OK
```

```bash
python3 - <<'PY'
import ast, pathlib
for root in ['.', 'tools', 'backtest', 'functions']:
    for path in pathlib.Path(root).glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('ast.parse OK')
PY
```

```text
ast.parse OK
```

```bash
git diff --check
```

```text
OK
```

## Push Confirmation

Pending until branch is pushed.
