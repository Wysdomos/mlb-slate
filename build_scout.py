#!/usr/bin/env python3
"""
build_scout.py  --  generates docs/scout.html  (SSJ: The Zone ⚡)
Called by build.py after build_day46 and build_editorial.
Reads same globals as build_editorial.py.
"""
import json, os, re

HR_LB = []; SP_PROJ = []; SS_BY_NAME = {}; BP_BAT = []; GAMES = []
TODAY_STR = ""; DAY_NUM = ""

def set_data(hr_lb, sp_proj, ss_by_name, bp_bat, games, today_str, day_num=""):
    global HR_LB, SP_PROJ, SS_BY_NAME, BP_BAT, GAMES, TODAY_STR, DAY_NUM
    HR_LB, SP_PROJ, SS_BY_NAME = hr_lb, sp_proj, ss_by_name
    BP_BAT, GAMES = bp_bat, games
    TODAY_STR = today_str; DAY_NUM = day_num

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
def build():
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
            bats=_bats(batter,r), throws=_throws(pitcher),
            pitcher=pitcher, pTeam=pt, era=era_s,
            iso=str(r.get("ISO","—") or "—"),
            woba=str(r.get("wOBA","—") or "—"),
            hr=int(r.get("HR") or 0), grade=grade,
            zone=parse_zone(r.get("Zone","")),
            hitStreak=int(r.get("hitStreak") or r.get("HitStreak") or 0),
            hrStreak =int(r.get("hrStreak")  or r.get("HRStreak")  or 0),
            hrrStreak=int(r.get("hrrStreak") or r.get("HRRStreak") or 0),
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
    out  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "scout.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"build_scout: wrote scout.html  ({len(players)} players, "
          f"{counts['STRONG']} SSJ / {counts['MODERATE']} BASE / {counts['BAD']} BAD)")

# ── HTML ──────────────────────────────────────────────────────────────
def _html(data_json, counts_json, today_str):
    GLOS = json.dumps([
      {"title":"THE TABS — ROW 1","entries":[
        {"term":"SUPER SAIYAN","def":"Top-tier matchups. Elite ISO, wOBA, Zone score, facing an exploitable pitcher. Primary targets every day."},
        {"term":"BASE FORM","def":"Solid but not elite. Good matchups worth monitoring as backup plays."},
        {"term":"BAD","def":"Unfavorable matchups. Use as fades or avoid entirely."},
        {"term":"ALL","def":"The full slate with no grade filter."},
      ]},
      {"title":"THE TABS — ROW 2 (DBZ SPECIALS)","entries":[
        {"term":"SSJ MATCHUPS","def":"All top-ranked plays sorted by composite Power Score combining Zone, pitcher vulnerability, ISO, wOBA, HR, and streaks. The definitive ranked list for the day."},
        {"term":"FUSIONS","def":"25 random 2-player combos from the Top 50 SSJ Matchups. Each pair is a suggested parlay. Hit RE-FUSE to generate fresh pairings. Look for ELITE or SAME GAME tags."},
        {"term":"POWER LEVELS","def":"You are reading it now. A full guide to every metric, tag, badge, filter, and feature in SSJ (The Zone)."},
      ]},
      {"title":"THE ZONE BADGE","entries":[
        {"term":"THE NUMBER","def":"A composite matchup score from the best-spots model combining ISO, wOBA, home run output, pitcher grade, and platoon advantage. Higher = stronger matchup quality."},
        {"term":"Zone 10+ — FEATURED PLAYS","def":"Zone scores of 10 or higher are elevated to the Featured Plays section at the top of any view. Start here every day."},
        {"term":"FIRE ON THE BADGE","def":"Active hot streak: HIT 4+ games, HR 2+ consecutive, or HRR 3+ consecutive games. Badge switches from gold glow to orange fire pulse."},
      ]},
      {"title":"GRADES","entries":[
        {"term":"STRONG — SUPER SAIYAN","def":"Elite matchup. Power metrics, pitcher vulnerability, and zone score all align. Primary target tier."},
        {"term":"MODERATE — BASE FORM","def":"Solid but one or two factors working against. Supporting play tier."},
        {"term":"BAD","def":"One or more significant negatives. Reference only, not a recommendation."},
      ]},
      {"title":"DANGER TAG","entries":[
        {"term":"WHAT DANGER MEANS","def":"The opposing pitcher has a Vulnerability Score of 70 or higher. Highly exploitable based on ERA trends, HR/9 rate, park factors, and today's matchup."},
        {"term":"STRONG + DANGER","def":"The strongest single-play signal. Top-grade batter facing a highly vulnerable pitcher. Backtesting shows MODERATE+DANGER also outperforms STRONG-only on HR rate."},
        {"term":"RED INDICATORS","def":"Red dots appear on PROJ H (8.0+) and PROJ ERA (5.50+) when projections enter the danger zone. Both lit = maximum exploitation signal."},
      ]},
      {"title":"THE STATS","entries":[
        {"term":"ISO — Isolated Power","def":"Slugging % minus batting average. Pure extra-base hit power with singles removed. The most direct HR predictor in the model."},
        {"term":"wOBA — Weighted On-Base Average","def":"The most complete single-number hitting metric. Weights each hit type by its actual run value."},
        {"term":"HR — Season Home Runs","def":"The batter's total HR on the year. Context for their power ceiling."},
      ]},
      {"title":"PITCHER PROJECTIONS","entries":[
        {"term":"VULN — Vulnerability Score 0-100","def":"Our internal pitcher grade. ERA trend + HR/9 + park + matchup history. 70+ = DANGER (red). 50-69 = caution (gold). Under 50 = manageable (dim)."},
        {"term":"PROJ H — Projected Hits Allowed","def":"Expected hits for this start. Flags red at 8.0 or higher."},
        {"term":"PROJ ERA — Projected ERA","def":"Expected ERA for this start. Flags red at 5.50 or higher. Both red = full meltdown projection."},
      ]},
      {"title":"STREAKS","entries":[
        {"term":"HIT — Hit Streak","def":"Consecutive games with at least one hit. Fires at 4+ games."},
        {"term":"HR — Home Run Streak","def":"Consecutive games with at least one HR. Fires at 2+ consecutive games."},
        {"term":"HRR — Hits + Runs + RBIs","def":"Tracks whether a batter recorded at least one Hit, one Run, AND one RBI in the same game. Active at 3+ consecutive games. Sign of elite all-around production across every major offensive category."},
        {"term":"DASH","def":"No active streak. Not a negative, just neutral."},
      ]},
      {"title":"PLATOON ADVANTAGE","entries":[
        {"term":"L to R or R to L","def":"Batter faces a pitcher from the opposite throwing hand. Confirmed platoon advantage with statistically higher BA, SLG, and HR rate. Shown gold."},
        {"term":"L to L or R to R","def":"Same-sided matchup. No platoon advantage. Shown dimmed."},
        {"term":"Switch hitter","def":"Always bats from the favorable side. Always treated as having platoon advantage."},
      ]},
      {"title":"WHAT IT'S OVER NINE THOUSAAAAAND","entries":[
        {"term":"WHAT IT IS","def":"Top 5 power plays of the day by composite SSJ Score, pinned above all main tab content. The absolute highest-priority targets on today's slate."},
        {"term":"HOW TO USE IT","def":"Swipe right to see all 5 cards. Each shows Zone, grade, DANGER, streaks, ISO, wOBA, and platoon at a glance. Start every session here."},
      ]},
      {"title":"SSJ MATCHUPS — FILTERS","entries":[
        {"term":"DANGER ONLY","def":"Hides every batter whose opposing pitcher VulnScore is below 70. Focus exclusively on the most exploitable pitching matchups."},
        {"term":"PLATOON ADV ONLY","def":"Filters to batters with confirmed opposite-hand platoon advantage only. Eliminates all same-side matchups. Combine with DANGER ONLY for the tightest filter stack."},
      ]},
      {"title":"FUSIONS","entries":[
        {"term":"HOW IT WORKS","def":"25 random pairs from the Top 50 SSJ Matchups. Both players in each Fusion share the full card view with all stats and projections."},
        {"term":"RE-FUSE","def":"Generates 25 brand new random pairs from the same Top 50 pool."},
        {"term":"ELITE","def":"Both players are STRONG (Super Saiyan) grade. Highest-quality parlay tier."},
        {"term":"SOLID","def":"At least one STRONG player. Strong parlay with one anchor."},
        {"term":"SAME GAME","def":"Both players from the same game and same lineup vs same pitcher. Correlated parlay — statistically the strongest Fusion type."},
      ]},
      {"title":"GAME FILTER DROPDOWN","entries":[
        {"term":"WHAT IT DOES","def":"Filters every view to a single game matchup. Use for single-game stacks or when you have conviction on a specific game. Clear with the CLEAR button."},
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
.si .sl{font-size:9px;letter-spacing:.12em;text-transform:uppercase}
.si .sv{font-size:13px;font-weight:700}
.ph{text-align:center;margin-bottom:5px}
.ph span{display:inline-block;font-size:8px;font-weight:700;letter-spacing:.18em;
  padding:2px 9px;border-radius:10px;background:rgba(255,255,255,.055)}
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
#rf{background:rgba(255,215,0,.1);border:1px solid rgba(255,215,0,.38);color:var(--gold);
  font-size:12px;font-weight:700;padding:9px 14px;border-radius:6px;cursor:pointer;
  letter-spacing:.08em;font-family:"Rajdhani",sans-serif;flex-shrink:0;margin-left:10px;
  box-shadow:0 0 10px rgba(255,215,0,.12)}
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
</style>
</head>
<body>
''')
    parts.append('<div id="hdr">\n')
    parts.append('  <div class="ghost">\u26a1</div>\n')
    parts.append('  <h1 class="t-glow">SSJ (THE ZONE) \u26a1</h1>\n')
    parts.append('  <div class="sub">' + today_str + ' \u00b7 MLB Matchup Intelligence</div>\n')
    parts.append('</div>\n\n')
    parts.append('<div id="spills"></div>\n\n')
    parts.append('''<div class="tab-row" id="tr1">
  <button class="tab" data-f="STRONG" onclick="sf(this)">\u26a1 SUPER SAIYAN</button>
  <button class="tab" data-f="MODERATE" onclick="sf(this)">BASE FORM</button>
  <button class="tab" data-f="BAD" onclick="sf(this)">BAD</button>
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
<nav id="dock">
  <a class="da" href="index.html"><span class="di">\U0001f4ca</span>Slate</a>
  <a class="da" href="k-report.html"><span class="di">\U0001f4cb</span>K Report</a>
  <a class="da" href="streaks.html"><span class="di">\U0001f525</span>Streaks</a>
  <a class="da act" href="scout.html"><span class="di">\u26a1</span>SSJ</a>
  <a class="da" href="record.html"><span class="di">\U0001f3c6</span>Record</a>
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
function gk(p){return [p.team,p.pTeam].sort().join(' \u00b7 ');}
function pl(b,t){if(b==='S')return{l:'S\u2192'+t,a:true};return{l:b+'\u2192'+t,a:b!==t};}
function sd2(v,thr,ic){
  if(!v||v===0)return{t:'\u2014',c:'rgba(255,255,255,.2)',s:''};
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
  if(p.grade==='STRONG'&&p.zone>=10)return'bglow';
  return'';
}
function bnc(p){return p.grade==='STRONG'?'#FFD700':(p.grade==='MODERATE'?'#AAAAAA':'#666');}
function rs(p,compact){
  var pt=pl(p.bats,p.throws),sl=slc(p.grade),sv=svc(p.grade),dc=dc2(p.grade);
  var vs=p.vulnScore,phR=p.projHits>=8.0,peR=p.projERA>=5.5;
  var phC=phR?'#FF6B6B':sv,peC=peR?'#FF6B6B':sv;
  var hit=sd2(p.hitStreak,4,'\U0001f525'),hr=sd2(p.hrStreak,2,'\u26a1'),hrr=sd2(p.hrrStreak,3,'\u26a1');
  var sz=compact?42:46,ba=ban(p),hs=p.hitStreak>=4||p.hrStreak>=2||p.hrrStreak>=3;
  return '<div class="ct">'+
    '<div class="bw '+ba+'" style="width:'+sz+'px;height:'+sz+'px;'+bws(p)+'">'+
      '<span class="bz" style="color:'+(p.grade==='STRONG'?'#FFD700':'#3a3a3a')+'">\u26a1</span>'+
      '<span class="bn" style="color:'+bnc(p)+';font-size:'+(compact?'18px':'21px')+'">'+p.zone+'</span>'+
      (hs?'<span class="bf">\U0001f525</span>':'')+
    '</div>'+
    '<div class="ci">'+
      '<div class="cn" style="color:'+nc(p.grade)+'">'+p.batter+
        ' <span style="font-size:11px;font-weight:700;color:rgba(255,215,0,.65);letter-spacing:.1em">'+p.team+'</span></div>'+
      '<div class="cm" style="color:'+(p.grade==='STRONG'?'rgba(255,255,255,.65)':'rgba(255,255,255,.5)')+'">'+
        'vs '+p.pitcher+' \u00b7 '+p.pTeam+' \u00b7 ERA '+p.era+'</div>'+
    '</div>'+
    '<div class="cr">'+
      '<span class="pt" style="color:'+(pt.a?'#FFD700':'rgba(255,255,255,.22)')+'">'+pt.l+(pt.a?' \u26a1':'')+'</span>'+
      '<span class="gt" style="'+gts(p.grade)+'">'+p.grade+'</span>'+
      (p.vulnScore>=70?'<span class="dt">\u26a0 DANGER</span>':'')+
    '</div>'+
  '</div>'+
  '<div class="sr" style="border-color:'+dc+'">'+
    '<div class="si"><div class="sl" style="color:'+sl+'">VULN</div><div class="sv" style="color:'+vc(vs)+'">'+vs+'</div></div>'+
    '<div class="si"><div class="sl" style="color:'+sl+'">PROJ H</div>'+
      '<div class="sv" style="color:'+phC+'">'+(p.pitcher==='TBD'?'\u2014':p.projHits)+'</div>'+(phR&&p.pitcher!=='TBD'?' \U0001f534':'')+' </div>'+
    '<div class="si"><div class="sl" style="color:'+sl+'">PROJ ERA</div>'+
      '<div class="sv" style="color:'+peC+'">'+(p.pitcher==='TBD'?'\u2014':p.projERA)+'</div>'+(peR&&p.pitcher!=='TBD'?' \U0001f534':'')+' </div>'+
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
  if(g1==='STRONG'&&g2==='STRONG')return{l:'\u26a1 ELITE',c:'#FFD700',b:'rgba(255,215,0,.18)'};
  if(g1==='STRONG'||g2==='STRONG')return{l:'\U0001f525 SOLID',c:'#FFA040',b:'rgba(255,140,0,.14)'};
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
    '<div class="fd"><span>\u26a1 + \u26a1</span></div>'+
    rs(p2,true)+
  '</div>';
}
function rglos(){
  return '<div id="gh" class="t-glow"><h2>\u26a1 POWER LEVELS</h2>'+
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
      '<div><div class="ft">FUU\u2026 SION\u2026 HAA!</div>'+
      '<div class="fs">25 RANDOM PAIRS \u00b7 TOP 50 SSJ MATCHUPS</div></div>'+
      '<button id="rf" onclick="rF()">\U0001f500 RE-FUSE</button>'+
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
      '<button class="fp" onclick="tD()" style="border:'+dn+';background:'+db+';color:'+dc+'">\u26a0 DANGER ONLY</button>'+
      '<button class="fp" onclick="tP()" style="border:'+pn+';background:'+pb+';color:'+pc+'">\u26a1 PLATOON ADV ONLY</button>'+
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
            '<span style="font-family:Bebas Neue,sans-serif;font-size:14px;color:#FFD700">\u26a1'+p.zone+'</span>'+
          '</div>'+
          '<div style="font-weight:700;font-size:13px;color:#FFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px">'+p.batter+'</div>'+
          '<div style="font-size:10px;color:rgba(255,215,0,.65);letter-spacing:.1em;margin-bottom:7px">'+p.team+'</div>'+
          '<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:7px">'+
            '<span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;background:'+(p.grade==='STRONG'?'rgba(255,215,0,.16)':'rgba(255,255,255,.08)')+';color:'+(p.grade==='STRONG'?'#FFD700':'#999')+'">'+p.grade+'</span>'+
            (iD?'<span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;background:rgba(255,80,80,.18);color:#FF6B6B">\u26a0</span>':'')+
            (hs?'<span style="font-size:10px">\U0001f525</span>':'')+
          '</div>'+
          '<div style="font-size:11px;color:rgba(255,255,255,.45);margin-bottom:3px">ISO <span style="color:#FFD700;font-weight:700">'+p.iso+'</span></div>'+
          '<div style="font-size:11px;color:rgba(255,255,255,.45);margin-bottom:3px">wOBA <span style="color:#FFD700;font-weight:700">'+p.woba+'</span></div>'+
          '<div style="font-size:11px;color:rgba(255,255,255,.4)">'+pt.l+(pt.a?' <span style="color:#FFD700">\u26a1</span>':'')+
          '</div>'+
        '</div>';
      }).join('');
      html+='<div id="o9k"><div class="o9t v-text">WHAT?! IT\'S OVER NINE THOUSAAAAAND!!</div>'+
        '<div class="o9s">Today\'s Top 5 Power Plays</div>'+
        '<div class="o9r">'+cards+'</div></div>';
    }
    if(feat.length)html+=sh('\u26a1 Featured Plays','Zone \u2265 10',true)+feat.map(function(p){return rc(p,null);}).join('');
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
            ['BAD',C.BAD,'#666','transparent']];
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
</script>
</body>
</html>
''')
    return ''.join(parts)
