# Chapter D Discovery: Hybrid BPP Tabs

Date run: 2026-07-25

Scope: discovery only. No Chapter D build code was written.

## Live Pull Evidence

Live BPP payloads were pulled with `BPP_API_KEY` set and cache bypassed using `BppClient(use_cache=False)` plus `force_refresh=True`.

Files written outside the repo:

- `/tmp/chapter_d_live_bpp_2026-07-25/games_2026-07-25.json`
- `/tmp/chapter_d_live_bpp_2026-07-25/projection_averages_824244.json`
- `/tmp/chapter_d_live_bpp_2026-07-25/projection_probabilities_824244.json`
- `/tmp/chapter_d_live_bpp_2026-07-25/parkfactors_2026-07-25.json`
- `/tmp/chapter_d_live_bpp_2026-07-25/parkfactors_hitters_2026-07-25.json`

Top-level structure observed:

- `games(date)`: `data.items[]` with `gameDate`, `gameId`, `gameTime`, `gameTimeFull`, `gameTimeUTC`, `lineupsOfficial`, `teamAwayId`, `teamHomeId`, `venueId`.
- `projection_averages(gameId)`: `data.batters[]`, `data.pitchers[]`, `data.teams[]`, `data.gameId`.
- `projection_probabilities(gameId)`: `data.items[]` with market rows.
- `parkfactors(date)`: `data.items[]` with game-level park factor fields.
- `parkfactors_hitters(date)`: `data.items[]` with player-level hitter park factor split fields.

Raw `projection_probabilities` market entry structure, value-redacted:

```json
{
  "average": "<number-or-null>",
  "displayName": "<string>",
  "line": "<number>",
  "marketKey": "<string>",
  "marketType": "<string>",
  "odds": "<integer>",
  "probability": "<number>",
  "side": "<string>",
  "subject": {
    "id": "<integer>",
    "type": "<string>"
  },
  "teamId": "<integer>"
}
```

## Yes/No Findings

1. Pitcher home-runs-allowed market in `projection_probabilities`?
   - No. The live probability market list includes pitcher walks, strikeouts, earned runs, hits allowed, and outs, but no pitcher home-runs-allowed market.
   - Evidence: `homeRunsAllowed` exists in `projection_averages.data.pitchers[]`; no `projection_probabilities.data.items[]` market name/key corresponds to pitcher home runs allowed.

2. Stolen-base attempt market, distinct from successes?
   - No. The live probability market list includes batter stolen bases, which represents stolen-base successes, not attempts.
   - Evidence: no key containing `attempt` exists in the live payloads; `projection_averages.data.batters[]` contains `stolenBaseSuccesses` only.

3. Exact-count buckets anywhere: `Runs0-20`, `HomeRuns0-5`, `RunsInning1-9`?
   - No.
   - Evidence: no exact-count bucket keys appear in the live payloads. `projection_probabilities` has over/under market rows, not exact bucket distributions.

4. Batter/pitcher handedness in any pulled BPP endpoint?
   - No.
   - Evidence: no `BatterStand`, `PitcherHand`, `Throws`, `batSide`, or `pitchHand` fields appear in the live payload structures.

5. Does summing `projection_averages.batters[]` per team reproduce `BP_Teams` doubles, strikeouts, and walks?
   - Live-only delta is not available from the current repo state.
   - Reason: committed `day_data.json` is a 2026-07-22 workbook, while the required live pull is for 2026-07-25. A same-date comparison requires either a 2026-07-25 workbook `BP_Teams` tab or historical live BPP projection responses for 2026-07-22.
   - Attempted evidence: live `projection_averages(gameId)` for the workbook date returned BPP error: `Historical data is not available. Only today and future dates are served.`
   - Discovery conclusion: because there is no exact team-level doubles/strikeouts/walks field in the live BPP payloads, summing batter rows is at best an approximation and is not schema-parity evidence for replacing `BP_Teams`.

## Coverage Tables

Status meanings:

- `DERIVABLE`: the API exposes an exact field or a deterministic schema-preserving transform.
- `MISSING`: no exact schema-equivalent source exists in the pulled BPP payloads. Approximate starter-sums are not treated as derivable for workbook parity.

### BP_Batters

| Column | Source endpoint + field | Status |
|---|---|---|
| GamePk | `projection_averages.data.gameId` or `games.data.items[].gameId` | DERIVABLE |
| GameDate | `games.data.items[].gameDate` | DERIVABLE |
| GameTime | `games.data.items[].gameTime` | DERIVABLE |
| PlayerId | `projection_averages.data.batters[].playerId` | DERIVABLE |
| FullName | `projection_averages.data.batters[].playerName` | DERIVABLE |
| LastName | derive from `projection_averages.data.batters[].playerName` | DERIVABLE |
| BatterStand | no BPP field | MISSING |
| Side | derive from `projection_averages.data.batters[].teamId` plus `games.data.items[].teamAwayId/teamHomeId` | DERIVABLE |
| Team | `projection_averages.data.batters[].team` | DERIVABLE |
| Opponent | derive opposite team from game teams | DERIVABLE |
| BattingPosition | `projection_averages.data.batters[].battingPosition` | DERIVABLE |
| PlateAppearances | `projection_averages.data.batters[].plateAppearances` | DERIVABLE |
| AtBats | `projection_averages.data.batters[].atBats` | DERIVABLE |
| Hits | `projection_averages.data.batters[].hits` | DERIVABLE |
| Bases | `projection_averages.data.batters[].totalBases` | DERIVABLE |
| Strikeouts | `projection_averages.data.batters[].strikeouts` | DERIVABLE |
| Walks | `projection_averages.data.batters[].walks` | DERIVABLE |
| Singles | `projection_averages.data.batters[].singles` | DERIVABLE |
| Doubles | `projection_averages.data.batters[].doubles` | DERIVABLE |
| Triples | `projection_averages.data.batters[].triples` | DERIVABLE |
| HomeRuns | `projection_averages.data.batters[].homeRuns` | DERIVABLE |
| RBIs | `projection_averages.data.batters[].rbis` | DERIVABLE |
| Runs | `projection_averages.data.batters[].runs` | DERIVABLE |
| StolenBaseAttempts | no BPP field | MISSING |
| StolenBaseSuccesses | `projection_averages.data.batters[].stolenBaseSuccesses` | DERIVABLE |
| PointsDK | `projection_averages.data.batters[].fantasyPointsDK` | DERIVABLE |
| PointsFD | `projection_averages.data.batters[].fantasyPointsFD` | DERIVABLE |
| HomeRunProbability | `projection_probabilities.data.items[]` where market is batter home runs and side is over | DERIVABLE |
| HitProbability | `projection_probabilities.data.items[]` where market is batter hits and side is over | DERIVABLE |
| StolenBaseProbability | `projection_probabilities.data.items[]` where market is batter stolen bases and side is over | DERIVABLE |

### BP_Pitchers

| Column | Source endpoint + field | Status |
|---|---|---|
| GamePk | `projection_averages.data.gameId` or `games.data.items[].gameId` | DERIVABLE |
| GameDate | `games.data.items[].gameDate` | DERIVABLE |
| GameTime | `games.data.items[].gameTime` | DERIVABLE |
| PlayerId | `projection_averages.data.pitchers[].playerId` | DERIVABLE |
| FullName | `projection_averages.data.pitchers[].playerName` | DERIVABLE |
| LastName | derive from `projection_averages.data.pitchers[].playerName` | DERIVABLE |
| PitcherHand | no BPP field | MISSING |
| Side | derive from `projection_averages.data.pitchers[].teamId` plus `games.data.items[].teamAwayId/teamHomeId` | DERIVABLE |
| Team | `projection_averages.data.pitchers[].team` | DERIVABLE |
| Opponent | derive opposite team from game teams | DERIVABLE |
| BattersFaced | `projection_averages.data.pitchers[].battersFaced` | DERIVABLE |
| Innings | `projection_averages.data.pitchers[].innings` | DERIVABLE |
| WinPct | `projection_averages.data.pitchers[].winProbability` | DERIVABLE |
| LossPct | `projection_averages.data.pitchers[].lossProbability` | DERIVABLE |
| NdPct | derive as non-decision remainder from win/loss probabilities | DERIVABLE |
| QualityStart | `projection_averages.data.pitchers[].qualityStartProbability` | DERIVABLE |
| PointsDK | `projection_averages.data.pitchers[].fantasyPointsDK` | DERIVABLE |
| PointsFD | `projection_averages.data.pitchers[].fantasyPointsFD` | DERIVABLE |
| RunsAllowed | `projection_averages.data.pitchers[].runsAllowed` | DERIVABLE |
| HitsAllowed | `projection_averages.data.pitchers[].hitsAllowed` | DERIVABLE |
| Strikeouts | `projection_averages.data.pitchers[].strikeouts` | DERIVABLE |
| Walks | `projection_averages.data.pitchers[].walks` | DERIVABLE |
| HomeRunsAllowed | `projection_averages.data.pitchers[].homeRunsAllowed` | DERIVABLE |
| StolenBasesAllowed | no BPP field | MISSING |

### BP_Teams

| Column | Source endpoint + field | Status |
|---|---|---|
| GamePk | `projection_averages.data.gameId` or `games.data.items[].gameId` | DERIVABLE |
| GameDate | `games.data.items[].gameDate` | DERIVABLE |
| Side | derive from `projection_averages.data.teams[].teamId` plus `games.data.items[].teamAwayId/teamHomeId` | DERIVABLE |
| Team | `projection_averages.data.teams[].team` | DERIVABLE |
| Opponent | derive opposite team from game teams | DERIVABLE |
| Runs | `projection_averages.data.teams[].runs` | DERIVABLE |
| WinPercent | `projection_probabilities.data.items[]` moneyline market | DERIVABLE |
| WinMargin2 | no exact BPP field | MISSING |
| WinMargin3 | no exact BPP field | MISSING |
| LossMargin2 | no exact BPP field | MISSING |
| LossMargin3 | no exact BPP field | MISSING |
| HomeRuns | no exact team-level BPP field; batter sum is approximate | MISSING |
| Triples | no exact team-level BPP field; batter sum is approximate | MISSING |
| Doubles | no exact team-level BPP field; batter sum is approximate | MISSING |
| Singles | no exact team-level BPP field; batter sum is approximate | MISSING |
| Walks | no exact team-level BPP field; batter sum is approximate | MISSING |
| Strikeouts | no exact team-level BPP field; batter sum is approximate | MISSING |
| HomeRuns0 | no exact-count bucket field | MISSING |
| HomeRuns1 | no exact-count bucket field | MISSING |
| HomeRuns2 | no exact-count bucket field | MISSING |
| HomeRuns3 | no exact-count bucket field | MISSING |
| HomeRuns4 | no exact-count bucket field | MISSING |
| HomeRuns5 | no exact-count bucket field | MISSING |
| Runs0 | no exact-count bucket field | MISSING |
| Runs1 | no exact-count bucket field | MISSING |
| Runs2 | no exact-count bucket field | MISSING |
| Runs3 | no exact-count bucket field | MISSING |
| Runs4 | no exact-count bucket field | MISSING |
| Runs5 | no exact-count bucket field | MISSING |
| Runs6 | no exact-count bucket field | MISSING |
| Runs7 | no exact-count bucket field | MISSING |
| Runs8 | no exact-count bucket field | MISSING |
| Runs9 | no exact-count bucket field | MISSING |
| Runs10 | no exact-count bucket field | MISSING |
| Runs11 | no exact-count bucket field | MISSING |
| Runs12 | no exact-count bucket field | MISSING |
| Runs13 | no exact-count bucket field | MISSING |
| Runs14 | no exact-count bucket field | MISSING |
| Runs15 | no exact-count bucket field | MISSING |
| RunsInning1 | no exact inning bucket field | MISSING |
| RunsInning2 | no exact inning bucket field | MISSING |
| RunsInning3 | no exact inning bucket field | MISSING |
| RunsInning4 | no exact inning bucket field | MISSING |
| RunsInning5 | no exact inning bucket field | MISSING |
| RunsInning6 | no exact inning bucket field | MISSING |
| RunsInning7 | no exact inning bucket field | MISSING |
| RunsInning8 | no exact inning bucket field | MISSING |
| RunsInning9 | no exact inning bucket field | MISSING |
| RunsInningExtra | no exact inning bucket field | MISSING |

### BP_Games

| Column | Source endpoint + field | Status |
|---|---|---|
| GamePk | `projection_averages.data.gameId` or `games.data.items[].gameId` | DERIVABLE |
| GameDate | `games.data.items[].gameDate` | DERIVABLE |
| AwayTeam | derive from game away team id and `projection_averages.data.teams[]` | DERIVABLE |
| HomeTeam | derive from game home team id and `projection_averages.data.teams[]` | DERIVABLE |
| RunsAway | `projection_averages.data.teams[].runs` for away team | DERIVABLE |
| RunsHome | `projection_averages.data.teams[].runs` for home team | DERIVABLE |
| AwayWinPct | `projection_probabilities.data.items[]` moneyline market for away team | DERIVABLE |
| HomeWinPct | `projection_probabilities.data.items[]` moneyline market for home team | DERIVABLE |
| AwayWinMargin3 | no exact BPP field | MISSING |
| AwayWinMargin2 | no exact BPP field | MISSING |
| AwayWinMargin1 | no exact BPP field | MISSING |
| HomeWinMargin3 | no exact BPP field | MISSING |
| HomeWinMargin2 | no exact BPP field | MISSING |
| HomeWinMargin1 | no exact BPP field | MISSING |
| RunsFirstInningPct | `projection_probabilities.data.items[]` runs first inning market, over side | DERIVABLE |
| RunsFirst5Away | `projection_averages.data.teams[].runsFirstFive` for away team | DERIVABLE |
| RunsFirst5Home | `projection_averages.data.teams[].runsFirstFive` for home team | DERIVABLE |
| AwayWinFirst5 | `projection_averages.data.teams[].winFirstFiveProbability` for away team | DERIVABLE |
| HomeWinFirst5 | `projection_averages.data.teams[].winFirstFiveProbability` for home team | DERIVABLE |
| Runs0 | no exact-count bucket field | MISSING |
| Runs1 | no exact-count bucket field | MISSING |
| Runs2 | no exact-count bucket field | MISSING |
| Runs3 | no exact-count bucket field | MISSING |
| Runs4 | no exact-count bucket field | MISSING |
| Runs5 | no exact-count bucket field | MISSING |
| Runs6 | no exact-count bucket field | MISSING |
| Runs7 | no exact-count bucket field | MISSING |
| Runs8 | no exact-count bucket field | MISSING |
| Runs9 | no exact-count bucket field | MISSING |
| Runs10 | no exact-count bucket field | MISSING |
| Runs11 | no exact-count bucket field | MISSING |
| Runs12 | no exact-count bucket field | MISSING |
| Runs13 | no exact-count bucket field | MISSING |
| Runs14 | no exact-count bucket field | MISSING |
| Runs15 | no exact-count bucket field | MISSING |
| Runs16 | no exact-count bucket field | MISSING |
| Runs17 | no exact-count bucket field | MISSING |
| Runs18 | no exact-count bucket field | MISSING |
| Runs19 | no exact-count bucket field | MISSING |
| Runs20 | no exact-count bucket field | MISSING |

### Park_Factors

| Column | Source endpoint + field | Status |
|---|---|---|
| Date | request date used for `parkfactors(date)` | DERIVABLE |
| Venue | no venue name field in BPP; `games.data.items[].venueId` is id only | MISSING |
| Game | `parkfactors.data.items[].teamAway/teamHome` | DERIVABLE |
| Time | `parkfactors.data.items[].gameTime` or `games.data.items[].gameTime` | DERIVABLE |
| HR % | `parkfactors.data.items[].homeRunsPercent` | DERIVABLE |
| 2B/3B % | `parkfactors.data.items[].doublesTriplesPercent` | DERIVABLE |
| 1B % | `parkfactors.data.items[].singlesPercent` | DERIVABLE |
| Runs % | `parkfactors.data.items[].runsPercent` | DERIVABLE |
| HR % Stadium | no venue-level stadium split field | MISSING |
| 2B/3B % Stadium | no venue-level stadium split field | MISSING |
| Runs % Stadium | no venue-level stadium split field | MISSING |
| HR % Weather | no venue-level weather split field | MISSING |
| 2B/3B % Weather | no venue-level weather split field | MISSING |
| Runs % Weather | no venue-level weather split field | MISSING |

### SP_Projections

| Column | Source endpoint + field | Status |
|---|---|---|
| Team | `projection_averages.data.pitchers[].team` where `isStarter` | DERIVABLE |
| Pitcher | `projection_averages.data.pitchers[].playerName` where `isStarter` | DERIVABLE |
| Throws | no BPP field | MISSING |
| Opp | derive opposite team from game teams | DERIVABLE |
| Inn | `projection_averages.data.pitchers[].innings` where `isStarter` | DERIVABLE |
| BF | `projection_averages.data.pitchers[].battersFaced` where `isStarter` | DERIVABLE |
| R | `projection_averages.data.pitchers[].runsAllowed` where `isStarter` | DERIVABLE |
| H | `projection_averages.data.pitchers[].hitsAllowed` where `isStarter` | DERIVABLE |
| HR | `projection_averages.data.pitchers[].homeRunsAllowed` where `isStarter` | DERIVABLE |
| K | `projection_averages.data.pitchers[].strikeouts` where `isStarter` | DERIVABLE |
| BB | `projection_averages.data.pitchers[].walks` where `isStarter` | DERIVABLE |

## Merge Gate Implication

The API can support a hybrid override for a subset of tabs, but it does not pass full replacement parity for all six BPP workbook tabs.

Safe exact candidates from these payloads:

- `SP_Projections` except `Throws`, which needs an external handedness source.
- Consumed `Park_Factors` fields except `Venue` if a separate venue lookup is allowed.
- Most player projection fields in `BP_Batters` and `BP_Pitchers`, excluding handedness, stolen-base attempts, and pitcher stolen bases allowed.

Do not replace from BPP alone:

- `BP_Teams`: exact team-level doubles, strikeouts, walks, and exact-count buckets are missing.
- `BP_Games`: exact run distribution buckets and win margin buckets are missing.
