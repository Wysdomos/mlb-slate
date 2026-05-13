"""Day 46 Build — May 12, 2026 — Full Slate (15 games) + new SP_Projections integration.

Structure: Day 44 board depth + Day 45 canonical section labels.
Reads: /home/user/workspace/day46_data.json
Writes: /home/user/workspace/built_sections_d46.json
"""
import json, re
from datetime import datetime

DATA = json.load(open('/home/user/workspace/day46_data.json'))

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
    except: return 0

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
    except: return '—'
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
    except: return f'<span style="color:var(--text-dim)">{v}</span>'
    if vv >= 50: return f'<strong style="color:var(--bad)">V{vv} 🔥</strong>'
    if vv >= 32: return f'<span style="color:var(--hot)">V{vv}</span>'
    return f'<span style="color:var(--text-dim)">V{vv}</span>'

def batter_bats(name):
    """Lookup batter handedness (L/R/S) from BP_Batters by full name."""
    if not name: return None
    r = BP_BAT_BY_NAME.get(str(name).strip().lower())
    return r.get('BatterStand') if r else None

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
        except: iso_f = 0
        iso_disp = iso if iso.startswith('.') else f'.{iso}'
        if iso_f >= 0.280: iso_html = f'<strong style="color:var(--bad)">{iso_disp}</strong>'
        elif iso_f >= 0.250: iso_html = f'<span style="color:var(--hot)">{iso_disp}</span>'
        elif iso_f >= 0.200: iso_html = f'<span style="color:var(--good)">{iso_disp}</span>'
        else: iso_html = iso_disp
        parts.append(f'ISO {iso_html}')
    if zone:
        parts.append(f'<span style="color:var(--hot)">{zone}</span>')
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
  <div class="flag-row"><div class="icon">🎯</div><div><strong>SP HR-Vulnerability Board (NEW — using SP_Projections data):</strong> Eury Pérez 1.02 HR/9 (vs MIN, V46), Miles Mikolas 1.02 (vs CIN, V76), Erick Fedde 0.86 (vs KC, V29), Slade Cecconi 0.86 (vs LAA, V56), Bailey Ober 0.85 (vs MIA, V25). All five have <strong>HR-stack potential</strong> — see new "SP HR/BB Risk Board" section.</div></div>
  <div class="flag-row"><div class="icon">🥶</div><div><strong>Fenway -23% / Truist -23% / PNC -20% HR all FADED.</strong> Phillies @ BOS (Fenway weather suppressed -23% HR but +18% 2B/3B — doubles play). CHC @ ATL (Truist -23%) and COL @ PIT (-20%) skip HR alts. Citi Field -14% HR / -29% 2B/3B = full suppressor — DET @ NYM is the under spot (NRFI 56%+).</div></div>
  <div class="flag-row"><div class="icon">📋</div><div><strong>SKIP arms / fades:</strong> Walbert Urena (LAA, K only 4.0 — skip K alts), Erick Fedde (CHW, K 2.6 — skip K alts entirely), Brayan Bello (BOS, K 2.9 — skip), Patrick Corbin (TOR, K 3.0 — skip). All HR plays at Citi/Fenway/Truist/PNC. Pivot to 1+H / RBI plays in suppressed parks.</div></div>
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
        except: return 9999
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
            except: return ''
            v_str = f'V{vuln}' if vuln != '—' else ''
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
            except: return '—'
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
            innings = r.get('Innings') or 0
            outs = innings * 3 if innings else 0
            hits = r.get('HitsAllowed') or 0
            qs = r.get('QualityStart') or 0
            hra = r.get('HomeRunsAllowed') or 0
            bp_bb = r.get('Walks') or 0
            # Format with indicators (Day 44 thresholds: Outs ≥17 = green 🟢, <14 = red 🔻)
            if outs:
                if outs >= 17: outs_s = f'<strong style="color:var(--good)">🟢 {outs:.1f}</strong>'
                elif outs < 14: outs_s = f'<span style="color:var(--bad)">🔻 {outs:.1f}</span>'
                else: outs_s = f'{outs:.1f}'
            else: outs_s = '—'
            # Hits: ≥6.0 = red (hot), ≤5.0 = green (cold)
            if hits:
                if hits >= 6.0: hits_s = f'<span style="color:var(--hot)">🔺 {hits:.2f}</span>'
                elif hits <= 5.0 and hits > 0: hits_s = f'<strong style="color:var(--good)">{hits:.2f}</strong>'
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
            except: pass
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
                f'<td><strong>V{vuln}</strong></td>'
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
        if isinstance(ap_vuln, int) and ap_vuln >= 50: notes_bits.append(f'{ap_name} V{ap_vuln} 🔥 — target {away} stack.')
        if isinstance(hp_vuln, int) and hp_vuln >= 50: notes_bits.append(f'{hp_name} V{hp_vuln} 🔥 — target {home} stack.')
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

    def batter_bats(name):
        if not name: return None
        r = BP_BAT_BY_NAME.get(name.lower())
        if r: return r.get('BatterStand')
        # Fallback: Sweet_Spot_Analyzer
        for s in SSA:
            if (s.get('Batter') or '').strip().lower() == name.lower():
                return s.get('Bats')
        return None

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
        try: v = int(sp.get('VulnScore') or 0)
        except: v = 0
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
        vuln_cell = f'<td>{vuln_s}</td>'
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
            f'      <tr class="{row_cls}">{pitcher_cell}{era_cell}{k9_cell}{vuln_cell}{park_cell}'
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
    <p style="font-size:11px; color:var(--text-dim); margin-top:10px;">Hit% / HR% from <strong>Hit_Probabilities</strong>. ISO from <strong>Sweet_Spot_Slate</strong> DangerBatter columns.</p>
  </div></div>
</section>
'''

# ---- BUILD: K BOARD (Day 44 structure: Tier | Pitcher | B | Tm | SS Ks | BPP Ks | Outs | Hits | ERA | QS% | HRA | Vuln | Best Line | Note) ----
def build_k_board():
    sp_sorted = sorted(SP_PROJ, key=lambda r: -(r.get('K') or 0))
    rows = []
    for r in sp_sorted:
        name = r.get('Pitcher','')
        ss_k = r.get('K')  # SP_Projections K (= SS Ks)
        try: kf = float(ss_k) if ss_k is not None else 0
        except: kf = 0

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
            if hits >= 5.0: hits_s = f'<span style="color:var(--hot)">🔺 {hits:.2f}</span>'
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
        except: vuln_n = 0
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
        note = ' · '.join(note_parts) if note_parts else '—'

        rows.append(
            f'      <tr class="{tier_cls}">'
            f'<td>{tier_badge}</td>'
            f'<td><strong>{name}</strong></td>'
            f'<td style="text-align:center">{hand_chip(throws,"throws")}</td>'
            f'<td>{team}</td>'
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
        )
    table_body = '\n'.join(rows)

    return f'''<!-- K BOARD -->
<section id="k-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">⚡ Full K's Tier Board</div>
      <span class="game-tag">Tap to expand · {len(sp_sorted)} starters · ordered by SS K desc · Skenes/Wheeler T0</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">SS Ks from <strong>SP_Projections</strong>, BPP Ks from <strong>BP_Pitchers</strong>. <strong>Tier:</strong> T0 ≥5.5 · T1 4.5–5.4 · T2 4.0–4.4 · SKIP &lt;4.0. <strong>Best Line:</strong> ≥5 → O 5+, 4.5–4.99 → O 3.5, &lt;4.5 → O 2.5.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Tier</th><th>Pitcher</th><th>B</th><th>Tm</th><th>SS Ks</th><th>BPP Ks</th><th>Outs</th><th>Hits</th><th>ERA</th><th>QS%</th><th>HRA</th><th>Vuln</th><th>Best Line</th><th>Note</th></tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
    <p style="font-size:11px; color:var(--text-dim); margin-top:10px;">🟢 Outs ≥17. 🔻 Outs &lt;14. 🔺 Hits ≥5.0. QS% ≥40% bold. HRA ≥0.85 caution.</p>
  </div></div>
</section>
'''

# ---- BUILD: HR BOARD (top 25) ----
def build_hr_board():
    rows = []
    for r in HR_LB[:25]:
        score = r.get('Score',0)
        if score >= 80: tier = 'row-tier0'
        elif score >= 70: tier = 'row-tier1'
        else: tier = ''
        team = tn(r.get('Team',''))
        park = PARK_BY_TEAM.get(team)
        park_hr = parse_pct(park.get('HR %')) if park else 0
        hr_pct = '—'
        rbi_pct = '—'
        nm = r.get('Batter','')
        hr_row = HIT_BY_NAME.get(nm.lower())
        if hr_row:
            hr_pct = hr_row.get('To Hit HR','—')
            rbi_pct = hr_row.get('To Get RBI','—')
        # Pitcher handedness + Vuln
        pit_name = r.get('Pitcher','') or ''
        throws = pitcher_throws(pit_name)
        v = get_vuln_for_pitcher(pit_name)
        vuln = v.get('VulnScore') if v else None
        # Inline cells
        batter_cell = f'<strong>{nm}</strong> {hand_chip(r.get("Bats"), "bats")}'
        pitcher_cell = f'{pit_name} {hand_chip(throws, "throws")}' if pit_name and pit_name != '—' else '—'
        rows.append(
            f'      <tr class="{tier}">'
            f'<td>{r.get("Rank","")}</td>'
            f'<td>{batter_cell}</td>'
            f'<td>{team}</td>'
            f'<td>{pitcher_cell}</td>'
            f'<td>{vuln_cell(vuln)}</td>'
            f'<td><strong>{score}</strong></td>'
            f'<td>{r.get("Zone","—")}</td>'
            f'<td>{r.get("Barrel%","—")}</td>'
            f'<td>{hr_pct}</td>'
            f'<td>{rbi_pct}</td>'
            f'<td>{pf_chip(park_hr)}</td>'
            f'</tr>'
        )
    table_body = '\n'.join(rows)

    return f'''<!-- HR BOARD -->
<section id="hr-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🏆 Top 25 HR Board</div>
      <span class="game-tag">Tap to expand · HR_Leaderboard top 25 · handedness + Vuln · park cross-ref</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Sourced from <strong>HR_Leaderboard</strong> (Quality Score = Barrel% · HH% · Zone · xwOBA · Launch · Pull%, park-adjusted). All bats here use <strong>Ov 0.5</strong> on the HR ladder. Vuln ≥50 = 🔥 stack target.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>vs Pitcher</th><th>Vuln</th><th>Score</th><th>Zone</th><th>Barrel%</th><th>HR%</th><th>RBI%</th><th>Park HR%</th></tr></thead>
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
        except: return 0
    hp_sorted = sorted(HIT, key=lambda r: -hp_val(r,'1+ Hit'))[:50]
    rows = []
    for i, r in enumerate(hp_sorted, 1):
        nm = _hit_full(r)
        team = tn(r.get('Team',''))
        bp = BP_BAT_BY_NAME.get(nm.lower())
        bats = bp.get('BatterStand') if bp else None
        # Opp pitcher from BP_Batters Opponent
        opp_team = tn(bp.get('Opponent','')) if bp else ''
        opp_sp_row = SP_BY_TEAM.get(opp_team) if opp_team else None
        opp_sp = opp_sp_row.get('Pitcher') if opp_sp_row else None
        v = get_vuln_for_pitcher(opp_sp) if opp_sp else None
        vuln = v.get('VulnScore') if v else None
        try: vv = int(vuln) if vuln is not None else 0
        except: vv = 0
        h1 = r.get('1+ Hit','—')
        h2 = r.get('2+ Hits ','—')
        rbi = r.get('To Get RBI','—')
        hr = r.get('To Hit HR','—')
        match = r.get('Matchup','—')
        try: h1f = float(str(h1).replace('%',''))
        except: h1f = 0
        if h1f >= 65: tier = 'row-tier0'
        elif h1f >= 60: tier = 'row-tier1'
        else: tier = ''
        batter_cell = f'<strong>{nm}</strong> {hand_chip(bats, "bats")}'
        # Matchup cell: add Vuln color/🔥 if pitcher resolved
        if opp_sp:
            match_cell = f'{match} · {vuln_cell(vuln)}'
        else:
            match_cell = match
        rows.append(
            f'      <tr class="{tier}"><td>{i}</td>'
            f'<td>{batter_cell}</td>'
            f'<td>{team}</td>'
            f'<td>{match_cell}</td>'
            f'<td><strong>{h1}</strong></td>'
            f'<td>{h2}</td>'
            f'<td>{rbi}</td>'
            f'<td>{hr}</td>'
            f'</tr>'
        )
    return f'''<!-- OO5 BOARD -->
<section id="oo5-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">☄️ Top 50 Hits Board</div>
      <span class="game-tag">Tap to expand · Hit_Probabilities sorted by 1+ Hit% · handedness + opp Vuln</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Default play: <strong>Ov 0.5</strong> hits. Top 50 bats by 1+ Hit% from <strong>Hit_Probabilities</strong>. Matchup cell shows opp-SP Vuln (≥50 = 🔥 stack target).</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>Matchup</th><th>1+H</th><th>2+H</th><th>RBI</th><th>HR</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: TOTALS BOARD (game totals from BP_Games) ----
def build_totals_board():
    rows = []
    games_sorted = sorted(GAMES_RAW, key=lambda g: -((g.get('RunsAway') or 0) + (g.get('RunsHome') or 0)))
    for g in games_sorted:
        away = tn(g.get('AwayTeam'))
        home = tn(g.get('HomeTeam'))
        ra = g.get('RunsAway') or 0
        rh = g.get('RunsHome') or 0
        total = ra + rh
        f5 = total * 0.55
        if total >= 10: lean = '<span class="badge b-tier0">OVER lean</span>'
        elif total >= 9: lean = '<span class="badge b-tier1">OVER lean</span>'
        elif total <= 7.5: lean = '<span class="badge b-bad">UNDER lean</span>'
        elif total <= 8.5: lean = '<span class="badge b-warn">UNDER lean</span>'
        else: lean = '<span class="badge b-neutral">Neutral</span>'
        rows.append(
            f'      <tr><td>{away} @ {home}</td><td>{ra:.2f}</td><td>{rh:.2f}</td>'
            f'<td><strong>{total:.2f}</strong></td><td>{f5:.2f}</td><td>{lean}</td></tr>'
        )
    return f'''<!-- TOTALS BOARD -->
<section id="totals-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">📈 Game Totals & F5 Board</div>
      <span class="game-tag">Tap to expand · 15 games · BP_Games projections</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Total runs (away + home) and approx F5. Lean derived from projected total only — confirm against book line.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Game</th><th>Away R</th><th>Home R</th><th>Total</th><th>F5 (~)</th><th>Lean</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: NRFI / YRFI ----
def build_nrfi_board():
    # Heuristic: NRFI candidates = both SPs have low HR/9 + decent K
    rows = []
    games_sorted = sorted(GAMES_RAW, key=lambda g: ((g.get('RunsAway') or 0) + (g.get('RunsHome') or 0)))
    for g in games_sorted:
        away = tn(g.get('AwayTeam'))
        home = tn(g.get('HomeTeam'))
        ap = SP_BY_TEAM.get(away)
        hp = SP_BY_TEAM.get(home)
        if not ap or not hp: continue
        # Combined HR/9 of both starters
        try:
            hr_combined = float(ap.get('HR',0)) + float(hp.get('HR',0))
            k_combined = float(ap.get('K',0)) + float(hp.get('K',0))
        except: continue
        # NRFI rating
        nrfi_score = (12 - hr_combined*4) + (k_combined/2)
        if nrfi_score >= 12: lean = '<span class="badge b-tier0">NRFI</span>'
        elif nrfi_score >= 10: lean = '<span class="badge b-tier1">Lean NRFI</span>'
        elif nrfi_score <= 8: lean = '<span class="badge b-bad">YRFI</span>'
        else: lean = '<span class="badge b-neutral">Neutral</span>'
        rows.append(
            f'      <tr><td>{away} @ {home}</td>'
            f'<td>{ap["Pitcher"]}</td><td>{ap.get("HR","—")}</td><td>{ap.get("K","—")}</td>'
            f'<td>{hp["Pitcher"]}</td><td>{hp.get("HR","—")}</td><td>{hp.get("K","—")}</td>'
            f'<td>{lean}</td></tr>'
        )
    return f'''<!-- NRFI BOARD -->
<section id="nrfi-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🥶 NRFI / YRFI Watch</div>
      <span class="game-tag">Tap to expand · derived from SP HR/9 + K</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Heuristic blend of both SPs' HR/9 (lower = better) and K (higher = better). Confirm against book NRFI line.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Game</th><th>Away SP</th><th>HR/9</th><th>K</th><th>Home SP</th><th>HR/9</th><th>K</th><th>Lean</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: SB BOARD ----
def build_sb_board():
    # From BP_Batters StolenBaseProbability sorted desc
    sb_sorted = sorted(BP_BAT, key=lambda r: -(r.get('StolenBaseProbability') or 0))[:20]
    rows = []
    for i, r in enumerate(sb_sorted, 1):
        if not r.get('FullName'): continue
        sbp = r.get('StolenBaseProbability') or 0
        if sbp < 0.05: continue
        team = tn(r.get('Team'))
        opp = tn(r.get('Opponent'))
        # Opp SP — pull their BB to flag walk-prone (more SB chances)
        opp_sp = SP_BY_TEAM.get(opp)
        opp_bb = opp_sp.get('BB','—') if opp_sp else '—'
        sb_pct = f'{sbp*100:.1f}%'
        if sbp >= 0.15: tier = 'row-tier0'
        elif sbp >= 0.10: tier = 'row-tier1'
        else: tier = ''
        rows.append(
            f'      <tr class="{tier}"><td>{i}</td>'
            f'<td><strong>{r["FullName"]}</strong></td>'
            f'<td>{team}</td>'
            f'<td>{opp}</td>'
            f'<td><strong>{sb_pct}</strong></td>'
            f'<td>{opp_bb}</td></tr>'
        )
    return f'''<!-- SB BOARD -->
<section id="sb-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🏃 Stolen Base Targets</div>
      <span class="game-tag">Tap to expand · BP_Batters SB% · opp SP BB cross-ref</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Top 20 runners by stolen-base probability. Opp SP BB column flags high-walk arms (more on-base = more SB opportunity). Plays use <strong>Ov 0.5</strong>.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Runner</th><th>Tm</th><th>Opp</th><th>SB %</th><th>Opp SP BB</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

# ---- BUILD: DOUBLES ----
def build_doubles_board():
    # From BP_Batters Doubles projection sorted desc + park 2B/3B%
    db_sorted = sorted(BP_BAT, key=lambda r: -(r.get('Doubles') or 0))[:20]
    rows = []
    for i, r in enumerate(db_sorted, 1):
        if not r.get('FullName'): continue
        dbls = r.get('Doubles') or 0
        team = tn(r.get('Team'))
        opp = tn(r.get('Opponent'))
        park = PARK_BY_TEAM.get(team) or PARK_BY_TEAM.get(opp)
        xbh = parse_pct(park.get('2B/3B %')) if park else 0
        if dbls >= 0.30: tier = 'row-tier0'
        elif dbls >= 0.25: tier = 'row-tier1'
        else: tier = ''
        rows.append(
            f'      <tr class="{tier}"><td>{i}</td>'
            f'<td><strong>{r["FullName"]}</strong></td>'
            f'<td>{team}</td>'
            f'<td>{opp}</td>'
            f'<td><strong>{dbls:.2f}</strong></td>'
            f'<td>{fmt_pct_cell(xbh,10,-10)}</td></tr>'
        )
    return f'''<!-- DOUBLES BOARD -->
<section id="doubles-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">☄️ Doubles Targets</div>
      <span class="game-tag">Tap to expand · BP doubles proj × park 2B/3B%</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Top 20 by projected doubles. Fenway +18% / PNC +13% 2B/3B = highlight venues today. Plays use <strong>Ov 0.5</strong>.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>Opp</th><th>Proj 2B</th><th>Park 2B/3B%</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
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
        dk = r.get('PointsDK',0) or 0
        fd = r.get('PointsFD',0) or 0
        hr_p = r.get('HomeRunProbability',0) or 0
        hit_p = r.get('HitProbability',0) or 0
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
    skip_pitchers = sorted([r for r in SP_PROJ if (r.get('K') or 0) < 3.5], key=lambda r: (r.get('K') or 0))
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
    sp_sorted = sorted(SP_PROJ, key=lambda r: -((r.get('HR') or 0)*2 + (r.get('BB') or 0)*0.5 - (r.get('K') or 0)*0.3))
    rows = []
    for r in sp_sorted:
        hr = r.get('HR') or 0
        bb = r.get('BB') or 0
        k = r.get('K') or 0
        v = get_vuln_for_pitcher(r['Pitcher'])
        vuln = v.get('VulnScore') if v else None
        danger = v.get('DangerBatter1') if v else '—'
        throws = pitcher_throws(r['Pitcher'])
        # Row tier from vuln (HR-stack target indicator)
        try: vv = int(vuln) if vuln is not None else 0
        except: vv = 0
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
      <div class="game-title">☢️ SP HR/BB Risk Board</div>
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

print(f"Built {len(SECTIONS)} sections")
for k, v in SECTIONS.items():
    print(f"  {k}: {len(v)} bytes")
