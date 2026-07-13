# AGENTS.md — The Daily Slate
Automated daily MLB betting analytics. Solo operator (Wysdomos), mobile-first.
Repo = single source of truth. Live: wysdomos.github.io/mlb-slate (GitHub Pages).

## PIPELINE (plain Python — NO AI in CI; Firebase healer fires on failure only)
Upload `MLB Slate M-D-YY.xlsx` → GitHub Actions (daily.yml) →
extract_xlsx.py → fetch_props.py (balldontlie K lines, BDL_KEY) →
fetch_phase2.py (Savant metrics, cache-first) → build.py
(build_day46 → build_streaks → build_editorial → build_k_report) →
sync.py assembles index.html → grade_results.py (grade.yml) → auto-commit.
Pages: index.html, k-report.html, streaks.html, record.html.

## HARD RULES (any AI touching this repo)
1. Never commit to main — review branch + PR; developer merges everything.
2. No fake data. No invented prop lines/projections. Missing data = dash.
3. CSS inside Python f-strings MUST use doubled braces {{ }} — single braces
   crash the build. #1 historical crash source.
4. Edits: `assert OLD in src` before str.replace; ast.parse() after every .py
   change. If assert fails, file drifted — stop, request fresh state.
5. Straight quotes only in .py (no curly “ ” from autocorrect).
6. Design tokens FROZEN: header #0D1B2A · INDEX bar #1B3A5C · T0 green
   #D4EDDA · T1 yellow #FFF3CD · warn red #FDECEA.
7. Team abbrevs canonicalized before lookups: WAS→WSH, SFG→SF. Mismatches
   fail silently.
8. Workbook selection: parse dates from filenames, use NEWEST (never
   alphabetical). BallparkPal files: highest __N_ suffix wins.

## KNOWN FAILURE PATTERNS (for auto-repair)
- KeyError on column names: trailing spaces in workbook headers (e.g.
  '2+ Hits '). Strip/verify before .get().
- player_projections CSVs: EVEN suffix = hit probs (col[4]="1+ Hit"),
  ODD = pitcher proj (col[4]="Earned runs"). Verify col[4] before use.
- MLB Stats API (statsapi.mlb.com, free) or balldontlie endpoint changes:
  wrap fetches, fail loudly, never fabricate fallback data.
- GitHub Actions push conflicts: workflows already use
  `git merge -X ours` + 5-attempt retry — freshly built files win.
- PyYAML parses workflow `on:` as boolean True locally; GitHub parses fine.
- Unicode \uXXXX inside r'''...''' renders literal — use real characters.
- Scout/Best_Spots disk reads can return 0/partial rows (caching) — embed
  from context as StringIO when disk fails. Scout needs FULL 234-270 rows.

## SCORING PHILOSOPHY
Flat scoring until backtests prove weighting. Validated: MODERATE+DANGER
dual-tag batters hit HR at 15.6% vs 5.6% STRONG-only — dual-tag beats raw
projected %. Floor is the hero, not the book line. Honest labels always.

---

## AI TEAM & LANES
| AI | Role | Never does |
|---|---|---|
| Claude (claude.ai Project) | Architect, reviewer, specs, diff review — wins architecture disputes | rapid inline builds, CI |
| Claude Code (M5 terminal) | Local executor: files, git, gh, deploys | merge to main |
| Codex (cloud+CLI) | Primary builder, phone-dispatched PRs | build without a spec |
| Antigravity ($20 tier, M5) | Multi-file refactors, parallel backtests | daily pipeline, exceed tier |
| Perplexity/Comet | Morning research: lineups, injuries, weather | write code |
| Gemini (Google One Pro) | Assistant, big CSV analysis, healer reasoning engine | orchestrate other AIs |
| AI Studio | Large JSON payload testing | production code |

Loop: **Plan (Claude) → Build (Codex/Claude Code) → Review (Claude) → Developer merges.**
Verification checklists mandatory on Gemini deliverables (3-strike history).

## SELF-HEALING PIPELINE
Phase 1 LIVE: Telegram alerts on workflow failure (both workflows, final step,
if: failure(); secrets TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).
Phase 2 staged: functions/main.py = Firebase webhook (HMAC-verified) → fetches
logs (zip-aware) + broken file + this AGENTS.md → Gemini free tier writes fix →
ast.parse gate → auto-heal/<run_id> PR → Telegram. Firebase is a failure
responder ONLY — never a deployment surface. Developer reviews every heal PR.

## DATA SOURCES
Active: balldontlie (BDL_KEY, K props — known gaps), MLB Stats API (free;
schedule/linescore/game logs; probables via
/api/v1/schedule?hydrate=probablePitcher), Baseball Savant (SwStr%, chase),
BallparkPal (4 BP_ tabs), hrtargets.com (HR results authority).
Roadmap: The Odds API (ODDS_API_KEY) → OpenMeteo (free, wind/park factors) →
pybaseball (backtesting).

## FILE MAP
build_day46.py ~1,673 ln (main slate) · build_k_report.py ~1,143 ·
build_streaks.py ~944 · build_editorial.py ~939 · build_record.py ~349 ·
extract_xlsx.py · sync.py · grade_results.py · functions/main.py (healer).
Workbook tabs (13): HR_Leaderboard, Hit_Probabilities, Sweet_Spot_Analyzer,
Sweet_Spot_Slate, Pitcher_Projections, SP_Projections, Park_Factors, Streaks,
HR_Results, BP_Batters, BP_Pitchers, BP_Teams, BP_Games.

*Committed July 12, 2026. Update when architecture changes — every AI reads
this at session start; the self-healer reads the first 3,000 characters.*
