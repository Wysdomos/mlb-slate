#!/usr/bin/env python3
"""
build_scout.py  --  generates docs/scout.html  (SSJ: The Zone ⚡)
Called by build.py after build_day46 and build_editorial.
Reads same globals as build_editorial.py.
"""
import json, os, re

HR_LB = []; SP_PROJ = []; SS_BY_NAME = {}; BP_BAT = []; GAMES = []
TODAY_STR = ""; DAY_NUM = ""
_SSA = []; _SCOUT = []; _STREAKS = []

def set_data(hr_lb, sp_proj, ss_by_name, bp_bat, games, today_str, day_num="", ssa=None, scout=None, streaks=None):
    global HR_LB, SP_PROJ, SS_BY_NAME, BP_BAT, GAMES, TODAY_STR, DAY_NUM, _SSA, _SCOUT, _STREAKS
    HR_LB, SP_PROJ, SS_BY_NAME = hr_lb, sp_proj, ss_by_name
    BP_BAT, GAMES = bp_bat, games
    TODAY_STR = today_str; DAY_NUM = day_num
    _SSA = ssa or []; _SCOUT = scout or []; _STREAKS = streaks or []

# ── helpers ───────────────────────────────────────────────────────────
def tn(t):
    if not t: return ""
    M = {"WAS":"WSH","SFG":"SF","SDP":"SD","KCR":"KC","TBR":"TB","ARI":"AZ","ATH":"OAK","CHW":"CWS"}
    return M.get(str(t).strip().upper(), str(t).strip().upper())

def parse_zone(z):
    if not z: return 0
    m = re.search(r'\d+', str(z))
    return int(m.group()) if m else 0

def _vuln(pitcher):
    row = SS_BY_NAME.get((pitcher or "").strip().lower())
    if row:
        try: return int(row.get("VulnScore") or 0)
        except: pass
    sp = next((r for r in SP_PROJ if (r.get("Pitcher","") or "").strip().lower()
               == (pitcher or "").strip().lower()), None)
    if sp:
        try:
            era = float(sp.get("ERA") or sp.get("SS ERA") or 4.5)
            hr9 = float(sp.get("HR") or 0.8); k = float(sp.get("K") or 4.0)
            return max(0, min(100, int(era/7.5*40 + hr9/1.5*35 - k/8.0*25 + 25)))
        except: pass
    return 45

def _proj_hits(pitcher):
    sp = next((r for r in SP_PROJ if (r.get("Pitcher","") or "").strip().lower()
               == (pitcher or "").strip().lower()), None)
    if sp:
        try: return round(4.0 + (float(sp.get("ERA") or sp.get("SS ERA") or 4.5)/9.0)*5.5, 1)
        except: pass
    return 7.0

def _proj_era(pitcher):
    sp = next((r for r in SP_PROJ if (r.get("Pitcher","") or "").strip().lower()
               == (pitcher or "").strip().lower()), None)
    if sp:
        try: return round(float(sp.get("ERA") or sp.get("SS ERA") or 4.0), 2)
        except: pass
    return 4.00

def _pitcher_team(pitcher):
    sp = next((r for r in SP_PROJ if (r.get("Pitcher","") or "").strip().lower()
               == (pitcher or "").strip().lower()), None)
    return tn(sp.get("Team","")) if sp else ""

def _throws(pitcher):
    sp = next((r for r in SP_PROJ if (r.get("Pitcher","") or "").strip().lower()
               == (pitcher or "").strip().lower()), None)
    if sp:
        t = sp.get("Throws") or sp.get("Hand") or ""
        if t: return str(t).upper()[:1]
    return "R"

def _bats(batter, row):
    b = row.get("Bats") or row.get("Hand") or ""
    if b: return str(b).upper()[:1]
    bp = next((r for r in BP_BAT if
               (r.get("Name","") or r.get("FullName","") or "").strip().lower()
               == (batter or "").strip().lower()), None)
    if bp:
        b2 = bp.get("Bats") or bp.get("BatHand") or ""
        if b2: return str(b2).upper()[:1]
    return "R"

def _ssj(p):
    try: iso = float(p.get("iso","0") or 0)
    except: iso = 0
    try: woba = float(p.get("woba","0") or 0)
    except: woba = 0
    z = int(p.get("zone",0) or 0); hr = int(p.get("hr",0) or 0)
    vs = int(p.get("vulnScore",50) or 50); g = p.get("grade","")
    s  = z*3 + (vs/100)*20 + iso*30 + woba*20 + hr*0.2
    if vs >= 70: s += 12
    if g == "STRONG": s += 10
    elif g == "MODERATE": s += 4
    return round(s*1000)

# ── build ────────────────────────────────────────────────────────────

# ── Live streak fetch (MLB Stats API) ────────────────────────────────
def _fetch_live_streaks():
    """
    Pulls the last 8 days of box scores from the MLB Stats API and
    computes Hit streak, HR streak, and HRR streak for every batter.
    Returns dict: {batter_name_lower: {hitStreak, hrStreak, hrrStreak}}
    Falls back silently to empty dict on any network error.
    """
    import urllib.request, json
    from datetime import datetime, timedelta

    today = datetime.utcnow().date()
    start = today - timedelta(days=8)

    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&startDate={start}&endDate={today}"
        "&hydrate=boxscore(fields(teams,players,stats,person,atBats,hits,homeRuns,runs,rbi))"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DailySlate/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        print(f"[scout] streak API unavailable: {e}")
        return {}

    # player_games[name_lower] = [(date_str, hits, hrs, runs, rbi), ...]
    player_games = {}

    for date_obj in data.get("dates", []):
        date_str = date_obj.get("date", "")
        for game in date_obj.get("games", []):
            # Only use Final / completed games
            status = (game.get("status") or {}).get("codedGameState", "")
            if status not in ("F", "O", "C", "TR"):
                continue
            boxscore = game.get("boxscore") or {}
            for side in ("home", "away"):
                team_data = (boxscore.get("teams") or {}).get(side) or {}
                for pid, pdata in (team_data.get("players") or {}).items():
                    full_name = ((pdata.get("person") or {}).get("fullName") or "").strip()
                    if not full_name:
                        continue
                    batting = (pdata.get("stats") or {}).get("batting") or {}
                    ab   = int(batting.get("atBats")    or 0)
                    hits = int(batting.get("hits")      or 0)
                    hrs  = int(batting.get("homeRuns")  or 0)
                    runs = int(batting.get("runs")      or 0)
                    rbi  = int(batting.get("rbi")       or 0)
                    # Skip non-batters / did-not-play entries
                    if ab == 0 and hits == 0 and hrs == 0 and runs == 0:
                        continue
                    key = full_name.lower()
                    if key not in player_games:
                        player_games[key] = []
                    player_games[key].append((date_str, hits, hrs, runs, rbi))

    # Sort each player oldest→newest, then streak from end
    result = {}
    for key, games in player_games.items():
        games.sort(key=lambda x: x[0])
        rev = list(reversed(games))
        hit_s = hr_s = hrr_s = 0
        for g in rev:
            if g[1] >= 1: hit_s += 1
            else: break
        for g in rev:
            if g[2] >= 1: hr_s += 1
            else: break
        for g in rev:
            if g[1] >= 1 and g[3] >= 1 and g[4] >= 1: hrr_s += 1
            else: break
        if hit_s or hr_s or hrr_s:
            result[key] = {"hitStreak": hit_s, "hrStreak": hr_s, "hrrStreak": hrr_s}

    active = sum(1 for v in result.values() if any(v.values()))
    print(f"[scout] live streaks: {active} active players ({len(result)} with data)")
    return result

def build():
    # Live streaks from MLB Stats API (8-day lookback)
    _live_streaks = _fetch_live_streaks()

    # Workbook Streaks tab fallback (fields: 'Hit Streak', 'HR Streak')
    _streak_lu = {}
    for _sr in _STREAKS:
        _nm = (_sr.get('Batter') or '').strip().lower()
        if _nm: _streak_lu[_nm] = _sr

    # Scout tab: ISO/wOBA lookup (filter out placeholder rows where ISO >= 0.40)
    _scout_lu = {}
    for _sr in _SCOUT:
        _nm = (_sr.get('Batter') or '').strip().lower()
        _iso_v = _sr.get('ISO'); _wb_v = _sr.get('wOBA')
        try:
            if _nm and _iso_v is not None and float(_iso_v) < 0.40:
                _scout_lu[_nm] = {'iso': round(float(_iso_v),3),
                                  'woba': round(float(_wb_v),3) if _wb_v else None}
        except: pass

    # SSA: pitcher Throws lookup by batter name
    _throws_lu = {}
    for _ar in _SSA:
        _nm = (_ar.get('Batter') or '').strip().lower()
        _th = _ar.get('Throws')
        if _nm and _th: _throws_lu[_nm] = str(_th).upper()[:1]

    players = []; seen = set()
    for r in HR_LB:
        grade = (r.get("Grade") or "").strip().upper()
        if grade not in ("STRONG","MODERATE","BAD"): continue
        batter = (r.get("Batter") or "").strip()
        if not batter or batter in seen: continue
        seen.add(batter)
        pitcher = (r.get("Pitcher") or "").strip()
        team    = tn(r.get("Team",""))
        vs  = _vuln(pitcher); ph = _proj_hits(pitcher); pe = _proj_era(pitcher)
        pt  = _pitcher_team(pitcher) or tn(
              r.get("Pitcher Team","") or r.get("OppTeam","") or r.get("Opp","") or "")
        try:
            era_raw = r.get("ERA") or ""
            era_s   = str(round(float(era_raw),2)) if era_raw and era_raw not in ("--","—","") else "—"
        except: era_s = str(r.get("ERA","—"))
        p = dict(
            batter=batter, team=team,
            bats=_bats(batter,r), throws=_throws_lu.get(batter.lower()) or _throws(pitcher),
            pitcher=pitcher, pTeam=pt, era=era_s,
            iso=str(_scout_lu.get(batter.lower(),{}).get('iso') or '—'),
            woba=str(_scout_lu.get(batter.lower(),{}).get('woba') or r.get("xwOBA","—") or '—'),
            hr=int(r.get("HR") or 0), grade=grade,
            zone=parse_zone(r.get("Zone","")),
            hitStreak=int(_live_streaks.get(batter.lower(), {}).get('hitStreak')
                         or (_streak_lu.get(batter.lower()) or {}).get('Hit Streak')
                         or r.get('hitStreak') or r.get('HitStreak') or 0),
            hrStreak =int(_live_streaks.get(batter.lower(), {}).get('hrStreak')
                         or (_streak_lu.get(batter.lower()) or {}).get('HR Streak')
                         or r.get('hrStreak') or r.get('HRStreak') or 0),
            hrrStreak=int(_live_streaks.get(batter.lower(), {}).get('hrrStreak')
                         or r.get('hrrStreak') or r.get('HRRStreak') or 0),
            vulnScore=vs, projHits=ph, projERA=pe,
        )
        p["ssjScore"] = _ssj(p)
        players.append(p)

    players.sort(key=lambda p: -p["ssjScore"])
    counts = {
        "STRONG":   sum(1 for p in players if p["grade"]=="STRONG"),
        "MODERATE": sum(1 for p in players if p["grade"]=="MODERATE"),
        "BAD":      sum(1 for p in players if p["grade"]=="BAD"),
        "ALL":      len(players),
    }
    html = _html(json.dumps(players, ensure_ascii=False),
                 json.dumps(counts,  ensure_ascii=False), TODAY_STR)
    out  = "scout.html"  # write to repo root, same as index.html / k-report.html / streaks.html
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"build_scout: wrote scout.html  ({len(players)} players, "
          f"{counts['STRONG']} SSJ / {counts['MODERATE']} BASE / {counts['BAD']} BAD)")

# ── HTML ──────────────────────────────────────────────────────────────
def _html(data_json, counts_json, today_str):
    GLOS = json.dumps([
      {"title":"WHAT IS SSJ (THE ZONE)?","entries":[
        {"term":"The Concept","def":"SSJ (The Zone) is matchup intelligence. Every batter on today's slate is scored against their specific pitcher and ranked from strongest to weakest matchup. Think of it as going Super Saiyan — when the conditions align perfectly, a batter enters a different power level."},
        {"term":"What It Is NOT","def":"SSJ is not a straight stat lookup. It weights Zone score, pitcher vulnerability, ISO power, wOBA, platoon advantage, and active streaks into a single composite ranking. A high-average hitter facing a soft-tossing lefty will score differently than a power hitter facing the same pitcher."},
        {"term":"How To Use It Daily","def":"Start with the OVER NINE THOUSAND section — top 5 plays of the day. Then check the SSJ MATCHUPS tab ranked list for the full ordered board. Filter by DANGER ONLY to find the highest-exploitation matchups. Cross-reference with the main Slate's Conviction Board for double-signal plays."},
      ]},
      {"title":"THE GRADES — YOUR POWER CLASS","entries":[
        {"term":"SUPER SAIYAN — Elite Tier","def":"All factors align: high Zone score, strong ISO and wOBA, facing a vulnerable or struggling pitcher, often with platoon advantage. These are the day's primary targets. A SUPER SAIYAN play with a DANGER tag is the strongest single-play signal on the board."},
        {"term":"BASE FORM — Solid Tier","def":"Decent matchup but one or two factors are working against the play — a tough pitcher, a suppressor park, weak streak, or marginal platoon. Still worth including in combos or as supporting legs. Not the anchor, but a valid contributor."},
        {"term":"YAMCHA — Fade Tier","def":"Named after the Dragon Ball Z character who famously loses every fight. These matchups have one or more significant negatives — a dominant pitcher, bad park factor for HRs, or unfavorable platoon. Listed for transparency and as fade targets. If you see a YAMCHA play getting heavy betting action, that's a fade signal, not a tail."},
        {"term":"How Grades Are Set","def":"Grades come from the Sweet Spot Analyzer in the workbook — a multi-factor model combining ISO, wOBA, Zone matchup score, park HR factor, and pitcher grade. Grades are locked at build time and do not change intraday. Check back the next build for updates."},
      ]},
      {"title":"THE ZONE BADGE \u26a1N","entries":[
        {"term":"What the Number Means","def":"The Zone badge score is a composite matchup grade from the best-spots model. It combines ISO, wOBA, home run output, pitcher vulnerability, and platoon advantage into a single integer. Higher is better. A Zone 11 batter has a significantly stronger matchup profile than a Zone 4."},
        {"term":"Zone 10+ — FEATURED PLAYS","def":"Any Zone score of 10 or higher is elevated to the Featured Plays section at the top of the current grade tab. These are the elite matchups of the day within each grade tier. Start here before scrolling the full board."},
        {"term":"Gold Glow \u26a1","def":"A Zone badge with gold glow animation means the batter is STRONG grade and Zone 10+. Maximum matchup quality — prioritize these."},
        {"term":"Fire Badge \U0001f525","def":"When a batter has an active hot streak (Hit streak 4+ games, HR streak 2+ games, or HRR streak 3+ games), the badge switches from gold glow to orange fire pulse. The \U0001f525 icon also appears on the badge itself. Streaks compound the matchup quality signal."},
      ]},
      {"title":"DANGER TAG \u26a0","entries":[
        {"term":"What DANGER Means","def":"The opposing pitcher has a Vulnerability Score of 70 or higher — meaning they are highly exploitable today based on ERA trend, HR/9 rate, park factors, and matchup history. DANGER is the single most actionable signal on the board."},
        {"term":"STRONG + DANGER = Top Priority","def":"A STRONG-grade batter with a DANGER-tagged pitcher is the strongest signal combination. Backtesting shows MODERATE + DANGER also outperforms STRONG-only on HR rate (exploitable pitcher matters more than batter tier in many matchups)."},
        {"term":"Red Indicators \U0001f534","def":"If PROJ H shows 8.0+ or PROJ ERA shows 5.50+, a red dot appears next to the value. Both lit simultaneously means the pitcher is in full meltdown projection for this start. These are the most exploitable starts on the board."},
        {"term":"VulnScore 50-69 (Gold)","def":"Caution zone — the pitcher is hittable but not in meltdown territory. Worth considering especially when combined with strong batter metrics. No DANGER tag but still above average exploitation potential."},
        {"term":"VulnScore Under 50 (Dim)","def":"The pitcher is in reasonable control. Matchup is still tracked but exploitation upside is limited. Weight the batter's own metrics more heavily in these matchups."},
      ]},
      {"title":"PITCHER PROJECTIONS","entries":[
        {"term":"VULN — Vulnerability Score (0 to 100)","def":"Our internal pitcher exploitation grade computed from ERA trend, HR/9 rate, park HR factor, and walk rate. 70+ triggers the DANGER tag (red). 50-69 = elevated risk (gold). Under 50 = manageable (dim). Built from the Sweet Spot Slate tab in the workbook."},
        {"term":"PROJ H — Projected Hits Allowed","def":"Estimated hits allowed for today's start based on ERA and BF projections. Shows in red when 8.0 or higher. At that level, the pitcher is expected to be consistently hittable — every batter in the lineup benefits."},
        {"term":"PROJ ERA — Projected ERA","def":"Expected ERA for this start. Shows in red when 5.50 or higher. Combined with PROJ H red — both lit at once means this is one of the most attackable starts on the entire slate. Target the batter's whole combo board, not just HR."},
        {"term":"ERA (Card Sub-line)","def":"The season ERA shown next to the pitcher's name in each card. This is the raw season figure from the workbook. PROJ ERA is the model's day-specific forecast, which can differ significantly from the season number based on current form."},
      ]},
      {"title":"BATTER STATS","entries":[
        {"term":"ISO — Isolated Power","def":"Slugging percentage minus batting average. Strips out singles and measures pure extra-base power. The most direct predictor of HR output in the model. ISO above .250 is elite. Above .300 is rare and is the strongest single-stat HR signal available."},
        {"term":"wOBA — Weighted On-Base Average","def":"The most complete single-number offensive metric. Weights singles, doubles, triples, HRs, and walks by their actual run value. An elite wOBA (.400+) combined with high ISO means a batter is both powerful and consistently dangerous. Source: Scout tab in the workbook."},
        {"term":"HR — Season Home Runs","def":"The batter's total home runs on the year. Context for their current power output ceiling. A player at 20+ HRs in June is in a different risk profile than someone at 5. The model uses this alongside ISO to weight HR probability."},
      ]},
      {"title":"STREAKS — MOMENTUM FLAGS","entries":[
        {"term":"HIT — Hit Streak","def":"Consecutive games with at least one hit. Active at any length, highlighted in gold when it reaches 4 or more games. A long hit streak increases the probability of continued contact. \U0001f525 fire appears at 4+ games."},
        {"term":"HR — Home Run Streak","def":"Consecutive games with at least one home run. \u26a1 activates at 2+ consecutive games. A player on a 2-game HR streak is in confirmed power form. A 3-game HR streak is extremely rare and significantly increases today's probability."},
        {"term":"HRR — Hits + Runs + RBIs Streak","def":"Tracks whether a batter recorded at least one Hit AND one Run AND one RBI in the same game. All three must occur in the same game for the game to count toward the streak. Active at 3+ consecutive games. A player maintaining an HRR streak is contributing across all three offensive categories — the most complete signal of elite performance."},
        {"term":"Dash ( \u2014 )","def":"No active streak. This is neutral, not negative. Many elite plays have no streak because streaks are rare. The absence of a streak does not reduce the matchup quality grade."},
        {"term":"Streak Stacking","def":"When a player has multiple active streaks (e.g., hit streak 6 games AND HR streak 2 games), their Zone badge glows fire orange and \U0001f525 appears. The SSJ composite score also receives a bonus for each active streak. Stack signals are the highest-conviction plays."},
      ]},
      {"title":"PLATOON ADVANTAGE","entries":[
        {"term":"What Platoon Means","def":"Batters historically perform significantly better against pitchers throwing from the opposite hand. A left-handed batter vs a right-handed pitcher (L\u2192R) has a statistically measurable edge in batting average, slugging, and home run rate."},
        {"term":"L\u2192R or R\u2192L with \u26a1 (Gold)","def":"Confirmed platoon advantage. The batter faces the opposite-hand pitcher. Shows gold with \u26a1 symbol. This is a meaningful edge — especially in power matchups. It compounds Zone score and pitcher vulnerability."},
        {"term":"L\u2192L or R\u2192R (Dimmed)","def":"Same-hand matchup. No platoon advantage. The platoon edge is removed from the scoring. The play can still be valid on other factors, but one signal is missing."},
        {"term":"S\u2192R or S\u2192L with \u26a1 (Always Gold)","def":"Switch hitters always bat from the favorable side regardless of pitcher hand. Always treated as a confirmed platoon advantage. Switch hitters facing any pitcher always get the \u26a1 platoon tag."},
      ]},
      {"title":"WHAT?! IT'S OVER NINE THOUSAAAAAND!!","entries":[
        {"term":"What It Is","def":"The five highest-ranked plays of the day by composite SSJ Score, pinned at the top above all other content on every main grade tab. These are the absolute highest-conviction plays on today's slate. Named after the famous Dragon Ball Z scene where Vegeta's scouter explodes reading Goku's power level."},
        {"term":"How It's Ranked","def":"SSJ Score = (Zone \u00d7 3) + (VulnScore / 100 \u00d7 20) + (ISO \u00d7 30) + (wOBA \u00d7 20) + (HR \u00d7 0.2) + streak bonuses + DANGER/grade bonuses. The top 5 by this score appear in the horizontal scroll strip."},
        {"term":"How To Use It","def":"Swipe right to see all 5 cards. Each shows Zone, grade, DANGER, streaks, ISO, wOBA, and platoon at a glance. These are your daily anchors. If you only play 2 picks today, start here. Cross-reference with the Conviction Board on the main Slate."},
        {"term":"Why Only 5?","def":"Five is intentional. Giving you 20 elite plays dilutes the signal. Five forces ranking and prioritization. On a 15-game slate, 5 truly elite matchups is a generous count. If all 5 are STRONG + DANGER, that's a rare convergence worth noting."},
      ]},
      {"title":"THE TABS — ROW 1 (GRADE FILTERS)","entries":[
        {"term":"\u26a1 SUPER SAIYAN","def":"Shows only STRONG-grade matchups. These are the elite plays of the day. Default view when you open SSJ. Start here every session."},
        {"term":"BASE FORM","def":"Shows only MODERATE-grade matchups. Solid supporting plays. Use for combo legs, backup plays when Super Saiyan count is low, or when a MODERATE play has a DANGER tag and strong ISO."},
        {"term":"YAMCHA","def":"Shows only WEAK-grade matchups — the Yamcha plays. Good for identifying fade targets. If you see heavy sharp money on a YAMCHA play, that is a counter-signal. Also useful for identifying which pitchers are truly elite today."},
        {"term":"ALL (N)","def":"Shows all matchups across all grades with no filter. The number in parentheses is the total count for the day. Use this for a full slate overview or when researching a specific batter across grade lines."},
      ]},
      {"title":"THE TABS — ROW 2 (DBZ SPECIALS)","entries":[
        {"term":"\U0001f31f SSJ MATCHUPS","def":"The full ranked list sorted by composite SSJ Score — the definitive ordered board for the day. Top 50 shown. Apply DANGER ONLY or PLATOON ADV ONLY filters here for the tightest signal stack. Rank numbers (#01, #02...) appear on each card. This is the page's primary use case."},
        {"term":"\U0001f501 FUSIONS","def":"25 randomly generated 2-player parlay combos from the Top 50 SSJ Matchups. Each Fusion shows full card detail for both players. Hit RE-FUSE to generate fresh random pairs. SAME GAME tag means both players are in the same lineup — correlated parlay, strongest Fusion type. ELITE grade means both players are STRONG."},
        {"term":"\u26a1 POWER LEVELS","def":"This guide. A complete explanation of every metric, tag, badge, filter, and concept on the SSJ page. Bookmark this for reference when learning the system."},
      ]},
      {"title":"SSJ MATCHUPS — FILTERS","entries":[
        {"term":"\u26a0 DANGER ONLY","def":"Hides all matchups where the opposing pitcher's VulnScore is below 70. You see only batters facing a DANGER-tagged pitcher. This is the highest-signal filter — every result is a potential exploitation target. Best used on the SSJ MATCHUPS tab for a clean ranked danger board."},
        {"term":"\u26a1 PLATOON ADV ONLY","def":"Filters to batters with confirmed opposite-hand platoon advantage only. Eliminates all same-side matchups. Combine with DANGER ONLY to create the tightest possible filter — batters with platoon edge facing exploitable pitchers, ranked by composite score."},
        {"term":"Result Count","def":"When either filter is active, a count appears showing how many plays remain. If DANGER ONLY returns 4 results on a given day, those 4 are the day's most important plays regardless of their raw grade."},
      ]},
      {"title":"FUSIONS — PARLAY BUILDER","entries":[
        {"term":"How Fusions Work","def":"The system randomly picks 25 pairs from the Top 50 SSJ Matchups and presents them as parlay candidates. Both players in each Fusion are shown with full card stats — you can evaluate the pair directly without switching tabs."},
        {"term":"🔁 RE-FUSE","def":"Generates 25 brand new random pairs from the same Top 50 pool without reloading the page. Hit it multiple times to explore different combinations."},
        {"term":"\u26a1 ELITE","def":"Both players in the Fusion are STRONG (Super Saiyan) grade. Highest-quality parlay tier. An ELITE Fusion with SAME GAME tag is the most correlated, highest-upside combination."},
        {"term":"\U0001f525 SOLID","def":"At least one player in the Fusion is STRONG. Strong parlay with one dominant anchor leg."},
        {"term":"BASE FORM","def":"Both players are MODERATE grade. Solid supporting play parlay. Lower upside but lower variance."},
        {"term":"SAME GAME","def":"Both players are in the same game — meaning they face the same pitcher or are in the same lineup. This is a correlated parlay. When both players are stacking against the same vulnerable pitcher, the implied correlation is real and should increase conviction."},
      ]},
      {"title":"GAME FILTER + SUPER SCROLL GRIP","entries":[
        {"term":"Game Filter Dropdown","def":"The dropdown below the tab rows filters the entire page to one specific game. Use it when you have conviction on a specific matchup and want to see only batters from that game. The CLEAR button removes the filter and restores the full view."},
        {"term":"The Golden Scroll Grip","def":"The gold bar on the right edge of the screen is a drag-to-scroll control. Drag it up or down to navigate the page at any speed. It works on both touch and mouse. The grip glows brighter gold when actively dragging. It automatically hides if the page content fits on screen."},
        {"term":"Why Gold?","def":"Everything on this page is gold. You're in Super Saiyan mode. That's the rule."},
      ]},
    ], ensure_ascii=False)

    # Build HTML using string concatenation to avoid f-string emoji issues
    parts = []
    parts.append('<!DOCTYPE html>\n<html lang="en">\n<head>\n')
    parts.append('<meta charset="UTF-8">\n')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover">\n')
    parts.append('<meta name="theme-color" content="#070707">\n')
    parts.append('<title>SSJ (The Zone) \u26a1 \u00b7 ' + today_str + '</title>\n')
    parts.append('''<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#070707;--gold:#FFD700;--gold-d:rgba(255,215,0,.45);--gold-s:rgba(255,215,0,.1);
  --danger:#FF6B6B;--danger-s:rgba(255,80,80,.14);--text:#F0F0F0;--text-d:rgba(255,255,255,.45);
  --r:8px;--border:rgba(255,255,255,.08)}
html,body{background:var(--bg);color:var(--text);font-family:"Rajdhani",system-ui,sans-serif;
  min-height:100vh;padding-bottom:70px;
  background-image:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(255,255,255,.007) 2px,rgba(255,255,255,.007) 3px),
    radial-gradient(ellipse 80% 40% at 50% 0%,rgba(255,215,0,.055) 0%,transparent 70%)}
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Rajdhani:wght@400;600;700&display=swap');
@keyframes aura{0%,100%{text-shadow:0 0 18px #FFD700,0 0 40px rgba(255,215,0,.5),0 0 90px rgba(255,215,0,.2)}
  50%{text-shadow:0 0 30px #FFF59D,0 0 65px rgba(255,215,0,.85),0 0 140px rgba(255,215,0,.4)}}
@keyframes bglow{0%,100%{box-shadow:0 0 8px rgba(255,215,0,.4),inset 0 0 8px rgba(255,215,0,.07)}
  50%{box-shadow:0 0 22px rgba(255,215,0,.85),0 0 44px rgba(255,215,0,.28),inset 0 0 16px rgba(255,215,0,.15)}}
@keyframes bfire{0%,100%{box-shadow:0 0 10px rgba(255,120,0,.65),0 0 22px rgba(255,60,0,.35)}
  50%{box-shadow:0 0 22px rgba(255,160,0,.95),0 0 44px rgba(255,80,0,.55)}}
@keyframes vpulse{0%,100%{text-shadow:0 0 10px #FFD700,0 0 22px rgba(255,215,0,.6)}
  50%{text-shadow:0 0 16px #FFF59D,0 0 36px rgba(255,215,0,.9)}}
@keyframes o9k{0%,100%{box-shadow:0 0 0 rgba(255,215,0,0)}50%{box-shadow:0 0 12px rgba(255,215,0,.18)}}
.t-glow{animation:aura 2.6s ease-in-out infinite}
.v-text{animation:vpulse 1.8s ease-in-out infinite}
.bglow{animation:bglow 2.1s ease-in-out infinite}
.bfire{animation:bfire 1.5s ease-in-out infinite}
.o9k-c{animation:o9k 3s ease-in-out infinite}
#hdr{padding:24px 16px 16px;position:relative;overflow:hidden;
  background:linear-gradient(180deg,rgba(255,215,0,.055) 0%,transparent 100%);
  border-bottom:1px solid rgba(255,215,0,.14)}
#hdr .ghost{position:absolute;right:-12px;top:50%;transform:translateY(-50%);
  font-size:120px;opacity:.035;line-height:1;pointer-events:none;filter:blur(1px)}
#hdr h1{font-family:"Bebas Neue",sans-serif;font-size:clamp(34px,10vw,64px);
  letter-spacing:.05em;color:var(--gold);line-height:.92;margin:0}
#hdr .sub{font-size:10px;color:var(--gold-d);letter-spacing:.2em;
  text-transform:uppercase;margin-top:8px;font-weight:600}
#spills{display:flex;border-bottom:1px solid var(--border)}
.spill{flex:1;padding:12px 6px;text-align:center}
.spill:not(:last-child){border-right:1px solid var(--border)}
.spill-n{font-family:"Bebas Neue",sans-serif;font-size:24px;line-height:1}
.spill-l{font-size:8px;color:rgba(255,255,255,.25);letter-spacing:.1em;margin-top:2px}
.tab-row{display:flex;padding:8px 14px;gap:7px;border-bottom:1px solid var(--border);
  overflow-x:auto;scrollbar-width:none}
.tab-row::-webkit-scrollbar{display:none}
.tab-row.dbz{background:rgba(255,215,0,.018);border-color:rgba(255,215,0,.1)}
.tab{cursor:pointer;font-family:"Rajdhani",sans-serif;font-weight:700;font-size:12px;
  letter-spacing:.08em;padding:7px 14px;border-radius:20px;white-space:nowrap;flex-shrink:0;
  border:1px solid rgba(255,255,255,.14);background:transparent;color:rgba(255,255,255,.45);
  transition:all .15s ease}
.tab:hover{border-color:rgba(255,215,0,.45);color:rgba(255,215,0,.85)}
.tab.active{background:var(--gold);color:#000;border-color:var(--gold)}
.tab.dbz-tab{border-color:rgba(255,215,0,.25);color:rgba(255,200,0,.65)}
.tab.dbz-tab.active{background:linear-gradient(135deg,#FFD700,#FF9500);color:#000;border-color:var(--gold)}
#gf{display:flex;align-items:center;gap:10px;padding:8px 14px;border-bottom:1px solid var(--border)}
#gf label{font-size:9px;font-weight:700;color:var(--gold-d);letter-spacing:.15em;white-space:nowrap}
#gf select{flex:1;background:#0d0d0d;border:1px solid rgba(255,215,0,.2);color:rgba(255,255,255,.65);
  padding:7px 10px;border-radius:6px;font-family:"Rajdhani",sans-serif;font-weight:600;
  font-size:12px;outline:none;appearance:none;-webkit-appearance:none}
#gf-clear{background:transparent;border:1px solid rgba(255,80,80,.3);color:var(--danger);
  font-size:10px;font-weight:700;padding:5px 10px;border-radius:4px;cursor:pointer;
  font-family:"Rajdhani",sans-serif;display:none}
#content{padding:14px 14px 0}
.card{border-radius:var(--r);padding:13px 14px;transition:transform .12s ease;cursor:default;margin-bottom:8px}
.card:hover{transform:translateX(3px)}
.card.strong{border-left:3px solid var(--gold);
  background:linear-gradient(90deg,rgba(255,215,0,.09),rgba(255,215,0,.02) 50%,transparent)}
.card.moderate{border-left:3px solid transparent;background:rgba(255,255,255,.03)}
.card.bad{border-left:3px solid transparent;background:rgba(255,255,255,.018);opacity:.65}
.ct{display:flex;align-items:center;gap:10px}
.bw{border-radius:var(--r);flex-shrink:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center}
.bw .bz{font-size:9px;line-height:1}
.bw .bn{font-family:"Bebas Neue",sans-serif;line-height:1;font-weight:700}
.bw .bf{font-size:8px;line-height:1;margin-top:1px}
.ci{flex:1;min-width:0}
.cn{font-weight:700;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cm{font-size:12px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cr{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0}
.pt{font-size:12px;font-weight:700;letter-spacing:.04em}
.gt{font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px;letter-spacing:.1em}
.dt{font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px;
  background:var(--danger-s);color:var(--danger);border:1px solid rgba(255,80,80,.3);letter-spacing:.08em}
.rn{font-family:"Bebas Neue",sans-serif;font-size:20px;line-height:1;display:block;margin-bottom:6px}
.sr{display:flex;gap:16px;flex-wrap:wrap;margin-top:9px;padding-top:8px;border-top:1px solid}
.si .sl{font-size:9px;letter-spacing:.14em;text-transform:uppercase;
  font-family:"Bebas Neue",sans-serif}
.si .sv{font-size:13px;font-weight:700;font-family:"Bebas Neue",sans-serif;letter-spacing:.05em}
.ph{text-align:center;margin-bottom:5px}
.ph span{display:inline-block;font-size:8px;font-weight:700;letter-spacing:.18em;
  padding:2px 9px;border-radius:10px;background:rgba(255,215,0,.07);
  font-family:"Bebas Neue",sans-serif;color:rgba(255,215,0,.55)}
.tc{display:flex;margin-top:9px;padding-top:8px;border-top:1px solid}
.tc .col{flex:1}
.cd{width:1px;background:rgba(255,255,255,.1);margin:0 12px}
.sh{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.sh span{font-size:11px;font-weight:700;letter-spacing:.2em;white-space:nowrap}
.sh .ln{flex:1;height:1px}
.sh .sl2{font-size:10px;letter-spacing:.12em;white-space:nowrap}
#o9k{margin-bottom:22px}
.o9t{font-family:"Bebas Neue",sans-serif;font-size:clamp(14px,4.5vw,22px);
  color:var(--gold);letter-spacing:.03em;line-height:1;margin-bottom:4px}
.o9s{font-size:9px;color:rgba(255,215,0,.38);letter-spacing:.18em;text-transform:uppercase;margin-bottom:12px}
.o9r{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px;scrollbar-width:none}
.o9r::-webkit-scrollbar{display:none}
.o9c{min-width:138px;max-width:138px;flex-shrink:0;border-radius:var(--r);padding:11px}
#sf{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.fp{cursor:pointer;font-family:"Rajdhani",sans-serif;font-weight:700;font-size:11px;
  letter-spacing:.1em;padding:6px 14px;border-radius:16px;transition:all .15s ease;background:transparent}
.fh{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px}
.ft{font-family:"Bebas Neue",sans-serif;font-size:clamp(20px,6vw,32px);
  color:var(--gold);letter-spacing:.1em;
  text-shadow:0 0 18px rgba(255,215,0,.65),0 0 40px rgba(255,215,0,.3)}
.fs{font-size:10px;color:rgba(255,215,0,.4);letter-spacing:.14em;margin-top:4px}
@keyframes rfglow{0%,100%{box-shadow:0 0 8px rgba(255,215,0,.4),0 0 18px rgba(255,215,0,.15)}
  50%{box-shadow:0 0 18px rgba(255,215,0,.85),0 0 38px rgba(255,215,0,.35)}}
#rf{background:rgba(255,215,0,.12);border:1px solid rgba(255,215,0,.5);color:var(--gold);
  font-size:13px;font-weight:700;padding:9px 16px;border-radius:6px;cursor:pointer;
  letter-spacing:.1em;font-family:"Bebas Neue",sans-serif;flex-shrink:0;margin-left:10px;
  animation:rfglow 2s ease-in-out infinite}
.fc{border-radius:10px;padding:14px;margin-bottom:12px;border:1px solid rgba(255,215,0,.25);
  background:linear-gradient(135deg,rgba(255,215,0,.06) 0%,rgba(255,80,0,.03) 50%,rgba(255,215,0,.06) 100%)}
.fm{display:flex;justify-content:space-between;align-items:center;margin-bottom:11px}
.fn{font-family:"Bebas Neue",sans-serif;font-size:12px;color:rgba(255,215,0,.5);letter-spacing:.18em}
.fts{display:flex;gap:6px;align-items:center}
.sg{font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px;
  background:rgba(100,200,255,.12);color:#80CFFF;border:1px solid rgba(100,200,255,.25);letter-spacing:.08em}
.cg{font-size:10px;font-weight:700;padding:2px 9px;border-radius:4px;letter-spacing:.08em}
.fd{text-align:center;padding:10px 0;margin:10px 0;
  border-top:1px solid rgba(255,215,0,.15);border-bottom:1px solid rgba(255,215,0,.15)}
.fd span{font-family:"Bebas Neue",sans-serif;font-size:22px;color:var(--gold);
  letter-spacing:.6em;text-shadow:0 0 14px rgba(255,215,0,.8),0 0 30px rgba(255,215,0,.35)}
#gh{margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid rgba(255,215,0,.15)}
#gh h2{font-family:"Bebas Neue",sans-serif;font-size:clamp(28px,8vw,48px);
  color:var(--gold);letter-spacing:.05em;line-height:.9}
#gh .gs{font-size:10px;color:var(--gold-d);letter-spacing:.18em;
  text-transform:uppercase;margin-top:8px;font-weight:600}
.gs-sec{border-radius:var(--r);border:1px solid rgba(255,215,0,.13);
  background:rgba(255,215,0,.025);padding:14px;margin-bottom:10px}
.gs-t{font-family:"Bebas Neue",sans-serif;font-size:11px;letter-spacing:.22em;
  color:rgba(255,215,0,.5);border-bottom:1px solid rgba(255,215,0,.1);
  padding-bottom:8px;margin-bottom:12px}
.ge{margin-bottom:13px}
.ge:last-child{margin-bottom:0}
.gterm{font-family:"Bebas Neue",sans-serif;font-size:15px;color:var(--gold);
  letter-spacing:.04em;line-height:1;margin-bottom:5px}
.gdef{font-size:12px;color:rgba(255,255,255,.62);line-height:1.6;letter-spacing:.01em}
#dock{position:fixed;bottom:0;left:0;right:0;z-index:200;
  display:flex;align-items:center;justify-content:space-around;
  background:rgba(8,18,15,.88);backdrop-filter:blur(20px) saturate(140%);
  border-top:1px solid rgba(255,255,255,.1);padding:8px 4px;
  padding-bottom:calc(8px + env(safe-area-inset-bottom))}
.da{display:flex;flex-direction:column;align-items:center;gap:2px;
  text-decoration:none;color:rgba(255,255,255,.45);font-size:9.5px;
  font-weight:700;letter-spacing:.06em;padding:4px 8px;border-radius:8px;
  transition:color .15s ease;min-width:50px}
.da:hover,.da.act{color:var(--gold)}
.di{font-size:16px;line-height:1}
[data-theme="light"]{
  --bg:#FBF7E6;--gold:#A07000;--gold-d:rgba(160,112,0,.5);--gold-s:rgba(160,112,0,.08);
  --danger:#C02020;--danger-s:rgba(192,32,32,.1);--text:#1A1000;--text-d:rgba(26,16,0,.5);
  --border:rgba(26,16,0,.1)}
[data-theme="light"] body{background:#FBF7E6;
  background-image:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.006) 2px,rgba(0,0,0,.006) 3px),
    radial-gradient(ellipse 80% 40% at 50% 0%,rgba(160,112,0,.05) 0%,transparent 70%)}
[data-theme="light"] #app-bar{background:rgba(251,247,230,.94);border-color:rgba(160,112,0,.15)}
[data-theme="light"] #hdr{background:linear-gradient(180deg,rgba(160,112,0,.06) 0%,transparent 100%);
  border-color:rgba(160,112,0,.1)}
[data-theme="light"] #spills,[data-theme="light"] .tab-row{border-color:rgba(0,0,0,.08)}
[data-theme="light"] #gf{border-color:rgba(0,0,0,.08)}
[data-theme="light"] #gf select{background:#FFF8E0;border-color:rgba(160,112,0,.25);color:#1A1000}
[data-theme="light"] .card.moderate,[data-theme="light"] .card.bad{background:rgba(0,0,0,.03)}
[data-theme="light"] .fc{background:linear-gradient(135deg,rgba(160,112,0,.07) 0%,rgba(180,90,0,.03) 50%,rgba(160,112,0,.07) 100%)}
[data-theme="light"] #dock{background:rgba(251,247,230,.92)}
[data-theme="light"] #scroll-track{background:rgba(160,112,0,.12)}
[data-theme="light"] #scroll-thumb{background:rgba(160,112,0,.25);border-color:rgba(160,112,0,.5)}
[data-theme="light"] #scroll-thumb .grip-line{background:var(--gold)}
#app-bar{display:flex;align-items:center;padding:calc(8px + env(safe-area-inset-top,0px)) 14px 8px;gap:10px;
  background:rgba(7,7,7,.92);backdrop-filter:blur(18px) saturate(140%);
  -webkit-backdrop-filter:blur(18px) saturate(140%);position:sticky;top:0;z-index:100;
  border-bottom:1px solid rgba(255,215,0,.12)}
.back-chip{width:36px;height:36px;border-radius:10px;flex-shrink:0;
  background:rgba(255,215,0,.1);border:1px solid rgba(255,215,0,.28);
  color:var(--gold);text-decoration:none;
  display:inline-flex;align-items:center;justify-content:center;font-size:20px;line-height:1}
.bar-title{font-family:"Bebas Neue",sans-serif;font-size:17px;letter-spacing:.1em;
  color:var(--gold);text-shadow:0 0 12px rgba(255,215,0,.4);white-space:nowrap}
.bar-spacer{flex:1}
.icon-btn{width:36px;height:36px;border-radius:10px;flex-shrink:0;
  background:rgba(255,215,0,.1);border:1px solid rgba(255,215,0,.28);
  color:var(--gold);font-size:15px;cursor:pointer;font-family:inherit;
  display:inline-flex;align-items:center;justify-content:center}
#scroll-track{position:fixed;right:6px;top:50%;transform:translateY(-50%);height:56vh;width:6px;
  background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.12);border-radius:999px;z-index:64}
#scroll-thumb{position:absolute;left:50%;transform:translateX(-50%);width:28px;height:52px;
  background:rgba(255,215,0,.22);border:1px solid rgba(255,215,0,.55);border-radius:999px;
  cursor:grab;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:3px;touch-action:none;transition:background .15s;
  box-shadow:0 0 12px rgba(255,215,0,.28),inset 0 1px 0 rgba(255,255,255,.12)}
#scroll-thumb.dragging{background:rgba(255,215,0,.7);cursor:grabbing;
  box-shadow:0 0 22px rgba(255,215,0,.65)}
#scroll-thumb .grip-line{width:10px;height:2px;background:#FFD700;border-radius:999px;
  box-shadow:0 0 4px rgba(255,215,0,.6)}
#scroll-thumb.dragging .grip-line{background:#1a1000}
</style>
</head>
<body>
''')
    parts.append('<div id="app-bar">\n')
    parts.append('  <a class="back-chip" href="index.html">‹</a>\n')
    parts.append('  <div class="bar-title">⚡ SSJ (THE ZONE)</div>\n')
    parts.append('  <div class="bar-spacer"></div>\n')
    parts.append('  <button class="icon-btn" id="themeToggle">🌙</button>\n')
    parts.append('</div>\n')
    parts.append('<div id="hdr">\n')
    parts.append('  <div class="ghost">\u26a1</div>\n')
    parts.append('  <h1 class="t-glow">SSJ (THE ZONE) \u26a1</h1>\n')
    parts.append('  <div class="sub">' + today_str + ' \u00b7 MLB Matchup Intelligence</div>\n')
    parts.append('</div>\n\n')
    parts.append('<div id="spills"></div>\n\n')
    parts.append('''<div class="tab-row" id="tr1">
  <button class="tab" data-f="STRONG" onclick="sf(this)">\u26a1 SUPER SAIYAN</button>
  <button class="tab" data-f="MODERATE" onclick="sf(this)">BASE FORM</button>
  <button class="tab" data-f="BAD" onclick="sf(this)">YAMCHA</button>
  <button class="tab" id="tab-all" data-f="ALL" onclick="sf(this)">ALL</button>
</div>
<div class="tab-row dbz" id="tr2">
  <button class="tab dbz-tab" data-f="SSJ" onclick="sf(this)">\U0001f31f SSJ MATCHUPS</button>
  <button class="tab dbz-tab" data-f="FUSIONS" onclick="sf(this)">\U0001f501 FUSIONS</button>
  <button class="tab dbz-tab" data-f="POWER" onclick="sf(this)">\u26a1 POWER LEVELS</button>
</div>
<div id="gf">
  <label>GAME</label>
  <select id="gfs" onchange="sg(this.value)"><option value="ALL">ALL GAMES</option></select>
  <button id="gf-clear" onclick="sg('ALL')">CLEAR \u00d7</button>
</div>
<main id="content"></main>
<div id="scroll-track"><div id="scroll-thumb"><div class="grip-line"></div><div class="grip-line"></div><div class="grip-line"></div></div></div>
<nav id="dock">
  <a class="da" href="index.html"><span class="di">⚾️</span>Slate</a>
  <a class="da" href="k-report.html"><span class="di">📰</span>K Report</a>
  <a class="da" href="streaks.html"><span class="di">\U0001f525</span>Streaks</a>
  <a class="da" href="record.html"><span class="di">💿</span>Record</a>
</nav>
''')
    parts.append('<script id="sd" type="application/json">' + data_json + '</script>\n')
    parts.append('<script id="cd" type="application/json">' + counts_json + '</script>\n')
    parts.append('<script id="gd" type="application/json">' + GLOS + '</script>\n')
    parts.append(r'''<script>
var D=JSON.parse(document.getElementById('sd').textContent);
var C=JSON.parse(document.getElementById('cd').textContent);
var G=JSON.parse(document.getElementById('gd').textContent);
var cf='STRONG',cg='ALL',dO=false,pO=false,fS=0;
function gk(p){return [p.team,p.pTeam].sort().join(' · ');}
function pl(b,t){if(b==='S')return{l:'S→'+t,a:true};return{l:b+'→'+t,a:b!==t};}
function sd2(v,thr,ic){
  if(!v||v===0)return{t:'—',c:'rgba(255,255,255,.2)',s:''};
  if(v>=thr)return{t:''+v,c:'#FFD700',s:ic};
  return{t:''+v,c:'rgba(255,255,255,.65)',s:''};
}
function vc(v){return v>=70?'#FF6B6B':v>=50?'#FFD700':'rgba(255,255,255,.45)';}
function nc(g){return g==='STRONG'?'#FFF':(g==='MODERATE'?'#E8E8E8':'#A0A0A0');}
function svc(g){return g==='STRONG'?'#FFD700':(g==='MODERATE'?'#D0D0D0':'#909090');}
function slc(g){return g==='STRONG'?'rgba(255,215,0,.48)':(g==='MODERATE'?'rgba(255,255,255,.42)':'rgba(255,255,255,.3)');}
function dc2(g){return g==='STRONG'?'rgba(255,215,0,.12)':'rgba(255,255,255,.07)';}
function gts(g){
  if(g==='STRONG')return'background:rgba(255,215,0,.16);color:#FFD700;';
  if(g==='MODERATE')return'background:rgba(255,255,255,.08);color:#AAAAAA;';
  return'background:transparent;color:#666;';
}
function gdsp(g){return g==='BAD'?'WEAK':g;}
function bws(p){
  var iS=p.grade==='STRONG',iF=p.zone>=10;
  var br=iS?(iF?'1px solid rgba(255,215,0,.65)':'1px solid rgba(255,215,0,.38)'):
    (p.grade==='MODERATE'?'1px solid rgba(255,255,255,.14)':'1px solid rgba(255,255,255,.06)');
  var bg=iS?(iF?'rgba(255,215,0,.16)':'rgba(255,215,0,.09)'):'rgba(255,255,255,.04)';
  return 'border:'+br+';background:'+bg+';';
}
function ban(p){
  var hs=p.hitStreak>=4||p.hrStreak>=2||p.hrrStreak>=3;
  if(hs)return'bfire';
  if(p.zone>=10)return'bglow';
  return'';
}
function bnc(p){return p.grade==='STRONG'?'#FFD700':(p.grade==='MODERATE'?'#AAAAAA':'#666');}
function rs(p,compact){
  var pt=pl(p.bats,p.throws),sl=slc(p.grade),sv=svc(p.grade),dc=dc2(p.grade);
  var vs=p.vulnScore,phR=p.projHits>=8.0,peR=p.projERA>=5.5;
  var phC=phR?'#FF6B6B':sv,peC=peR?'#FF6B6B':sv;
  var hit=sd2(p.hitStreak,4,'🔥'),hr=sd2(p.hrStreak,2,'⚡'),hrr=sd2(p.hrrStreak,3,'⚡');
  var sz=compact?42:46,ba=ban(p),hs=p.hitStreak>=4||p.hrStreak>=2||p.hrrStreak>=3;
  return '<div class="ct">'+
    '<div class="bw '+ba+'" style="width:'+sz+'px;height:'+sz+'px;'+bws(p)+'">'+
      '<span class="bz" style="color:'+(p.grade==='STRONG'?'#FFD700':'#3a3a3a')+'">⚡</span>'+
      '<span class="bn" style="color:'+bnc(p)+';font-size:'+(compact?'18px':'21px')+'">'+p.zone+'</span>'+
      (hs?'<span class="bf">🔥</span>':'')+
    '</div>'+
    '<div class="ci">'+
      '<div class="cn" style="color:'+nc(p.grade)+'">'+p.batter+
        ' <span style="font-size:11px;font-weight:700;color:rgba(255,215,0,.65);letter-spacing:.1em">'+p.team+'</span></div>'+
      '<div class="cm" style="color:'+(p.grade==='STRONG'?'rgba(255,255,255,.65)':'rgba(255,255,255,.5)')+'">'+
        'vs '+p.pitcher+' · '+p.pTeam+' · ERA '+p.era+'</div>'+
    '</div>'+
    '<div class="cr">'+
      '<span class="pt" style="color:'+(pt.a?'#FFD700':'rgba(255,255,255,.22)')+'">'+pt.l+(pt.a?' ⚡':'')+'</span>'+
      '<span class="gt" style="'+gts(p.grade)+'">'+gdsp(p.grade)+'</span>'+
      (p.vulnScore>=70?'<span class="dt">⚠ DANGER</span>':'')+
    '</div>'+
  '</div>'+
  '<div class="sr" style="border-color:'+dc+'">'+
    '<div class="si"><div class="sl" style="color:'+sl+'">VULN</div><div class="sv" style="color:'+vc(vs)+'">'+vs+'</div></div>'+
    '<div class="si"><div class="sl" style="color:'+sl+'">PROJ H</div>'+
      '<div class="sv" style="color:'+phC+'">'+(p.pitcher==='TBD'?'—':p.projHits)+'</div>'+(phR&&p.pitcher!=='TBD'?' 🔴':'')+' </div>'+
    '<div class="si"><div class="sl" style="color:'+sl+'">PROJ ERA</div>'+
      '<div class="sv" style="color:'+peC+'">'+(p.pitcher==='TBD'?'—':p.projERA)+'</div>'+(peR&&p.pitcher!=='TBD'?' 🔴':'')+' </div>'+
  '</div>'+
  '<div class="tc" style="border-color:'+dc+'">'+
    '<div class="col">'+
      '<div class="ph"><span style="color:'+sl+'">AVERAGES</span></div>'+
      '<div style="display:flex;gap:12px;flex-wrap:wrap">'+
        [['ISO',p.iso],['wOBA',p.woba],['HR',p.hr]].map(function(x){
          return '<div><div class="sl" style="color:'+sl+'">'+x[0]+'</div>'+
            '<div class="sv" style="color:'+sv+'">'+x[1]+'</div></div>';
        }).join('')+
      '</div>'+
    '</div>'+
    '<div class="cd"></div>'+
    '<div class="col">'+
      '<div class="ph"><span style="color:'+sl+'">STREAKS</span></div>'+
      '<div style="display:flex;gap:12px;flex-wrap:wrap">'+
        [['HIT',hit],['HR',hr],['HRR',hrr]].map(function(x){
          return '<div><div class="sl" style="color:'+sl+'">'+x[0]+'</div>'+
            '<div class="sv" style="color:'+x[1].c+'">'+x[1].t+(x[1].s?x[1].s:'')+'</div></div>';
        }).join('')+
      '</div>'+
    '</div>'+
  '</div>';
}
function rc(p,rank){
  var cls='card '+p.grade.toLowerCase();
  var rh=rank!=null?'<span class="rn" style="color:'+(rank<=3?'#FFD700':rank<=10?'rgba(255,215,0,.65)':'rgba(255,215,0,.35)')+'">#'+('0'+rank).slice(-2)+'</span>':'';
  return '<div class="'+cls+'">'+rh+rs(p,false)+'</div>';
}
function cgf(g1,g2){
  if(g1==='STRONG'&&g2==='STRONG')return{l:'⚡ ELITE',c:'#FFD700',b:'rgba(255,215,0,.18)'};
  if(g1==='STRONG'||g2==='STRONG')return{l:'🔥 SOLID',c:'#FFA040',b:'rgba(255,140,0,.14)'};
  if(g1==='MODERATE'&&g2==='MODERATE')return{l:'BASE FORM',c:'#AAAAAA',b:'rgba(255,255,255,.08)'};
  return{l:'MIXED',c:'#777',b:'rgba(255,255,255,.05)'};
}
function rfusion(pair,idx){
  var p1=pair[0],p2=pair[1];if(!p1||!p2)return'';
  var cg=cgf(p1.grade,p2.grade),sg2=gk(p1)===gk(p2);
  return '<div class="fc">'+
    '<div class="fm">'+
      '<span class="fn">FUSION #'+('0'+(idx+1)).slice(-2)+'</span>'+
      '<div class="fts">'+(sg2?'<span class="sg">SAME GAME</span>':'')+
        '<span class="cg" style="background:'+cg.b+';color:'+cg.c+'">'+cg.l+'</span>'+
      '</div>'+
    '</div>'+
    rs(p1,true)+
    '<div class="fd"><span>⚡ + ⚡</span></div>'+
    rs(p2,true)+
  '</div>';
}
function rglos(){
  return '<div id="gh" class="t-glow"><h2>⚡ POWER LEVELS</h2>'+
    '<div class="gs">A Saiyan\'s Field Guide to the Zone</div></div>'+
    G.map(function(sec){
      return '<div class="gs-sec">'+
        '<div class="gs-t">'+sec.title+'</div>'+
        sec.entries.map(function(e){
          return '<div class="ge"><div class="gterm">'+e.term+'</div>'+
            '<div class="gdef">'+e.def+'</div></div>';
        }).join('')+
      '</div>';
    }).join('');
}
function sh(lbl,sub,gold){
  var c=gold?'#FFD700':'rgba(255,255,255,.3)';
  var bg=gold?'linear-gradient(90deg,rgba(255,215,0,.35),transparent)':'rgba(255,255,255,.07)';
  return '<div class="sh"><span style="color:'+c+'">'+lbl+'</span>'+
    '<div class="ln" style="background:'+bg+'"></div>'+
    (sub?'<span class="sl2" style="color:'+(gold?'rgba(255,215,0,.4)':'rgba(255,255,255,.2)')+'">'+sub+'</span>':'')+
  '</div>';
}
function gfusions(){
  var pool=D.map(function(p,i){return Object.assign({},p,{_i:i});});
  var s=fS+1234;
  function rng(){s=(s^(s<<17))^(s>>13);s^=s<<5;return((s>>>0)/4294967296);}
  pool.sort(function(){return rng()-0.5;});
  pool=pool.slice(0,50);
  var pairs=[];
  for(var i=0;i<25&&i*2+1<pool.length;i++){pairs.push([pool[i*2],pool[i*2+1]]);}
  return pairs;
}
function getMain(g){
  var d=g==='ALL'?D.slice():D.filter(function(p){return p.grade===g;});
  if(cg!=='ALL')d=d.filter(function(p){return gk(p)===cg;});
  return d;
}
function getSsj(){
  var d=D.slice();
  if(cg!=='ALL')d=d.filter(function(p){return gk(p)===cg;});
  return d;
}
function render(){
  var html='';
  var gfel=document.getElementById('gf');
  if(cf==='POWER'){
    gfel.style.display='none'; html=rglos();
  } else if(cf==='FUSIONS'){
    gfel.style.display='none';
    var pairs=gfusions();
    html='<div class="fh">'+
      '<div><div class="ft">FUU… SION… HAA!</div>'+
      '<div class="fs">25 RANDOM PAIRS · TOP 50 SSJ MATCHUPS</div></div>'+
      '<button id="rf" onclick="rF()">🔁 RE-FUSE</button>'+
    '</div>'+pairs.map(function(p,i){return rfusion(p,i);}).join('');
  } else if(cf==='SSJ'){
    gfel.style.display='flex';
    var fd=getSsj().slice(0,50)
      .filter(function(p){return !dO||p.vulnScore>=70;})
      .filter(function(p){return !pO||pl(p.bats,p.throws).a;});
    var dn=dO?'1px solid #FF6B6B':'1px solid rgba(255,80,80,.3)';
    var db=dO?'rgba(255,80,80,.2)':'transparent';
    var dc=dO?'#FF6B6B':'rgba(255,100,80,.65)';
    var pn=pO?'1px solid #FFD700':'1px solid rgba(255,215,0,.25)';
    var pb=pO?'rgba(255,215,0,.15)':'transparent';
    var pc=pO?'#FFD700':'rgba(255,215,0,.5)';
    html='<div id="sf">'+
      '<button class="fp" onclick="tD()" style="border:'+dn+';background:'+db+';color:'+dc+'">⚠ DANGER ONLY</button>'+
      '<button class="fp" onclick="tP()" style="border:'+pn+';background:'+pb+';color:'+pc+'">⚡ PLATOON ADV ONLY</button>'+
      ((dO||pO)?'<span style="font-size:10px;color:rgba(255,255,255,.3);align-self:center">'+fd.length+' results</span>':'')+
    '</div>'+
    (fd.length===0?'<div style="text-align:center;padding:40px;color:rgba(255,255,255,.22);font-size:13px">No matchups match the active filters.</div>':
      fd.map(function(p,i){return rc(p,i+1);}).join(''));
  } else {
    gfel.style.display='flex';
    var d=getMain(cf),top5=getSsj().slice(0,5);
    var feat=d.filter(function(p){return p.zone>=10;});
    var rest=d.filter(function(p){return p.zone<10;});
    if(top5.length){
      var cards=top5.map(function(p,i){
        var pt=pl(p.bats,p.throws),iD=p.vulnScore>=70,hs=p.hitStreak>=4||p.hrStreak>=2||p.hrrStreak>=3;
        return '<div class="o9c o9k-c" style="border:'+(i===0?'1px solid rgba(255,215,0,.55)':'1px solid rgba(255,215,0,.22)')+
          ';background:'+(i===0?'linear-gradient(135deg,rgba(255,215,0,.13),rgba(255,140,0,.06))':'rgba(255,215,0,.05)')+'">'+
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px">'+
            '<span style="font-family:Bebas Neue,sans-serif;font-size:18px;color:'+(i===0?'#FFD700':'rgba(255,215,0,.5)')+'">#'+(i+1)+'</span>'+
            '<span style="font-family:Bebas Neue,sans-serif;font-size:14px;color:#FFD700">⚡'+p.zone+'</span>'+
          '</div>'+
          '<div style="font-weight:700;font-size:13px;color:#FFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px">'+p.batter+'</div>'+
          '<div style="font-size:10px;color:rgba(255,215,0,.65);letter-spacing:.1em;margin-bottom:7px">'+p.team+'</div>'+
          '<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:7px">'+
            '<span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;background:'+(p.grade==='STRONG'?'rgba(255,215,0,.16)':'rgba(255,255,255,.08)')+';color:'+(p.grade==='STRONG'?'#FFD700':'#999')+'">'+gdsp(p.grade)+'</span>'+
            (iD?'<span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;background:rgba(255,80,80,.18);color:#FF6B6B">⚠</span>':'')+
            (hs?'<span style="font-size:10px">🔥</span>':'')+
          '</div>'+
          '<div style="font-size:11px;color:rgba(255,255,255,.45);margin-bottom:3px">ISO <span style="color:#FFD700;font-weight:700">'+p.iso+'</span></div>'+
          '<div style="font-size:11px;color:rgba(255,255,255,.45);margin-bottom:3px">wOBA <span style="color:#FFD700;font-weight:700">'+p.woba+'</span></div>'+
          '<div style="font-size:11px;color:rgba(255,255,255,.4)">'+pt.l+(pt.a?' <span style="color:#FFD700">⚡</span>':'')+
          '</div>'+
        '</div>';
      }).join('');
      html+='<div id="o9k"><div class="o9t v-text">WHAT?! IT\'S OVER NINE THOUSAAAAAND!!</div>'+
        '<div class="o9s">Today\'s Top 5 Power Plays</div>'+
        '<div class="o9r">'+cards+'</div></div>';
    }
    if(feat.length)html+=sh('⚡ Featured Plays','Zone ≥ 10',true)+feat.map(function(p){return rc(p,null);}).join('');
    if(rest.length){if(feat.length)html+=sh('Full Board','',false);html+=rest.map(function(p){return rc(p,null);}).join('');}
    if(!d.length)html+='<div style="text-align:center;padding:50px;color:rgba(255,255,255,.22);font-size:13px">NO PLAYS IN THIS CATEGORY</div>';
  }
  document.getElementById('content').innerHTML=html;
}
function sf(btn){cf=btn.dataset.f;document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});btn.classList.add('active');render();}
function sg(v){cg=v;document.getElementById('gfs').value=v;document.getElementById('gf-clear').style.display=(v==='ALL'?'none':'block');render();}
function tD(){dO=!dO;render();}
function tP(){pO=!pO;render();}
function rF(){fS++;render();}
(function(){
  var sp=document.getElementById('spills');
  var pill=[['SUPER SAIYAN',C.STRONG,'#FFD700','rgba(255,215,0,.055)'],
            ['BASE FORM',C.MODERATE,'#C8C8C8','transparent'],
            ['WEAK',C.BAD,'#888','transparent']];
  sp.innerHTML=pill.map(function(p,i){
    return '<div class="spill" style="background:'+p[3]+';border-right:'+(i<2?'1px solid rgba(255,255,255,.05)':'none')+'">'+
      '<div class="spill-n" style="color:'+p[2]+'">'+p[1]+'</div>'+
      '<div class="spill-l">'+p[0]+'</div></div>';
  }).join('');
  document.getElementById('tab-all').textContent='ALL ('+C.ALL+')';
  var games=new Set();
  D.forEach(function(p){games.add(gk(p));});
  var sel=document.getElementById('gfs');
  Array.from(games).sort().forEach(function(g){
    var o=document.createElement('option');o.value=g;o.textContent=g;sel.appendChild(o);
  });
  document.querySelector('[data-f="STRONG"]').classList.add('active');
  render();
})();
// ── Theme Toggle ────────────────────────────────────────────────────
(function(){
  var cur='dark';
  try{var s=localStorage.getItem('slateTheme');if(s==='light'||s==='dark')cur=s;}catch(e){}
  document.documentElement.setAttribute('data-theme',cur);
  var t=document.getElementById('themeToggle');
  if(t){
    t.textContent=cur==='dark'?'🌙':'☀️';
    t.addEventListener('click',function(){
      cur=cur==='dark'?'light':'dark';
      document.documentElement.setAttribute('data-theme',cur);
      t.textContent=cur==='dark'?'🌙':'☀️';
      try{localStorage.setItem('slateTheme',cur);}catch(e){}
    });
  }
})();
// ── Golden Scroll Grip ──────────────────────────────────────────────
(function(){
  var track=document.getElementById('scroll-track');
  var thumb=document.getElementById('scroll-thumb');
  if(!track||!thumb)return;
  var dragging=false,startY=0,startScroll=0;
  function updateThumb(){
    var docH=document.documentElement.scrollHeight-window.innerHeight;
    var trackH=track.clientHeight-thumb.clientHeight;
    if(docH<=0){track.style.display='none';return;}
    track.style.display='block';
    thumb.style.top=((window.scrollY/docH)*trackH)+'px';
  }
  window.addEventListener('scroll',updateThumb,{passive:true});
  window.addEventListener('resize',updateThumb);
  updateThumb();
  function startDrag(y){dragging=true;startY=y;startScroll=window.scrollY;thumb.classList.add('dragging');}
  function moveDrag(y){
    if(!dragging)return;
    var delta=y-startY,trackH=track.clientHeight-thumb.clientHeight;
    var docH=document.documentElement.scrollHeight-window.innerHeight;
    window.scrollTo(0,Math.max(0,startScroll+(delta/trackH)*docH));
  }
  function endDrag(){dragging=false;thumb.classList.remove('dragging');}
  thumb.addEventListener('touchstart',function(e){startDrag(e.touches[0].clientY);e.preventDefault();},{passive:false});
  document.addEventListener('touchmove',function(e){if(dragging){moveDrag(e.touches[0].clientY);e.preventDefault();}},{passive:false});
  document.addEventListener('touchend',endDrag);
  thumb.addEventListener('mousedown',function(e){startDrag(e.clientY);});
  document.addEventListener('mousemove',function(e){moveDrag(e.clientY);});
  document.addEventListener('mouseup',endDrag);
  // Re-sync thumb after every render call
  var _origRender=window.render;
  if(_origRender)window.render=function(){_origRender();setTimeout(updateThumb,60);};
})();
</script>
</body>
</html>
''')
    return ''.join(parts)
