# THE DAILY SLATE — PROJECT STATUS
**Updated:** July 12, 2026 (post Phase 1 live test)
**Repo:** github.com/Wysdomos/mlb-slate · **Live:** wysdomos.github.io/mlb-slate
*Repo state verified against live main branch at time of writing.*

---

# ✅ COMPLETED

## The Platform (running in production)
- [x] Full automated pipeline: xlsx upload → GitHub Actions → live site in ~5 min
- [x] 4 live pages: index.html (main slate), k-report.html, streaks.html, record.html
- [x] 13-tab daily workbook structure locked (INDEX, HR/Hit/SSJ, BP tabs, Streaks, Results)
- [x] grade_results.py grading prior-day picks → For The Record
- [x] Merge-conflict-proof workflows (git merge -X ours, 5-attempt retry)
- [x] Validated backtest insight: MODERATE+DANGER dual-tag = 15.6% HR rate vs 5.6% STRONG-only

## MacBook M5 Dev Environment
- [x] Homebrew + PATH configured (Apple Silicon)
- [x] node, git, gh CLI installed; gh authenticated (repo/workflow scopes)
- [x] Repo cloned to ~/mlb-slate
- [x] VS Code, Xcode tools
- [x] Claude Code installed + signed in (executed all of Phase 1)
- [x] Codex CLI + Cloud connected to repo + phone dispatch
- [x] Firebase CLI installed + authenticated
- [x] Antigravity installed (not yet pointed at repo)
- [x] Telegram, ChatGPT, Comet apps

## AI Team (operational)
- [x] Roles locked: Claude architect/reviewer · Codex builder · Antigravity heavy-lift/backtest · Perplexity research · Gemini assistant/data · AI Studio payload testing
- [x] Master AI Brief PDF (roles, guardrails, decision matrix)
- [x] Core loop proven live: handoff → Claude Code build → Claude independent review → developer merge
- [x] Firebase self-healer code: 3 review rounds (Gemini) + final rewrite (Claude), all 9 issues fixed

## Self-Healing Pipeline — PHASE 1 LIVE 🚨
- [x] Telegram bot created · Chat ID 1744153296
- [x] GitHub Secrets set: TELEGRAM_BOT_TOKEN (✓ confirmed), TELEGRAM_CHAT_ID
- [x] Telegram failure alert step live on daily.yml AND grade.yml (final step, if: failure())
- [x] functions/main.py (291 lines, byte-verified vs reviewed version) — staged on main
- [x] functions/requirements.txt + firebase.json (python311) — staged on main
- [x] PR #1 squash-merged to main (commit 3ff4db4)
- [x] **LIVE TEST PASSED — phone buzzed** (run 29179455821)

---

# 🔶 IN FLIGHT (minutes of work)

- [ ] **Merge the cleanup PR** — test-alert.yml is still on main; the removal PR
  is open and unmerged. One tap: github.com/Wysdomos/mlb-slate/pulls
- [ ] **git identity** (cosmetic): `git config --global user.name "Wysdomos"` +
  `user.email "you@example.com"` — commits currently show auto-generated identity

---

# 🔲 NEEDS FINISHING

## 1. AGENTS.md ← do before Phase 2
Not on main (verified). The self-healer fetches it to give Gemini project
context — fixes will be materially better with it. Gemini's version never
landed; have Claude write it directly (2 min) and commit.

## 2. Self-Healer PHASE 2 — Firebase deploy (~1 hr total)
**Browser prereqs (phone-friendly, ~15 min):**
- [ ] Firebase console → create project → upgrade to Blaze (card on file)
- [ ] Budget alert: $1 tripwire (alerts notify, don't cap — expected bill $0.00)
- [ ] Gemini API key from aistudio.google.com (free tier)
- [ ] Fine-grained GitHub PAT scoped to mlb-slate: Contents R/W, Pull requests R/W, Actions R

**At the MacBook (~30 min, Claude Code has Phase 2 gated in the handoff):**
- [ ] Verify gemini-2.0-flash-thinking-exp still live (swap model string if rotated)
- [ ] firebase init → set 5 secrets (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
      GEMINI_API_KEY, GITHUB_TOKEN, WEBHOOK_SECRET via openssl rand -hex 32)
- [ ] firebase deploy --only functions (first deploy 5-10 min; say YES to
      container-image cleanup prompt)
- [ ] gh secret set FIREBASE_WEBHOOK_URL + WEBHOOK_SECRET
- [ ] PR: signed HMAC webhook step appended to both workflows → merge
- [ ] Live test: forced Python failure → Gemini diagnoses → auto-heal PR →
      Telegram buzz with PR link

## 3. Antigravity first-open (~5 min, no urgency)
Point it at ~/mlb-slate. Needed before backtesting work starts.

---

# 🎯 AFTER SETUP — THE PRODUCT ROADMAP
*Everything below is "picking winning plays" work. Setup era ends at Phase 2.*

1. **The Odds API** — ODDS_API_KEY secret + fetch_props.py update. Kills the
   balldontlie K-prop gap; opens HR/hit/RBI book lines. (Free 500 req/mo tier)
2. **RBI+ formula** — OO5 board 5-factor composite (base_rbi + hits_traffic +
   K9_suppressor + park_runs + ERA); ≥32% green / 25-31% yellow / <25% dim
3. **Savant expansion** — barrel rate, hard-hit %, xSLG, xERA into
   fetch_phase2.py → smarter pitcher vulnerability
4. **OpenMeteo weather** — free, no key; live wind/temp per park → dynamic HR
   park factors (real edge most tools lack)
5. **Backtesting pipeline** — Antigravity parallel scenarios on
   slate_picks_*.json + results.json; validate MODERATE+DANGER season-scale;
   pybaseball for historical depth
6. **Alt parlay revamp** — K combos T0-2 only, HRR vs high hits-allowed,
   anchors require DANGER label, max 2× same player

---

# STANDING GUARDRAILS (unchanged)
No AI in CI (healer = failure-only exception) · GitHub is single source of
truth · Developer merges everything · Checkpoint before AI tasks · No fake
data · Frozen design tokens · ast.parse after every .py edit
