"""
build_k_report.py — The Safe K Report
======================================
Reads:  day_data.json        (or DATA_FILE env var)
Writes: k-report.html        (or K_REPORT_FILE env var)

Runs as a standalone script OR as part of the daily pipeline:
    python3 build_k_report.py
    DATA_FILE=day_data.json K_REPORT_FILE=k-report.html python3 build_k_report.py

12-Point Grading Model
-----------------------
Phase 1 (workbook):
  1. IP Protection          SP_Projections.Inn     >= 5.5 green / >= 5.0 yellow
  2. Projected Ks           SP_Projections.K       >= 5.0 green / >= 4.5 yellow
  3. Quality Start %        BP_Pitchers.QualityStart >= 50% green / >= 35% yellow
  4. Opp Team K Rate        BP_Teams.Strikeouts    >= 9.0 green / >= 8.0 yellow
  5. Walk Rate              SP_Projections.BB      <= 2.0 green / <= 3.0 yellow
  6. Batters Faced          SP_Projections.BF      >= 22 green / >= 20 yellow

Phase 2 (pybaseball — unlocks when k_savant_data.json is present):
  7. SwStr% / Whiff%        Savant pitching stats
  8. Opp Lineup Chase%      Savant team batting stats
  9. K-Pitch Arsenal Whiff% Savant pitch arsenal
  10. Opp Lineup Season K%  Savant team batting stats
  11. Home / Away Split     Savant splits
  12. Recent Form (last 5)  Savant game logs, weighted

Tier → O Line:
  Diamond  (6/6 P1 or 10-12/12 P2) → O 3.5
  Elite    (5/6 or 8-9/12)          → O 2.5
  Strong   (4/6 or 7/12)            → O 2.5
  Strong   (3/6 or 6/12)            → O 1.5
  Borderline (2/6 or 4-5/12)        → O 1.5
  Fade     (<=1/6 or <=3/12)        → No play
"""

import json, os, re, random
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────
DATA_FILE     = os.environ.get('DATA_FILE',     'day_data.json')
K_REPORT_FILE = os.environ.get('K_REPORT_FILE', 'k-report.html')
SAVANT_FILE   = os.environ.get('K_SAVANT_FILE', 'k_savant_data.json')  # Phase 2

# ── Load data ───────────────────────────────────────────────────────────────
DATA = json.load(open(DATA_FILE, encoding='utf-8'))

SP_PROJ = DATA.get('SP_Projections', [])
BP_PIT  = DATA.get('BP_Pitchers', [])
BP_TEAM = DATA.get('BP_Teams', [])
PARKS   = DATA.get('Park_Factors', [])

# Phase 2 — load if available
SAVANT = {}
if os.path.exists(SAVANT_FILE):
    SAVANT = json.load(open(SAVANT_FILE, encoding='utf-8'))
PHASE2_ACTIVE = bool(SAVANT)

# Real prop lines — load if available (from balldontlie)
K_PROPS_FILE = os.environ.get('K_PROPS_FILE', 'k_props.json')
K_PROPS = {}
if os.path.exists(K_PROPS_FILE):
    K_PROPS = json.load(open(K_PROPS_FILE, encoding='utf-8'))
PROPS_ACTIVE = bool(K_PROPS)

def floor_value(ou_str):
    """Numeric floor from an 'O 3.5' style string."""
    try:
        return float(str(ou_str).replace('O', '').replace('o', '').strip())
    except (TypeError, ValueError):
        return None

# ── Lookup indexes ──────────────────────────────────────────────────────────
bpp_by_last = {}
for r in BP_PIT:
    ln = (r.get('LastName') or '').strip().lower()
    fn = (r.get('FullName') or '').strip().lower()
    bpp_by_last[ln] = r
    bpp_by_last[fn] = r

bpt_by_team = {}
for r in BP_TEAM:
    t = (r.get('Team') or '').strip()
    bpt_by_team[t] = r

park_by_game = {}
for p in PARKS:
    park_by_game[p.get('Game', '')] = p

# ── Date / slate info from data ─────────────────────────────────────────────
def get_slate_info():
    date_str = 'Today'
    day_label = ''
    game_count = len(PARKS)

    if PARKS and PARKS[0].get('Date'):
        try:
            d = datetime.strptime(str(PARKS[0]['Date'])[:10], '%Y-%m-%d')
            date_str = d.strftime('%B %-d, %Y')
            day_label = d.strftime('%A')
        except Exception:
            pass

    # Try INDEX sheet for Day N label
    idx = DATA.get('INDEX', [])
    for row in idx:
        for cell in (row if isinstance(row, (list, tuple)) else row.values()):
            if cell and 'Day' in str(cell) and 'Slate' in str(cell):
                m = re.search(r'\(Day (\d+)\)', str(cell))
                if m:
                    day_label = f'Day {m.group(1)} · {day_label}'
                break

    return date_str, f'{game_count}-Game {day_label} Slate'.strip(' ·')

DATE_STR, SLATE_DAY = get_slate_info()

# ── Helpers ─────────────────────────────────────────────────────────────────
def sf(v, d=0.0):
    try: return float(v) if v not in (None, '', 'None') else d
    except (TypeError, ValueError): return d

def parse_pct(s):
    if s is None: return 0.0
    try: return float(str(s).replace('%','').replace('+','').strip())
    except (TypeError, ValueError): return 0.0

def get_bpp(name):
    ln = name.strip().split()[-1].lower()
    return bpp_by_last.get(ln) or bpp_by_last.get(name.strip().lower())

def get_park(team, opp):
    for game, p in park_by_game.items():
        parts = game.replace(' ', '').split('@')
        if len(parts) == 2:
            away, home = parts[0].strip(), parts[1].strip()
            if team.strip() in [away, home] or opp.strip() in [away, home]:
                return p
    return None

def grade(val, green_thresh, yellow_thresh):
    """Higher is better."""
    v = sf(val)
    if v >= green_thresh:  return 'green'
    if v >= yellow_thresh: return 'yellow'
    return 'red'

def grade_inv(val, green_thresh, yellow_thresh):
    """Lower is better (for walk rate)."""
    v = sf(val)
    if v <= green_thresh:  return 'green'
    if v <= yellow_thresh: return 'yellow'
    return 'red'

def grade_qs(val):
    v = sf(val)
    if v >= 0.50: return 'green'
    if v >= 0.35: return 'yellow'
    return 'red'

def tier_and_ou(phase1_score, phase2_loaded_count, score, total_pts, k_proj_green):
    """
    Multi-path tier system with Phase 1 perfection bonus and K proj gate.

    Diamond paths:
      A — Phase 1 perfect (6/6) + K proj + ≥2 Phase 2 green
      B — Phase 1 missing ≤2 (4-5/6) + K proj + total ≥9
      C — Phase 1 missing >2 (≤3/6) + K proj + total ≥9  → warn=True
    Phase 1 only fallback (no Phase 2 loaded): Diamond = 6/6 + K proj

    Returns (tier, icon, ou, ou_cls, warn)
    warn=True adds ⚠️ to Diamond badge when Phase 1 is weak.
    """
    warn = False
    p2_active = phase2_loaded_count > 0

    # Determine tier (checked in priority order)
    tier = None
    if k_proj_green:
        if p2_active:
            if phase1_score == 6 and score >= 8:
                tier, icon = 'DIAMOND', '💎'                    # Path A
            elif phase1_score >= 4 and score >= 9:
                tier, icon = 'DIAMOND', '💎'                    # Path B
            elif phase1_score <= 3 and score >= 9:
                tier, icon = 'DIAMOND', '💎'; warn = True       # Path C ⚠️
            elif phase1_score >= 5 and score >= 7:
                tier, icon = 'ELITE', '🏆'
        else:
            # Phase 1 only
            if phase1_score == 6:   tier, icon = 'DIAMOND', '💎'
            elif phase1_score >= 5: tier, icon = 'ELITE',   '🏆'

    if tier is None:
        if p2_active:
            if score >= 5:   tier, icon = 'STRONG',     '💪'
            elif score >= 3: tier, icon = 'BORDERLINE', '⚪'
            else:            tier, icon = 'FADE',       '❌'
        else:
            if phase1_score >= 3:   tier, icon = 'STRONG',     '💪'
            elif phase1_score >= 2: tier, icon = 'BORDERLINE', '⚪'
            else:                   tier, icon = 'FADE',       '❌'

    # O-line floors (unchanged)
    if tier == 'DIAMOND':                          ou, cls = 'O 3.5', 'ou-top'
    elif tier == 'ELITE':                          ou, cls = 'O 2.5', 'ou-mid'
    elif tier == 'STRONG' and phase1_score >= 4:   ou, cls = 'O 2.5', 'ou-mid'
    elif tier == 'STRONG':                         ou, cls = 'O 1.5', 'ou-low'
    elif tier == 'BORDERLINE':                     ou, cls = 'O 1.5', 'ou-low'
    else:                                          ou, cls = '—',     'ou-none'

    return tier, icon, ou, cls, warn

# ── Grade every pitcher ─────────────────────────────────────────────────────
OU_COLOR = {'ou-top': '#3b82f6', 'ou-mid': '#22c55e', 'ou-low': '#eab308'}

pitchers = []
for sp in SP_PROJ:
    name    = (sp.get('Pitcher') or '').strip()
    team    = (sp.get('Team')    or '').strip()
    opp     = (sp.get('Opp')     or '').strip()
    inn     = sf(sp.get('Inn'))
    k_proj  = sf(sp.get('K'))
    bf      = sf(sp.get('BF'))
    bb      = sf(sp.get('BB'))

    bpp      = get_bpp(name)
    qs       = sf(bpp.get('QualityStart') if bpp else None)
    bpp_w    = sf(bpp.get('Walks')        if bpp else None)
    proj_bb  = bb if bb > 0 else bpp_w

    ot       = (bpt_by_team.get(opp) or bpt_by_team.get(opp + ' ')
                or bpt_by_team.get(' ' + opp))
    opp_k    = sf(ot.get('Strikeouts') if ot else None)

    park     = get_park(team, opp)
    runs_pct = parse_pct(park.get('Runs %') if park else None)
    venue    = (park.get('Venue', '') if park else '') or ''
    game_str = (park.get('Game',  '') if park else '') or ''
    is_road  = game_str.startswith(team.strip())

    # Phase 1 — 6 workbook criteria
    c1 = grade(inn,     5.5, 5.0)   # IP protection
    c2 = grade(k_proj,  5.0, 4.5)   # Projected Ks
    c3 = grade_qs(qs)               # QS%
    c4 = grade(opp_k,   9.0, 8.0)   # Opp team K rate
    c5 = grade_inv(proj_bb, 2.0, 3.0) # Walk rate (lower = better)
    c6 = grade(bf,     22.0, 20.0)  # Batters faced

    p1_val = f'{inn:.1f}'
    p2_val = f'{k_proj:.1f}'
    p3_val = f'{qs*100:.1f}%'
    p4_val = f'{opp_k:.1f}'
    p5_val = f'{proj_bb:.1f}'
    p6_val = f'{bf:.0f}'

    phase1_score = sum(1 for c in [c1, c2, c3, c4, c5, c6] if c == 'green')

    # Phase 2 — balldontlie metrics. Score only the ones that actually loaded.
    # total_pts adjusts dynamically so the denominator is always honest.
    savant = SAVANT.get(name.lower(), {})

    def p2(metric, green, yellow, fmt):
        v = savant.get(metric)
        if v is None or v == '':
            return (None, None)
        fv = sf(v)
        return (grade(fv, green, yellow), fmt(fv))

    c7,  p7_val  = p2('swstr_pct',        11.0, 10.0, lambda x: f'{x:.1f}%')
    c8,  p8_val  = p2('chase_pct',        29.0, 27.0, lambda x: f'{x:.1f}%')
    c9,  p9_val  = p2('arsenal_whiff',    30.0, 28.0, lambda x: f'{x:.1f}%')
    c10, p10_val = p2('opp_lineup_k_pct', 24.0, 22.0, lambda x: f'{x:.1f}%')
    c11, p11_val = p2('ha_split',          0.5,  0.3, lambda x: f'{x:+.1f}K')
    c12, p12_val = p2('recent_form',       5.5,  4.5, lambda x: f'{x:.1f}')

    p2_loaded = [c for c in [c7, c8, c9, c10, c11, c12] if c is not None]
    phase2_score = sum(1 for c in p2_loaded if c == 'green')
    score     = phase1_score + phase2_score
    total_pts = 6 + len(p2_loaded)

    k_proj_green = (c2 == 'green')
    tier, tier_icon, ou, ou_cls, tier_warn = tier_and_ou(
        phase1_score, len(p2_loaded), score, total_pts, k_proj_green
    )

    # Flags (warnings — shown on card, never auto-remove)
    flags = []
    if runs_pct >= 15:    flags.append(('🌋', f'Park {runs_pct:+.0f}% Runs — {venue}', 'red'))
    if qs < 0.15:         flags.append(('📋', f'QS% only {qs*100:.1f}% — short start risk', 'red'))
    if is_road:           flags.append(('🛣️', f'Road start at {venue}', 'yellow'))
    if proj_bb >= 3.5:    flags.append(('⚠️', f'Walk risk — {proj_bb:.1f} proj BB', 'red'))

    red_flag = any(f[2] == 'red' for f in flags)

    pitchers.append({
        'name': name, 'team': team, 'opp': opp, 'venue': venue,
        'inn': inn, 'k': k_proj, 'qs': qs * 100, 'opp_k': opp_k,
        'bf': bf, 'bb': proj_bb,
        # Phase 1 criteria
        'c1':(c1,'IP',p1_val), 'c2':(c2,'Proj K',p2_val), 'c3':(c3,'QS%',p3_val),
        'c4':(c4,'Opp K',p4_val), 'c5':(c5,'Proj BB',p5_val), 'c6':(c6,'BF',p6_val),
        # Phase 2 criteria (None if not active)
        'c7' :(c7,  'SwStr%',  p7_val),  'c8' :(c8,  'Chase%',  p8_val),
        'c9' :(c9,  'Arsenal', p9_val),  'c10':(c10, 'Lineup K%',p10_val),
        'c11':(c11, 'H/A',     p11_val), 'c12':(c12, 'Form×5',  p12_val),
        'score': score, 'total_pts': total_pts,
        'tier': tier, 'tier_icon': tier_icon,
        'ou': ou, 'ou_cls': ou_cls, 'tier_warn': tier_warn,
        'flags': flags, 'red_flag': red_flag,
    })

pitchers.sort(key=lambda x: (-x['score'], -x['k']))

# Tier groups
diamonds   = [p for p in pitchers if p['tier'] == 'DIAMOND']
elites     = [p for p in pitchers if p['tier'] == 'ELITE']
strongs    = [p for p in pitchers if p['tier'] == 'STRONG']
borderlines= [p for p in pitchers if p['tier'] == 'BORDERLINE']
clean_d    = [p for p in diamonds    if not p['red_flag']]
clean_e    = [p for p in elites      if not p['red_flag']]
clean_s    = [p for p in strongs     if not p['red_flag']]

# ── HTML helpers ────────────────────────────────────────────────────────────
TIER_COLOR = {
    'DIAMOND':    '#3b82f6',
    'ELITE':      '#22c55e',
    'STRONG':     '#eab308',
    'BORDERLINE': '#6b7280',
    'FADE':       '#374151',
}

def crit_box(color, label, val):
    if color is None:  # Phase 2 placeholder
        return (f'<div class="crit crit-p2">'
                f'<span class="ci">📡</span>'
                f'<span class="cl">{label}</span>'
                f'<span class="cv">P2</span></div>')
    icon = '✅' if color == 'green' else ('🟡' if color == 'yellow' else '❌')
    return (f'<div class="crit crit-{color}">'
            f'<span class="ci">{icon}</span>'
            f'<span class="cl">{label}</span>'
            f'<span class="cv">{val}</span></div>')

def pitcher_card(p, idx):
    tier_cls  = p['tier'].lower()
    flag_html = ''.join(
        f'<div class="flag flag-{f[2]}">{f[0]} {f[1]}</div>'
        for f in p['flags'])

    # Row 1 — center projection
    pk_color = p['c2'][0]
    pk_icon  = '✅' if pk_color == 'green' else ('🟡' if pk_color == 'yellow' else '❌')

    # Real book line + cushion (only if a line was fetched for this pitcher)
    line_html = ''
    prop = K_PROPS.get(p['name'].lower()) if PROPS_ACTIVE else None
    fl = floor_value(p['ou'])
    if prop and fl is not None:
        book = prop.get('line')
        if book is not None:
            cushion = round(book - fl, 1)
            cush_cls = 'cush-hi' if cushion >= 1.5 else ('cush-mid' if cushion >= 0.5 else 'cush-lo')
            line_html = (
                f'<div class="line-compare">'
                f'<div class="lc-item"><span class="lc-label">Safe Floor</span>'
                f'<span class="lc-val lc-floor">{p["ou"]}</span></div>'
                f'<div class="lc-item"><span class="lc-label">Book Line</span>'
                f'<span class="lc-val lc-book">O/U {book:g}</span></div>'
                f'<div class="lc-item"><span class="lc-label">Cushion</span>'
                f'<span class="lc-val {cush_cls}">{("+" if cushion > 0 else "")}{cushion:g} K</span></div>'
                f'</div>'
            )

    row1 = (f'<div class="proj-row">'
            f'<div class="proj-center crit-{pk_color}">'
            f'<span class="proj-icon">{pk_icon}</span>'
            f'<span class="proj-k">{p["k"]:.1f}</span>'
            f'<span class="proj-label">Proj K</span>'
            f'<div class="ou-badge {p["ou_cls"]}">{p["ou"]}</div>'
            f'</div></div>'
            f'{line_html}')

    # Row 2 — workbook criteria (6 cells)
    row2_cells = ''.join([
        crit_box(p['c1'][0], 'IP',      p['c1'][2]),
        crit_box(p['c3'][0], 'QS%',     p['c3'][2]),
        crit_box(p['c4'][0], 'Opp K',   p['c4'][2]),
        crit_box(p['c5'][0], 'Proj BB', p['c5'][2]),
        crit_box(None,       'Lineup K%', None) if not PHASE2_ACTIVE else crit_box(p['c10'][0], 'Lineup K%', p['c10'][2]),
        crit_box(p['c6'][0], 'BF',      p['c6'][2]),
    ])
    row2 = f'<div class="crit-section"><div class="crit-row r6">{row2_cells}</div></div>'

    # Row 3 — Savant criteria (6 cells)
    row3_cells = ''.join([
        crit_box(p['c7'][0]  if PHASE2_ACTIVE else None, 'SwStr%',   p['c7'][2]  if PHASE2_ACTIVE else None),
        crit_box(p['c8'][0]  if PHASE2_ACTIVE else None, 'Chase%',   p['c8'][2]  if PHASE2_ACTIVE else None),
        crit_box(p['c9'][0]  if PHASE2_ACTIVE else None, 'Arsenal',  p['c9'][2]  if PHASE2_ACTIVE else None),
        crit_box(p['c11'][0] if PHASE2_ACTIVE else None, 'H/A',      p['c11'][2] if PHASE2_ACTIVE else None),
        crit_box(p['c12'][0] if PHASE2_ACTIVE else None, 'Form×5',   p['c12'][2] if PHASE2_ACTIVE else None),
        (f'<div class="crit crit-p2 p2-tag">'
         f'<span class="ci">📡</span>'
         f'<span class="cl" style="color:var(--accent);font-weight:700;">Phase 2</span>'
         f'<span class="cv" style="color:var(--p2);font-size:9px;">{"LIVE" if PHASE2_ACTIVE else "PENDING"}</span>'
         f'</div>'),
    ])
    savant_bg = '' if PHASE2_ACTIVE else ' crit-savant'
    row3 = f'<div class="crit-section{savant_bg}"><div class="crit-row r6">{row3_cells}</div></div>'

    return (f'<article class="pcard tier-{tier_cls}">'
            f'<div class="pc-head">'
            f'<div class="pc-left">'
            f'<span class="pc-rank">#{idx+1}</span>'
            f'<div><div class="pc-name">{p["name"]}</div>'
            f'<div class="pc-match">{p["team"]} vs {p["opp"]} · {p["venue"] or "TBD"}</div></div>'
            f'</div>'
            f'<div class="pc-right">'
            f'<div class="pc-tier tier-{tier_cls}">{p["tier_icon"]} {p["tier"]}{"  ⚠️" if p.get("tier_warn") else ""}</div>'
            f'<div class="pc-score">{p["score"]}<span class="pc-of">/{p["total_pts"]}</span></div>'
            f'</div></div>'
            f'{row1}{row2}{row3}'
            f'{f"<div class=flags>{flag_html}</div>" if flag_html else ""}'
            f'</article>')

def qual_row(p):
    flags_txt = ' '.join(f[0] for f in p['flags'])
    c = OU_COLOR.get(p['ou_cls'], '#6b7280')
    return (f'<div class="qrow tier-{p["tier"].lower()}-border">'
            f'<div class="ql"><span class="qt">{p["tier_icon"]}</span>'
            f'<div><div class="qname">{p["name"]} '
            f'<span class="qteam">{p["team"]} vs {p["opp"]}</span></div>'
            f'<div class="qstats">K: {p["k"]:.1f} · BB: {p["bb"]:.1f} · '
            f'QS: {p["qs"]:.1f}% · OppK: {p["opp_k"]:.1f}</div></div></div>'
            f'<div class="qr">'
            f'<span class="ou-badge {p["ou_cls"]}">{p["ou"]}</span>'
            f'<span class="qscore">{p["score"]}/{p["total_pts"]}</span>'
            f'{f"<span>{flags_txt}</span>" if flags_txt else ""}'
            f'</div></div>')

def pleg(p):
    c = OU_COLOR.get(p['ou_cls'], '#6b7280')
    return (f'<div class="pleg"><div class="pl-info">'
            f'<span class="pl-tier">{p["tier_icon"]}</span>'
            f'<div><span class="pl-name">{p["name"]}</span>'
            f'<span class="pl-match"> · {p["team"]} vs {p["opp"]}</span></div>'
            f'</div><span class="pl-ou" style="color:{c}">{p["ou"]}</span></div>')

def pcard(label, color_top, legs, desc, is_mix=False):
    mix_tag = '<span class="mix-tag">MIX</span>' if is_mix else ''
    return (f'<div class="pcard-parlay" style="border-top:3px solid {color_top}">'
            f'<div class="ph"><span class="pl">{label}{mix_tag}</span>'
            f'<span class="p-legs">{len(legs)}-leg</span></div>'
            f'<div class="pd">{desc}</div>'
            + ''.join(pleg(l) for l in legs) + '</div>')

# ── Build parlays ───────────────────────────────────────────────────────────
# Standard
safe_legs = (clean_d + clean_e)[:2]
mod_legs  = (clean_d + clean_e)[:3]
risk_legs = clean_s[:3]

p_safe = pcard('🟢 Safe',     '#22c55e', safe_legs, '2 legs · Diamond anchors · no red flags')
p_mod  = pcard('🟡 Moderate', '#eab308', mod_legs,  '2–3 legs · Diamond + Elite')
p_risk = pcard('🔴 Risky',    '#ef4444', risk_legs, '3 legs · Strong arms · your call')

# Mix — fully randomized, no repeats
pool = [p for p in pitchers if p['ou'] != '—']
random.shuffle(pool)
used_in_mix = set()

def pick_mix(n):
    legs = []
    for p in pool:
        if p['name'] not in used_in_mix and len(legs) < n:
            legs.append(p)
    for p in legs:
        used_in_mix.add(p['name'])
    return legs

mix_configs = [
    ('🔀 Mix A', '#6366f1', 3, 'Random 3-leg'),
    ('🔀 Mix B', '#f97316', 4, 'Random 4-leg'),
    ('🔀 Mix C', '#3b82f6', 3, 'Random 3-leg'),
    ('🔀 Mix D', '#34d399', 4, 'Random 4-leg'),
    ('🔀 Mix E', '#a855f7', 3, 'Random 3-leg'),
]
mix_cards = []
for label, color, n, desc in mix_configs:
    legs = pick_mix(n)
    if len(legs) >= 2:
        mix_cards.append(pcard(label, color, legs, desc, is_mix=True))

# ── Assemble section HTML ───────────────────────────────────────────────────
cards_html   = ''.join(pitcher_card(p, i) for i, p in enumerate(pitchers))
qualifiers   = [p for p in pitchers if p['tier'] in ('DIAMOND','ELITE')]
qual_html    = (''.join(qual_row(p) for p in qualifiers)
                or '<p class="empty">No qualifying arms today</p>')

# ── Full HTML ───────────────────────────────────────────────────────────────
PHASE_NOTE = ('All 12 points scoring live.' if PHASE2_ACTIVE else
              'Points 1–6 scoring from workbook. Points 7–12 unlock automatically when Colab connects.')

html = f'''<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>📰 The Safe K Report — {DATE_STR}</title>
<style>
:root{{
  --bg:#0a1612;--card:#111c18;--border:#1e2e28;--glass:rgba(255,255,255,0.04);
  --glass-strong:rgba(255,255,255,0.07);
  --text:#ecf1ee;--soft:#c2cec8;--dim:#7a9088;
  --blue:#3b82f6;--blue-bg:rgba(59,130,246,0.15);--blue-bd:rgba(59,130,246,0.42);
  --green:#22c55e;--green-bg:rgba(34,197,94,0.14);--green-bd:rgba(34,197,94,0.40);
  --yellow:#eab308;--yellow-bg:rgba(234,179,8,0.14);--yellow-bd:rgba(234,179,8,0.40);
  --grey:#6b7280;--grey-bg:rgba(107,114,128,0.14);--grey-bd:rgba(107,114,128,0.35);
  --red:#ef4444;--red-bg:rgba(239,68,68,0.14);--red-bd:rgba(239,68,68,0.40);
  --accent:#34d399;--accent-bg:rgba(52,211,153,0.12);--accent-bd:rgba(52,211,153,0.35);
  --p2:#475569;--p2-bg:rgba(71,85,105,0.18);
  --r:12px;--rs:8px;
}}
[data-theme="light"]{{
  --bg:#f1f5f3;--card:#ffffff;--border:rgba(15,23,42,0.12);
  --glass:rgba(15,23,42,0.03);--glass-strong:rgba(15,23,42,0.06);
  --text:#0f1a16;--soft:#2c3935;--dim:#5b6b65;
  --blue:#2563eb;--green:#15803d;--yellow:#b45309;--grey:#64748b;
  --red:#dc2626;--accent:#059669;--p2:#64748b;
}}
.theme-toggle-fab{{position:fixed;bottom:22px;right:16px;z-index:200;width:48px;height:48px;
  border-radius:50%;background:rgba(30,40,60,.9);color:#fff;border:1px solid rgba(255,255,255,0.18);
  display:flex;align-items:center;justify-content:center;font-size:20px;cursor:pointer;
  box-shadow:0 4px 16px rgba(0,0,0,.4);transition:transform .2s;-webkit-tap-highlight-color:transparent}}
.theme-toggle-fab:active{{transform:scale(0.92)}}
[data-theme="light"] .theme-toggle-fab{{background:rgba(255,255,255,.9);color:#0f1a16;border-color:rgba(15,23,42,.15)}}
[data-theme="light"] .kfab-home{{background:rgba(255,255,255,.9) !important;color:#0f1a16}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;
  font-size:14px;line-height:1.5;padding-bottom:60px;-webkit-font-smoothing:antialiased;}}

/* NAV */
.top-nav{{background:rgba(10,22,18,0.96);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--border);padding:12px 16px;
  display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:100;}}
.back{{color:var(--accent);text-decoration:none;font-size:13px;font-weight:600;}}
.nav-t{{font-size:16px;font-weight:800;letter-spacing:-0.02em;}}
.nav-d{{font-size:11px;color:var(--dim);text-align:right;}}

/* HERO */
.hero{{padding:20px 16px 16px;border-bottom:1px solid var(--border);}}
.hero-title{{font-size:32px;font-weight:900;letter-spacing:-0.03em;line-height:1;}}
.hero-title span{{color:var(--accent);}}
.hero-sub{{color:var(--dim);font-size:13px;margin-top:4px;}}
.hero-pills{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;}}
.pill{{padding:5px 12px;border-radius:999px;font-size:12px;font-weight:700;border:1px solid;}}
.pill-blue{{background:var(--blue-bg);border-color:var(--blue-bd);color:var(--blue);}}
.pill-green{{background:var(--green-bg);border-color:var(--green-bd);color:var(--green);}}
.pill-yellow{{background:var(--yellow-bg);border-color:var(--yellow-bd);color:var(--yellow);}}
.pill-grey{{background:var(--grey-bg);border-color:var(--grey-bd);color:var(--grey);}}
.pill-dim{{background:var(--glass);border-color:var(--border);color:var(--dim);}}

/* HOW IT WORKS */
.how-wrap{{margin:12px 16px 0;}}
.how-toggle{{width:100%;background:var(--card);border:1px solid var(--border);
  border-radius:var(--rs);padding:12px 14px;display:flex;justify-content:space-between;
  align-items:center;color:var(--text);font-size:13px;font-weight:600;cursor:pointer;
  font-family:inherit;text-align:left;}}
.how-toggle.open{{border-bottom-left-radius:0;border-bottom-right-radius:0;border-bottom-color:transparent;}}
.how-toggle.open .how-arrow{{transform:rotate(180deg);}}
.how-arrow{{transition:transform .2s;color:var(--accent);font-size:16px;}}
.how-body{{display:none;background:var(--card);border:1px solid var(--border);
  border-top:none;border-bottom-left-radius:var(--rs);border-bottom-right-radius:var(--rs);
  padding:16px 14px;flex-direction:column;gap:16px;}}
.how-body.visible{{display:flex;}}
.how-title{{font-size:13px;font-weight:700;color:var(--text);margin-bottom:6px;}}
.how-body p{{font-size:13px;color:var(--soft);line-height:1.6;margin:0;}}
.how-body strong{{color:var(--accent);}}
.how-grid,.rule-grid{{display:flex;flex-direction:column;gap:6px;margin-top:8px;}}
.how-row{{display:flex;gap:10px;align-items:flex-start;padding:8px 10px;
  background:var(--glass);border-radius:6px;border:1px solid var(--border);}}
.how-tier{{font-size:12px;font-weight:700;white-space:nowrap;min-width:90px;flex-shrink:0;}}
.how-desc{{font-size:12px;color:var(--soft);line-height:1.45;}}
.rule-item{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}}
.rule-badge{{font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px;
  border:1px solid;white-space:nowrap;flex-shrink:0;}}
.rule-desc{{font-size:12px;color:var(--soft);}}

/* SECTION NAV */
.snav{{display:flex;gap:8px;padding:12px 16px;overflow-x:auto;
  border-bottom:1px solid var(--border);scrollbar-width:none;}}
.snav::-webkit-scrollbar{{display:none;}}
.snav a{{white-space:nowrap;padding:7px 14px;border-radius:999px;
  border:1px solid var(--border);background:var(--card);
  color:var(--soft);font-size:12px;font-weight:600;text-decoration:none;}}
.snav a.on{{background:var(--accent-bg);border-color:var(--accent-bd);color:var(--accent);}}

/* SECTION */
.sec{{padding:0 16px;margin-top:20px;}}
.sec-hd{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:var(--dim);margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border);
  display:flex;justify-content:space-between;align-items:center;}}
.sec-hd span{{color:var(--soft);font-size:11px;font-weight:400;text-transform:none;letter-spacing:0;}}
.mnote{{background:var(--accent-bg);border:1px solid var(--accent-bd);border-radius:var(--rs);
  padding:12px 14px;margin-bottom:16px;font-size:12px;color:var(--soft);line-height:1.6;}}
.mnote strong{{color:var(--accent);}}

/* PITCHER CARD */
.pcard{{background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);margin-bottom:10px;overflow:hidden;}}
.tier-diamond{{border-left:5px solid var(--blue);}}
.tier-elite{{border-left:5px solid var(--green);}}
.tier-strong{{border-left:5px solid var(--yellow);}}
.tier-borderline{{border-left:5px solid var(--grey);}}
.tier-fade{{border-left:5px solid #374151;opacity:0.65;}}
.pc-head{{display:flex;justify-content:space-between;align-items:flex-start;padding:12px 14px;gap:10px;}}
.pc-left{{display:flex;align-items:flex-start;gap:8px;flex:1;min-width:0;}}
.pc-rank{{font-size:11px;color:var(--dim);font-weight:600;padding-top:3px;flex-shrink:0;}}
.pc-name{{font-size:15px;font-weight:700;}}
.pc-match{{font-size:11px;color:var(--dim);margin-top:2px;}}
.pc-right{{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0;}}
.pc-tier{{font-size:11px;font-weight:800;white-space:nowrap;}}
.pc-tier.tier-diamond{{color:var(--blue);}}
.pc-tier.tier-elite{{color:var(--green);}}
.pc-tier.tier-strong{{color:var(--yellow);}}
.pc-tier.tier-borderline{{color:var(--grey);}}
.pc-tier.tier-fade{{color:#4b5563;}}
.pc-score{{font-size:20px;font-weight:900;line-height:1;}}
.pc-of{{font-size:12px;color:var(--dim);font-weight:400;}}

/* CENTER PROJECTION ROW */
.proj-row{{border-top:1px solid var(--border);padding:14px;display:flex;justify-content:center;}}
.proj-center{{display:flex;align-items:center;gap:14px;padding:12px 28px;border-radius:10px;border:1px solid;}}
.crit-green.proj-center{{background:var(--green-bg);border-color:var(--green-bd);}}
.crit-yellow.proj-center{{background:var(--yellow-bg);border-color:var(--yellow-bd);}}
.crit-red.proj-center{{background:var(--red-bg);border-color:var(--red-bd);}}
.line-compare{{display:flex;justify-content:center;gap:0;margin:0 14px 14px;border:1px solid var(--border);border-radius:10px;overflow:hidden;}}
.lc-item{{flex:1;text-align:center;padding:8px 6px;border-right:1px solid var(--border);background:var(--glass);}}
.lc-item:last-child{{border-right:none;}}
.lc-label{{display:block;font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;font-weight:600;}}
.lc-val{{display:block;font-size:15px;font-weight:900;margin-top:3px;}}
.lc-floor{{color:var(--accent);}}
.lc-book{{color:var(--soft);}}
.cush-hi{{color:var(--green);}}
.cush-mid{{color:var(--yellow);}}
.cush-lo{{color:var(--red);}}
.proj-icon{{font-size:20px;}}
.proj-k{{font-size:36px;font-weight:900;letter-spacing:-0.03em;line-height:1;}}
.crit-green .proj-k{{color:var(--green);}}
.crit-yellow .proj-k{{color:var(--yellow);}}
.crit-red .proj-k{{color:var(--red);}}
.proj-label{{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em;font-weight:600;}}

/* O BADGE */
.ou-badge{{font-size:14px;font-weight:900;padding:6px 14px;border-radius:8px;
  text-align:center;white-space:nowrap;letter-spacing:-0.01em;}}
.ou-top{{background:var(--blue-bg);border:1px solid var(--blue-bd);color:var(--blue);}}
.ou-mid{{background:var(--green-bg);border:1px solid var(--green-bd);color:var(--green);}}
.ou-low{{background:var(--yellow-bg);border:1px solid var(--yellow-bd);color:var(--yellow);}}
.ou-none{{background:var(--grey-bg);border:1px solid var(--grey-bd);color:var(--grey);font-size:12px;}}

/* CRITERIA ROWS */
.crit-section{{border-top:1px solid var(--border);}}
.crit-savant{{background:rgba(71,85,105,0.06);}}
.crit-row{{border-top:1px solid var(--border);}}
.r6{{display:grid;grid-template-columns:repeat(6,1fr);}}
.crit{{padding:8px 3px;text-align:center;border-right:1px solid var(--border);}}
.crit:last-child{{border-right:none;}}
.ci{{font-size:12px;display:block;}}
.cl{{font-size:8px;color:#ffffff;display:block;margin-top:2px;
  text-transform:uppercase;letter-spacing:.02em;font-weight:600;}}
.cv{{font-size:11px;font-weight:700;display:block;margin-top:2px;}}
.crit-green .cv{{color:var(--green);}}
.crit-yellow .cv{{color:var(--yellow);}}
.crit-red .cv{{color:var(--red);}}
.crit-p2{{background:var(--p2-bg);}}
.crit-p2 .ci{{opacity:0.5;font-size:10px;}}
.crit-p2 .cv{{color:var(--p2);font-size:9px;font-weight:600;}}

/* FLAGS */
.flags{{padding:8px 12px;border-top:1px solid var(--border);display:flex;flex-direction:column;gap:4px;}}
.flag{{font-size:11px;padding:4px 8px;border-radius:6px;}}
.flag-red{{background:var(--red-bg);color:var(--red);border:1px solid var(--red-bd);}}
.flag-yellow{{background:var(--yellow-bg);color:var(--yellow);border:1px solid var(--yellow-bd);}}

/* QUALIFIERS */
.qrow{{display:flex;justify-content:space-between;align-items:center;
  background:var(--card);border:1px solid var(--border);border-radius:var(--rs);
  padding:10px 12px;margin-bottom:8px;gap:10px;}}
.tier-diamond-border{{border-left:4px solid var(--blue);}}
.tier-elite-border{{border-left:4px solid var(--green);}}
.tier-strong-border{{border-left:4px solid var(--yellow);}}
.ql{{display:flex;align-items:center;gap:10px;min-width:0;flex:1;}}
.qt{{font-size:22px;flex-shrink:0;}}
.qname{{font-size:13px;font-weight:700;}}
.qteam{{font-size:11px;color:var(--dim);font-weight:400;}}
.qstats{{font-size:11px;color:var(--dim);margin-top:2px;}}
.qr{{display:flex;align-items:center;gap:8px;flex-shrink:0;}}
.qscore{{font-size:14px;font-weight:800;}}
.empty{{color:var(--dim);font-size:13px;text-align:center;padding:24px;}}

/* PARLAYS */
.parlay-group{{margin-bottom:24px;}}
.group-label{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:var(--dim);margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--border);}}
.parlay-list{{display:flex;flex-direction:column;gap:10px;}}
.pcard-parlay{{background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);padding:14px;}}
.ph{{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;}}
.pl{{font-size:13px;font-weight:700;}}
.p-legs{{font-size:11px;color:var(--dim);font-weight:600;background:var(--glass);
  padding:3px 8px;border-radius:999px;border:1px solid var(--border);}}
.mix-tag{{font-size:9px;font-weight:700;background:rgba(52,211,153,0.15);
  color:var(--accent);padding:2px 6px;border-radius:999px;
  border:1px solid rgba(52,211,153,0.35);letter-spacing:.04em;vertical-align:middle;margin-left:4px;}}
.pd{{font-size:11px;color:var(--dim);margin-bottom:6px;}}
.pleg{{display:flex;justify-content:space-between;align-items:center;
  padding:8px 0;border-top:1px solid var(--border);}}
.pl-info{{display:flex;align-items:center;gap:8px;min-width:0;flex:1;}}
.pl-tier{{font-size:16px;flex-shrink:0;}}
.pl-name{{font-size:13px;font-weight:700;}}
.pl-match{{font-size:11px;color:var(--dim);}}
.pl-ou{{font-size:14px;font-weight:900;flex-shrink:0;margin-left:8px;}}

/* DISCLAIMER */
.disclaimer{{margin:28px 16px 16px;padding:14px 16px;background:var(--glass);
  border:1px solid var(--border);border-radius:var(--rs);border-left:3px solid var(--accent);}}
.disclaimer p{{font-size:12px;color:var(--dim);line-height:1.7;margin:0;}}
.disclaimer strong{{color:var(--soft);}}
.disclaimer .dyod{{font-size:13px;font-weight:800;color:var(--accent);
  display:block;margin-top:8px;letter-spacing:0.02em;}}

/* SCROLL THUMB */
#scroll-track{{position:fixed;right:6px;top:50%;transform:translateY(-50%);
  height:60vh;width:6px;background:rgba(255,255,255,0.06);border-radius:999px;
  z-index:999;}}
#scroll-thumb{{position:absolute;left:50%;transform:translateX(-50%);
  width:24px;height:48px;background:rgba(52,211,153,0.35);
  border:1px solid rgba(52,211,153,0.6);border-radius:999px;cursor:grab;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:3px;touch-action:none;transition:background .15s;}}
#scroll-thumb.dragging{{background:rgba(52,211,153,0.7);cursor:grabbing;}}
.grip-line{{width:10px;height:2px;background:rgba(52,211,153,0.9);border-radius:999px;}}

/* Page FABs for k-report */
.kpage-fab{{position:fixed;right:16px;z-index:200;width:48px;height:48px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;font-size:22px;text-decoration:none;
  border:1px solid rgba(255,255,255,0.18);box-shadow:0 4px 16px rgba(0,0,0,.3);
  transition:transform .2s;-webkit-tap-highlight-color:transparent;}}
.kpage-fab:active{{transform:scale(0.92);}}
.kfab-home{{bottom:80px;background:rgba(30,40,60,.9);}}
.kfab-streaks{{bottom:138px;background:linear-gradient(135deg,#f97316,#ef4444);}}
</style>
</head>
<body>

<!-- FAST SCROLL THUMB -->
<div id="scroll-track">
  <div id="scroll-thumb">
    <div class="grip-line"></div>
    <div class="grip-line"></div>
    <div class="grip-line"></div>
  </div>
</div>

<!-- NAV -->
<nav class="top-nav">
  <a href="index.html" class="back">← Daily Slate</a>
  <div class="nav-t">📰 The Safe K Report</div>
  <div class="nav-d">{DATE_STR}<br>{SLATE_DAY}</div>
</nav>

<!-- HERO -->
<div class="hero">
  <div class="hero-title">The Safe K <span>Report</span></div>
  <div class="hero-sub">Strikeout Prop Analysis · 12-Point Model · Max Line O 3.5</div>
  <div class="hero-pills">
    <div class="pill pill-blue">💎 {len(diamonds)} Diamond · O 3.5</div>
    <div class="pill pill-green">🏆 {len(elites)} Elite · O 2.5</div>
    <div class="pill pill-yellow">💪 {len(strongs)} Strong · O 2.5 / O 1.5</div>
    <div class="pill pill-grey">⚪ {len(borderlines)} Borderline · O 1.5</div>
    <div class="pill pill-dim">⚾ {len(pitchers)} Total</div>
  </div>
</div>

<!-- HOW IT WORKS -->
<div class="how-wrap">
  <button class="how-toggle" onclick="this.classList.toggle('open');document.getElementById('how-body').classList.toggle('visible')">
    <span>📖 How This System Works</span>
    <span class="how-arrow">▾</span>
  </button>
  <div id="how-body" class="how-body">
    <div>
      <div class="how-title">🎯 What is The Safe K Report?</div>
      <p>Every starting pitcher gets graded on a 12-point system — projected strikeouts, how deep they go, walk rate, opposing lineup strikeout tendencies, swing-and-miss rates, and more. The more green boxes a pitcher has, the higher their tier: Diamond down to Borderline.</p>
    </div>
    <div>
      <div class="how-title">🔒 Why "Safe"?</div>
      <p>The O line we recommend is always the <strong>floor</strong> — the most conservative bet for that pitcher. A pitcher projecting 6 Ks gets <strong>O 3.5</strong>, not O 5.5. Even if they underperform a little, you still win. We never chase lines.</p>
    </div>
    <div>
      <div class="how-title">➕ How to use these plays</div>
      <p>These are designed as <strong>extra legs on a parlay</strong> — not standalone bets. You already have your main plays locked in. Tack on a Safe K leg to boost the payout without blowing up the slip. Low risk, real value.</p>
    </div>
    <div>
      <div class="how-title">📈 Can I go higher than the recommended line?</div>
      <p>Always your call. The tier tells you how much cushion you have:</p>
      <div class="how-grid">
        <div class="how-row"><span class="how-tier" style="color:#3b82f6">💎 Diamond</span><span class="how-desc">All criteria green. Comfortable going up one line for more value.</span></div>
        <div class="how-row"><span class="how-tier" style="color:#22c55e">🏆 Elite</span><span class="how-desc">Very strong. Stick to recommended or go up one with caution.</span></div>
        <div class="how-row"><span class="how-tier" style="color:#eab308">💪 Strong</span><span class="how-desc">Solid play. Stick to the recommended line.</span></div>
        <div class="how-row"><span class="how-tier" style="color:#6b7280">⚪ Borderline</span><span class="how-desc">Recommended floor only. Do not go higher.</span></div>
      </div>
    </div>
    <div>
      <div class="how-title">⚡ The simple rule</div>
      <div class="rule-grid">
        <div class="rule-item"><span class="rule-badge" style="background:rgba(34,197,94,0.15);border-color:rgba(34,197,94,0.4);color:#22c55e">O line shown</span><span class="rule-desc">Safe floor — bet with full confidence</span></div>
        <div class="rule-item"><span class="rule-badge" style="background:rgba(59,130,246,0.15);border-color:rgba(59,130,246,0.4);color:#3b82f6">💎 or 🏆 tier</span><span class="rule-desc">Can consider going up one line for better odds</span></div>
        <div class="rule-item"><span class="rule-badge" style="background:rgba(239,68,68,0.12);border-color:rgba(239,68,68,0.4);color:#ef4444">Never skip more than +1</span><span class="rule-desc">Don't jump two lines — the floor exists for a reason</span></div>
      </div>
    </div>
  </div>
</div>

<!-- SECTION NAV -->
<div class="snav">
  <a href="#scorecard" class="on">📊 Full Scorecard</a>
  <a href="#qualifiers">🎯 Top Qualifiers</a>
  <a href="#parlays">🔗 Daily Parlays</a>
</div>

<!-- MODEL NOTE -->
<div class="sec">
  <div class="mnote">
    <strong>12-Point Model · {"Phase 2 Active ✅" if PHASE2_ACTIVE else "Phase 1 Active"}</strong> — 
    Tier → O Line: 💎 Diamond = O 3.5 · 🏆 Elite = O 2.5 · 💪 Strong (top) = O 2.5 · 
    💪 Strong (bottom) = O 1.5 · ⚪ Borderline = O 1.5 · ❌ Fade = No play. {PHASE_NOTE}
  </div>
</div>

<!-- FULL SCORECARD -->
<div class="sec" id="scorecard">
  <div class="sec-hd">📊 Full Scorecard <span>{len(pitchers)} starters · sorted by score</span></div>
  {cards_html}
</div>

<!-- TOP QUALIFIERS -->
<div class="sec" id="qualifiers">
  <div class="sec-hd">🎯 Top Qualifiers <span>Diamond + Elite only</span></div>
  {qual_html}
</div>

<!-- PARLAYS -->
<div class="sec" id="parlays">
  <div class="sec-hd">🔗 Daily Parlay Builder <span>Your final call</span></div>
  <div class="parlay-group">
    <div class="group-label">📌 Standard</div>
    <div class="parlay-list">{p_safe}{p_mod}{p_risk}</div>
  </div>
  <div class="parlay-group">
    <div class="group-label">🔀 Mix — Fully Random · No Repeats</div>
    <div class="parlay-list">{''.join(mix_cards)}</div>
  </div>
</div>

<!-- DISCLAIMER -->
<div class="disclaimer">
  <p><strong>⚠️ Always verify the starting pitcher before placing any bet.</strong>
  A scratch or bullpen day makes these grades invalid instantly.
  Check your book and confirm the arm is actually taking the mound before you lock anything in.</p>
  <p style="margin-top:8px;">The O lines shown are <strong>floor lines</strong> — the safest,
  most conservative option for each pitcher. Moving up to a higher line is always
  <strong>optional</strong> and based on your own read of the matchup.
  Higher tier = more cushion. Lower tier = stay at the floor.</p>
  <span class="dyod">📚 D.Y.O.R. — Do Your Own Research. This is a tool, not a guarantee.</span>
</div>

<script>
(function(){{
  const track=document.getElementById('scroll-track');
  const thumb=document.getElementById('scroll-thumb');
  let dragging=false,startY=0,startScroll=0;
  function updateThumb(){{
    const docH=document.documentElement.scrollHeight-window.innerHeight;
    const trackH=track.clientHeight-thumb.clientHeight;
    thumb.style.top=(docH>0?(window.scrollY/docH)*trackH:0)+'px';
  }}
  window.addEventListener('scroll',updateThumb,{{passive:true}});
  updateThumb();
  function startDrag(y){{dragging=true;startY=y;startScroll=window.scrollY;thumb.classList.add('dragging');}}
  function moveDrag(y){{
    if(!dragging)return;
    const delta=y-startY;
    const trackH=track.clientHeight-thumb.clientHeight;
    const docH=document.documentElement.scrollHeight-window.innerHeight;
    window.scrollTo(0,startScroll+(delta/trackH)*docH);
  }}
  function endDrag(){{dragging=false;thumb.classList.remove('dragging');}}
  thumb.addEventListener('touchstart',e=>{{startDrag(e.touches[0].clientY);e.preventDefault();}},{{passive:false}});
  document.addEventListener('touchmove',e=>{{if(dragging){{moveDrag(e.touches[0].clientY);e.preventDefault();}}}},{{passive:false}});
  document.addEventListener('touchend',endDrag);
  thumb.addEventListener('mousedown',e=>startDrag(e.clientY));
  document.addEventListener('mousemove',e=>moveDrag(e.clientY));
  document.addEventListener('mouseup',endDrag);
}})();

// ---- Theme toggle (shares slateTheme with main slate) ----
(function(){{
  var cur='dark';
  try{{var s=localStorage.getItem('slateTheme');
    if(s==='light'||s==='dark'){{cur=s;document.documentElement.setAttribute('data-theme',cur);}}
  }}catch(e){{}}
  function wire(){{
    var tt=document.getElementById('themeToggle');
    if(!tt)return;
    tt.textContent=cur==='dark'?'🌙':'☀️';
    tt.addEventListener('click',function(){{
      cur=cur==='dark'?'light':'dark';
      document.documentElement.setAttribute('data-theme',cur);
      tt.textContent=cur==='dark'?'🌙':'☀️';
      try{{localStorage.setItem('slateTheme',cur);}}catch(e){{}}
    }});
  }}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);
  else wire();
}})();
</script>
<button class="theme-toggle-fab" id="themeToggle" aria-label="Toggle theme">🌙</button>
<a class="kpage-fab kfab-home" href="index.html" title="Daily Slate">⚾️</a>
<a class="kpage-fab kfab-streaks" href="streaks.html" title="Hot Streaks">🔥</a>
</body>
</html>'''

# ── Write output ─────────────────────────────────────────────────────────────
with open(K_REPORT_FILE, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'The Safe K Report built → {K_REPORT_FILE} ({len(html):,} bytes)')
print(f'  Date:     {DATE_STR}')
print(f'  Slate:    {SLATE_DAY}')
print(f'  Phase 2:  {"Active ✅" if PHASE2_ACTIVE else "Pending — Savant file not found"}')
print(f'  💎 Diamond ({len(diamonds)}): {[p["name"] for p in diamonds]}')
print(f'  🏆 Elite   ({len(elites)}): {[p["name"] for p in elites]}')
print(f'  💪 Strong  ({len(strongs)}): {len(strongs)} arms')
print(f'  ⚪ Borderline ({len(borderlines)}): {len(borderlines)} arms')


# ════════════════════════════════════════════════════════════════════════════
# Daily Slate v4.1 theme — applied automatically after every build.
# Restyles the generated page (app bar, ticker rail, bottom dock, scroll grip,
# Bebas/DM design system) without touching any of the model logic above.
# ════════════════════════════════════════════════════════════════════════════
# ==== Daily Slate v4.1 theme transform (canonical, auto-generated) ====
import re as _v41_re

_V41_FONTS = "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">\n<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>\n<link href=\"https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Mono:wght@400;500&family=DM+Sans:opsz,wght@9..40,400;9..40,600;9..40,700;9..40,800&display=swap\" rel=\"stylesheet\">"
_V41_KREPORT_CSS = "\n:root{\n  --bg:#07090f;--bg-grad-1:#0a1410;--bg-grad-2:#0a0f1a;--bg-grad-3:#14100a;\n  --surface:#0d1118;--surface-2:#11161f;\n  --glass:rgba(132,150,170,0.07);--glass-strong:rgba(132,150,170,0.13);--glass-elev:rgba(132,150,170,0.05);\n  --glass-border:rgba(140,160,185,0.14);--glass-border-strong:rgba(140,160,185,0.22);--border:rgba(140,160,185,0.16);\n  --text:#eaf0f4;--text-soft:#c0cbd3;--text-dim:#8696a3;\n  --accent:#2de38f;--accent-soft:rgba(45,227,143,0.13);--gold:#f5b83d;\n  --tier0:#2de38f;--tier0-bg:rgba(45,227,143,0.13);--tier0-border:rgba(45,227,143,0.45);\n  --tier1:#f5b83d;--tier1-bg:rgba(245,184,61,0.12);--tier1-border:rgba(245,184,61,0.42);\n  --good:#2de38f;--bad:#ff6262;--bad-bg:rgba(255,98,98,0.12);--bad-border:rgba(255,98,98,0.45);\n  --warn:#ffa63d;--warn-bg:rgba(255,166,61,0.12);--hot:#ff8a4a;--cold:#56a8ff;--info:#56a8ff;--p2:#56a8ff;\n  --shadow-sm:0 1px 2px rgba(0,0,0,0.35);\n  --shadow:0 10px 28px -10px rgba(0,0,0,0.6),0 2px 8px rgba(0,0,0,0.3);\n  --header-bg:rgba(7,9,15,0.78);\n  --radius:16px;--radius-sm:11px;--appbar-h:52px;\n  --font-display:\"Bebas Neue\",\"Arial Narrow\",sans-serif;\n  --font-body:\"DM Sans\",-apple-system,\"Segoe UI\",sans-serif;\n  --font-mono:\"DM Mono\",ui-monospace,SFMono-Regular,Menlo,monospace;\n}\n[data-theme=\"light\"]{\n  --bg:#f2f4f1;--bg-grad-1:#e9f3ec;--bg-grad-2:#edf1f6;--bg-grad-3:#f6f1e7;\n  --surface:#ffffff;--surface-2:#f7f9f8;\n  --glass:rgba(255,255,255,0.72);--glass-strong:rgba(255,255,255,0.9);--glass-elev:rgba(255,255,255,0.62);\n  --glass-border:rgba(18,26,34,0.1);--glass-border-strong:rgba(18,26,34,0.17);--border:rgba(18,26,34,0.13);\n  --text:#10181e;--text-soft:#2e3c44;--text-dim:#5d6e79;\n  --accent:#0c9d5f;--accent-soft:rgba(12,157,95,0.11);--gold:#b07b10;\n  --tier0:#0c9d5f;--tier0-bg:rgba(12,157,95,0.11);--tier0-border:rgba(12,157,95,0.42);\n  --tier1:#b07b10;--tier1-bg:rgba(176,123,16,0.11);--tier1-border:rgba(176,123,16,0.4);\n  --good:#0c9d5f;--bad:#d63a3a;--bad-bg:rgba(214,58,58,0.09);--bad-border:rgba(214,58,58,0.42);\n  --warn:#c4720a;--warn-bg:rgba(196,114,10,0.1);--hot:#d96a23;--cold:#2277d4;--info:#2277d4;--p2:#2277d4;\n  --header-bg:rgba(245,247,244,0.82);\n}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}\nhtml{scroll-behavior:smooth}\nhtml,body{margin:0;padding:0}\nbody{font-family:var(--font-body);background:var(--bg);\n  background-image:radial-gradient(1100px 520px at 85% -120px,var(--bg-grad-1) 0%,transparent 62%),\n    radial-gradient(900px 500px at -180px 18%,var(--bg-grad-2) 0%,transparent 58%),\n    radial-gradient(1000px 700px at 50% 115%,var(--bg-grad-3) 0%,transparent 55%);\n  background-attachment:fixed;color:var(--text);font-size:14px;line-height:1.55;\n  padding-bottom:calc(62px + env(safe-area-inset-bottom,0px) + 18px);}\na{color:var(--info)}\n:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}\nbutton{font-family:inherit}\n.app-bar{position:sticky;top:0;z-index:60;height:auto;min-height:calc(var(--appbar-h) + env(safe-area-inset-top,0px));display:flex;align-items:center;gap:10px;\n  padding:0 14px;padding-top:env(safe-area-inset-top,0px);background:var(--header-bg);\n  -webkit-backdrop-filter:blur(18px) saturate(1.4);backdrop-filter:blur(18px) saturate(1.4);\n  border-bottom:1px solid var(--glass-border)}\n.back-chip{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:11px;\n  background:var(--glass);border:1px solid var(--glass-border);color:var(--text);text-decoration:none;font-size:16px}\n.brand{display:flex;align-items:baseline;gap:7px;color:var(--text);text-decoration:none}\n.brand .wordmark{font-family:var(--font-display);font-size:21px;letter-spacing:1.4px;line-height:1}\n.brand .wordmark em{font-style:normal;color:var(--accent)}\n.bar-spacer{flex:1}\n.icon-btn{width:38px;height:38px;border-radius:12px;display:inline-flex;align-items:center;justify-content:center;\n  background:var(--glass);border:1px solid var(--glass-border);color:var(--text);font-size:16px;cursor:pointer}\n.icon-btn:active{transform:scale(.94)}\n.rail-wrap{position:sticky;top:calc(var(--appbar-h) + env(safe-area-inset-top,0px));z-index:55;background:var(--header-bg);\n  -webkit-backdrop-filter:blur(18px) saturate(1.4);backdrop-filter:blur(18px) saturate(1.4);\n  border-bottom:1px solid var(--glass-border)}\n.rail{display:flex;gap:7px;align-items:center;height:46px;overflow-x:auto;overflow-y:hidden;padding:0 12px;\n  scrollbar-width:none;-webkit-overflow-scrolling:touch;scroll-behavior:smooth}\n.rail::-webkit-scrollbar{display:none}\n.rail .chip-nav{flex:0 0 auto;display:inline-flex;align-items:center;gap:5px;height:30px;padding:0 11px;border-radius:9px;\n  border:1px solid var(--glass-border);background:var(--glass-elev);color:var(--text-dim);\n  font-family:var(--font-display);font-size:14.5px;letter-spacing:1.1px;text-decoration:none;white-space:nowrap;cursor:pointer}\n.rail .chip-nav .e{font-family:var(--font-body);font-size:12px}\n.rail .chip-nav.active{color:var(--accent);border-color:var(--tier0-border);background:var(--accent-soft);\n  box-shadow:0 0 14px rgba(45,227,143,.25),inset 0 0 8px rgba(45,227,143,.08);text-shadow:0 0 12px rgba(45,227,143,.6)}\n[data-theme=\"light\"] .rail .chip-nav.active{text-shadow:none;box-shadow:inset 0 0 0 1px var(--tier0-border)}\n.rail-div{flex:0 0 auto;width:1px;height:20px;background:var(--glass-border-strong)}\n.page-wrap{max-width:760px;margin:0 auto;padding:0 14px}\n.hero{padding:22px 2px 6px}\n.hero-kicker{font-size:11px;font-weight:700;letter-spacing:2.2px;text-transform:uppercase;color:var(--text-dim)}\n.hero-chips{display:flex;flex-wrap:wrap;gap:7px;margin:10px 0 2px}\n.hero-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:999px;\n  border:1px solid var(--glass-border);background:var(--glass);font-family:var(--font-mono);\n  font-size:11.5px;letter-spacing:.4px;color:var(--text-soft)}\n.hero-chip .led{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}\n.site-foot,.footer{max-width:760px;margin:22px auto 8px;padding:0 16px;text-align:center;font-size:11px;\n  color:var(--text-dim);font-family:var(--font-mono)}\nsection,.sec{scroll-margin-top:calc(var(--appbar-h) + 56px)}\n\n/* ---- bottom dock ---- */\n.dock{position:fixed;left:0;right:0;bottom:0;z-index:70;display:flex;justify-content:space-around;align-items:stretch;\n  height:calc(62px + env(safe-area-inset-bottom,0px));padding:6px 8px calc(env(safe-area-inset-bottom,0px) + 6px);\n  background:var(--header-bg);-webkit-backdrop-filter:blur(20px) saturate(1.5);backdrop-filter:blur(20px) saturate(1.5);\n  border-top:1px solid var(--glass-border)}\n.dock-btn{position:relative;flex:1;max-width:120px;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;\n  background:none;border:none;border-radius:12px;color:var(--text-dim);cursor:pointer;text-decoration:none}\n.dock-btn .di{font-size:19px;line-height:1}\n.dock-btn .dl{font-family:var(--font-display);font-size:11.5px;letter-spacing:0.8px}\n.dock-btn:active{color:var(--accent)}\n/* ---- super scroll grip ---- */\n#scroll-track{position:fixed;right:6px;top:50%;transform:translateY(-50%);height:56vh;width:6px;background:var(--glass-border-strong);border-radius:999px;z-index:64;}\n#scroll-thumb{position:absolute;left:50%;transform:translateX(-50%);width:26px;height:50px;background:rgba(45,227,143,0.35);border:1px solid rgba(45,227,143,0.65);border-radius:999px;cursor:grab;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;touch-action:none;transition:background .15s;}\n#scroll-thumb.dragging{background:rgba(45,227,143,0.8);cursor:grabbing;}\n#scroll-thumb .grip-line{width:10px;height:2px;background:var(--accent);border-radius:999px;}\n#scroll-thumb.dragging .grip-line{background:#04130b;}\n[data-theme=\"light\"] #scroll-thumb{background:rgba(12,157,95,0.3);border-color:rgba(12,157,95,0.6);}\n[data-theme=\"light\"] #scroll-thumb.dragging{background:rgba(12,157,95,0.85);}\n[data-theme=\"light\"] #scroll-thumb.dragging .grip-line{background:#fff;}\n/* ---- fire gradient (streaks) ---- */\n.fire{background:linear-gradient(90deg,#f97316,#ef4444,#f97316);background-size:200%;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:#f97316;}\n@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition-duration:.01ms!important;animation:none!important}}\n\n/* ---- K Report hero ---- */\n.hero-title{font-family:var(--font-display);font-size:clamp(36px,10.5vw,52px);line-height:.98;letter-spacing:1px;margin:4px 0 6px}\n.hero-title span{color:var(--accent)}\n.hero-sub{font-size:12px;color:var(--text-dim);font-family:var(--font-mono);letter-spacing:.3px}\n.hero-pills{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}\n.pill{display:inline-flex;align-items:center;padding:5px 11px;border-radius:999px;font-size:11px;font-weight:800;\n  border:1px solid var(--glass-border);background:var(--glass);color:var(--text-soft)}\n.pill-blue{background:rgba(86,168,255,.12);border-color:rgba(86,168,255,.4);color:var(--cold)}\n.pill-green{background:var(--tier0-bg);border-color:var(--tier0-border);color:var(--accent)}\n.pill-yellow{background:var(--tier1-bg);border-color:var(--tier1-border);color:var(--gold)}\n.pill-grey{color:var(--text-dim)}\n.pill-dim{font-family:var(--font-mono);font-weight:500;color:var(--text-dim)}\n/* ---- How it works ---- */\n.how-wrap{margin:14px 0;background:var(--glass-elev);border:1px solid var(--glass-border);border-radius:var(--radius);overflow:clip}\n.how-toggle{display:flex;align-items:center;justify-content:space-between;width:100%;padding:14px 16px;background:none;border:none;\n  color:var(--text);cursor:pointer;font-family:var(--font-display);font-size:18px;letter-spacing:1px;text-align:left}\n.how-arrow{width:28px;height:28px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;\n  background:var(--glass);border:1px solid var(--glass-border);color:var(--text-dim);font-size:13px;transition:transform .3s}\n.how-toggle.open .how-arrow{transform:rotate(180deg);color:var(--accent);border-color:var(--tier0-border)}\n.how-body{display:none;padding:2px 16px 16px;font-size:13px;color:var(--text-soft);line-height:1.6}\n.how-body.visible{display:grid;gap:14px}\n.how-body p{margin:4px 0 0}\n.how-title{font-weight:800;color:var(--text);font-size:13px;margin-bottom:2px}\n.how-grid,.rule-grid{display:grid;gap:7px;margin-top:8px}\n.how-row,.rule-item{display:flex;gap:10px;align-items:baseline;padding:9px 11px;border-radius:10px;\n  background:var(--glass);border:1px solid var(--glass-border)}\n.how-tier{font-weight:900;font-size:12px;flex:0 0 92px}\n.how-desc,.rule-desc{font-size:12px;color:var(--text-dim)}\n.rule-badge{flex:0 0 auto;padding:3px 9px;border-radius:7px;font-size:10.5px;font-weight:900;border:1px solid}\n/* ---- model note + sections ---- */\n.mnote{margin:4px 0 0;padding:11px 13px;border-radius:var(--radius-sm);font-size:12px;line-height:1.6;color:var(--text-soft);\n  background:rgba(86,168,255,.07);border:1px solid rgba(86,168,255,.22)}\n.mnote strong{color:var(--cold)}\n.sec{margin:20px 0}\n.sec-hd{font-family:var(--font-display);font-size:24px;letter-spacing:1.1px;display:flex;align-items:baseline;gap:9px;margin:0 0 10px}\n.sec-hd span{font-family:var(--font-body);font-size:11px;color:var(--text-dim);font-weight:700;letter-spacing:.3px}\n/* ---- pitcher scorecards ---- */\n.pcard{position:relative;background:var(--glass-elev);border:1px solid var(--glass-border);border-radius:var(--radius);\n  margin:10px 0;padding:13px 13px 12px;box-shadow:var(--shadow-sm);overflow:clip}\n.pcard::before{content:\"\";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--tc,var(--glass-border-strong))}\n.tier-diamond{--tc:var(--cold)} .tier-elite{--tc:var(--accent)} .tier-strong{--tc:var(--gold)}\n.tier-borderline{--tc:var(--text-dim)} .tier-fade{--tc:var(--bad)}\n.pc-head{display:flex;justify-content:space-between;gap:10px}\n.pc-left{display:flex;gap:10px;min-width:0}\n.pc-rank{font-family:var(--font-mono);color:var(--text-dim);font-size:12px;padding-top:4px}\n.pc-name{font-family:var(--font-display);font-size:22px;letter-spacing:.8px;line-height:1.02}\n.pc-match{font-size:11px;color:var(--text-dim);margin-top:3px}\n.pc-right{text-align:right;flex:0 0 auto}\ndiv.pc-tier{display:inline-flex;padding:3.5px 9px;border-radius:7px;font-size:9.5px;font-weight:900;letter-spacing:.9px;border:1px solid}\ndiv.pc-tier.tier-diamond{background:rgba(86,168,255,.13);border-color:rgba(86,168,255,.4);color:var(--cold)}\ndiv.pc-tier.tier-elite{background:var(--tier0-bg);border-color:var(--tier0-border);color:var(--accent)}\ndiv.pc-tier.tier-strong{background:var(--tier1-bg);border-color:var(--tier1-border);color:var(--gold)}\ndiv.pc-tier.tier-borderline{background:var(--glass);border-color:var(--glass-border-strong);color:var(--text-dim)}\ndiv.pc-tier.tier-fade{background:var(--bad-bg);border-color:var(--bad-border);color:var(--bad)}\n.pc-score{font-family:var(--font-mono);font-size:19px;font-weight:500;margin-top:5px}\n.pc-of{font-size:11px;color:var(--text-dim)}\n.proj-row{display:flex;justify-content:center;margin:11px 0 2px}\n.proj-center{display:flex;align-items:center;gap:10px;padding:8px 15px;border-radius:13px;\n  background:var(--surface);border:1px solid var(--glass-border)}\n.proj-icon{font-size:13px}\n.proj-k{font-family:var(--font-display);font-size:31px;letter-spacing:.5px;line-height:1}\n.proj-label{font-size:9px;letter-spacing:1.3px;text-transform:uppercase;color:var(--text-dim);max-width:46px;line-height:1.25}\n.proj-center.crit-green .proj-k{color:var(--accent)}\n.proj-center.crit-yellow .proj-k{color:var(--gold)}\n.proj-center.crit-red .proj-k{color:var(--bad)}\n.ou-badge{font-family:var(--font-display);font-size:16.5px;letter-spacing:1px;padding:5px 13px;border-radius:9px;margin-left:4px}\n.ou-top{background:var(--cold);color:#04101f}\n.ou-mid{background:var(--accent);color:#04130b}\n.ou-low{background:var(--gold);color:#221a04}\n.ou-none{background:transparent;border:1.5px dashed var(--glass-border-strong);color:var(--text-dim)}\n[data-theme=\"light\"] .ou-top,[data-theme=\"light\"] .ou-mid,[data-theme=\"light\"] .ou-low{color:#fff}\n.line-compare{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:10px 0 0}\n.lc-item{background:var(--surface);border:1px solid var(--glass-border);border-radius:10px;padding:7px 9px;text-align:center}\n.lc-label{display:block;font-size:8.5px;letter-spacing:1.1px;text-transform:uppercase;color:var(--text-dim);margin-bottom:1px}\n.lc-val{font-family:var(--font-mono);font-size:13.5px;font-weight:500}\n.lc-floor{color:var(--accent)} .lc-book{color:var(--text-soft)} .cush-hi{color:var(--cold)}\n.crit-section{margin-top:9px}\n.crit-row.r6{display:grid;grid-template-columns:repeat(6,1fr);gap:5px}\n.crit{display:flex;flex-direction:column;align-items:center;gap:1px;padding:5px 2px;border-radius:8px;\n  border:1px solid var(--glass-border);background:var(--glass);min-width:0}\n.crit .ci{font-size:9px;line-height:1}\n.crit .cl{font-size:7.6px;letter-spacing:.2px;color:var(--text-dim);text-transform:uppercase;white-space:nowrap;max-width:100%;overflow:hidden}\n.crit .cv{font-family:var(--font-mono);font-size:10.5px;font-weight:500;white-space:nowrap}\n.crit-green{background:var(--tier0-bg);border-color:var(--tier0-border)} .crit-green .cv{color:var(--accent)}\n.crit-yellow{background:var(--tier1-bg);border-color:var(--tier1-border)} .crit-yellow .cv{color:var(--gold)}\n.crit-red{background:var(--bad-bg);border-color:var(--bad-border)} .crit-red .cv{color:var(--bad)}\n.crit-p2{background:rgba(86,168,255,.08);border-color:rgba(86,168,255,.3)} .crit-p2 .cv{color:var(--cold)}\n.flags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}\n.flag{font-size:10.5px;font-weight:700;padding:4px 9px;border-radius:7px;border:1px solid}\n.flag-red{background:var(--bad-bg);border-color:var(--bad-border);color:var(--bad)}\n.flag-yellow{background:var(--warn-bg);border-color:rgba(255,166,61,.4);color:var(--warn)}\n/* ---- qualifiers ---- */\n.qrow{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:8px 0;padding:11px 13px;\n  background:var(--glass-elev);border:1px solid var(--glass-border);border-radius:var(--radius-sm);border-left-width:3px}\n.tier-diamond-border{border-left-color:var(--cold)}\n.tier-elite-border{border-left-color:var(--accent)}\n.ql{display:flex;gap:10px;align-items:center;min-width:0}\n.qt{font-size:18px}\n.qname{font-family:var(--font-display);font-size:18px;letter-spacing:.7px}\n.qteam{font-family:var(--font-body);font-size:10.5px;color:var(--text-dim);letter-spacing:.2px;margin-left:5px}\n.qstats{font-family:var(--font-mono);font-size:10.5px;color:var(--text-dim);margin-top:2px}\n.qr{display:flex;align-items:center;gap:8px;flex:0 0 auto}\n.qr .ou-badge{font-size:14px;padding:4px 10px;margin:0}\n.qscore{font-family:var(--font-mono);font-size:12px;color:var(--text-soft)}\n/* ---- parlays ---- */\n.parlay-group{margin:0 0 16px}\n.group-label{font-size:10.5px;font-weight:800;letter-spacing:1.6px;text-transform:uppercase;color:var(--text-dim);margin:0 0 8px 2px}\n.parlay-list{display:grid;gap:9px}\n@media(min-width:680px){.parlay-list{grid-template-columns:1fr 1fr}}\n.pcard-parlay{background:var(--glass-elev);border:1px solid var(--glass-border);border-radius:var(--radius-sm);\n  padding:12px 13px;box-shadow:var(--shadow-sm)}\n.ph{display:flex;justify-content:space-between;align-items:center;margin-bottom:2px}\n.ph .pl{font-family:var(--font-display);font-size:17px;letter-spacing:.8px}\n.p-legs{font-family:var(--font-mono);font-size:10.5px;color:var(--text-dim);border:1px solid var(--glass-border);\n  border-radius:999px;padding:2px 9px}\n.pd{font-size:11px;color:var(--text-dim);margin-bottom:8px}\n.pleg{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 10px;margin-top:6px;\n  background:var(--surface);border:1px solid var(--glass-border);border-radius:9px}\n.pl-info{display:flex;gap:8px;align-items:center;min-width:0}\n.pl-tier{font-size:13px}\n.pl-name{font-weight:700;font-size:12.5px}\n.pl-match{font-size:10.5px;color:var(--text-dim)}\n.pl-ou{font-family:var(--font-mono);font-weight:500;font-size:12.5px;flex:0 0 auto}\n.mix-tag{font-size:8.5px;font-weight:900;letter-spacing:.8px;color:var(--cold);border:1px solid rgba(86,168,255,.4);\n  border-radius:5px;padding:1px 5px;margin-left:7px;vertical-align:3px;font-family:var(--font-body)}\n/* ---- disclaimer ---- */\n.disclaimer{margin:22px 0 6px;padding:14px 15px;border-radius:var(--radius);font-size:12px;line-height:1.65;color:var(--text-soft);\n  background:var(--warn-bg);border:1px solid rgba(255,166,61,.35)}\n.disclaimer strong{color:var(--warn)}\n.dyod{display:inline-block;margin-top:10px;font-family:var(--font-mono);font-size:10.5px;color:var(--text-dim)}\n"
_V41_STREAKS_CSS = "\n:root{\n  --bg:#07090f;--bg-grad-1:#0a1410;--bg-grad-2:#0a0f1a;--bg-grad-3:#14100a;\n  --surface:#0d1118;--surface-2:#11161f;\n  --glass:rgba(132,150,170,0.07);--glass-strong:rgba(132,150,170,0.13);--glass-elev:rgba(132,150,170,0.05);\n  --glass-border:rgba(140,160,185,0.14);--glass-border-strong:rgba(140,160,185,0.22);--border:rgba(140,160,185,0.16);\n  --text:#eaf0f4;--text-soft:#c0cbd3;--text-dim:#8696a3;\n  --accent:#2de38f;--accent-soft:rgba(45,227,143,0.13);--gold:#f5b83d;\n  --tier0:#2de38f;--tier0-bg:rgba(45,227,143,0.13);--tier0-border:rgba(45,227,143,0.45);\n  --tier1:#f5b83d;--tier1-bg:rgba(245,184,61,0.12);--tier1-border:rgba(245,184,61,0.42);\n  --good:#2de38f;--bad:#ff6262;--bad-bg:rgba(255,98,98,0.12);--bad-border:rgba(255,98,98,0.45);\n  --warn:#ffa63d;--warn-bg:rgba(255,166,61,0.12);--hot:#ff8a4a;--cold:#56a8ff;--info:#56a8ff;--p2:#56a8ff;\n  --shadow-sm:0 1px 2px rgba(0,0,0,0.35);\n  --shadow:0 10px 28px -10px rgba(0,0,0,0.6),0 2px 8px rgba(0,0,0,0.3);\n  --header-bg:rgba(7,9,15,0.78);\n  --radius:16px;--radius-sm:11px;--appbar-h:52px;\n  --font-display:\"Bebas Neue\",\"Arial Narrow\",sans-serif;\n  --font-body:\"DM Sans\",-apple-system,\"Segoe UI\",sans-serif;\n  --font-mono:\"DM Mono\",ui-monospace,SFMono-Regular,Menlo,monospace;\n}\n[data-theme=\"light\"]{\n  --bg:#f2f4f1;--bg-grad-1:#e9f3ec;--bg-grad-2:#edf1f6;--bg-grad-3:#f6f1e7;\n  --surface:#ffffff;--surface-2:#f7f9f8;\n  --glass:rgba(255,255,255,0.72);--glass-strong:rgba(255,255,255,0.9);--glass-elev:rgba(255,255,255,0.62);\n  --glass-border:rgba(18,26,34,0.1);--glass-border-strong:rgba(18,26,34,0.17);--border:rgba(18,26,34,0.13);\n  --text:#10181e;--text-soft:#2e3c44;--text-dim:#5d6e79;\n  --accent:#0c9d5f;--accent-soft:rgba(12,157,95,0.11);--gold:#b07b10;\n  --tier0:#0c9d5f;--tier0-bg:rgba(12,157,95,0.11);--tier0-border:rgba(12,157,95,0.42);\n  --tier1:#b07b10;--tier1-bg:rgba(176,123,16,0.11);--tier1-border:rgba(176,123,16,0.4);\n  --good:#0c9d5f;--bad:#d63a3a;--bad-bg:rgba(214,58,58,0.09);--bad-border:rgba(214,58,58,0.42);\n  --warn:#c4720a;--warn-bg:rgba(196,114,10,0.1);--hot:#d96a23;--cold:#2277d4;--info:#2277d4;--p2:#2277d4;\n  --header-bg:rgba(245,247,244,0.82);\n}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}\nhtml{scroll-behavior:smooth}\nhtml,body{margin:0;padding:0}\nbody{font-family:var(--font-body);background:var(--bg);\n  background-image:radial-gradient(1100px 520px at 85% -120px,var(--bg-grad-1) 0%,transparent 62%),\n    radial-gradient(900px 500px at -180px 18%,var(--bg-grad-2) 0%,transparent 58%),\n    radial-gradient(1000px 700px at 50% 115%,var(--bg-grad-3) 0%,transparent 55%);\n  background-attachment:fixed;color:var(--text);font-size:14px;line-height:1.55;\n  padding-bottom:calc(62px + env(safe-area-inset-bottom,0px) + 18px);}\na{color:var(--info)}\n:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}\nbutton{font-family:inherit}\n.app-bar{position:sticky;top:0;z-index:60;height:auto;min-height:calc(var(--appbar-h) + env(safe-area-inset-top,0px));display:flex;align-items:center;gap:10px;\n  padding:0 14px;padding-top:env(safe-area-inset-top,0px);background:var(--header-bg);\n  -webkit-backdrop-filter:blur(18px) saturate(1.4);backdrop-filter:blur(18px) saturate(1.4);\n  border-bottom:1px solid var(--glass-border)}\n.back-chip{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:11px;\n  background:var(--glass);border:1px solid var(--glass-border);color:var(--text);text-decoration:none;font-size:16px}\n.brand{display:flex;align-items:baseline;gap:7px;color:var(--text);text-decoration:none}\n.brand .wordmark{font-family:var(--font-display);font-size:21px;letter-spacing:1.4px;line-height:1}\n.brand .wordmark em{font-style:normal;color:var(--accent)}\n.bar-spacer{flex:1}\n.icon-btn{width:38px;height:38px;border-radius:12px;display:inline-flex;align-items:center;justify-content:center;\n  background:var(--glass);border:1px solid var(--glass-border);color:var(--text);font-size:16px;cursor:pointer}\n.icon-btn:active{transform:scale(.94)}\n.rail-wrap{position:sticky;top:calc(var(--appbar-h) + env(safe-area-inset-top,0px));z-index:55;background:var(--header-bg);\n  -webkit-backdrop-filter:blur(18px) saturate(1.4);backdrop-filter:blur(18px) saturate(1.4);\n  border-bottom:1px solid var(--glass-border)}\n.rail{display:flex;gap:7px;align-items:center;height:46px;overflow-x:auto;overflow-y:hidden;padding:0 12px;\n  scrollbar-width:none;-webkit-overflow-scrolling:touch;scroll-behavior:smooth}\n.rail::-webkit-scrollbar{display:none}\n.rail .chip-nav{flex:0 0 auto;display:inline-flex;align-items:center;gap:5px;height:30px;padding:0 11px;border-radius:9px;\n  border:1px solid var(--glass-border);background:var(--glass-elev);color:var(--text-dim);\n  font-family:var(--font-display);font-size:14.5px;letter-spacing:1.1px;text-decoration:none;white-space:nowrap;cursor:pointer}\n.rail .chip-nav .e{font-family:var(--font-body);font-size:12px}\n.rail .chip-nav.active{color:var(--accent);border-color:var(--tier0-border);background:var(--accent-soft);\n  box-shadow:0 0 14px rgba(45,227,143,.25),inset 0 0 8px rgba(45,227,143,.08);text-shadow:0 0 12px rgba(45,227,143,.6)}\n[data-theme=\"light\"] .rail .chip-nav.active{text-shadow:none;box-shadow:inset 0 0 0 1px var(--tier0-border)}\n.rail-div{flex:0 0 auto;width:1px;height:20px;background:var(--glass-border-strong)}\n.page-wrap{max-width:760px;margin:0 auto;padding:0 14px}\n.hero{padding:22px 2px 6px}\n.hero-kicker{font-size:11px;font-weight:700;letter-spacing:2.2px;text-transform:uppercase;color:var(--text-dim)}\n.hero-chips{display:flex;flex-wrap:wrap;gap:7px;margin:10px 0 2px}\n.hero-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:999px;\n  border:1px solid var(--glass-border);background:var(--glass);font-family:var(--font-mono);\n  font-size:11.5px;letter-spacing:.4px;color:var(--text-soft)}\n.hero-chip .led{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}\n.site-foot,.footer{max-width:760px;margin:22px auto 8px;padding:0 16px;text-align:center;font-size:11px;\n  color:var(--text-dim);font-family:var(--font-mono)}\nsection,.sec{scroll-margin-top:calc(var(--appbar-h) + 56px)}\n\n/* ---- bottom dock ---- */\n.dock{position:fixed;left:0;right:0;bottom:0;z-index:70;display:flex;justify-content:space-around;align-items:stretch;\n  height:calc(62px + env(safe-area-inset-bottom,0px));padding:6px 8px calc(env(safe-area-inset-bottom,0px) + 6px);\n  background:var(--header-bg);-webkit-backdrop-filter:blur(20px) saturate(1.5);backdrop-filter:blur(20px) saturate(1.5);\n  border-top:1px solid var(--glass-border)}\n.dock-btn{position:relative;flex:1;max-width:120px;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;\n  background:none;border:none;border-radius:12px;color:var(--text-dim);cursor:pointer;text-decoration:none}\n.dock-btn .di{font-size:19px;line-height:1}\n.dock-btn .dl{font-family:var(--font-display);font-size:11.5px;letter-spacing:0.8px}\n.dock-btn:active{color:var(--accent)}\n/* ---- super scroll grip ---- */\n#scroll-track{position:fixed;right:6px;top:50%;transform:translateY(-50%);height:56vh;width:6px;background:var(--glass-border-strong);border-radius:999px;z-index:64;}\n#scroll-thumb{position:absolute;left:50%;transform:translateX(-50%);width:26px;height:50px;background:rgba(45,227,143,0.35);border:1px solid rgba(45,227,143,0.65);border-radius:999px;cursor:grab;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;touch-action:none;transition:background .15s;}\n#scroll-thumb.dragging{background:rgba(45,227,143,0.8);cursor:grabbing;}\n#scroll-thumb .grip-line{width:10px;height:2px;background:var(--accent);border-radius:999px;}\n#scroll-thumb.dragging .grip-line{background:#04130b;}\n[data-theme=\"light\"] #scroll-thumb{background:rgba(12,157,95,0.3);border-color:rgba(12,157,95,0.6);}\n[data-theme=\"light\"] #scroll-thumb.dragging{background:rgba(12,157,95,0.85);}\n[data-theme=\"light\"] #scroll-thumb.dragging .grip-line{background:#fff;}\n/* ---- fire gradient (streaks) ---- */\n.fire{background:linear-gradient(90deg,#f97316,#ef4444,#f97316);background-size:200%;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:#f97316;}\n@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition-duration:.01ms!important;animation:none!important}}\n\n/* ---- Streaks hero ---- */\n.header-title{font-family:var(--font-display);font-size:clamp(36px,10.5vw,52px);line-height:.98;letter-spacing:1px;margin:4px 0 4px}\n\n/* ---- guide ---- */\n.streak-guide{margin:14px 0;background:var(--glass-elev);border:1px solid var(--glass-border);border-radius:var(--radius);overflow:clip}\n.streak-guide-summary{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;cursor:pointer;\n  font-family:var(--font-display);font-size:18px;letter-spacing:1px;list-style:none}\n.streak-guide-summary::-webkit-details-marker{display:none}\n.collapse-tag{width:28px;height:28px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;\n  background:var(--glass);border:1px solid var(--glass-border);color:var(--text-dim);font-size:13px;transition:transform .3s}\n.collapse-tag::after{content:\"\u25be\"}\ndetails[open] .collapse-tag{transform:rotate(180deg);color:var(--accent);border-color:var(--tier0-border)}\n.streak-guide-body{padding:0 16px 16px;font-size:13px;color:var(--text-soft);line-height:1.6}\n.guide-table{width:100%;border-collapse:separate;border-spacing:0 6px;margin-top:6px}\n.guide-table td{padding:8px 11px;background:var(--glass);border-top:1px solid var(--glass-border);border-bottom:1px solid var(--glass-border);font-size:12px}\n.guide-table td:first-child{border-left:1px solid var(--glass-border);border-radius:9px 0 0 9px;white-space:nowrap;width:74px;font-weight:800}\n.guide-table td:last-child{border-right:1px solid var(--glass-border);border-radius:0 9px 9px 0;color:var(--text-dim)}\n/* ---- filter rail buttons (type colors come inline from the generator) ---- */\n.filter-btn{flex:0 0 auto;display:inline-flex;align-items:center;height:31px;padding:0 12px;border-radius:9px;\n  border:1.5px solid;font-family:var(--font-display);font-size:14.5px;letter-spacing:1px;cursor:pointer;white-space:nowrap}\n.filter-btn.active{box-shadow:0 0 13px color-mix(in srgb,currentColor 0%,transparent)}\n/* ---- streak cards ---- */\n#streak-list{padding-top:2px}\n.streak-row{background:var(--glass-elev);border:1px solid var(--glass-border);border-radius:var(--radius-sm);\n  padding:12px 13px;margin:10px 0;box-shadow:var(--shadow-sm)}\n.row-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px}\n.type-badge{display:inline-flex;padding:3px 9px;border-radius:7px;font-size:9.5px;font-weight:900;letter-spacing:.9px}\n.hrr-tag{font-size:9px;font-weight:800;color:var(--text-dim);border:1px solid var(--glass-border-strong);border-radius:5px;padding:1.5px 6px}\n.player-row{display:flex;justify-content:space-between;align-items:baseline;gap:10px}\n.player-name{font-family:var(--font-display);font-size:21px;letter-spacing:.8px;line-height:1.05}\n.team-badge{font-family:var(--font-mono);font-size:11px;color:var(--text-soft);background:var(--surface);\n  border:1px solid var(--glass-border);border-radius:7px;padding:2.5px 8px}\n.dots-row{display:flex;justify-content:space-between;align-items:center;margin:9px 0 2px}\n.dots{display:flex;gap:5px;align-items:center}\n.dot{width:10px;height:10px;border-radius:50%}\n.dot-label{font-size:9.5px;letter-spacing:.8px;text-transform:uppercase;color:var(--text-dim);margin-left:7px;font-family:var(--font-mono)}\n.streak-count{font-family:var(--font-display);font-size:16px;letter-spacing:.8px}\n.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}\n.chip{display:inline-flex;align-items:center;gap:3px;background:var(--surface);border:1px solid var(--glass-border);\n  border-radius:8px;padding:4px 9px;font-size:11px}\n.chip .dim{color:var(--text-dim);font-size:10px}\n.insight{margin:9px 0 0;padding:8px 0 0;border-top:1px dashed var(--glass-border-strong);\n  font-size:11.5px;color:var(--text-dim);line-height:1.55}\n"

_V41_GRIP_HTML = ('<div id="scroll-track" aria-hidden="true"><div id="scroll-thumb">'
  '<div class="grip-line"></div><div class="grip-line"></div><div class="grip-line"></div></div></div>')

def _v41_appbar(back, wordmark):
    return ('<header class="app-bar">'
      '<a class="back-chip" href="' + back + '" aria-label="Back to Daily Slate">\u2039</a>'
      '<a class="brand" href="' + back + '"><span class="wordmark">' + wordmark + '</span></a>'
      '<div class="bar-spacer"></div>'
      '<button class="icon-btn" id="themeToggle" aria-label="Toggle theme">\U0001F319</button>'
      '</header>')

def _v41_head(h):
    if '<meta name="viewport"' in h:
        h = _v41_re.sub(r'<meta name="viewport"[^>]*>',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">', h, count=1)
    if '<!--V41THEME-->' not in h:
        h = h.replace('<head>', '<head>\n<!--V41THEME-->', 1)
    h = h.replace('</title>', '</title>\n' + _V41_FONTS, 1)
    return h

_V41_KR_JS = """<script>
(function(){
  var cur='dark';
  try{var s=localStorage.getItem('slateTheme');if(s==='light'||s==='dark'){cur=s;}}catch(e){}
  document.documentElement.setAttribute('data-theme',cur);
  var tt=document.getElementById('themeToggle');
  tt.textContent=cur==='dark'?'\U0001F319':'\u2600\uFE0F';
  tt.addEventListener('click',function(){
    cur=cur==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',cur);
    tt.textContent=cur==='dark'?'\U0001F319':'\u2600\uFE0F';
    try{localStorage.setItem('slateTheme',cur);}catch(e){}
  });
  var chips=Array.prototype.slice.call(document.querySelectorAll('.chip-nav.spy'));
  var ids=chips.map(function(c){return c.getAttribute('href').slice(1);});
  var act=null,tick=false;
  function spy(){
    tick=false;var cur2=null;
    for(var i=0;i<ids.length;i++){var el=document.getElementById(ids[i]);
      if(el&&el.getBoundingClientRect().top<=120)cur2=i;}
    var c=cur2===null?null:chips[cur2];
    if(c===act)return;
    if(act)act.classList.remove('active');
    act=c;
    if(c){
      c.classList.add('active');
      var r2=document.querySelector('.rail');
      if(r2){var t2=c.offsetLeft-r2.clientWidth/2+c.offsetWidth/2;r2.scrollTo({left:Math.max(0,t2),behavior:'smooth'});}
    }
  }
  window.addEventListener('scroll',function(){if(!tick){tick=true;requestAnimationFrame(spy);}},{passive:true});
  spy();
})();
(function(){
function initGrip(){
  var track=document.getElementById('scroll-track');
  var thumb=document.getElementById('scroll-thumb');
  if(!track||!thumb)return;
  var dragging=false,startY=0,startScroll=0;
  function updateThumb(){
    var docH=document.documentElement.scrollHeight-window.innerHeight;
    var trackH=track.clientHeight-thumb.clientHeight;
    thumb.style.top=(docH>0?(window.scrollY/docH)*trackH:0)+'px';
  }
  window.addEventListener('scroll',updateThumb,{passive:true});
  window.addEventListener('resize',updateThumb,{passive:true});
  updateThumb();
  function startDrag(y){dragging=true;startY=y;startScroll=window.scrollY;thumb.classList.add('dragging');}
  function moveDrag(y){
    if(!dragging)return;
    var delta=y-startY;
    var trackH=track.clientHeight-thumb.clientHeight;
    var docH=document.documentElement.scrollHeight-window.innerHeight;
    window.scrollTo(0,Math.max(0,Math.min(docH,startScroll+(delta/trackH)*docH)));
  }
  function endDrag(){dragging=false;thumb.classList.remove('dragging');}
  thumb.addEventListener('touchstart',function(e){startDrag(e.touches[0].clientY);e.preventDefault();},{passive:false});
  document.addEventListener('touchmove',function(e){if(dragging){moveDrag(e.touches[0].clientY);e.preventDefault();}},{passive:false});
  document.addEventListener('touchend',endDrag);
  thumb.addEventListener('mousedown',function(e){startDrag(e.clientY);});
  document.addEventListener('mousemove',function(e){moveDrag(e.clientY);});
  document.addEventListener('mouseup',endDrag);
}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',initGrip);}else{initGrip();}
})();
</script>"""

def v41_kreport(h):
    h = _v41_head(h)
    h = _v41_re.sub(r'<style>[\s\S]*?</style>', lambda m: '<style>' + _V41_KREPORT_CSS + '</style>', h, count=1)
    h = _v41_re.sub(r'<!-- FAST SCROLL THUMB -->[\s\S]*?</div>\s*</div>\s*\n', '', h, count=1)
    navd = _v41_re.search(r'<div class="nav-d">([\s\S]*?)</div>', h)
    bits = _v41_re.sub(r'<br\s*/?>', '|', navd.group(1)).split('|') if navd else ['', '']
    rail = ('<nav class="rail-wrap"><div class="rail">'
      '<button class="chip-nav" onclick="window.scrollTo({top:0,behavior:\'smooth\'})"><span class="e">\u2912</span></button>'
      '<a class="chip-nav spy" href="#scorecard"><span class="e">\U0001F4CA</span>SCORECARD</a>'
      '<a class="chip-nav spy" href="#qualifiers"><span class="e">\U0001F3AF</span>QUALIFIERS</a>'
      '<a class="chip-nav spy" href="#parlays"><span class="e">\U0001F517</span>PARLAYS</a>'
      '</div></nav>')
    h = _v41_re.sub(r'<nav class="top-nav">[\s\S]*?</nav>',
        _v41_appbar('index.html', 'THE SAFE <em>K REPORT</em>') + '\n' + rail + '\n<div class="page-wrap">', h, count=1)
    h = h.replace('<div class="hero">',
        '<div class="hero"><div class="hero-kicker">Strikeout Floors \u00b7 Companion to The Daily Slate</div>', 1)
    chips = ('<div class="hero-chips">'
      '<span class="hero-chip"><span class="led"></span>' + bits[0].strip() + '</span>'
      '<span class="hero-chip">' + (bits[1].strip().upper() if len(bits) > 1 else '') + '</span></div>')
    h = _v41_re.sub(r'(<div class="hero-sub">[\s\S]*?</div>)', lambda m: m.group(1) + chips, h, count=1)
    h = _v41_re.sub(r'(<div class="hero-title">[\s\S]*?)(</div>)',
        lambda m: m.group(1) + (' \U0001F4F0' if '\U0001F4F0' not in m.group(1) else '') + m.group(2), h, count=1)
    h = _v41_re.sub(r'<!-- SECTION NAV -->\s*<div class="snav">[\s\S]*?</div>\s*\n', '', h, count=1)
    h = _v41_re.sub(r'<button class="theme-toggle-fab"[^>]*>[\s\S]*?</button>\s*', '', h)
    h = _v41_re.sub(r'<a class="kpage-fab[\s\S]*?</a>\s*', '', h)
    h = _v41_re.sub(r'<script>[\s\S]*?</script>', lambda m: _V41_KR_JS, h, count=1)
    tail = ('</div>\n<div class="site-foot">The Safe K Report \u00b7 part of The Daily Slate \u26be</div>\n'
      + _V41_GRIP_HTML + '\n'
      '<nav class="dock">'
      '<a class="dock-btn" href="index.html"><span class="di">\u26be</span><span class="dl">SLATE</span></a>'
      '<a class="dock-btn" href="streaks.html"><span class="di">\U0001F525</span><span class="dl">STREAKS</span></a>'
      '<a class="dock-btn" href="scout.html"><span class="di">\u26a1</span><span class="dl">SSJ</span></a>'
      '</nav>\n</body>')
    h = h.replace('</body>', tail, 1)
    return h

def v41_streaks(h):
    h = _v41_head(h)
    h = _v41_re.sub(r'<style>[\s\S]*?</style>', lambda m: '<style>' + _V41_STREAKS_CSS + '</style>', h, count=1)
    hsub = _v41_re.search(r'<div class="header-sub">([^<]*)</div>', h)
    hdate = _v41_re.search(r'<div class="header-date">([\s\S]*?)</div>', h)
    count_txt = hsub.group(1).strip() if hsub else ''
    bits = _v41_re.sub(r'<br\s*/?>', '|', hdate.group(1)).split('|') if hdate else ['', '']
    fl = _v41_re.search(r'<div class="filter-row">([\s\S]*?)</div>', h)
    filter_btns = fl.group(1) if fl else ''
    g = _v41_re.search(r'<details class="streak-guide"[\s\S]*?</details>', h)
    guide_html = g.group(0) if g else ''
    rail = ('<nav class="rail-wrap"><div class="rail">'
      '<button class="chip-nav" onclick="window.scrollTo({top:0,behavior:\'smooth\'})"><span class="e">\u2912</span></button>'
      '<span class="rail-div"></span>' + filter_btns + '</div></nav>')
    hero = ('<div class="page-wrap"><div class="hero">'
      '<div class="hero-kicker">Confirmed Game-Log Runs \u00b7 Companion to The Daily Slate</div>'
      '<div class="header-title">\U0001F525 <span class="fire">HOT STREAKS</span></div>'
      '<div class="hero-chips">'
      '<span class="hero-chip"><span class="led"></span>' + count_txt.upper() + '</span>'
      '<span class="hero-chip">' + bits[0].strip() + '</span>'
      '<span class="hero-chip">' + (bits[1].strip().upper() if len(bits) > 1 else '') + '</span>'
      '</div></div>' + guide_html +
      '<p style="font-size:11px;color:var(--text-dim);margin:2px 2px 0;">Tap a tab above \u2014 or swipe a card left / right \u2014 to switch streak types.</p></div>')
    h = _v41_re.sub(r'<div class="page-header">[\s\S]*?</div>\s*\n<div id="streak-list">',
        _v41_appbar('index.html', '\U0001F525 <span class="fire">HOT STREAKS</span>') + '\n' + rail + '\n' + hero +
        '\n<div class="page-wrap"><div id="streak-list">', h, count=1)
    h = h.replace('style="border-left:3px solid', 'style="border-left-color:')
    h = _v41_re.sub(r';background:rgba\(255,255,255,\.012\)"', '"', h)
    h = _v41_re.sub(r';background:transparent"', '"', h)
    h = _v41_re.sub(r'<button class="theme-toggle-fab"[^>]*>[\s\S]*?</button>\s*', '', h)
    h = _v41_re.sub(r'<a class="page-fab[\s\S]*?</a>\s*', '', h)
    tail = ('</div>\n<div class="site-foot">Hot Streaks \u00b7 part of The Daily Slate \u26be</div>\n'
      '<nav class="dock">'
      '<a class="dock-btn" href="index.html"><span class="di">\u26be</span><span class="dl">SLATE</span></a>'
      '<a class="dock-btn" href="k-report.html"><span class="di">\U0001F4F0</span><span class="dl">K REPORT</span></a>'
      '<a class="dock-btn" href="scout.html"><span class="di">\u26a1</span><span class="dl">SSJ</span></a>'
      '<a class="dock-btn" href="record.html"><span class="di">\U0001F4BF</span><span class="dl">RECORD</span></a>'
      '</nav>\n'
      '<script>(function(){'
      'var rail=document.querySelector(".rail");'
      'function center(b){if(!rail||!b)return;var t=b.offsetLeft-rail.clientWidth/2+b.offsetWidth/2;rail.scrollTo({left:Math.max(0,t),behavior:"smooth"});}'
      'var _f=window.filter;'
      'if(_f){window.filter=function(t,b){_f(t,b);center(b);};}'
      'setTimeout(function(){center(document.querySelector(".filter-btn.active"));},350);'
      '})();</script>\n</body>')
    h = h.replace('</body>', tail, 1)
    return h


try:
    _v41_path = K_REPORT_FILE
    _v41_html = open(_v41_path, encoding='utf-8').read()
    if '<!--V41THEME-->' not in _v41_html:
        open(_v41_path, 'w', encoding='utf-8').write(v41_kreport(_v41_html))
        print(f'[k-report] v4.1 theme applied -> {_v41_path}')
except Exception as _v41_e:
    print('[k-report] v4.1 theme SKIPPED:', _v41_e)
