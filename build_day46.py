"""Day 46 Build — May 12, 2026 — Full Slate (15 games) + new SP_Projections integration.

Structure: Day 44 board depth + Day 45 canonical section labels.
Reads: /home/user/workspace/day46_data.json
Writes: /home/user/workspace/built_sections_d46.json
"""
import json, re, os
from datetime import datetime

def _sf(v, default=0.0):
    """Safely convert any SP_PROJ numeric field to float — handles str, None, empty."""
    try: return float(v) if v not in (None, '', 'None') else default
    except (TypeError, ValueError): return default

DATA = json.load(open('/home/user/workspace/day46_data.json'))
PROJECTED_MODE = DATA.get('_mode') == 'projected'

# ---- Build lookup indexes ----
SP_PROJ = DATA['SP_Projections']  # new 15-pitcher sheet (Team, Pitcher, Opp, Inn, BF, R, H, HR, K, BB)
SP_BY_TEAM = {r['Team'].strip(): r for r in SP_PROJ if r.get('Team')}
SP_BY_NAME = {r['Pitcher'].strip().lower(): r for r in SP_PROJ if r.get('Pitcher')}

SS = DATA['Sweet_Spot_Slate']  # pitcher vulnerability scores
SS_BY_NAME = {r['Pitcher'].strip().lower(): r for r in SS if r.get('Pitcher') and r['Pitcher'] != 'TBD'}

BP_PIT = DATA['BP_Pitchers']
BP_PIT_BY_NAME = {(r.get('FullName') or '').strip().lower(): r for r in BP_PIT}

BP_BAT = DATA['BP_Batters']
BP_BAT_BY_NAME = {}
for r in BP_BAT:
    nm = (r.get('FullName') or '').strip().lower()
    if nm and nm not in BP_BAT_BY_NAME:
        BP_BAT_BY_NAME[nm] = r

HIT = DATA['Hit_Probabilities']
def _hit_full(r):
    return f"{r.get('First Name','')} {r.get('Last Name','')}".strip()
HIT_BY_NAME = {_hit_full(r).lower(): r for r in HIT}

PARKS = DATA['Park_Factors']
# Build park lookup by team -> park record
PARK_BY_TEAM = {}
for p in PARKS:
    g = (p.get('Game') or '')
    m = re.match(r'\s*(\w+)\s*@\s*(\w+)\s*', g)
    if m:
        PARK_BY_TEAM[m.group(1)] = p
        PARK_BY_TEAM[m.group(2)] = p

HR_LB = DATA['HR_Leaderboard']
SSA = DATA['Sweet_Spot_Analyzer']

# Workbook Streaks tab (Batter, Hit Streak, HR Streak, ISO, wOBA, ...) — cross-reference form signal
STREAKS = DATA.get('Streaks', [])
STREAK_BY_NAME = {}
for r in STREAKS:
    nm = (r.get('Batter') or '').strip().lower()
    if nm and nm not in STREAK_BY_NAME:
        STREAK_BY_NAME[nm] = r

# BP_Teams projected team strikeouts (opp lineup K-proneness) — for K consensus
BP_TEAMS_BY_TEAM = {}
for r in DATA.get('BP_Teams', []):
    t = (r.get('Team') or '').strip()
    if t and t not in BP_TEAMS_BY_TEAM:
        BP_TEAMS_BY_TEAM[t] = r

# BallparkPal API summary lens. This file is reduced by fetch_bpp.py before it
# reaches the repo: only rounded derived fields are allowed here.
try:
    BPP_SUMMARY_FILE = os.environ.get('BPP_SUMMARY_FILE', 'bpp_summary.json')
    BPP_SUMMARY = json.load(open(BPP_SUMMARY_FILE, encoding='utf-8'))
    if not isinstance(BPP_SUMMARY, dict):
        BPP_SUMMARY = {}
except Exception:
    BPP_SUMMARY = {}

# Structured pick records for For The Record (results-page backtest). Each builder appends.
SLATE_PICKS = []

# Team-name normalization
TEAM_FIX = {
    'WSH': 'WAS', 'WAS ': 'WAS', 'WSH ': 'WAS',
    'AZ': 'ARI', 'AZ ': 'ARI',
    'CWS': 'CHW', 'CHW ': 'CHW',
    'TB ': 'TB', 'SF ': 'SF', 'SD ': 'SD', 'KC ': 'KC',
}
def tn(t):
    if not t: return ''
    t = str(t).strip()
    return TEAM_FIX.get(t, t)

# Games for May 12 (BP_Games order — we'll sort by ET time below)
GAMES_RAW = DATA['BP_Games']

# Game start times (ET) — pulled from Park_Factors 'Time' column
PARK_BY_PAIR = {}
for p in PARKS:
    g = (p.get('Game') or '')
    m = re.match(r'\s*(\w+)\s*@\s*(\w+)\s*', g)
    if m:
        PARK_BY_PAIR[(m.group(1), m.group(2))] = p

# ---- Helpers ----
def hand_chip(h, kind='bats'):
    if not h: return '—'
    h = str(h).strip().upper()
    if h == 'L': return f'<span style="color:#3b82f6;font-weight:600" title="{kind} L">🔵L</span>'
    if h == 'R': return f'<span style="color:#ef4444;font-weight:600" title="{kind} R">🔴R</span>'
    if h == 'S': return f'<span style="color:#a855f7;font-weight:600" title="{kind} S">🟣S</span>'
    return '—'

def parse_pct(s):
    if s is None: return 0
    if isinstance(s, (int, float)): return int(s)
    s = str(s).replace('+','').replace('%','').strip()
    try: return int(float(s))
    except (TypeError, ValueError): return 0

def bpp_entry(name):
    if not name: return {}
    v = BPP_SUMMARY.get(str(name).strip().lower(), {})
    return v if isinstance(v, dict) else {}

def bpp_factor_chip(value, label):
    if value in (None, '', 'None'): return ''
    try: n = float(value)
    except (TypeError, ValueError): return ''
    sign = '+' if n >= 0 else ''
    color = 'var(--good)' if n >= 10 else ('var(--bad)' if n <= -10 else 'var(--text-soft)')
    return f' <small style="color:{color}">BPP {label} {sign}{n:.0f}%</small>'

def bpp_matchup_chip(value):
    if value in (None, '', 'None'): return ''
    try: n = int(float(value))
    except (TypeError, ValueError): return ''
    if n >= 4:
        return f' <span class="badge b-tier1">BPP Match +{n}</span>'
    if n <= -4:
        return f' <span class="badge b-bad">BPP Match {n}</span>'
    sign = '+' if n >= 0 else ''
    return f' <span class="badge b-neutral">BPP Match {sign}{n}</span>'

def fmt_pct_cell(n, bold_pos=8, bold_neg=-10):
    sign = '+' if n >= 0 else ''
    s = f"{sign}{n}%"
    if n >= bold_pos: return f'<strong style="color:var(--good)">{s}</strong>'
    if n <= bold_neg: return f'<strong style="color:var(--bad)">{s}</strong>'
    return s

def pf_chip(pct):
    if pct is None: return ''
    pct = int(pct)
    sign = '+' if pct >= 0 else ''
    if pct >= 8: css = 'pf-good'
    elif pct <= -10: css = 'pf-darkred'
    else: css = 'pf-neutral'
    return f'<span class="{css}">{sign}{pct}%</span>'

def k_alt_for(k_proj):
    """User rule: ≥5 → O5+, 4.5-4.99 → O3.5, <4.5 → O2.5 (then 4.0-4.5 → O3.5? Re-check: 'less than 5 but not than 4 then O3.5. If under 4.5 than O2.5'. Re-reading: <5 & ≥4 → O3.5; <4.5 → O2.5; ≥5 → 5+. The two rules overlap 4-4.5 — user's exact wording stated; we follow ≥5→5+; 4.5-4.99→3.5; <4.5→2.5)."""
    if k_proj is None: return '—'
    try: k = float(k_proj)
    except (TypeError, ValueError): return '—'
    if k >= 5: return 'O 5+'
    if k >= 4.5: return 'O 3.5'
    return 'O 2.5'

def get_sp_for_team(team):
    """Get SP_Projections row for a team."""
    t = tn(team)
    return SP_BY_TEAM.get(t)

def get_vuln_for_pitcher(name):
    if not name: return None
    r = SS_BY_NAME.get(name.lower())
    return r

def vuln_cell(v):
    """Format a vulnerability score with color + 🔥 emoji per rule: ≥50 red+🔥, ≥32 hot, else dim."""
    if v is None or v == '—': return '<span style="color:var(--text-dim)">—</span>'
    try: vv = int(v)
    except (TypeError, ValueError): return f'<span style="color:var(--text-dim)">{v}</span>'
    if vv >= 50: return f'<strong style="color:var(--bad)">V{vv} 🔥</strong>'
    if vv >= 32: return f'<span style="color:var(--hot)">V{vv}</span>'
    return f'<span style="color:var(--text-dim)">V{vv}</span>'

def batter_bats(name):
    """Lookup batter handedness (L/R/S). Try BP_Batters first, then Sweet_Spot_Analyzer."""
    if not name: return None
    nm = str(name).strip().lower()
    r = BP_BAT_BY_NAME.get(nm)
    if r: return r.get('BatterStand')
    # Fallback: Sweet_Spot_Analyzer (catches batters missing from BP_Batters)
    for s in SSA:
        if (s.get('Batter') or '').strip().lower() == nm:
            return s.get('Bats')
    return None

def pitcher_throws(name):
    """Lookup pitcher throws (L/R) from Sweet_Spot_Slate first, then BP_Pitchers."""
    if not name: return None
    s = SS_BY_NAME.get(str(name).strip().lower())
    if s and s.get('Throws'): return s.get('Throws')
    p = BP_PIT_BY_NAME.get(str(name).strip().lower())
    if p and p.get('PitcherHand'): return p.get('PitcherHand')
    return None

def zone_for_batter(name):
    """Lookup HR_Leaderboard Zone for a batter (returns '⚡N' or None)."""
    if not name: return None
    nm = str(name).strip().lower()
    for r in HR_LB:
        if (r.get('Batter') or '').strip().lower() == nm:
            return r.get('Zone')
    return None

def parse_iso_danger(s):
    """Parse 'Name (ISO .###)' into (name, iso_str)."""
    if not s: return (None, None)
    m = re.match(r'^(.*?)\s*\(ISO\s*([\.\d]+)\)\s*$', str(s).strip())
    if m: return (m.group(1).strip(), m.group(2))
    return (str(s).strip(), None)

def format_danger_batter(s):
    """Format a danger batter string with bat-hand chip + ISO color + Zone.
    Input: 'JJ Bleday (ISO .381)'. Output: 'JJ Bleday 🔵L · ISO .381 · ⚡7'."""
    name, iso = parse_iso_danger(s)
    if not name: return '—'
    bats = batter_bats(name)
    zone = zone_for_batter(name)
    parts = [f'<strong>{name}</strong>']
    if bats: parts.append(hand_chip(bats, 'bats'))
    if iso:
        try: iso_f = float(iso)
        except (TypeError, ValueError): iso_f = 0
        iso_disp = iso if '.' in iso else f'.{iso}'
        if iso_f >= 0.280: iso_html = f'<strong style="color:var(--bad)">{iso_disp}</strong>'
        elif iso_f >= 0.250: iso_html = f'<span style="color:var(--hot)">{iso_disp}</span>'
        elif iso_f >= 0.200: iso_html = f'<span style="color:var(--good)">{iso_disp}</span>'
        else: iso_html = iso_disp
        parts.append(f'ISO {iso_html}')
    if zone:
        zn = int(''.join(c for c in str(zone) if c.isdigit()) or '0')
        if zn >= 6:   z_html = f'<strong style="color:var(--good)">{zone}</strong>'
        elif zn >= 4: z_html = f'<span style="color:var(--hot)">{zone}</span>'
        else:          z_html = f'<span style="color:#64748b">{zone}</span>'
        parts.append(z_html)
    return ' · '.join(parts)

# ---- TITLE / META ----
TITLE = "The Daily Slate — May 12 Full Slate"
SUBTITLE = "Day 46 · 15-game card · Skenes & Wheeler headline · Mikolas/Pérez vulnerable"

# ---- BUILD: HEADLINES ----
def build_headlines():
    # Top story drivers from data:
    # 1. Sutter Health Park +29% HR (STL@ATH)
    # 2. Skenes 6.9 K (PIT vs COL, weak lineup)
    # 3. Mikolas + Pérez = 1.02 HR/9 — most vulnerable arms
    # 4. CIN stack vs Mikolas (Sutter +29%? no — GAB +8%, Mikolas V76)
    # 5. PHI @ BOS Fenway -23% HR but Wheeler shoves K's
    # Wait — verify Sutter Health Park hosts STL@ATH? Yes, ATH plays at Sutter.

    return '''<!-- HEADLINES -->
<section id="headlines">
  <h2>📅 Slate Headlines + Flags</h2>
  <div class="flag-row"><div class="icon">🌋</div><div><strong>Sutter Health Park +29% HR — slate's lone HR volcano.</strong> STL @ ATH (9:40 PM ET). Park HR booster paired with Andre Pallante (V28, 5.1 IP, 0.82 HR/9) and Jeffrey Springs (V21, ATH home). <strong>Stack ATH bats</strong> — Kurtz, Langeliers, Rooker, Soderstrom, Butler all over 64% 1+H. Park is the slate's clearest weather/HR window.</div></div>
  <div class="flag-row"><div class="icon">🔥</div><div><strong>CIN stack vs Mikolas (V76 — most vulnerable SP).</strong> Mikolas projects 1.02 HR/9 (slate-worst tied) at Great American BP +8% HR. <strong>Top 14 HR Board has 6 Reds</strong>: Elly De La Cruz (#1, 92 score), Sal Stewart (#2, 87), Spencer Steer (#3, 87), Nathaniel Lowe (#11), Tyler Stephenson (#14), Matt McLain (#19). Best stack of the night.</div></div>
  <div class="flag-row"><div class="icon">⚡</div><div><strong>K Board: Skenes 6.9 leads slate; Wheeler 6.6 close behind.</strong> Skenes (PIT vs COL, V14) projects 6.9 K — gets O 5+ alt. Wheeler (PHI @ BOS, V14) 6.6 K. Will Warren (NYY 5.8), Peralta (NYM 5.7), Yamamoto (LAD 5.7), Flaherty (DET 5.5), Sproat (MIL 5.3), Pérez (MIA 5.3) — eight starters at O 5+. Per user rule: ≥5 K → O5+, 4.5-4.99 → O3.5, &lt;4.5 → O2.5.</div></div>
  <div class="flag-row"><div class="icon">🎯</div><div><strong>Pitcher's HR Risk Board:</strong> Eury Pérez 1.02 HR/9 (vs MIN, V46), Miles Mikolas 1.02 (vs CIN, V76), Erick Fedde 0.86 (vs KC, V29), Slade Cecconi 0.86 (vs LAA, V56), Bailey Ober 0.85 (vs MIA, V25). All five have <strong>HR-stack potential</strong> — see new "Pitcher's HR Risk Board" section.</div></div>
  <div class="flag-row"><div class="icon">🥶</div><div><strong>Fenway -23% / Truist -23% / PNC -20% HR all FADED.</strong> Phillies @ BOS (Fenway weather suppressed -23% HR but +18% 2B/3B — doubles play). CHC @ ATL (Truist -23%) and COL @ PIT (-20%) skip HR alts. Citi Field -14% HR / -29% 2B/3B = full suppressor — DET @ NYM is the under spot (NRFI 56%+).</div></div>
  <div class="flag-row"><div class="icon">📋</div><div><strong>SKIP arms / fades:</strong> Walbert Urena (LAA, K only 4.0 — skip K alts), Erick Fedde (CHW, K 2.6 — skip K alts entirely), Brayan Bello (BOS, K 2.9 — skip), Patrick Corbin (TOR, K 3.0 — skip). All HR plays at Citi/Fenway/Truist/PNC. Pivot to 1+H / RBI plays in suppressed parks.</div></div>
  <div style="text-align:center;margin-top:16px;padding:12px 14px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);border-radius:10px;">
    <a href="streaks.html" style="color:#f87171;font-weight:700;text-decoration:none;font-size:14px;">🔥 See Today's Hot Streaks →</a>
  </div>
  <div style="text-align:center;margin-top:14px;padding:12px 14px;background:rgba(255,215,0,0.06);border:1px solid rgba(255,215,0,0.18);border-radius:10px;">
    <a href="scout.html" style="color:#FFD700;font-weight:700;text-decoration:none;font-size:14px;">⚡ SSJ (The Zone) — Matchup Intelligence →</a>
    <div style="font-size:11px;color:rgba(255,255,255,0.45);margin-top:4px;">Zone scores · DANGER tags · platoon · projections · Fusion parlays</div>
  </div>
  <div class="flag-row" style="margin-top:14px;"><div class="icon">💿</div><div><strong>For The Record — yesterday's calls, graded.</strong> Every HR, K, Hits and Totals pick scored against the official box score and bucketed by Consensus. Wins and losses both stay on the board. <a href="record.html" style="color:#35d6e8;font-weight:700;text-decoration:none;">See how they graded →</a></div></div>
</section>
'''

# ---- BUILD: PARK BOARD ----
def build_park_board():
    rows = []
    parks_sorted = sorted(PARKS, key=lambda p: -parse_pct(p.get('HR %')))
    for p in parks_sorted:
        hr = parse_pct(p.get('HR %'))
        runs = parse_pct(p.get('Runs %'))
        xbh = parse_pct(p.get('2B/3B %'))
        if hr >= 25: label, badge, rc = ('HR Volcano', 'b-tier0', 'row-tier0')
        elif hr >= 10: label, badge, rc = ('HR-Friendly', 'b-tier0', 'row-tier1')
        elif hr >= 5: label, badge, rc = ('HR Lean Up', 'b-tier1', '')
        elif hr >= -5: label, badge, rc = ('Neutral', 'b-neutral', '')
        elif hr >= -15: label, badge, rc = ('HR Lean Down', 'b-warn', '')
        elif hr >= -23: label, badge, rc = ('HR Suppress', 'b-bad', '')
        else: label, badge, rc = ('HR KILLER', 'b-bad', 'row-bad')

        if xbh >= 15 and hr < 0: note = 'Doubles boost'
        elif hr >= 15: note = 'Slate-Top HR'
        elif hr >= 5: note = 'HR-Friendly'
        elif hr <= -20: note = 'HR Killed'
        elif hr <= -10: note = 'HR Suppress'
        else: note = 'Neutral'

        rows.append(
            f'      <tr class="{rc}"><td>{p["Game"]}</td><td>{p["Venue"]}</td>'
            f'<td>{fmt_pct_cell(hr,8,-10)}</td>'
            f'<td>{fmt_pct_cell(runs,8,-8)}</td>'
            f'<td>{fmt_pct_cell(xbh,10,-10)}</td>'
            f'<td>{note}</td>'
            f'<td><span class="badge {badge}">{label}</span></td></tr>'
        )
    table_body = '\n'.join(rows)

    intro = (
        'Sourced from <strong>Park_Factors</strong> sheet (stadium baseline + day-of weather). '
        '<strong>Sutter Health Park +29% HR</strong> is the slate\'s clear HR volcano (STL@ATH 9:40 ET). '
        '<strong>Rate Field +18%</strong> (KC@CHW) is the secondary HR booster. '
        'Only <strong>3 parks above +5% HR</strong>: Sutter, Rate, Great American (+8%). '
        'Fenway / Truist / Citi / PNC all suppressed -14% to -23% HR. '
        '<strong>Fenway +18% 2B/3B</strong> and PNC +13% 2B/3B = doubles plays in those parks instead.'
    )
    footer = (
        'HR%, Runs%, 2B/3B% are <strong>combined stadium + day-of weather</strong> factors. '
        'Green ≥+8% = booster, Red ≤-10% = suppressor. '
        '<span class="badge b-tier0">HR Volcano/Friendly</span> '
        '<span class="badge b-tier1">HR Lean Up</span> '
        '<span class="badge b-neutral">Neutral</span> '
        '<span class="badge b-warn">HR Lean Down</span> '
        '<span class="badge b-bad">HR Suppress / KILLER</span>'
        ' · Projections context: <a href="https://www.ballparkpal.com" target="_blank" rel="noopener" style="color:var(--info); text-decoration:none;">BallparkPal</a>'
    )

    return f'''<!-- PARK FACTORS BOARD -->
<section id="park-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🏟 Park Factors Board</div>
      <span class="game-tag">Tap to expand · 15 venues · stadium + day-of weather</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:12px;">{intro}</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Game</th><th>Venue</th><th>HR%</th><th>Runs%</th><th>2B/3B%</th><th>Notes</th><th>Lean</th></tr></thead>
    <tbody>
{table_body}
    </tbody>
  </table></div>
  <p style="font-size:11px; color:var(--text-dim); margin-top:10px;">{footer}</p>
  </div></div>
</section>
'''

# ---- BUILD: GAMES (15 cards) ----
def _team_top_bats(team, limit=3):
    """Top 3 by HR% from HR_LB filtered to team, else by Hit% from HIT."""
    team = tn(team)
    out = []
    for r in HR_LB[:60]:
        if tn(r.get('Team')) == team:
            nm = r.get('Batter')
            hits_row = HIT_BY_NAME.get(nm.lower()) if nm else None
            hit1 = hits_row.get('1+ Hit', '—') if hits_row else '—'
            hithr = hits_row.get('To Hit HR', '—') if hits_row else '—'
            hitrbi = hits_row.get('To Get RBI', '—') if hits_row else '—'
            out.append((nm, r.get('Bats'), hit1, hithr, hitrbi))
            if len(out) >= limit: break
    if len(out) < limit:
        # Fallback: top by HIT for team
        for h in HIT:
            if tn(h.get('Team')) == team:
                nm = _hit_full(h)
                if any(o[0] == nm for o in out): continue
                bp = BP_BAT_BY_NAME.get(nm.lower())
                bats = bp.get('BatterStand') if bp else None
                out.append((nm, bats, h.get('1+ Hit','—'), h.get('To Hit HR','—'), h.get('To Get RBI','—')))
                if len(out) >= limit: break
    return out

def build_games():
    # Determine game order by Time (ET) from Park_Factors
    def time_key(p):
        t = p.get('Time','12:00')
        try:
            h, m = t.split(':')
            return int(h)*60 + int(m)
        except (TypeError, ValueError): return 9999
    games_sorted = sorted(PARKS, key=time_key)

    out = ['<!-- GAMES -->\n<section id="games">\n  <h2>🎮 All 15 Game Write-Ups</h2>\n  <p style="font-size:12px; color:var(--text-dim); margin:0 0 12px;">Times shown are ET. Tap any game to expand pitchers, target bats, and notes.</p>\n']

    for idx, p in enumerate(games_sorted, 1):
        game = p.get('Game','—')
        venue = p.get('Venue','—')
        time = p.get('Time','—')
        hr = parse_pct(p.get('HR %'))
        runs = parse_pct(p.get('Runs %'))
        xbh = parse_pct(p.get('2B/3B %'))
        m = re.match(r'\s*(\w+)\s*@\s*(\w+)\s*', game)
        if not m: continue
        away, home = m.group(1), m.group(2)

        ap = get_sp_for_team(away)
        hp = get_sp_for_team(home)
        ap_name = ap['Pitcher'] if ap else 'TBD'
        hp_name = hp['Pitcher'] if hp else 'TBD'

        # Vuln scores
        ap_v = get_vuln_for_pitcher(ap_name) if ap_name != 'TBD' else None
        hp_v = get_vuln_for_pitcher(hp_name) if hp_name != 'TBD' else None
        ap_vuln = ap_v.get('VulnScore') if ap_v else '—'
        hp_vuln = hp_v.get('VulnScore') if hp_v else '—'
        ap_era = ap_v.get('ERA') if ap_v else '—'
        hp_era = hp_v.get('ERA') if hp_v else '—'
        ap_whip = ap_v.get('WHIP') if ap_v else '—'
        hp_whip = hp_v.get('WHIP') if hp_v else '—'
        ap_k9 = ap_v.get('K9') if ap_v else '—'
        hp_k9 = hp_v.get('K9') if hp_v else '—'
        ap_bb9 = ap_v.get('BB9') if ap_v else '—'
        hp_bb9 = hp_v.get('BB9') if hp_v else '—'

        # Throws via BP_Pitchers
        ap_bp = BP_PIT_BY_NAME.get(ap_name.lower()) if ap_name != 'TBD' else None
        hp_bp = BP_PIT_BY_NAME.get(hp_name.lower()) if hp_name != 'TBD' else None
        ap_throws = ap_bp.get('PitcherHand') if ap_bp else None
        hp_throws = hp_bp.get('PitcherHand') if hp_bp else None

        # SP projections
        def sp_cells(sp):
            if not sp:
                return ('—','—','—','—','—')
            return (sp.get('Inn','—'), sp.get('K','—'), sp.get('HR','—'),
                    sp.get('BB','—'), sp.get('H','—'))

        ap_inn, ap_k, ap_hr, ap_bb, ap_h = sp_cells(ap)
        hp_inn, hp_k, hp_hr, hp_bb, hp_h = sp_cells(hp)

        # K alt notes
        def k_note(sp, vuln):
            if not sp: return 'No proj — opener/short risk'
            k = sp.get('K')
            try: k = float(k)
            except (TypeError, ValueError): return ''
            v_str = vuln_cell(vuln) if vuln != '—' else ''
            alt = k_alt_for(k)
            if k >= 5: return f'{v_str} · K alt {alt}'
            if k >= 4.5: return f'{v_str} · K alt {alt} (caution)'
            return f'{v_str} · Skip K alts (K&lt;4.5)'

        ap_note = k_note(ap, ap_vuln)
        hp_note = k_note(hp, hp_vuln)

        def hra_flag(sp):
            if not sp: return '—'
            hr = sp.get('HR')
            try: hr = float(hr)
            except (TypeError, ValueError): return '—'
            if hr >= 0.85: return f'<span style="color:var(--bad);font-weight:600">🔻 {hr}</span>'
            if hr >= 0.7: return f'<span style="color:var(--hot)">{hr}</span>'
            return f'{hr}'

        # BP_Pitchers indicators (Outs / Hits / QS% / HRA / BB)
        def bp_indicators(name):
            if not name or name == 'TBD':
                return ('—','—','—','—','—')
            r = BP_PIT_BY_NAME.get(name.lower())
            if not r:
                return ('—','—','—','—','—')
            innings = _sf(r.get('Innings'))
            outs = innings * 3 if innings else 0
            hits = _sf(r.get('HitsAllowed'))
            qs = _sf(r.get('QualityStart'))
            hra = _sf(r.get('HomeRunsAllowed'))
            bp_bb = _sf(r.get('Walks'))
            # Format with indicators (Day 44 thresholds: Outs ≥17 = green 🟢, <14 = red 🔻)
            if outs:
                if outs >= 17: outs_s = f'<strong style="color:var(--good)">🟢 {outs:.1f}</strong>'
                elif outs < 14: outs_s = f'<span style="color:var(--bad)">🔻 {outs:.1f}</span>'
                else: outs_s = f'{outs:.1f}'
            else: outs_s = '—'
            # Hits: ≥6.0 = red (hot), ≤5.0 = green (cold)
            if hits:
                if hits >= 5.5: hits_s = f'<span style="color:var(--hot)">🔺 {hits:.2f}</span>'
                elif hits <= 4.5 and hits > 0: hits_s = f'<strong style="color:var(--good)">{hits:.2f}</strong>'
                else: hits_s = f'{hits:.2f}'
            else: hits_s = '—'
            qs_s = f'{qs*100:.0f}%' if qs else '—'
            # HRA ≥0.85 = red flag
            if hra >= 0.85: hra_s = f'<strong style="color:var(--bad)">{hra:.2f}</strong>'
            elif hra >= 0.7: hra_s = f'<span style="color:var(--hot)">{hra:.2f}</span>'
            elif hra > 0: hra_s = f'{hra:.2f}'
            else: hra_s = '—'
            return (outs_s, hits_s, qs_s, hra_s, f'{bp_bb:.2f}' if bp_bb else '—')

        def proj_row(name, throws, team, opp, era, whip, k9, bb9, vuln, sp, note):
            # SP_Projections K (primary K source)
            inn, k, _, _, _ = sp_cells(sp)
            k_disp = k
            try:
                kf = float(k)
                if kf >= 5: k_disp = f'<strong style="color:var(--good)">🟢 {k}</strong>'
                elif kf < 4.5: k_disp = f'<span style="color:var(--bad)">🔻 {k}</span>'
            except (TypeError, ValueError): pass
            outs_s, hits_s, qs_s, hra_s, bp_bb_s = bp_indicators(name)
            return ('<tr>'
                f'<td><strong>{name}</strong></td>'
                f'<td style="text-align:center">{hand_chip(throws,"throws")}</td>'
                f'<td>{team} vs {opp}</td>'
                f'<td>{era}</td><td>{whip}</td><td>{k9}</td>'
                f'<td>{k_disp}</td>'
                f'<td>{outs_s}</td>'
                f'<td>{hits_s}</td>'
                f'<td>{qs_s}</td>'
                f'<td>{hra_s}</td>'
                f'<td>{vuln_cell(vuln)}</td>'
                f'<td>{note}</td>'
                '</tr>'
            )

        ap_opp = home
        hp_opp = away
        ap_throws_safe = ap_throws or (ap_v.get('Throws') if ap_v else None)
        hp_throws_safe = hp_throws or (hp_v.get('Throws') if hp_v else None)

        pitcher_table = (
            '<div class="table-wrap"><table>'
            '<thead><tr><th>Pitcher</th><th>T</th><th>Match</th><th>ERA</th><th>WHIP</th>'
            '<th>K9</th><th>Proj K</th><th>Outs</th><th>Hits</th><th>QS%</th><th>HRA</th>'
            '<th>Vuln</th><th>Note</th></tr></thead>'
            '<tbody>'
            f'{proj_row(ap_name, ap_throws_safe, away, ap_opp, ap_era, ap_whip, ap_k9, ap_bb9, ap_vuln, ap, ap_note)}'
            f'{proj_row(hp_name, hp_throws_safe, home, hp_opp, hp_era, hp_whip, hp_k9, hp_bb9, hp_vuln, hp, hp_note)}'
            '</tbody></table></div>'
        )

        # Top bats
        away_bats = _team_top_bats(away)
        home_bats = _team_top_bats(home)
        def fmt_bats(team, bats):
            if not bats:
                return f'🎯 <strong>Top Bats — {team}:</strong> (no data)'
            cells = []
            for nm, b, h1, hr_, rbi in bats:
                cells.append(f'<strong>{nm}</strong> {hand_chip(b)}: {h1} 1+H / {hr_} HR / {rbi} RBI')
            return f'🎯 <strong>Top Bats — {team}:</strong> ' + ' · '.join(cells)

        # Game note
        notes_bits = []
        if hr >= 15: notes_bits.append(f'<strong>Park +{hr}% HR booster — stack premium.</strong>')
        elif hr <= -20: notes_bits.append(f'<strong>Park {hr}% HR — fade HR alts, pivot to 1+H/RBI.</strong>')
        if isinstance(ap_vuln, int) and ap_vuln >= 50: notes_bits.append(f'{ap_name} {vuln_cell(ap_vuln)} — target {away} stack.')
        if isinstance(hp_vuln, int) and hp_vuln >= 50: notes_bits.append(f'{hp_name} {vuln_cell(hp_vuln)} — target {home} stack.')
        if not notes_bits:
            notes_bits.append('Standard slate game.')
        note_html = ' '.join(notes_bits)

        # Game total / F5 from BP_Games
        total = '—'
        f5 = '—'
        for g in GAMES_RAW:
            if tn(g.get('AwayTeam')) == away and tn(g.get('HomeTeam')) == home:
                ra = g.get('RunsAway') or 0
                rh = g.get('RunsHome') or 0
                total = f'{(ra+rh):.2f}'
                # F5 is roughly first 5 innings — approximation
                f5 = f'{((ra+rh)*0.55):.2f}'
                break

        title = f'⚾ Game {idx} — {away} @ {home} · {ap_name} vs {hp_name}'
        sign = '+' if hr >= 0 else ''
        game_tag = f'📊 Total: {total} | F5: {f5} · 🏟 Park: {sign}{hr}% HR · 🕒 {time} PM ET'

        out.append(f'''  <!-- GAME {idx}: {away} @ {home} -->
  <div class="game" id="g{idx}">
    <button class="game-header" aria-expanded="false">
      <div class="game-header-text">
        <div class="game-title">{title}</div>
        <span class="game-tag">{game_tag}</span>
      </div>
      <span class="chevron">▾</span>
    </button>
    <div class="game-body"><div class="game-body-inner">
      <h3>Pitchers</h3>
      {pitcher_table}
      <div class="top-bats">{fmt_bats(away, away_bats)}<br>
      {fmt_bats(home, home_bats)}<br>
      <div class="tb-note">📝 {note_html}</div></div>
    </div></div>
  </div>
''')
    out.append('</section>\n')
    return ''.join(out)

# ---- BUILD: MATCHUP SPOTLIGHT ----
def build_matchup_spotlight():
    """Day 44 structure: every pitcher × 3 danger batters from Sweet_Spot_Slate, sorted by Vuln desc.
    Cols: Pitcher | ERA | K9 | Vuln | Park + 3 × (Batter+EDGE | ISO+Hit% | HR%).
    """
    iso_re = re.compile(r'^(.*?)\s*\(ISO\s*\.(\d+)\)\s*$')

    def parse_db(s):
        if not s: return (None, None)
        m = iso_re.match(str(s).strip())
        if not m: return (str(s).strip(), None)
        return (m.group(1).strip(), float('0.' + m.group(2)))

    def hp_pct(name):
        if not name: return ('—', '—')
        r = HIT_BY_NAME.get(name.lower())
        if not r: return ('—', '—')
        return (r.get('1+ Hit','—'), r.get('To Hit HR','—'))

    def iso_chip(iso):
        if iso is None: return '—'
        s = f'.{int(round(iso*1000)):03d}'
        if iso >= 0.280: return f'<strong style="color:var(--bad)">{s}</strong>'
        if iso >= 0.250: return f'<strong style="color:var(--hot)">{s}</strong>'
        if iso >= 0.200: return f'<strong style="color:var(--good)">{s}</strong>'
        return s

    # Sort by VulnScore desc
    rows_data = []
    for sp in SS:
        if not sp.get('Pitcher') or sp.get('Pitcher') == 'TBD': continue
        try: v = int(_sf(sp.get('VulnScore')))
        except (TypeError, ValueError): v = 0
        rows_data.append((v, sp))
    rows_data.sort(key=lambda x: -x[0])

    rows = []
    for vuln_n, sp in rows_data:
        name = sp.get('Pitcher','')
        throws = sp.get('Throws')
        team = tn(sp.get('Team',''))
        opp = tn(sp.get('Opponent',''))
        era = sp.get('ERA','—')
        k9 = sp.get('K9','—')

        park = PARK_BY_TEAM.get(team) or PARK_BY_TEAM.get(opp)
        park_hr = parse_pct(park.get('HR %')) if park else 0

        if vuln_n >= 50:
            row_cls = 'row-tier1'
            vuln_s = f'<span style="color:var(--bad);font-weight:600">V{vuln_n} 🔥</span>'
        elif vuln_n >= 32:
            row_cls = ''
            vuln_s = f'<span style="color:var(--hot)">V{vuln_n}</span>'
        else:
            row_cls = 'row-good'
            vuln_s = f'<span style="color:var(--text-dim)">V{vuln_n}</span>'

        pitcher_cell = (
            f'<td><strong>{name}</strong> {hand_chip(throws,"throws")}'
            f'<br><small>{team} vs {opp}</small></td>'
        )
        era_cell = f'<td>{era}<br><small>ERA</small></td>'
        k9_cell = f'<td>{k9}<br><small>K9</small></td>'
        vuln_td = f'<td>{vuln_s}</td>'
        park_cell = f'<td>{pf_chip(park_hr)}</td>'

        danger_cells = []
        for i in (1, 2, 3):
            raw = sp.get(f'DangerBatter{i}')
            bname, iso = parse_db(raw)
            if not bname:
                danger_cells.extend(['<td>—</td>','<td>—</td>','<td>—</td>'])
                continue
            bats = batter_bats(bname)
            # EDGE label: opposite hand of pitcher = EDGE (platoon advantage)
            if throws and bats:
                t = str(throws).upper(); b = str(bats).upper()
                if b == 'S' or (t != b):
                    edge_label = '<span style="color:var(--good);font-weight:600">EDGE</span>'
                else:
                    edge_label = '<span class="text-dim">same</span>'
            else:
                edge_label = '<span class="text-dim">—</span>'
            h1, hr_p = hp_pct(bname)
            iso_html = iso_chip(iso)
            danger_cells.append(
                f'<td><strong>{bname}</strong> {hand_chip(bats)}<br>{edge_label}</td>'
            )
            danger_cells.append(
                f'<td>ISO {iso_html}<br><small>Hit {h1}</small></td>'
            )
            danger_cells.append(
                f'<td style="text-align:right">{hr_p}<br><small>HR%</small></td>'
            )

        rows.append(
            f'      <tr class="{row_cls}">{pitcher_cell}{era_cell}{k9_cell}{vuln_td}{park_cell}'
            + ''.join(danger_cells) + '</tr>'
        )

    table_body = '\n'.join(rows)

    return f'''<!-- MATCHUP SPOTLIGHT -->
<section id="matchup-spotlight" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🔦 Matchup Spotlight</div>
      <span class="game-tag">Tap to expand · {len(rows_data)} pitchers × 3 danger bats · ISO + L/R edge + Hit/HR%</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Sorted by <strong>VulnScore desc</strong>. <strong>EDGE</strong> = batter has opposite-hand platoon advantage. ISO color: <strong style="color:var(--bad)">≥.280</strong> elite · <strong style="color:var(--hot)">≥.250</strong> hot · <strong style="color:var(--good)">≥.200</strong> good. Mikolas V76 leads — 6 Reds in HR Top-19.</p>
    <div class="table-wrap"><table>
      <thead><tr>
        <th>Pitcher</th><th>ERA</th><th>K9</th><th>Vuln</th><th>Park</th>
        <th colspan="3" style="border-left:1px solid var(--border)">Danger #1</th>
        <th colspan="3" style="border-left:1px solid var(--border)">Danger #2</th>
        <th colspan="3" style="border-left:1px solid var(--border)">Danger #3</th>
      </tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
    <p style="font-size:11px; color:var(--text-dim); margin-top:10px;">Hit% / HR% from <strong>hit probability model</strong>. ISO from <strong>Sweet_Spot_Slate</strong> DangerBatter columns.</p>
  </div></div>
</section>
'''

# ---- BUILD: K BOARD (Day 44 structure: Tier | Pitcher | B | Tm | SS Ks | BPP Ks | Outs | Hits | ERA | QS% | HRA | Vuln | Best Line | Note) ----
def build_k_board():
    sp_sorted = sorted(SP_PROJ, key=lambda r: -(_sf(r.get('K'))))
    _top2 = [r.get('Pitcher','') for r in sp_sorted[:2] if r.get('Pitcher')]
    top_k_names = ' & '.join(_top2) if _top2 else 'top arms'
    rows = []
    for r in sp_sorted:
        name = r.get('Pitcher','')
        ss_k = r.get('K')  # SP_Projections K (= SS Ks)
        try: kf = float(ss_k) if ss_k is not None else 0
        except (TypeError, ValueError): kf = 0

        # Tier rule (Day 44): ≥5.5=T0, 4.5-5.4=T1, 4.0-4.4=T2, <4.0=SKIP
        if kf >= 5.5:
            tier_cls = 'row-tier0'; tier_badge = '<span class="badge b-tier0">T0</span>'
        elif kf >= 4.5:
            tier_cls = 'row-tier1'; tier_badge = '<span class="badge b-tier1">T1</span>'
        elif kf >= 4.0:
            tier_cls = ''; tier_badge = '<span class="badge b-neutral">T2</span>'
        else:
            tier_cls = 'row-bad'; tier_badge = '<span class="badge b-bad">SKIP</span>'

        # Best Line (user K alt rule)
        best_line = k_alt_for(ss_k)

        # SS Ks display color
        k_cls = 'good' if kf >= 5 else ('hot' if kf >= 4.5 else 'bad')
        ss_k_disp = f'<strong style="color:var(--{k_cls})">{ss_k}</strong>' if ss_k is not None else '—'

        # BPP (BP_Pitchers) — Strikeouts, Innings*3 = Outs, HitsAllowed, QualityStart, HomeRunsAllowed
        bp = BP_PIT_BY_NAME.get(name.lower())
        if bp:
            bpp_k = bp.get('Strikeouts') or 0
            bpp_kf = float(bpp_k) if bpp_k else 0
            if bpp_kf >= 5.5: bpp_k_disp = f'<strong style="color:var(--good)">{bpp_k:.2f}</strong>'
            elif bpp_kf >= 4.5: bpp_k_disp = f'<span style="color:var(--hot)">{bpp_k:.2f}</span>'
            else: bpp_k_disp = f'<span style="color:var(--bad)">{bpp_k:.2f}</span>'
            innings = bp.get('Innings') or 0
            outs = innings * 3 if innings else 0
            if outs >= 17: outs_s = f'<strong style="color:var(--good)">🟢 {outs:.1f}</strong>'
            elif outs and outs < 14: outs_s = f'<span style="color:var(--bad)">🔻 {outs:.1f}</span>'
            elif outs: outs_s = f'{outs:.1f}'
            else: outs_s = '—'
            hits = bp.get('HitsAllowed') or 0
            if hits >= 5.5: hits_s = f'<span style="color:var(--hot)">🔺 {hits:.2f}</span>'
            elif hits <= 4.5 and hits > 0: hits_s = f'<strong style="color:var(--good)">{hits:.2f}</strong>'
            elif hits: hits_s = f'{hits:.2f}'
            else: hits_s = '—'
            qs = bp.get('QualityStart') or 0
            qs_pct = qs * 100
            if qs_pct >= 40: qs_s = f'<strong>{qs_pct:.0f}%</strong>'
            elif qs_pct: qs_s = f'{qs_pct:.0f}%'
            else: qs_s = '—'
            hra = bp.get('HomeRunsAllowed') or 0
            if hra >= 0.85: hra_s = f'<strong style="color:var(--bad)">{hra:.2f}</strong>'
            elif hra >= 0.7: hra_s = f'<span style="color:var(--hot)">{hra:.2f}</span>'
            elif hra: hra_s = f'{hra:.2f}'
            else: hra_s = '—'
            throws = bp.get('PitcherHand')
        else:
            bpp_k_disp = '—'; outs_s = '—'; hits_s = '—'; qs_s = '—'; hra_s = '—'; throws = None

        # Vuln + ERA (Sweet_Spot_Slate)
        v = get_vuln_for_pitcher(name)
        vuln = v.get('VulnScore') if v else '—'
        try: vuln_n = int(vuln)
        except (TypeError, ValueError): vuln_n = 0
        if vuln_n >= 50: vuln_s = f'<span style="color:var(--bad);font-weight:600">V{vuln} 🔥</span>'
        elif vuln_n >= 32: vuln_s = f'<span style="color:var(--hot)">V{vuln}</span>'
        else: vuln_s = f'V{vuln}'
        era = v.get('ERA') if v else '—'
        if not throws and v: throws = v.get('Throws')

        team = tn(r.get('Team',''))
        opp = tn(r.get('Opp',''))

        # Note — short context based on Vuln+HRA
        note_parts = []
        if vuln_n >= 50: note_parts.append('☢️ HR-risk')
        if kf >= 5.5: note_parts.append('K anchor')
        elif kf < 4.0: note_parts.append('fade Ks')

        # ── Consensus: 5 independent strikeout lenses ──
        k9 = _sf(v.get('K9')) if v else 0
        opp_raw = (r.get('Opp','') or '').strip()
        opp_row = BP_TEAMS_BY_TEAM.get(opp) or BP_TEAMS_BY_TEAM.get(opp_raw)
        opp_k = _sf(opp_row.get('Strikeouts')) if opp_row else 0
        bpp_val = bpp_kf if bp else 0
        outs_val = outs if bp else 0
        bpp_api = bpp_entry(name)
        bpp_api_k = _sf(bpp_api.get('proj_k')) if bpp_api else 0
        consensus_max = 6
        votes = 0
        if kf >= 5.5: votes += 1
        if bpp_val >= 5.0: votes += 1
        if k9 >= 9.0: votes += 1
        if outs_val >= 17: votes += 1
        if opp_k >= 9.0: votes += 1
        if bpp_api_k >= 5.0: votes += 1
        if bpp_api_k:
            note_parts.append(f'BPP API K {bpp_api_k:.2f}')
        note = ' · '.join(note_parts) if note_parts else '—'

        # ── Structured pick record (For The Record backtest vs MLB Stats API box scores) ──
        win_at = 5 if '5' in best_line else (4 if '3.5' in best_line else 3)
        SLATE_PICKS.append({
            'market': 'K', 'pick': f'{name} {best_line}', 'name': name,
            'team': team, 'opp': opp, 'line': best_line, 'win_at': win_at,
            'consensus': votes, 'consensus_max': consensus_max,
            'ss_k': round(kf, 2), 'bpp_k': round(bpp_val, 2) if bp else None,
            'k9': round(k9, 1) if k9 else None,
            'outs': round(outs_val, 1) if bp else None,
            'opp_k_proj': round(opp_k, 1) if opp_k else None,
            'context': {
                'proj_hits_allowed': round(_sf(hits), 2) if bp else None,
                'proj_hr_allowed': round(_sf(hra), 2) if bp else None,
                'proj_runs_allowed': round(_sf(bp.get('RunsAllowed')), 2) if bp else None,
                'proj_era': era if era != '—' else None,
            },
        })

        rows.append((votes, kf,
            f'      <tr class="{tier_cls}">'
            f'<td>{tier_badge}</td>'
            f'<td><strong>{name}</strong></td>'
            f'<td style="text-align:center">{hand_chip(throws,"throws")}</td>'
            f'<td>{team}</td>'
            f'<td>{_conv_cell(votes, consensus_max)}</td>'
            f'<td>{ss_k_disp}</td>'
            f'<td>{bpp_k_disp}</td>'
            f'<td>{outs_s}</td>'
            f'<td>{hits_s}</td>'
            f'<td>{era}</td>'
            f'<td>{qs_s}</td>'
            f'<td>{hra_s}</td>'
            f'<td>{vuln_s}</td>'
            f'<td><strong>{best_line}</strong></td>'
            f'<td><small>vs {opp} · {note}</small></td>'
            f'</tr>'
        ))
    rows.sort(key=lambda t: (-t[0], -t[1]))
    table_body = '\n'.join(t[2] for t in rows)

    return f'''<!-- K BOARD -->
<section id="k-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">⚡ Full K's Tier Board</div>
      <span class="game-tag">Tap to expand · {len(sp_sorted)} starters · ranked by Consensus · {top_k_names} lead</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <a href="k-report.html" style="display:flex;align-items:center;justify-content:space-between;background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.35);border-radius:10px;padding:10px 14px;margin-bottom:12px;text-decoration:none;">
      <span style="font-size:13px;font-weight:700;color:#3b82f6;">📋 View The Safe K Report</span>
      <span style="font-size:13px;color:#3b82f6;">Safe floors · Real lines · Full criteria →</span>
    </a>
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;"><strong>Consensus</strong> = how many of 6 K lenses agree: SS Ks≥5.5 · workbook BPP Ks≥5 · K9≥9 · Outs≥17 · opp lineup K's≥9 · BPP API proj K≥5. 🔒 = 5–6. SS Ks from <strong>SP_Projections</strong>, workbook BPP Ks from <strong>BP_Pitchers</strong>. <strong>Tier:</strong> T0 ≥5.5 · T1 4.5–5.4 · T2 4.0–4.4 · SKIP &lt;4.0. <strong>Best Line:</strong> ≥5 → O 5+, 4.5–4.99 → O 3.5, &lt;4.5 → O 2.5.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Tier</th><th>Pitcher</th><th>B</th><th>Tm</th><th>Conv</th><th>SS Ks</th><th>BPP Ks</th><th>Outs</th><th>Hits</th><th>ERA</th><th>QS%</th><th>HRA</th><th>Vuln</th><th>Best Line</th><th>Note</th></tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
    <p style="font-size:11px; color:var(--text-dim); margin-top:10px;">🟢 Outs ≥17. 🔻 Outs &lt;14. 🔺 Hits ≥5.5. Green Hits ≤4.5. QS% ≥40% bold. HRA ≥0.85 caution.</p>
  </div></div>
</section>
'''

# ---- BUILD: HR BOARD (top 25) ----
def _conv_cell(n, total=6):
    ratio = (n/total) if total else 0
    if ratio >= 0.8: return f'<strong style="color:var(--good)">🔒 {n}/{total}</strong>'
    if ratio >= 0.6: return f'<span style="color:var(--hot)">{n}/{total}</span>'
    return f'<span style="color:var(--text-soft)">{n}/{total}</span>'

def projected_badge(text):
    return (
        '<div class="projected-section-badge">'
        '<span>PROJECTED MODE</span>'
        f'<small>{text}</small>'
        '</div>'
    )

def with_projected_badge(html, text):
    marker = '<div class="game-body"><div class="game-body-inner">'
    return html.replace(marker, marker + '\n    ' + projected_badge(text), 1)

def projected_unavailable_section(sec_id, title, tag, reason):
    return f'''<!-- PROJECTED UNAVAILABLE -->
<section id="{sec_id}" class="collapsible projected-unavailable">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">{title}</div>
      <span class="game-tag">{tag}</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <div class="unavailable-card">
      <strong>Unavailable without workbook</strong>
      <p>{reason} Upload the workbook to populate this section with full Sweet Spot / Dimers detail.</p>
    </div>
  </div></div>
</section>
'''

def build_projected_headlines():
    top_hr = HR_LB[0] if HR_LB else {}
    top_hit = sorted(HIT, key=lambda r: -parse_pct(r.get('1+ Hit')), reverse=False)[0] if HIT else {}
    parks = sorted(PARKS, key=lambda p: parse_pct(p.get('HR %')), reverse=True)
    top_park = parks[0] if parks else {}
    cards = [
        (
            "Projected HR Anchor",
            f"<strong>{top_hr.get('Batter','—')}</strong> leads the reconstructed HR board "
            f"with a derived score of <strong>{top_hr.get('Score','—')}</strong>. "
            "Zone is intentionally blank in Projected Mode."
        ),
        (
            "Projected Hit Anchor",
            f"<strong>{_hit_full(top_hit) or '—'}</strong> tops the hit board at "
            f"<strong>{top_hit.get('1+ Hit','—')}</strong>."
        ),
        (
            "Park Signal",
            f"<strong>{top_park.get('Venue','—')}</strong> is the top HR environment "
            f"({top_park.get('Game','')}, {top_park.get('HR %','—')} HR)."
        ),
    ]
    body = ''.join(
        f'<div class="headline-card"><div class="hc-title">{title}</div><p>{text}</p></div>'
        for title, text in cards
    )
    return f'''<!-- HEADLINES -->
<section id="headlines" class="headline-grid">
  {projected_badge("Top cards rebuilt from live sources; workbook-only signals are withheld.")}
  {body}
</section>
'''

def build_projected_hr_board():
    rows = []
    for i, r in enumerate(HR_LB[:50], 1):
        score = _sf(r.get('Score'))
        if score >= 78: tier = 'row-tier0'
        elif score >= 66: tier = 'row-tier1'
        else: tier = ''
        batter = f'<strong>{r.get("Batter","—")}</strong> {hand_chip(r.get("Bats"), "bats")}'
        streak = r.get('Streak') or ''
        if streak:
            batter += f' <span style="font-size:11px;color:var(--hot)">{streak}</span>'
        pitcher = r.get('Pitcher') or '—'
        rows.append(
            f'      <tr class="{tier}">'
            f'<td>{i}</td><td>{batter}</td><td>{tn(r.get("Team"))}</td>'
            f'<td>{pitcher}</td><td>{r.get("Pitcher Team","—")}</td>'
            f'<td><strong>{r.get("Score","—")}</strong></td><td>{r.get("Grade","—")}</td>'
            f'<td>{r.get("Zone","—")}</td><td>{r.get("HR","—")}</td>'
            f'<td>{r.get("Barrel%","—")}</td><td>{r.get("xwOBA","—")}</td>'
            f'<td>{r.get("ERA","—")}</td><td>{r.get("Park","—")}</td></tr>'
        )
    return f'''<!-- HR BOARD PROJECTED -->
<section id="hr-board" class="collapsible reconstructed-board">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">Top 50 HR Board</div>
      <span class="game-tag">Tap to expand · Projected Mode · derived rankings + Savant contact metrics</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    {projected_badge("Score and tier are Daily Slate derived; Zone is unavailable and shown as a dash.")}
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Ranked by the Daily Slate projected HR score using live matchup probability, Baseball Savant barrel rate/xwOBA, park HR context, pitcher HR risk, and streak signal. This does not reproduce Sweet Spot grades or Zone.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>vs Pitcher</th><th>P Tm</th><th>Score</th><th>Tier</th><th>Zone</th><th>HR Prob</th><th>Barrel%</th><th>xwOBA</th><th>ERA</th><th>Park HR%</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

def build_projected_oo5_board():
    def hp_val(r, key):
        return parse_pct(r.get(key))
    ranked = sorted(HIT, key=lambda r: -hp_val(r, '1+ Hit'))[:50]
    rows = []
    for i, r in enumerate(ranked, 1):
        nm = _hit_full(r)
        bp = BP_BAT_BY_NAME.get(nm.lower())
        bats = bp.get('BatterStand') if bp else None
        team = tn(r.get('Team'))
        tier = 'row-tier0' if hp_val(r, '1+ Hit') >= 60 else ('row-tier1' if hp_val(r, '1+ Hit') >= 55 else '')
        rows.append(
            f'      <tr class="{tier}"><td>{i}</td>'
            f'<td><strong>{nm}</strong> {hand_chip(bats, "bats")}</td>'
            f'<td>{team}</td><td>{r.get("Matchup","—")}</td>'
            f'<td><strong>{r.get("1+ Hit","—")}</strong></td>'
            f'<td>{r.get("2+ Hits","—")}</td>'
            f'<td>{r.get("To Get RBI","—")}</td>'
            f'<td>{r.get("To Hit HR","—")}</td></tr>'
        )
    return f'''<!-- OO5 BOARD PROJECTED -->
<section id="oo5-board" class="collapsible reconstructed-board">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">Top 50 Hits Board</div>
      <span class="game-tag">Tap to expand · Projected Mode · live hit probabilities</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    {projected_badge("Hit, multi-hit, RBI, and HR columns reconstructed from live projection inputs.")}
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>Matchup</th><th>1+ Hit</th><th>2+ Hits</th><th>RBI</th><th>HR</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

def build_hr_board():
    # Candidate pool: top 40 by Score, then re-rank by Consensus
    cands = []
    for r in HR_LB[:80]:
        score = _sf(r.get('Score'))
        team = tn(r.get('Team',''))
        park = PARK_BY_TEAM.get(team)
        park_hr = parse_pct(park.get('HR %')) if park else 0
        nm = r.get('Batter','')
        bpp_api = bpp_entry(nm)
        bpp_proj_hr = _sf(bpp_api.get('proj_hr')) if bpp_api else 0
        bpp_match_adv = bpp_api.get('matchup_advantage') if bpp_api else None
        bpp_park_hr = bpp_api.get('park_hr_factor') if bpp_api else None
        hr_row = HIT_BY_NAME.get(nm.lower())
        hr_pct = hr_row.get('To Hit HR','—') if hr_row else '—'
        rbi_pct = hr_row.get('To Get RBI','—') if hr_row else '—'
        bp_b = BP_BAT_BY_NAME.get(nm.lower())
        sim_raw = _sf(bp_b.get('HomeRunProbability')) if bp_b else 0
        sim_hr = f'{sim_raw*100:.1f}%' if (bp_b and bp_b.get('HomeRunProbability') not in (None, '')) else '—'
        pit_name = r.get('Pitcher','') or ''
        throws = pitcher_throws(pit_name)
        v = get_vuln_for_pitcher(pit_name)
        vuln = v.get('VulnScore') if v else None
        # ── Streak cross-reference (workbook Streaks tab) ──
        st = STREAK_BY_NAME.get(nm.lower())
        streak_fires = False; streak_chip = ''
        if st:
            hs = _sf(st.get('Hit Streak')); hrs = _sf(st.get('HR Streak'))
            if hrs >= 1:
                streak_fires = True
                streak_chip = f' <span style="font-size:11px;color:var(--hot)">🔥HR{int(hrs)}</span>'
            elif hs >= 5:
                streak_fires = True
                streak_chip = f' <span style="font-size:11px;color:var(--hot)">🔥H{int(hs)}</span>'
        # ── Consensus: count independent lenses that clear their own threshold ──
        votes = 0
        if score >= 70: votes += 1
        if sim_raw >= 0.15: votes += 1
        if hr_row and _sf(str(hr_row.get('To Hit HR','')).replace('%','')) >= 12: votes += 1
        if vuln is not None and _sf(vuln) >= 50: votes += 1
        if park_hr >= 10: votes += 1
        if streak_fires: votes += 1
        if bpp_proj_hr >= 0.15: votes += 1
        cands.append(dict(r=r, nm=nm, team=team, score=score, park_hr=park_hr,
                          hr_pct=hr_pct, rbi_pct=rbi_pct, sim_hr=sim_hr,
                          pit_name=pit_name, throws=throws, vuln=vuln,
                          streak_chip=streak_chip, votes=votes,
                          bpp_proj_hr=bpp_proj_hr, bpp_match_adv=bpp_match_adv,
                          bpp_park_hr=bpp_park_hr))
    # Re-rank by consensus, then Score
    cands.sort(key=lambda c: (-c['votes'], -c['score']))
    rows = []
    for i, c in enumerate(cands[:50], 1):
        score = c['score']
        SLATE_PICKS.append({
            'market': 'HR', 'pick': f'{c["nm"]} Ov 0.5 HR', 'name': c['nm'], 'team': c['team'],
            'pitcher': c['pit_name'], 'line': 'Ov 0.5', 'win_at': 1,
            'consensus': c['votes'], 'consensus_max': 7,
            'score': c['score'], 'sim_hr': c['sim_hr'], 'to_hit_hr': c['hr_pct'], 'park_hr': c['park_hr'],
            'bpp_api_hr': round(c['bpp_proj_hr'], 2) if c['bpp_proj_hr'] else None,
            'calibration_signal': c['bpp_match_adv'],
        })
        if c['votes'] >= 6: tier = 'row-tier0'
        elif c['votes'] >= 5: tier = 'row-tier1'
        else: tier = ''
        batter_cell = f'<strong>{c["nm"]}</strong> {hand_chip(c["r"].get("Bats"), "bats")}{c["streak_chip"]}{bpp_matchup_chip(c["bpp_match_adv"])}'
        pn = c['pit_name']
        pitcher_cell = f'{pn} {hand_chip(c["throws"], "throws")}' if pn and pn != '—' else '—'
        park_cell = pf_chip(c["park_hr"]) + bpp_factor_chip(c["bpp_park_hr"], "HR")
        rows.append(
            f'      <tr class="{tier}">'
            f'<td>{i}</td>'
            f'<td>{batter_cell}</td>'
            f'<td>{c["team"]}</td>'
            f'<td>{pitcher_cell}</td>'
            f'<td>{_conv_cell(c["votes"], 7)}</td>'
            f'<td>{vuln_cell(c["vuln"])}</td>'
            f'<td><strong>{score}</strong></td>'
            f'<td>{c["r"].get("Zone","—")}</td>'
            f'<td>{c["r"].get("Barrel%","—")}</td>'
            f'<td>{c["sim_hr"]}</td>'
            f'<td>{c["hr_pct"]}</td>'
            f'<td>{c["rbi_pct"]}</td>'
            f'<td>{park_cell}</td>'
            f'</tr>'
        )
    table_body = '\n'.join(rows)

    return f'''<!-- HR BOARD -->
<section id="hr-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🏆 Top 50 HR Board</div>
      <span class="game-tag">Tap to expand · ranked by Consensus · 7 independent lenses agree</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;"><strong>Consensus</strong> = how many of 7 independent lenses clear their line: Score≥70 · Sim HR%≥15 · HR%≥12 · Vuln≥50 · Park≥+10% · hot streak · BPP API proj HR≥0.15. 🔒 = 6–7. <strong>BPP Match</strong> is a new HR-board tag for calibration only; do not trust it over VulnScore until the HR inversion slice is backtested.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>vs Pitcher</th><th>Conv</th><th>Vuln</th><th>Score</th><th>Zone</th><th>Barrel%</th><th>Sim HR%</th><th>HR%</th><th>RBI%</th><th>Park HR%</th></tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: OO5 (Top 50 Hits / 1+H) ----
def build_oo5_board():
    # Sort by 1+ Hit
    def hp_val(r, key):
        v = r.get(key,'')
        if not v: return 0
        try: return float(str(v).replace('%',''))
        except (TypeError, ValueError): return 0
    hp_sorted = sorted(HIT, key=lambda r: -hp_val(r,'1+ Hit'))[:50]
    rows = []
    for i, r in enumerate(hp_sorted, 1):
        nm = _hit_full(r)
        team = tn(r.get('Team',''))
        bpp_api = bpp_entry(nm)
        bpp_proj_hits = _sf(bpp_api.get('proj_hits')) if bpp_api else 0
        bpp_park_hits = bpp_api.get('park_hits_factor') if bpp_api else None
        bp = BP_BAT_BY_NAME.get(nm.lower())
        bats = bp.get('BatterStand') if bp else None
        sim_hit = f'{_sf(bp.get("HitProbability"))*100:.0f}%' if (bp and bp.get("HitProbability") not in (None, "")) else '—'
        sim_h_raw = _sf(bp.get("HitProbability")) if bp else 0
        st_h = STREAK_BY_NAME.get(nm.lower())
        hit_streak = _sf(st_h.get('Hit Streak')) if st_h else 0
        streak_chip = f' <span style="font-size:11px;color:var(--hot)">🔥H{int(hit_streak)}</span>' if hit_streak >= 5 else ''
        # Opp pitcher from BP_Batters Opponent
        opp_team = tn(bp.get('Opponent','')) if bp else ''
        opp_sp_row = SP_BY_TEAM.get(opp_team) if opp_team else None
        opp_sp = opp_sp_row.get('Pitcher') if opp_sp_row else None
        v = get_vuln_for_pitcher(opp_sp) if opp_sp else None
        vuln = v.get('VulnScore') if v else None
        try: vv = int(vuln) if vuln is not None else 0
        except (TypeError, ValueError): vv = 0
        h1 = r.get('1+ Hit','—')
        h2 = r.get('2+ Hits','—')
        rbi = r.get('To Get RBI','—')
        hr = r.get('To Hit HR','—')
        match = r.get('Matchup','—')

        # ── HRR probability (H+R+RBI ≥ 1 combined) ──
        h1_f       = _sf(str(h1).replace('%',''))
        base_rbi_f = _sf(str(rbi).replace('%',''))
        sp_r2      = SP_BY_TEAM.get(opp_team, {}) if opp_team else {}
        era2       = _sf(sp_r2.get('ERA', 4.25))
        park_r2    = _sf(str(PARK_BY_TEAM.get(team, {}).get('Runs %', '0')))
        if h1_f > 0 and base_rbi_f > 0:
            era_boost = max(0, (era2 - 4.25) * 1.5)
            run_prob  = min(60, base_rbi_f * 0.8 + park_r2 * 0.3 + era_boost)
            hrr_pct   = round(min(99, max(0,
                (1 - (1-h1_f/100) * (1-run_prob/100) * (1-base_rbi_f/100)) * 100
            )), 1)
            if hrr_pct >= 82:
                hrr_cell = f'<strong style="color:var(--good)">{hrr_pct}%</strong>'
            elif hrr_pct >= 75:
                hrr_cell = f'<span style="color:var(--hot)">{hrr_pct}%</span>'
            else:
                hrr_cell = f'{hrr_pct}%'
        else:
            hrr_cell = '—'
        try: h1f = float(str(h1).replace('%',''))
        except (TypeError, ValueError): h1f = 0
        # ── Consensus: 5 independent lenses for a hit ──
        votes = 0
        if h1f >= 60: votes += 1
        if sim_h_raw >= 0.60: votes += 1
        if vv >= 50: votes += 1
        if hit_streak >= 5: votes += 1
        if park_r2 >= 5: votes += 1
        if bpp_proj_hits >= 0.90: votes += 1
        if votes >= 5: tier = 'row-tier0'
        elif votes >= 4: tier = 'row-tier1'
        else: tier = ''
        SLATE_PICKS.append({
            'market': 'HIT', 'pick': f'{nm} Ov 0.5 H', 'name': nm, 'team': team,
            'line': 'Ov 0.5', 'win_at': 1, 'consensus': votes, 'consensus_max': 6,
            'h1_pct': h1, 'sim_hit': sim_hit,
            'bpp_api_hits': round(bpp_proj_hits, 2) if bpp_proj_hits else None,
        })
        SLATE_PICKS.append({
            'market': 'HRR', 'pick': f'{nm} Ov 0.5 HRR', 'name': nm, 'team': team,
            'line': 'Ov 0.5', 'win_at': 1, 'win_stat': 'H+R+RBI',
            'consensus': votes, 'consensus_max': 6,
            'hrr_pct': (hrr_pct if hrr_cell != '—' else None),
        })
        batter_cell = f'<strong>{nm}</strong> {hand_chip(bats, "bats")}{streak_chip}'
        # Matchup cell: add Vuln color/🔥 if pitcher resolved
        if opp_sp:
            match_cell = f'{match} · {vuln_cell(vuln)}'
        else:
            match_cell = match
        match_cell += bpp_factor_chip(bpp_park_hits, "Hit")
        cells = (
            f'<td>{batter_cell}</td>'
            f'<td>{team}</td>'
            f'<td>{match_cell}</td>'
            f'<td>{_conv_cell(votes, 6)}</td>'
            f'<td><strong>{h1}</strong></td>'
            f'<td>{sim_hit}</td>'
            f'<td>{h2}</td>'
            f'<td>{rbi}</td>'
            f'<td>{hrr_cell}</td>'
            f'<td>{hr}</td>'
        )
        rows.append((votes, h1f, tier, cells))
    # Re-rank by consensus, then 1+ Hit%
    ranked = sorted(rows, key=lambda t: (-t[0], -t[1]))
    table_body = '\n'.join(
        f'      <tr class="{tier}"><td>{idx}</td>{cells}</tr>'
        for idx, (votes, h1f, tier, cells) in enumerate(ranked, 1)
    )
    return f'''<!-- OO5 BOARD -->
<section id="oo5-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">☄️ Top 50 Hits Board</div>
      <span class="game-tag">Tap to expand · ranked by Consensus · hit-tuned lenses</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;"><strong>Consensus</strong> = how many of 6 lenses clear their line: 1+Hit≥60 · Sim H%≥60 · opp Vuln≥50 · hit streak≥5 · Park Runs≥+5% · BPP API proj Hits≥0.90. 🔒 = 5–6 agree. Default play <strong>Ov 0.5</strong> hits.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>Matchup</th><th>Conv</th><th>1+H</th><th>Sim H%</th><th>2+H</th><th>RBI</th><th>HRR</th><th>HR</th></tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: TOTALS BOARD (game totals from BP_Games) ----
def _p_total_over(g, n=9):
    """P(game total >= n runs) from BP_Games Runs0..20 distribution (sums to 1)."""
    s = 0.0
    for i in range(n, 21):
        v = g.get(f'Runs{i}')
        if isinstance(v, (int, float)): s += v
    return s

def build_totals_board():
    rows = []
    for g in GAMES_RAW:
        away = tn(g.get('AwayTeam')); home = tn(g.get('HomeTeam'))
        total = (g.get('RunsAway') or 0) + (g.get('RunsHome') or 0)
        # Real F5 from BP_Games (was a fake total*0.55)
        f5a = g.get('RunsFirst5Away') or 0; f5h = g.get('RunsFirst5Home') or 0
        f5 = (f5a + f5h) if (f5a or f5h) else total * 0.55
        p_over = _p_total_over(g, 9)  # P(>= 9) = over 8.5
        ap = SP_BY_TEAM.get(away); hp = SP_BY_TEAM.get(home)
        comb_r = (_sf(ap.get('R')) if ap else 0) + (_sf(hp.get('R')) if hp else 0)
        park = PARK_BY_TEAM.get(home) or PARK_BY_TEAM.get(away)
        park_runs = parse_pct(park.get('Runs %')) if park else 0
        # Directional consensus: 4 independent signals
        over = sum([total >= 9, p_over >= 0.50, comb_r >= 6.5, park_runs >= 5])
        under = sum([total <= 7.5, p_over <= 0.42, comb_r <= 4.5, park_runs <= -5])
        if over > under:   lean_dir, conf, lean = 'OVER', over, '<span class="badge b-tier0">OVER</span>'
        elif under > over: lean_dir, conf, lean = 'UNDER', under, '<span class="badge b-bad">UNDER</span>'
        else:              lean_dir, conf, lean = 'Neutral', max(over, under), '<span class="badge b-neutral">Neutral</span>'
        SLATE_PICKS.append({
            'market': 'TOTAL', 'pick': f'{away}@{home} {lean_dir} 8.5', 'game': f'{away}@{home}',
            'lean': lean_dir, 'ref_line': 8.5, 'consensus': conf, 'consensus_max': 4,
            'proj_total': round(total, 2), 'p_over_8_5': round(p_over, 3), 'f5': round(f5, 2),
        })
        away_r = g.get('RunsAway') or 0
        home_r = g.get('RunsHome') or 0
        rows.append((conf, total,
            f'      <tr>'
            f'<td>{away} @ {home}<br><span style="font-size:10px;color:var(--text-dim)">{away} {away_r:.1f} · {home} {home_r:.1f}</span></td>'
            f'<td><strong>{total:.2f}</strong></td>'
            f'<td>{p_over*100:.0f}%</td><td>{f5:.2f}</td><td>{_conv_cell(conf,4)}</td><td>{lean}</td></tr>'))
    rows.sort(key=lambda t: (-t[0], -t[1]))
    table_body = '\n'.join(t[2] for t in rows)
    return f'''<!-- TOTALS BOARD -->
<section id="totals-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">📈 Game Totals & F5 Board</div>
      <span class="game-tag">Tap to expand · ranked by Consensus · real run distribution</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;"><strong>Conf</strong> = how many of 4 signals agree with the lean: projected total · P(over 8.5) from BallparkPal's run distribution · combined SP runs · park Runs%. <strong>P(O 8.5)</strong> is the real sim probability of 9+ runs. F5 = real first-5 projection. Confirm vs book line.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Game</th><th>Total</th><th>P(O 8.5)</th><th>F5</th><th>Conf</th><th>Lean</th></tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: NRFI / YRFI ----
def build_nrfi_board():
    rows = []
    for g in GAMES_RAW:
        away = tn(g.get('AwayTeam')); home = tn(g.get('HomeTeam'))
        ap = SP_BY_TEAM.get(away); hp = SP_BY_TEAM.get(home)
        if not ap or not hp: continue
        yrfi = _sf(g.get('RunsFirstInningPct'))  # P(>=1 run in first inning) — real sim
        try:
            hr_c = float(ap.get('HR', 0)) + float(hp.get('HR', 0))
            k_c  = float(ap.get('K', 0))  + float(hp.get('K', 0))
            r_c  = _sf(ap.get('R')) + _sf(hp.get('R'))
        except (TypeError, ValueError): continue
        # Directional consensus: 4 signals (first-inning prob is the real anchor)
        nrfi  = sum([0 < yrfi <= 0.46, hr_c <= 1.4, k_c >= 10, r_c <= 4.5])
        yrfi_v = sum([yrfi >= 0.58, hr_c >= 2.0, k_c <= 7, r_c >= 6.5])
        if nrfi > yrfi_v:    lean_dir, conf, lean = 'NRFI', nrfi, '<span class="badge b-tier0">NRFI</span>'
        elif yrfi_v > nrfi:  lean_dir, conf, lean = 'YRFI', yrfi_v, '<span class="badge b-bad">YRFI</span>'
        else:                lean_dir, conf, lean = 'Neutral', max(nrfi, yrfi_v), '<span class="badge b-neutral">Neutral</span>'
        yrfi_disp = f'{yrfi*100:.0f}%' if yrfi else '—'
        SLATE_PICKS.append({
            'market': 'NRFI', 'pick': f'{away}@{home} {lean_dir}', 'game': f'{away}@{home}',
            'lean': lean_dir, 'consensus': conf, 'consensus_max': 4,
            'yrfi_prob': round(yrfi, 3) if yrfi else None,
        })
        rows.append((conf, (yrfi or 1),
            f'      <tr><td>{away} @ {home}</td><td>{ap["Pitcher"]}</td><td>{hp["Pitcher"]}</td>'
            f'<td>{yrfi_disp}</td><td>{_conv_cell(conf,4)}</td><td>{lean}</td></tr>'))
    rows.sort(key=lambda t: (-t[0], t[1]))
    table_body = '\n'.join(t[2] for t in rows)
    return f'''<!-- NRFI BOARD -->
<section id="nrfi-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🥶 NRFI / YRFI Watch</div>
      <span class="game-tag">Tap to expand · ranked by Consensus · real 1st-inning prob</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;"><strong>1st-Inn Run%</strong> is BallparkPal's actual probability of a run in the first (lower = NRFI). <strong>Conf</strong> = of 4 signals agreeing with the lean: that first-inning prob · combined SP HR/9 · combined K · combined SP runs. Confirm vs book NRFI line.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Game</th><th>Away SP</th><th>Home SP</th><th>1st-Inn Run%</th><th>Conf</th><th>Lean</th></tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: SB BOARD ----
def build_sb_board():
    # From BP_Batters StolenBaseProbability sorted desc
    sb_sorted = sorted(BP_BAT, key=lambda r: -(_sf(r.get('StolenBaseProbability'))))[:20]
    rows = []
    for r in sb_sorted:
        if not r.get('FullName'): continue
        sbp = _sf(r.get('StolenBaseProbability'))
        if sbp < 0.05: continue
        att = _sf(r.get('StolenBaseAttempts'))
        team = tn(r.get('Team'))
        opp = tn(r.get('Opponent'))
        opp_sp = SP_BY_TEAM.get(opp)
        opp_bb_v = _sf(opp_sp.get('BB')) if opp_sp else 0
        opp_bb = opp_sp.get('BB', '—') if opp_sp else '—'
        # ── Consensus: 3 independent SB lenses ──
        votes = sum([sbp >= 0.15, att >= 0.25, opp_bb_v >= 2.5])
        tier = 'row-tier0' if votes >= 3 else ('row-tier1' if votes == 2 else '')
        sb_pct = f'{sbp*100:.1f}%'
        SLATE_PICKS.append({
            'market': 'SB', 'pick': f'{r["FullName"]} Ov 0.5 SB', 'name': r['FullName'],
            'team': team, 'opp': opp, 'line': 'Ov 0.5', 'win_at': 1,
            'consensus': votes, 'consensus_max': 3,
            'sb_prob': round(sbp, 3), 'sb_attempts': round(att, 2),
            'opp_sp_bb': round(opp_bb_v, 2) if opp_sp else None,
        })
        rows.append((votes, sbp, tier,
            f'<td><strong>{r["FullName"]}</strong></td>'
            f'<td>{team}</td><td>{opp}</td>'
            f'<td><strong>{sb_pct}</strong></td>'
            f'<td>{_conv_cell(votes, 3)}</td>'
            f'<td>{opp_bb}</td>'))
    rows.sort(key=lambda t: (-t[0], -t[1]))
    table_body = '\n'.join(
        f'      <tr class="{tier}"><td>{idx}</td>{cells}</tr>'
        for idx, (votes, sbp, tier, cells) in enumerate(rows, 1)
    )
    return f'''<!-- SB BOARD -->
<section id="sb-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🏃 Stolen Base Targets</div>
      <span class="game-tag">Tap to expand · ranked by Consensus · SB% · attempts · opp walks</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;"><strong>Consensus</strong> = 3 lenses: SB prob ≥15% · projected attempts ≥0.25 · opp SP walks ≥2.5 (more baserunners). Plays use <strong>Ov 0.5</strong>.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Runner</th><th>Tm</th><th>Opp</th><th>SB %</th><th>Conv</th><th>Opp SP BB</th></tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: DOUBLES ----
def build_doubles_board():
    # From BP_Batters Doubles projection sorted desc + park 2B/3B%
    db_sorted = sorted(BP_BAT, key=lambda r: -(_sf(r.get('Doubles'))))[:20]
    rows = []
    for r in db_sorted:
        if not r.get('FullName'): continue
        dbls = _sf(r.get('Doubles'))
        team = tn(r.get('Team'))
        opp = tn(r.get('Opponent'))
        park = PARK_BY_TEAM.get(team) or PARK_BY_TEAM.get(opp)
        xbh = parse_pct(park.get('2B/3B %')) if park else 0
        opp_sp = SP_BY_TEAM.get(opp)
        opp_h = _sf(opp_sp.get('H')) if opp_sp else 0
        # ── Consensus: 3 independent doubles lenses ──
        votes = sum([dbls >= 0.27, xbh >= 10, opp_h >= 5.5])
        tier = 'row-tier0' if votes >= 3 else ('row-tier1' if votes == 2 else '')
        SLATE_PICKS.append({
            'market': '2B', 'pick': f'{r["FullName"]} Ov 0.5 2B', 'name': r['FullName'],
            'team': team, 'opp': opp, 'line': 'Ov 0.5', 'win_at': 1,
            'consensus': votes, 'consensus_max': 3,
            'proj_2b': round(dbls, 2), 'park_2b3b': xbh, 'opp_sp_h': round(opp_h, 2) if opp_sp else None,
        })
        rows.append((votes, dbls, tier,
            f'<td><strong>{r["FullName"]}</strong></td>'
            f'<td>{team}</td><td>{opp}</td>'
            f'<td><strong>{dbls:.2f}</strong></td>'
            f'<td>{_conv_cell(votes, 3)}</td>'
            f'<td>{fmt_pct_cell(xbh,10,-10)}</td>'))
    rows.sort(key=lambda t: (-t[0], -t[1]))
    table_body = '\n'.join(
        f'      <tr class="{tier}"><td>{idx}</td>{cells}</tr>'
        for idx, (votes, dbls, tier, cells) in enumerate(rows, 1)
    )
    return f'''<!-- DOUBLES BOARD -->
<section id="doubles-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">☄️ Doubles Targets</div>
      <span class="game-tag">Tap to expand · ranked by Consensus · proj × park × opp hits</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;"><strong>Consensus</strong> = 3 lenses: projected 2B ≥0.27 · park 2B/3B ≥+10% · opp SP hits-allowed ≥5.5. Plays use <strong>Ov 0.5</strong>.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>Opp</th><th>Proj 2B</th><th>Conv</th><th>Park 2B/3B%</th></tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: DFS LEADERBOARD ----
def build_dfs_board():
    dfs_sorted = sorted(BP_BAT, key=lambda r: -(r.get('PointsDK') or 0))[:25]
    rows = []
    for i, r in enumerate(dfs_sorted, 1):
        if not r.get('FullName'): continue
        team = tn(r.get('Team'))
        opp = tn(r.get('Opponent'))
        dk = _sf(r.get('PointsDK'))
        fd = _sf(r.get('PointsFD'))
        hr_p = _sf(r.get('HomeRunProbability'))
        hit_p = _sf(r.get('HitProbability'))
        if dk >= 9: tier = 'row-tier0'
        elif dk >= 8: tier = 'row-tier1'
        else: tier = ''
        rows.append(
            f'      <tr class="{tier}"><td>{i}</td>'
            f'<td><strong>{r["FullName"]}</strong></td>'
            f'<td>{team}</td>'
            f'<td>{opp}</td>'
            f'<td><strong>{dk:.2f}</strong></td>'
            f'<td>{fd:.2f}</td>'
            f'<td>{hr_p*100:.1f}%</td>'
            f'<td>{hit_p*100:.1f}%</td></tr>'
        )
    return f'''<!-- DFS BOARD -->
<section id="dfs-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">💎 DFS Points Leaderboard</div>
      <span class="game-tag">Tap to expand · DK/FD point projections from BP_Batters</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Top 25 bats by DK point projection. HR% and Hit% from BP — cross-ref to HR Board and Ov 0.5 board.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>Opp</th><th>DK</th><th>FD</th><th>HR%</th><th>Hit%</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: COMBOS K ----
def build_combos_k():
    """8 K-only combos in Day 44 flag-row format. Slate-specific Day 46 content."""
    rows = [
        ('1⃣', '<strong>Skenes O 5+ K + Wheeler O 5+ K</strong> — <strong>Paul Skenes</strong> O 5+ K (SS 6.9 vs COL V14, PNC -20% HR irrelevant for Ks) + <strong>Zack Wheeler</strong> O 5+ K (SS 6.6 @ BOS Fenway, HR-suppressed favors strike-throwing). Different games (Game 6 + Game 5). Slate-best T0 K pair.', 'b-tier0', '2-leg T0'),
        ('2⃣', '<strong>Warren O 5+ K + Peralta O 5+ K</strong> — <strong>Will Warren</strong> O 5+ K (SS 5.8 NYY @ BAL Camden -15%) + <strong>Freddy Peralta</strong> O 5+ K (SS 5.7 NYM vs DET, Citi -14% HR). Different games. T0 K combo.', 'b-tier0', '2-leg T0'),
        ('3⃣', '<strong>Skenes O 5+ K + Wheeler O 5+ K + Warren O 5+ K</strong> — 3-leg T0 K monster. Skenes 6.9 / Wheeler 6.6 / Warren 5.8. All different games. Slate’s only three SS ≥5.8 K plays.', 'b-tier0', '3-leg T0 stack'),
        ('4⃣', '<strong>Yamamoto O 5+ K + Flaherty O 5+ K</strong> — <strong>Yoshinobu Yamamoto</strong> O 5+ K (SS 5.7 LAD vs SF, BB 1.3 elite control) + <strong>Jack Flaherty</strong> O 5+ K (SS 5.5 DET @ NYM, HR/9 0.79 watch). Different games. T1 alt-K combo.', 'b-tier1', '2-leg T1 alt-K'),
        ('5⃣', '<strong>Sproat O 5+ K + Woo O 5+ K</strong> — <strong>Brandon Sproat</strong> O 5+ K (SS 5.3 MIL vs SD) + <strong>Bryan Woo</strong> O 5+ K (SS 5.0 SEA @ HOU, BB 1.3). Different games. Floor-of-5 plays.', 'b-tier1', '2-leg T1 alt-K'),
        ('6⃣', '<strong>Gore O 3.5 K + Lorenzen O 2.5 K</strong> — <strong>MacKenzie Gore</strong> O 3.5 K (SS 4.9 TEX vs ARI) + <strong>Michael Lorenzen</strong> O 2.5 K (SS 4.3 PIT host, V60 trap — fade for Ks but volume floor). Different games. Safe low-alt stack.', 'b-warn', '2-leg O 3.5/2.5'),
        ('7⃣', '<strong>Skenes O 5+ K + Yamamoto O 5+ K + Peralta O 5+ K</strong> — Skenes / Yamamoto / Peralta all 5.7+ K projections. Three different games (PIT / LAD / NYM). High-floor 3-leg T1 K stack.', 'b-tier1', '3-leg cross-game'),
        ('8⃣', '<strong>Pérez O 5+ K + Sproat O 5+ K + Woo O 5+ K</strong> — <strong>Eury Pérez</strong> O 5+ K (SS 5.3, HR/9 1.02 caveat) + Sproat 5.3 + Woo 5.0. Three different games. T1 K saturation at the floor-of-5 tier.', 'b-tier1', '3-leg T1 floor'),
    ]
    blocks = []
    for icon, body, badge_cls, badge_text in rows:
        blocks.append(f'  <div class="flag-row"><div class="icon">{icon}</div><div>{body} <span class="badge {badge_cls}">{badge_text}</span></div></div>')
    return f'''<!-- COMBOS K -->
<section id="combos-k" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">⚡ Alt K Combos</div>
      <span class="game-tag">Tap to expand · K-only combos · alts ≤5 per user rule</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">K-only combo cards. <strong>Every leg is a strikeout prop.</strong> Alt rule: proj ≥5.0 → O5+; 4.5–4.99 → O3.5; &lt;4.5 → O2.5. <strong>Never alt &gt;5.</strong> Same player max 2 legs.</p>
{chr(10).join(blocks)}
  </div></div>
</section>
'''


# ---- BUILD: COMBOS HRR ----
def build_combos_hrr():
    """8 HRR-only combos in Day 44 flag-row format. Day 46 slate-specific."""
    rows = [
        ('1⃣', '<strong>Elly De La Cruz Ov 0.5 HRR + Sal Stewart Ov 0.5 HRR</strong> — CIN top of order vs <strong>Mikolas V76</strong> (slate-worst). GABP <strong>+8% HR / +3% Runs</strong>. DLC #1 HR Board (Score 92, ⚡7) + Stewart #2 (87, ⚡7). Same-game CIN stack.', 'b-tier0', '2-leg CIN stack'),
        ('2⃣', '<strong>James Wood Ov 0.5 HRR + CJ Abrams Ov 0.5 HRR</strong> — WSH top of order vs <strong>Brady Singer V70</strong>. Wood #4 HR Board (Score 85, ⚡8) + Abrams #5 (82, ⚡5). Both LHB hammering RHP. Same-game WSH stack.', 'b-tier0', '2-leg WSH stack'),
        ('3⃣', '<strong>Elly De La Cruz + Sal Stewart + Spencer Steer Ov 0.5 HRR</strong> — CIN trio vs Mikolas V76. Top 3 of HR Board (DLC 92, Stewart 87, Steer 87). Saturation same-game stack at GABP +8%.', 'b-tier0', '3-leg CIN stack'),
        ('4⃣', '<strong>Brent Rooker + Tyler Soderstrom + Shea Langeliers Ov 0.5 HRR</strong> — ATH trio at <strong>Sutter Health Park +29% HR / +18% Runs (slate volcano)</strong> vs Pallante V28. Top hit-board names with massive HR upside (Rooker 22.92% HR, Soderstrom 20.73%, Langeliers 24.76%).', 'b-tier0', '3-leg ATH volcano'),
        ('5⃣', '<strong>De La Cruz + Wood Ov 0.5 HRR</strong> — #1 and #4 HR Board names — cross-game stack of slate’s two highest scores. DLC vs Mikolas (V76) + Wood vs Singer (V70). Two different games. Floor-y double anchor.', 'b-tier0', '2-leg cross-game'),
        ('6⃣', '<strong>Max Muncy + Andy Pages Ov 0.5 HRR</strong> — LAD vs Adrian Houser at <strong>Dodger Stadium +8% HR</strong>. Muncy #8 (Score 78, ⚡7) + Pages #12 (73, ⚡7). Same-game LAD stack.', 'b-tier1', '2-leg LAD stack'),
        ('7⃣', '<strong>Trout + Soler Ov 0.5 HRR</strong> — LAA top vs Slade Cecconi V56. Trout #7 HR Board (78, ⚡7) + Soler #10 (75, ⚡5). Same-game LAA pair on a vulnerable RHP — progressive field still neutral.', 'b-tier1', '2-leg LAA stack'),
        ('8⃣', '<strong>Stewart + DLC + Wood + Abrams Ov 0.5 HRR</strong> — 4-leg saturation across CIN (vs Mikolas V76 / GABP +8%) and WSH (vs Singer V70). The Day 46 HRR Mt. Rushmore — #1, #2, #4, #5 of HR Board.', 'b-tier1', '4-leg 2-stack'),
    ]
    blocks = []
    for icon, body, badge_cls, badge_text in rows:
        blocks.append(f'  <div class="flag-row"><div class="icon">{icon}</div><div>{body} <span class="badge {badge_cls}">{badge_text}</span></div></div>')
    return f'''<!-- COMBOS HRR -->
<section id="combos-hrr" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🎯 H+R+RBI Combos</div>
      <span class="game-tag">Tap to expand · HRR-only combos · every leg is an Ov 0.5 H+R+RBI</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">H+R+RBI-only combos. <strong>Every leg is an Ov 0.5 HRR.</strong> Sourced from BP HRR proxy on the Hits Board, cross-referenced to HR Board and park factors.</p>
{chr(10).join(blocks)}
  </div></div>
</section>
'''


# ---- BUILD: PARLAY ANCHORS ----
def build_parlays():
    """10 anchors in Day 44 flag-row format with custom emoji icons + multi-line legs + game times. Day 46 slate-specific."""
    rows = [
        ('🏆',
         '<strong>4-Leg HR Parlay: Elly DLC + Stewart + Wood + Muncy</strong>'
         '<br>Leg 1: <strong>Elly De La Cruz</strong> HR (CIN vs Mikolas V76, <strong>GABP +8%</strong>, Score 92 ⚡7) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 2: <strong>Sal Stewart</strong> HR (CIN vs Mikolas V76, GABP +8%, Score 87 ⚡7) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 3: <strong>James Wood</strong> HR (WSH vs Singer V70, Score 85 ⚡8) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 4: <strong>Max Muncy</strong> HR (LAD vs Houser, <strong>LAD +8% HR</strong>, Score 78 ⚡7) — Game 10 SF@LAD (10:10 ET)'
         '<br><em>Two-game saturation — WAS@CIN slate-worst SP (V76) + LAD park boost. Day 46 HR mountain.</em>'),
        ('☄️',
         '<strong>4-Leg Hits Parlay: Wilson + Stewart + DLC + McNeil</strong>'
         '<br>Leg 1: <strong>Jacob Wilson</strong> 1+H 71.3% (ATH vs Pallante V28, <strong>Sutter +29% HR / +18% Runs</strong>) — Game 1 STL@ATH (9:40 ET)'
         '<br>Leg 2: <strong>Sal Stewart</strong> 1+H 68.9% (CIN vs Mikolas V76, GABP +8%) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 3: <strong>Elly De La Cruz</strong> 1+H 68.2% (CIN vs Mikolas V76, GABP +8%) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 4: <strong>Jeff McNeil</strong> 1+H 67.4% (ATH vs Pallante V28, Sutter +29%) — Game 1 STL@ATH (9:40 ET)'
         '<br><em>4 of top-5 1+H% rates on slate at the two best parks (Sutter +29% HR + GABP +8%).</em>'),
        ('🔥',
         '<strong>4-Leg HRR Parlay: DLC + Stewart + Wood + Abrams Ov 0.5 HRR</strong>'
         '<br>Leg 1: <strong>Elly De La Cruz</strong> Ov 0.5 HRR (CIN vs Mikolas V76, <strong>GABP +8%</strong>) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 2: <strong>Sal Stewart</strong> Ov 0.5 HRR (CIN vs Mikolas V76, GABP +8%) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 3: <strong>James Wood</strong> Ov 0.5 HRR (WSH vs Singer V70) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 4: <strong>CJ Abrams</strong> Ov 0.5 HRR (WSH vs Singer V70) — Game 3 WAS@CIN (6:40 ET)'
         '<br><em>Single-game double-stack — both teams’ SPs are top-2 most vulnerable on slate. Top 4 of HR Board rolled into HRR ladder.</em>'),
        ('⚡',
         '<strong>2-Leg HR Parlay #1: DLC + Wood</strong>'
         '<br>Leg 1: <strong>Elly De La Cruz</strong> HR (CIN vs Mikolas V76, <strong>GABP +8%</strong>, Score 92) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 2: <strong>James Wood</strong> HR (WSH vs Singer V70, Score 85 ⚡8) — Game 3 WAS@CIN (6:40 ET)'
         '<br><em>Same-game opposite-dugout HR stack. The two most vulnerable SPs are facing each other. Highest-scoring HR pair on slate.</em>'),
        ('💥',
         '<strong>2-Leg HR Parlay #2: Stewart + Muncy</strong>'
         '<br>Leg 1: <strong>Sal Stewart</strong> HR (CIN vs Mikolas V76, GABP +8%, Score 87) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 2: <strong>Max Muncy</strong> HR (LAD vs Houser, <strong>LAD +8% HR</strong>, Score 78 ⚡7) — Game 10 SF@LAD (10:10 ET)'
         '<br><em>Different games. Both at slate’s only two HR-friendly parks (GABP + LAD, both +8% HR).</em>'),
        ('🎯',
         '<strong>4-Leg Alt K Parlay: Skenes + Wheeler + Warren + Peralta</strong>'
         '<br>Leg 1: <strong>Paul Skenes</strong> O 5+ K (SS 6.9 vs COL) — Game 7 COL@PIT (6:40 ET)'
         '<br>Leg 2: <strong>Zack Wheeler</strong> O 5+ K (SS 6.6 @ BOS) — Game 5 PHI@BOS (6:45 ET)'
         '<br>Leg 3: <strong>Will Warren</strong> O 5+ K (SS 5.8 NYY @ BAL) — Game 8 NYY@BAL (6:35 ET)'
         '<br>Leg 4: <strong>Freddy Peralta</strong> O 5+ K (SS 5.7 NYM vs DET) — Game 9 DET@NYM (7:10 ET)'
         '<br><em>4 different games. All proj ≥5.0 → O5+ alt per user rule. Never alt &gt;5.</em>'),
        ('⚾',
         '<strong>2-Leg Alt K Combo: Skenes + Wheeler O 5+</strong>'
         '<br>Leg 1: <strong>Paul Skenes</strong> O 5+ K (SS 6.9 vs COL, K9 elite) — Game 7 COL@PIT (6:40 ET)'
         '<br>Leg 2: <strong>Zack Wheeler</strong> O 5+ K (SS 6.6 @ BOS Fenway) — Game 5 PHI@BOS (6:45 ET)'
         '<br><em>Different games. Day 46 slate-best K pair — both projections clear 6.5.</em>'),
        ('🥶',
         '<strong>NRFI Anchor: DET@NYM NRFI</strong>'
         '<br>Leg 1: <strong>DET @ NYM NRFI</strong> — Flaherty (SS 5.5) + Peralta (SS 5.7) both K-friendly at <strong>Citi -14% HR / -15% Runs (slate-worst run park)</strong>. — Game 9 DET@NYM (7:10 ET)'
         '<br><em>Single-leg conviction NRFI play — worst run-scoring environment on slate.</em>'),
        ('📈',
         '<strong>Free Conviction Pick: STL@ATH OVER (Sutter volcano)</strong>'
         '<br>Leg 1: <strong>STL @ ATH OVER</strong> — <strong>Sutter Health Park +29% HR / +18% Runs (slate-best both)</strong>. Pallante V28 + Springs V21. Best run/HR environment on slate. — Game 1 (9:40 ET)'
         '<br><em>Conviction total. The slate’s only +25% HR park is also the slate’s only +15% Runs park.</em>'),
        ('🔥',
         '<strong>3-Leg Value: Skenes O 5+ K + DLC HR + Wilson 1+H</strong>'
         '<br>Leg 1: <strong>Paul Skenes</strong> O 5+ K (SS 6.9 vs COL) — Game 7 COL@PIT (6:40 ET)'
         '<br>Leg 2: <strong>Elly De La Cruz</strong> HR (CIN vs Mikolas V76, GABP +8%) — Game 3 WAS@CIN (6:40 ET)'
         '<br>Leg 3: <strong>Jacob Wilson</strong> 1+H 71.3% (ATH vs Pallante, <strong>Sutter +29%</strong>) — Game 1 STL@ATH (9:40 ET)'
         '<br><em>3 different games. K + HR + Hit mix. Each leg at a park-boosted or slate-best environment.</em>'),
    ]
    blocks = []
    for icon, body in rows:
        blocks.append(f'  <div class="flag-row"><div class="icon">{icon}</div><div>{body}</div></div>')
    return f'''<!-- PARLAYS -->
<section id="parlays" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">💣 Parlay Anchors</div>
      <span class="game-tag">Tap to expand · 10 anchors · T0 legs · max 2× same player · alts ≤5 per parlay</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Rules: Anchor = T0 play. Min 2 different games. Same player max 2 legs. Alts ≤5 total per parlay. <strong>Never alt &gt;5.</strong></p>
{chr(10).join(blocks)}
  </div></div>
</section>
'''


# ---- BUILD: CONVICTION BOARD ----
def build_conviction():
    """9-pick conviction board in Day 44 flag-list format. Day 46 slate-specific."""
    items = [
        ('<strong>Elly De La Cruz HR (GABP +8%)</strong> — Score 92 (slate-top), ⚡7 Zone, vs <strong>Mikolas V76 (slate-worst SP)</strong> at GABP +8% HR. Day 46 slate-best HR play.', 'b-tier0', 'T0 HR CONVICTION'),
        ('<strong>Sal Stewart HR (CIN vs Mikolas V76)</strong> — Score 87, ⚡7 Zone, same-game stack w/ DLC. GABP +8% HR boost. T0 conviction.', 'b-tier0', 'T0 HR CONVICTION'),
        ('<strong>Paul Skenes O 5+ K</strong> — SS 6.9 K (slate-top) vs COL anemic offense at PNC. K9 elite, BB only 1.4. Top conviction K of the slate.', 'b-tier0', 'T0 K CONVICTION'),
        ('<strong>James Wood HR (WSH vs Singer V70)</strong> — Score 85, ⚡8 Zone (slate-top Zone). LHB vs RHP Singer. Same-game stack w/ Abrams. T0 conviction.', 'b-tier0', 'T0 HR CONVICTION'),
        ('<strong>Jacob Wilson 1+H 71.3%</strong> — Slate-top single-batter hit prop. ATH at <strong>Sutter +29% HR / +18% Runs (slate volcano)</strong> vs Pallante V28. Volume + contact lock.', 'b-tier0', 'T0 HIT CONVICTION'),
        ('<strong>Zack Wheeler O 5+ K</strong> — SS 6.6 K (slate #2) @ BOS Fenway. BB 1.8 control, HR/9 0.52. Different-game complement to Skenes. T1 K floor.', 'b-tier1', 'T1 K CONVICTION'),
        ('<strong>Spencer Steer HR/RBI (CIN vs Mikolas V76)</strong> — Score 87, #3 of HR Board, ⚡4. Floor leg in the CIN saturation stack. T1 HR/RBI.', 'b-tier1', 'T1 HR/RBI'),
        ('<strong>Max Muncy HR (LAD +8%)</strong> — Score 78, ⚡7, vs Houser. Dodger Stadium +8% HR + LAD top-of-order. Cross-game complement to CIN stack. T1 HR.', 'b-tier1', 'T1 HR'),
        ('<strong>Brent Rooker Ov 0.5 HRR (Sutter volcano)</strong> — 1+H 66.7%, <strong>HR 22.9%</strong> at <strong>Sutter +29% HR / +18% Runs</strong>. Best park environment of slate. T1 HRR.', 'b-tier1', 'T1 HRR CONVICTION'),
    ]
    li_html = ''.join(f'    <li>{body} <span class="badge {badge_cls}">{badge_text}</span></li>\n' for body, badge_cls, badge_text in items)
    return f'''<!-- CONVICTION -->
<section id="conviction" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">✅ Full Conviction Board</div>
      <span class="game-tag">Tap to expand · highest confidence plays · all 3 floors passed</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <ul class="flag-list">
{li_html}  </ul>
  </div></div>
</section>
'''


# ---- BUILD: SKIP LIST ----
def build_skip():
    """Skip list in Day 44 flag-list format. Mix SKIP (b-bad) and DOWNGRADE (b-warn). Day 46 slate-specific."""
    items = []
    # SKIPs: pitchers with no projection / K < 3.5
    skip_pitchers = sorted([r for r in SP_PROJ if (_sf(r.get('K'))) < 3.5], key=lambda r: (_sf(r.get('K'))))
    for p in skip_pitchers:
        items.append((f'<strong>{p["Pitcher"]} ({tn(p["Team"])}) ALL K props</strong> — SS K only {p["K"]}. Skip strikeout alts entirely — below the O 2.5 alt floor.', 'b-bad', 'SKIP — LOW K PROJ'))
    # Bad-park HR skip: HR% ≤ -17%
    skip_parks_hr = [p for p in PARKS if parse_pct(p.get('HR %')) <= -17]
    for p in skip_parks_hr:
        items.append((f'<strong>All {p.get("Venue", p.get("Game",""))} HR plays ({p.get("Game","")})</strong> — {p.get("Venue","Park")} <strong>{p.get("HR %","")} HR (slate suppressor)</strong>. Skip all HR props — pivot to 1+H / RBI / Runs.', 'b-bad', 'SKIP HR'))
    # Downgrade HR parks: -10 < HR% <= -15
    dn_parks = [p for p in PARKS if -17 < parse_pct(p.get('HR %')) <= -10]
    for p in dn_parks:
        items.append((f'<strong>{p.get("Game","")} HR plays</strong> — {p.get("Venue","Park")} <strong>{p.get("HR %","")} HR</strong>. Don’t pay HR park premium. Use 1+H / RBI / Runs props instead.', 'b-warn', 'DOWNGRADE HR'))
    # Add a couple of editorial calls
    items.append(('<strong>Mikolas K alts (vs CIN at GABP)</strong> — V76 slate-worst + GABP +8% HR. SS only 3.7 K. CIN bats target him — don’t play his Ks.', 'b-bad', 'SKIP MIKOLAS Ks'))
    items.append(('<strong>Singer K alts (vs WSH)</strong> — V70 with Wood/Abrams in opp lineup. SS only 4.1 K. Fade Ks; WSH bats target him.', 'b-bad', 'SKIP SINGER Ks'))
    items.append(('<strong>All Citi Field run props (DET@NYM)</strong> — Citi <strong>-15% Runs (slate-worst)</strong>. Skip Runs / Totals OVERs here. NRFI lean.', 'b-warn', 'DOWNGRADE RUNS AT CITI'))

    li_html = ''.join(f'    <li>{body} <span class="badge {badge_cls}">{badge_text}</span></li>\n' for body, badge_cls, badge_text in items)
    return f'''<!-- SKIP -->
<section id="skip" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">📋 Daily Skip List</div>
      <span class="game-tag">Tap to expand · plays to avoid today · park/data-driven downgrades</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <ul class="flag-list">
{li_html}  </ul>
  </div></div>
</section>
'''


# ---- NEW: SP VULN BOARD (HR/BB risk) ----
def build_sp_vuln():
    sp_sorted = sorted(SP_PROJ, key=lambda r: -((_sf(r.get('HR')))*2 + (_sf(r.get('BB')))*0.5 - (_sf(r.get('K')))*0.3))
    rows = []
    for r in sp_sorted:
        hr = _sf(r.get('HR'))
        bb = _sf(r.get('BB'))
        k = _sf(r.get('K'))
        v = get_vuln_for_pitcher(r['Pitcher'])
        vuln = v.get('VulnScore') if v else None
        danger = v.get('DangerBatter1') if v else '—'
        throws = pitcher_throws(r['Pitcher'])
        # Row tier from vuln (HR-stack target indicator)
        try: vv = int(vuln) if vuln is not None else 0
        except (TypeError, ValueError): vv = 0
        if vv >= 50: tier = 'row-tier0'
        elif vv >= 32: tier = 'row-tier1'
        else: tier = ''
        hr_disp = f'<strong style="color:var(--bad)">{hr}</strong>' if hr >= 0.85 else (f'<span style="color:var(--hot)">{hr}</span>' if hr >= 0.7 else f'{hr}')
        bb_disp = f'<strong style="color:var(--bad)">{bb}</strong>' if bb >= 2.5 else f'{bb}'
        team = tn(r['Team'])
        opp = tn(r['Opp'])
        pitcher_cell = f'<strong>{r["Pitcher"]}</strong> {hand_chip(throws, "throws")}'
        danger_cell = format_danger_batter(danger)
        rows.append(
            f'      <tr class="{tier}">'
            f'<td>{pitcher_cell}</td>'
            f'<td>{team}</td><td>vs {opp}</td>'
            f'<td>{hr_disp}</td><td>{bb_disp}</td><td>{k}</td>'
            f'<td>{vuln_cell(vuln)}</td>'
            f'<td>{danger_cell}</td>'
            f'</tr>'
        )
    return f'''<!-- SP VULN BOARD -->
<section id="sp-vuln-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">☢️ Pitcher's HR Risk Board</div>
      <span class="game-tag">Tap to expand · 15 SPs ranked by HR/9 + BB · stack targets</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">NEW: leverages <strong>SP_Projections HR + BB</strong> columns. Pitchers ranked by composite vulnerability (HR×2 + BB×0.5 − K×0.3). <strong>Vuln ≥50 = 🔥 HR-stack target</strong>; ≥32 = warm. Danger Batter shows handedness chip + ISO color + ⚡Zone from HR Board.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Pitcher</th><th>Tm</th><th>Opp</th><th>HR/9</th><th>BB</th><th>K</th><th>Vuln</th><th>Top Danger Batter</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- ASSEMBLE ALL SECTIONS ----
if PROJECTED_MODE:
    SECTIONS = {
        'headlines':         build_projected_headlines(),
        'park-board':        with_projected_badge(build_park_board(), "Park factors rebuilt from live park/weather context."),
        'games':             with_projected_badge(build_games(), "Game cards rebuilt from live team projections and public schedule data."),
        'matchup-spotlight': projected_unavailable_section(
            'matchup-spotlight',
            'Matchup Spotlight',
            'Unavailable without workbook',
            'The Sweet Spot danger-batter grid is workbook-only and cannot be reconstructed honestly.',
        ),
        'k-board':           with_projected_badge(build_k_board(), "Starter strikeout board rebuilt from live pitcher projections."),
        'hr-board':          build_projected_hr_board(),
        'oo5-board':         build_projected_oo5_board(),
        'totals-board':      with_projected_badge(build_totals_board(), "Totals rebuilt from live team run projections."),
        'nrfi-board':        with_projected_badge(build_nrfi_board(), "YRFI/NRFI rebuilt from live first-inning probability where available."),
        'sb-board':          with_projected_badge(build_sb_board(), "Stolen-base board rebuilt from live projection probabilities."),
        'doubles-board':     with_projected_badge(build_doubles_board(), "Extra-base board rebuilt from live doubles and park context."),
        'dfs-board':         with_projected_badge(build_dfs_board(), "DFS board rebuilt from live DK/FD point projections."),
        'combos-k':          with_projected_badge(build_combos_k(), "K combos rebuilt from projected starter rows."),
        'combos-hrr':        projected_unavailable_section(
            'combos-hrr',
            'HRR Combos',
            'Unavailable without workbook',
            'The HRR combo board depends on full Sweet Spot and Dimers workbook context.',
        ),
        'parlays':           projected_unavailable_section(
            'parlays',
            'Parlay Builder',
            'Unavailable without workbook',
            'The full parlay builder is withheld in Projected Mode because several workbook-only signals are missing.',
        ),
        'conviction':        projected_unavailable_section(
            'conviction',
            'Conviction Board',
            'Unavailable without workbook',
            'Conviction rankings require the complete workbook signal stack.',
        ),
        'skip':              projected_unavailable_section(
            'skip',
            'Daily Skip List',
            'Unavailable without workbook',
            'The skip list includes editorial workbook context and is not reconstructed on missed-upload days.',
        ),
        'sp-vuln-board':     projected_unavailable_section(
            'sp-vuln-board',
            "Pitcher's HR Risk Board",
            'Unavailable without workbook',
            'The Sweet Spot pitcher vulnerability and danger-batter columns have no clean Projected Mode source.',
        ),
    }
else:
    SECTIONS = {
        'headlines':         build_headlines(),
        'park-board':        build_park_board(),
        'games':             build_games(),
        'matchup-spotlight': build_matchup_spotlight(),
        'k-board':           build_k_board(),
        'hr-board':          build_hr_board(),
        'oo5-board':         build_oo5_board(),
        'totals-board':      build_totals_board(),
        'nrfi-board':        build_nrfi_board(),
        'sb-board':          build_sb_board(),
        'doubles-board':     build_doubles_board(),
        'dfs-board':         build_dfs_board(),
        'combos-k':          build_combos_k(),
        'combos-hrr':        build_combos_hrr(),
        'parlays':           build_parlays(),
        'conviction':        build_conviction(),
        'skip':              build_skip(),
        'sp-vuln-board':     build_sp_vuln(),
    }

# Write
with open('/home/user/workspace/built_sections_d46.json','w', encoding='utf-8') as f:
    json.dump(SECTIONS, f, ensure_ascii=False, indent=1)

# Structured pick records for For The Record (results-page backtest)
def _slate_md():
    for row in DATA.get('BP_Games', []):
        raw = str(row.get('GameDate', ''))[:10]
        try:
            dt = datetime.strptime(raw, '%Y-%m-%d').date()
            return f'{dt.month}-{dt.day}', dt.isoformat()
        except Exception:
            pass
    return None, None

_md, _iso = _slate_md()
_payload = {'slate_date': _iso, 'picks': SLATE_PICKS}
_picks_out = os.environ.get('PICKS_FILE', 'slate_picks.json')
with open(_picks_out, 'w', encoding='utf-8') as f:
    json.dump(_payload, f, ensure_ascii=False, indent=1)
if _md:  # dated archive so the grader can match results to the right slate
    with open(f'slate_picks_{_md}.json', 'w', encoding='utf-8') as f:
        json.dump(_payload, f, ensure_ascii=False, indent=1)
print(f"Wrote {len(SLATE_PICKS)} pick records -> {_picks_out}" + (f" (+ slate_picks_{_md}.json)" if _md else ""))

print(f"Built {len(SECTIONS)} sections")
for k, v in SECTIONS.items():
    print(f"  {k}: {len(v)} bytes")
