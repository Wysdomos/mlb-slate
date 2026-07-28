# Firebase Functions Deploy Automation

This repo deploys Cloud Functions automatically only after a merge to `main`
changes `functions/**`.

## GitHub Secret

Create one repository secret:

- Name: `FIREBASE_FUNCTIONS_DEPLOY_SA`
- Where: GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret
- Value: the complete Google Cloud service-account key JSON for the deployer service account. Prefer a minified one-line JSON value.

Existing Telegram secrets are reused for failure alerts:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Service Account

In the Firebase project's Google Cloud console:

1. Go to IAM & Admin -> Service Accounts.
2. Create a service account named `github-functions-deployer`.
3. Grant the deployer service account:
   - Cloud Functions Admin: `roles/cloudfunctions.admin`
   - Service Account User: `roles/iam.serviceAccountUser` on the function runtime service account(s). For this project that is usually the Compute Engine default service account, `PROJECT_NUMBER-compute@developer.gserviceaccount.com`, for Cloud Functions for Firebase 2nd gen. If a 1st gen function is present, also grant it on `PROJECT_ID@appspot.gserviceaccount.com`.
4. Confirm the Cloud Build service account used by the project can build functions. Google documents this as the Cloud Build Service Account role, `roles/cloudbuild.builds.builder`, on the project for the active Cloud Build service account.
5. Create a JSON key for `github-functions-deployer`.
6. Paste that JSON into the GitHub Actions secret named `FIREBASE_FUNCTIONS_DEPLOY_SA`.

Do not add Firebase Hosting, Firestore, Storage, or Pages deploy permissions for this workflow. The workflow command is:

```bash
firebase deploy --only functions --project "$PROJECT_ID" --non-interactive
```

The `--only functions` flag is the guardrail that prevents Hosting, Firestore rules, Storage rules, Pages, or any other Firebase resource from being deployed.
