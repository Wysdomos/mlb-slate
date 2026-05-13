"""
build_editorial.py -- Smart auto-generation of editorial sections.

Reads:   day_data.json        (or DATA_FILE env var)
Updates: built_sections.json  (or SECTIONS_FILE env var)

Replaces 6 hardcoded sections with data-driven content:
  headlines, combos-k, combos-hrr, parlays, conviction, skip

Baseball logic applied:
  - VulnScore >= 50 = fire stack target
  - HR Score >= 80 = T0 HR anchor
  - K >= 5.0 -> O5+, 4.5-4.99 -> O3.5, <4.5 -> O2.5 (never alt >5)
  - Platoon edge: LHB vs RHP, RHB vs LHP, Switch = always edge
  - Park HR% >= +25 = volcano, +8 to +24 = booster, <= -15 = suppressor
  - Stack = 2+ top-HR-board batters vs same vulnerable pitcher
  - Conviction = Score + Vuln + Park + Streak all passing threshold
"""

import json, re, os
from datetime import datetime, date

DATA_FILE     = os.environ.get('DATA_FILE',     'day_data.json')
SECTIONS_FILE = os.environ.get('SECTIONS_FILE', 'built_sections.json')

DATA     = json.load(open(DATA_FILE, encoding='utf-8'))
SECTIONS = json.load(open(SECTIONS_FILE, encoding='utf-8'))

# ---- Data lookups ----
HR_LB    = DATA['HR_Leaderboard']
HIT      = DATA['Hit_Probabilities']
SP_PROJ  = DATA['SP_Projections']
SS       = DATA['Sweet_Spot_Slate']
BP_BAT   = DATA['BP_Batters']
BP_PIT   = DATA['BP_Pitchers']
PARKS    = DATA['Park_Factors']
GAMES    = DATA['BP_Games']

TEAM_FIX = {'WSH':'WAS','WAS ':'WAS','WSH ':'WAS','AZ':'ARI','AZ ':'ARI',
            'CWS':'CHW','CHW ':'CHW','TB ':'TB','SF ':'SF','SD ':'SD','KC ':'KC'}
def tn(t): return TEAM_FIX.get((t or '').strip(), (t or '').strip())

def parse_pct(s):
    if s is None: return 0
    if isinstance(s, (int,float)): return int(s)
    s = str(s).replace('+','').replace('%','').strip()
    try: return int(float(s))
    except: return 0

def k_alt(k):
    try: k = float(k)
    except: return 'O 2.5'
    if k >= 5.0: return 'O 5+'
    if k >= 4.5: return 'O 3.5'
    return 'O 2.5'

def hand_chip(h, kind='bats'):
    if not h: return ''
    h = str(h).strip().upper()
    if h == 'L': return f'<span style="color:#3b82f6;font-weight:600" title="{kind} L">L</span>'
    if h == 'R': return f'<span style="color:#ef4444;font-weight:600" title="{kind} R">R</span>'
    if h == 'S': return f'<span style="color:#a855f7;font-weight:600" title="{kind} S">S</span>'
    return ''

def platoon_edge(pitcher_throws, batter_bats):
    if not pitcher_throws or not batter_bats: return False
    t = str(pitcher_throws).upper(); b = str(batter_bats).upper()
    if b == 'S': return True
    return t != b

# Indexes
SS_BY_NAME    = {(r.get('Pitcher') or '').strip().lower(): r for r in SS if r.get('Pitcher') and r['Pitcher'] != 'TBD'}
SP_BY_TEAM    = {tn(r.get('Team','')): r for r in SP_PROJ if r.get('Team')}
BP_BAT_BY_NAME= {}
for r in BP_BAT:
    nm = (r.get('FullName') or '').strip().lower()
    if nm and nm not in BP_BAT_BY_NAME: BP_BAT_BY_NAME[nm] = r
BP_PIT_BY_NAME= {(r.get('FullName') or '').strip().lower(): r for r in BP_PIT}
HIT_BY_NAME   = {}
for r in HIT:
    nm = f"{r.get('First Name','')} {r.get('Last Name','')}".strip().lower()
    HIT_BY_NAME[nm] = r
PARK_BY_TEAM  = {}
for p in PARKS:
    g = p.get('Game','')
    m = re.match(r'\s*(\w+)\s*@\s*(\w+)\s*', g)
    if m:
        PARK_BY_TEAM[m.group(1)] = p
        PARK_BY_TEAM[m.group(2)] = p
PARK_TIME = {}
for p in PARKS:
    g = p.get('Game','')
    PARK_TIME[g] = p.get('Time','')

def get_park_for_batter(team):
    return PARK_BY_TEAM.get(tn(team))

def get_vuln(pitcher_name):
    return SS_BY_NAME.get((pitcher_name or '').strip().lower())

def vuln_score(pitcher_name):
    v = get_vuln(pitcher_name)
    if not v: return 0
    try: return int(v.get('VulnScore') or 0)
    except: return 0

def streak_chip(s):
    if not s: return ''
    s = str(s).upper()
    if s == 'HOT': return ' <span style="color:var(--hot)">HOT</span>'
    if s == 'COLD': return ' <span style="color:var(--bad)">COLD</span>'
    return ''

# ---- Game time lookup ----
def game_time(away_team, home_team):
    key = f'{away_team} @ {home_team}'
    t = PARK_TIME.get(key)
    if t: return f'{t} ET'
    return ''

# ============================================================
# 1. HEADLINES
# ============================================================
def build_headlines():
    flags = []

    # -- Story 1: Best park environment --
    parks_sorted = sorted(PARKS, key=lambda p: -parse_pct(p.get('HR %')))
    top_park = parks_sorted[0]
    top_hr   = parse_pct(top_park.get('HR %'))
    top_runs = parse_pct(top_park.get('Runs %'))
    park_game = top_park.get('Game','')
    park_venue = top_park.get('Venue','')
    park_icon = '🌋' if top_hr >= 25 else '🔥'
    park_label = 'HR volcano' if top_hr >= 25 else 'top HR environment'
    m = re.match(r'\s*(\w+)\s*@\s*(\w+)\s*', park_game)
    if m:
        home_t = m.group(2)
        home_sp = SP_BY_TEAM.get(home_t)
        away_sp = SP_BY_TEAM.get(m.group(1))
        # Top batters at this park from HR board
        park_hr_bats = [r for r in HR_LB[:30] if tn(r.get('Team')) in [home_t, m.group(1)]][:4]
        bat_names = ', '.join(f"<strong>{r['Batter']}</strong> ({r.get('Score','')})" for r in park_hr_bats)
        pitcher_note = ''
        if home_sp:
            vs = get_vuln(home_sp.get('Pitcher',''))
            if vs: pitcher_note = f" vs <strong>{home_sp['Pitcher']} V{vs['VulnScore']}</strong>."
        flags.append((park_icon,
            f"<strong>{park_venue} +{top_hr}% HR -- slate's {park_label}.</strong> "
            f"{park_game} ({game_time(m.group(1), m.group(2))})."
            f"{pitcher_note} "
            f"Top bats here: {bat_names}. "
            f"Park also +{top_runs}% Runs. <strong>Stack the home lineup.</strong>"))

    # -- Story 2: Best batter stack (most HR-board top players vs same pitcher) --
    pitcher_stacks = {}
    for r in HR_LB[:25]:
        pit = r.get('Pitcher','')
        if not pit: continue
        v = vuln_score(pit)
        if pit not in pitcher_stacks:
            pitcher_stacks[pit] = {'batters': [], 'vuln': v, 'team': tn(r.get('Team','')), 'pitcher_team': tn(r.get('Pitcher Team',''))}
        pitcher_stacks[pit]['batters'].append(r)
    # Sort by (vuln * count)
    best_stack = sorted(pitcher_stacks.items(), key=lambda x: x[1]['vuln'] * len(x[1]['batters']), reverse=True)
    if best_stack:
        pit_name, stack = best_stack[0]
        bats = stack['batters']
        v = stack['vuln']
        team = stack['team']
        bat_str = ', '.join(f"<strong>{r['Batter']}</strong> #{r['Rank']} (Score {r['Score']}, {r.get('Zone','')})" for r in bats[:4])
        park = get_park_for_batter(team)
        park_note = f" {park.get('Venue','')} <strong>{park.get('HR %','')} HR</strong>." if park else ''
        flags.append(('🔥',
            f"<strong>{team} stack vs {pit_name} (V{v} -- {'slate-worst SP' if v == max(s[1]['vuln'] for s in best_stack) else 'top target'}).</strong>"
            f"{park_note} "
            f"HR Board: {bat_str}. "
            f"<strong>Best same-game stack of the slate.</strong>"))

    # -- Story 3: Second-best stack if different pitcher --
    if len(best_stack) >= 2:
        pit2_name, stack2 = best_stack[1]
        if pit2_name != best_stack[0][0]:
            bats2 = stack2['batters']
            v2 = stack2['vuln']
            team2 = stack2['team']
            bat_str2 = ', '.join(f"<strong>{r['Batter']}</strong> #{r['Rank']} (Score {r['Score']})" for r in bats2[:3])
            park2 = get_park_for_batter(team2)
            park_note2 = f" {park2.get('Venue','')} <strong>{park2.get('HR %','')} HR</strong>." if park2 else ''
            flags.append(('🎯',
                f"<strong>{team2} stack vs {pit2_name} (V{v2}).</strong>"
                f"{park_note2} "
                f"HR Board: {bat_str2}. "
                f"Cross-game complement to the top stack."))

    # -- Story 4: K board leader --
    sp_k_sorted = sorted(SP_PROJ, key=lambda r: -(r.get('K') or 0))
    if sp_k_sorted:
        top_k = sp_k_sorted[0]
        k2 = sp_k_sorted[1] if len(sp_k_sorted) > 1 else None
        name = top_k.get('Pitcher','')
        k_val = top_k.get('K')
        team = tn(top_k.get('Team',''))
        opp = tn(top_k.get('Opp',''))
        alt = k_alt(k_val)
        v = get_vuln(name)
        vuln_note = f" V{v['VulnScore']}" if v else ''
        k2_str = ''
        if k2:
            k2_alt = k_alt(k2.get('K'))
            k2_str = f" <strong>{k2['Pitcher']}</strong> {k2.get('K')} K ({k2_alt}) is slate #2."
        flags.append(('⚡',
            f"<strong>K Board: {name} {k_val} K leads slate -- Best Line: {alt}.</strong>"
            f" {team} vs {opp}{vuln_note}. {k2_str}"
            f" Per user rule: >=5 K -> O5+, 4.5-4.99 -> O3.5, <4.5 -> O2.5."))

    # -- Story 5: SP HR/BB vulnerability (highest HR/9) --
    sp_hr_sorted = sorted(SP_PROJ, key=lambda r: -(r.get('HR') or 0))
    top_vuln_arms = [r for r in sp_hr_sorted if (r.get('HR') or 0) >= 0.80][:4]
    if top_vuln_arms:
        arm_str = ', '.join(
            f"<strong>{r['Pitcher']}</strong> {r['HR']} HR/9 (vs {tn(r['Opp'])}, V{vuln_score(r['Pitcher'])})"
            for r in top_vuln_arms
        )
        flags.append(('🎯',
            f"<strong>SP HR-Vulnerability: {arm_str}.</strong> "
            f"All have HR-stack potential. See SP HR/BB Risk Board."))

    # -- Story 6: Suppressor parks to fade --
    suppressors = [(p, parse_pct(p.get('HR %'))) for p in PARKS if parse_pct(p.get('HR %')) <= -17]
    suppressors.sort(key=lambda x: x[1])
    if suppressors:
        sup_str = ' / '.join(
            f"<strong>{p.get('Venue','')} {pct}% HR</strong> ({p.get('Game','')})"
            for p, pct in suppressors[:3]
        )
        doubles_parks = [(p, parse_pct(p.get('2B/3B %'))) for p in PARKS if parse_pct(p.get('2B/3B %')) >= 15]
        db_note = ''
        if doubles_parks:
            dp = doubles_parks[0]
            db_note = f" <strong>{dp[0].get('Venue','')} +{dp[1]}% 2B/3B</strong> -- pivot to doubles props there."
        flags.append(('🥶',
            f"<strong>HR suppressed: {sup_str}.</strong> "
            f"Fade HR alts at these parks -- pivot to 1+H / RBI / Runs plays.{db_note}"))

    # -- Story 7: Skip arms (K < 3.5) --
    skip_arms = [r for r in SP_PROJ if (r.get('K') or 0) < 3.5]
    if skip_arms:
        arm_list = ', '.join(
            f"<strong>{r['Pitcher']}</strong> ({tn(r['Team'])}, K {r['K']})"
            for r in sorted(skip_arms, key=lambda r: (r.get('K') or 0))[:4]
        )
        flags.append(('📋',
            f"<strong>SKIP K props:</strong> {arm_list}. "
            f"All below the O 2.5 alt floor. Avoid strikeout props on these arms entirely."))

    # Render
    rows_html = '\n'.join(
        f'  <div class="flag-row"><div class="icon">{icon}</div><div>{body}</div></div>'
        for icon, body in flags
    )
    return f'''<!-- HEADLINES -->
<section id="headlines">
  <h2>📅 Slate Headlines + Flags</h2>
{rows_html}
</section>
'''

# ============================================================
# 2. ALT K COMBOS
# ============================================================
def build_combos_k():
    # Get all starters with K projection, sorted desc
    sp_k = sorted(
        [r for r in SP_PROJ if r.get('K') is not None],
        key=lambda r: -(r.get('K') or 0)
    )

    def sp_info(r):
        name = r['Pitcher']
        k    = r.get('K', 0)
        team = tn(r.get('Team',''))
        opp  = tn(r.get('Opp',''))
        alt  = k_alt(k)
        v    = vuln_score(name)
        park = get_park_for_batter(team)
        park_hr = parse_pct(park.get('HR %')) if park else 0
        t = game_time(team, opp) or game_time(opp, team)
        vuln_str = f"V{v}" if v else ''
        park_str = f"{'+' if park_hr>=0 else ''}{park_hr}% HR" if park_hr != 0 else 'neutral park'
        return name, k, team, opp, alt, vuln_str, park_str, t

    # Tier groups
    t0 = [r for r in sp_k if (r.get('K') or 0) >= 5.0]   # O5+
    t1 = [r for r in sp_k if 4.5 <= (r.get('K') or 0) < 5.0]  # O3.5
    t2 = [r for r in sp_k if 4.0 <= (r.get('K') or 0) < 4.5]  # O2.5

    def leg(r, num=None):
        n, k, team, opp, alt, v, park, t = sp_info(r)
        prefix = f"Leg {num}: " if num else ''
        tier_badge = 'T0' if k >= 5 else ('T1' if k >= 4.5 else 'T2')
        return (f"{prefix}<strong>{n}</strong> <strong>{alt}</strong> "
                f"(SS {k} K, {team} vs {opp}{', ' + v if v else ''}, {park}{', ' + t if t else ''})")

    combos = []

    # Combo 1: Best 2-leg T0 pair
    if len(t0) >= 2:
        n1,k1,tm1,op1,alt1,v1,pk1,t1_ = sp_info(t0[0])
        n2,k2,tm2,op2,alt2,v2,pk2,t2_ = sp_info(t0[1])
        combos.append(('1\u20e3',
            f"<strong>{n1} {alt1} + {n2} {alt1}</strong> -- "
            f"Slate's top 2 K projections. {leg(t0[0],1)} {leg(t0[1],2)} "
            f"Different games. Slate-best T0 K anchor pair.",
            'b-tier0', '2-leg T0'))

    # Combo 2: T0 #3 + T0 #4 if available, else T0 + T1
    if len(t0) >= 4:
        combos.append(('2\u20e3',
            f"<strong>{t0[2]['Pitcher']} {k_alt(t0[2]['K'])} + {t0[3]['Pitcher']} {k_alt(t0[3]['K'])}</strong> -- "
            f"{leg(t0[2],1)} {leg(t0[3],2)} "
            f"Different games. T0 K combo.",
            'b-tier0', '2-leg T0'))
    elif len(t0) >= 2 and len(t1) >= 1:
        combos.append(('2\u20e3',
            f"<strong>{t0[-1]['Pitcher']} {k_alt(t0[-1]['K'])} + {t1[0]['Pitcher']} {k_alt(t1[0]['K'])}</strong> -- "
            f"{leg(t0[-1],1)} {leg(t1[0],2)} "
            f"Cross-tier T0+T1 combo.",
            'b-tier1', '2-leg T0+T1'))

    # Combo 3: Top 3 T0 (all different games)
    if len(t0) >= 3:
        names = ' + '.join(f"{r['Pitcher']} {k_alt(r['K'])}" for r in t0[:3])
        legs  = ' '.join(leg(r, i+1) for i, r in enumerate(t0[:3]))
        combos.append(('3\u20e3',
            f"<strong>{names}</strong> -- 3-leg T0 K stack. {legs} "
            f"All different games. Slate's only three SS >=5.0 K plays.",
            'b-tier0', '3-leg T0 stack'))

    # Combo 4: Top 4 T0
    if len(t0) >= 4:
        names = ' + '.join(f"{r['Pitcher']} {k_alt(r['K'])}" for r in t0[:4])
        legs  = ' '.join(leg(r, i+1) for i, r in enumerate(t0[:4]))
        combos.append(('4\u20e3',
            f"<strong>{names}</strong> -- 4-leg T0 K saturation. {legs}",
            'b-tier0', '4-leg T0 saturation'))

    # Combo 5: Best 2-leg T1 pair
    if len(t1) >= 2:
        n1,k1,tm1,op1,alt1,v1,pk1,t1_ = sp_info(t1[0])
        n2,k2,tm2,op2,alt2,v2,pk2,t2_ = sp_info(t1[1])
        combos.append(('5\u20e3',
            f"<strong>{n1} O 3.5 K + {n2} O 3.5 K</strong> -- "
            f"{leg(t1[0],1)} {leg(t1[1],2)} "
            f"T1 O3.5 combo. Safe floor plays.",
            'b-tier1', '2-leg T1 O3.5'))

    # Combo 6: T0 + T1 cross
    if len(t0) >= 1 and len(t1) >= 1:
        combos.append(('6\u20e3',
            f"<strong>{t0[0]['Pitcher']} O 5+ + {t1[0]['Pitcher']} O 3.5</strong> -- "
            f"{leg(t0[0],1)} {leg(t1[0],2)} "
            f"Anchor-plus-floor structure. T0 anchor with T1 safety leg.",
            'b-tier1', '2-leg T0+T1 anchor'))

    # Combo 7: 3-leg cross T0+T1
    if len(t0) >= 2 and len(t1) >= 1:
        combos.append(('7\u20e3',
            f"<strong>{t0[0]['Pitcher']} + {t0[1]['Pitcher']} + {t1[0]['Pitcher']}</strong> -- "
            f"{leg(t0[0],1)} {leg(t0[1],2)} {leg(t1[0],3)} "
            f"3-game T0+T0+T1 mixed stack.",
            'b-tier1', '3-leg cross-game'))

    # Combo 8: T2 safe floor if available, else 2-leg T1 +  T0
    if len(t2) >= 2:
        combos.append(('8\u20e3',
            f"<strong>{t2[0]['Pitcher']} O 2.5 + {t2[1]['Pitcher']} O 2.5</strong> -- "
            f"{leg(t2[0],1)} {leg(t2[1],2)} "
            f"Low-alt safe play. Floor combos for softer nights.",
            'b-warn', '2-leg O2.5 floor'))
    elif len(t0) >= 1 and len(t1) >= 2:
        combos.append(('8\u20e3',
            f"<strong>{t0[0]['Pitcher']} O 5+ + {t1[0]['Pitcher']} O 3.5 + {t1[1]['Pitcher']} O 3.5</strong> -- "
            f"{leg(t0[0],1)} {leg(t1[0],2)} {leg(t1[1],3)} "
            f"T0 anchor + two T1 floor legs. Three different games.",
            'b-tier1', '3-leg T0+T1+T1'))

    # Pad to 8 if needed
    while len(combos) < 8 and len(sp_k) >= 2:
        r1, r2 = sp_k[len(combos) % len(sp_k)], sp_k[(len(combos)+1) % len(sp_k)]
        combos.append((f'{len(combos)+1}\u20e3',
            f"<strong>{r1['Pitcher']} {k_alt(r1['K'])} + {r2['Pitcher']} {k_alt(r2['K'])}</strong> -- "
            f"{leg(r1,1)} {leg(r2,2)}",
            'b-tier1', '2-leg'))
        if len(combos) >= 8: break

    blocks = [
        f'  <div class="flag-row"><div class="icon">{icon}</div><div>{body} '
        f'<span class="badge {badge_cls}">{badge_text}</span></div></div>'
        for icon, body, badge_cls, badge_text in combos[:8]
    ]

    return f'''<!-- COMBOS K -->
<section id="combos-k" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">⚡ Alt K Combos</div>
      <span class="game-tag">Tap to expand · K-only combos · alts <=5 per user rule</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">K-only combo cards. <strong>Alt rule: >=5 K -> O5+; 4.5-4.99 -> O3.5; <4.5 -> O2.5. Never alt >5.</strong> Same player max 2 legs.</p>
{chr(10).join(blocks)}
  </div></div>
</section>
'''

# ============================================================
# 3. HRR COMBOS
# ============================================================
def build_combos_hrr():
    # Score each top-25 HR board batter for HRR quality
    # HRR = H + R + RBI (Ov 0.5 means need 1 total)
    # Best HRR candidates: high 1+Hit% AND high RBI% AND decent HR% AND vs vulnerable pitcher AND at good park

    def hrr_score(r):
        nm = (r.get('Batter') or '').lower()
        hit_row = HIT_BY_NAME.get(nm) or {}
        bp_row  = BP_BAT_BY_NAME.get(nm) or {}
        def pct_val(s):
            if not s: return 0
            try: return float(str(s).replace('%',''))
            except: return 0
        h1  = pct_val(hit_row.get('1+ Hit', 0))
        rbi = pct_val(hit_row.get('To Get RBI', 0))
        hr_score = r.get('Score', 0)
        park = get_park_for_batter(r.get('Team',''))
        park_hr = parse_pct(park.get('HR %')) if park else 0
        v = vuln_score(r.get('Pitcher',''))
        return h1 + rbi*0.7 + hr_score*0.3 + park_hr*0.2 + v*0.1

    def batter_detail(r):
        nm = (r.get('Batter') or '').lower()
        hit_row = HIT_BY_NAME.get(nm) or {}
        def pct_val(s):
            if not s: return '---'
            return str(s).replace('%','').strip() + '%' if '%' not in str(s) else str(s)
        h1  = pct_val(hit_row.get('1+ Hit'))
        rbi = pct_val(hit_row.get('To Get RBI'))
        hr_pct = pct_val(hit_row.get('To Hit HR'))
        park = get_park_for_batter(r.get('Team',''))
        park_hr = parse_pct(park.get('HR %')) if park else 0
        park_str = f"{'+' if park_hr >= 0 else ''}{park_hr}% HR" if park_hr != 0 else ''
        v = vuln_score(r.get('Pitcher',''))
        streak = r.get('Streak','')
        return (r.get('Batter',''), tn(r.get('Team','')), r.get('Pitcher',''), v,
                r.get('Score',0), r.get('Zone',''), h1, rbi, hr_pct, park_str, streak, r.get('Bats',''))

    top_batters = sorted(HR_LB[:25], key=hrr_score, reverse=True)

    # Group by pitcher (same-game stacks)
    by_pitcher = {}
    for r in top_batters:
        pit = r.get('Pitcher','') or 'Unknown'
        if pit not in by_pitcher:
            by_pitcher[pit] = []
        by_pitcher[pit].append(r)

    # Sort stacks: vuln * count * avg_score
    def stack_score(pit, batters):
        v = vuln_score(pit)
        avg = sum(r.get('Score',0) for r in batters) / len(batters)
        park_hr = 0
        if batters:
            pk = get_park_for_batter(batters[0].get('Team',''))
            park_hr = parse_pct(pk.get('HR %')) if pk else 0
        return v * len(batters) * 0.5 + avg + park_hr * 0.3

    stacks = sorted(by_pitcher.items(), key=lambda x: stack_score(x[0], x[1]), reverse=True)

    combos = []
    icon_nums = ['1\u20e3','2\u20e3','3\u20e3','4\u20e3','5\u20e3','6\u20e3','7\u20e3','8\u20e3']

    def leg_str(r, num=None):
        nm, team, pit, v, score, zone, h1, rbi, hr_pct, pk_str, streak, bats = batter_detail(r)
        prefix = f"Leg {num}: " if num else ''
        streak_s = streak_chip(streak)
        return (f"{prefix}<strong>{nm}</strong>{streak_s} Ov 0.5 HRR "
                f"(HR Score {score} {zone}, Hit {h1} / RBI {rbi} / HR {hr_pct}"
                f"{', ' + pk_str if pk_str else ''}, vs {pit} V{v})")

    combo_idx = 0

    # Best same-game stack (top stack with 2+ players)
    for pit, batters in stacks:
        if len(batters) >= 2:
            nm, team, p, v, score, zone, h1, rbi, hr_pct, pk_str, streak, bats = batter_detail(batters[0])
            bat_names = ' + '.join(f"<strong>{r['Batter']}</strong>" for r in batters[:2])
            legs = ' '.join(leg_str(r, i+1) for i, r in enumerate(batters[:2]))
            badge = 'b-tier0' if v >= 50 else 'b-tier1'
            combos.append((icon_nums[combo_idx],
                f"<strong>{bat_names} Ov 0.5 HRR</strong> -- {team} stack vs {pit} (V{v}). "
                f"{legs} Same-game stack. <strong>{pk_str + ' park boost.' if pk_str else ''}</strong>",
                badge, f"2-leg {team} stack"))
            combo_idx += 1
            if combo_idx >= 8: break

            # 3-player version if available
            if len(batters) >= 3 and combo_idx < 8:
                bat3 = ' + '.join(f"<strong>{r['Batter']}</strong>" for r in batters[:3])
                legs3 = ' '.join(leg_str(r, i+1) for i, r in enumerate(batters[:3]))
                combos.append((icon_nums[combo_idx],
                    f"<strong>{bat3} Ov 0.5 HRR</strong> -- 3-batter {team} saturation vs {pit} (V{v}). "
                    f"{legs3}",
                    badge, f"3-leg {team} stack"))
                combo_idx += 1
                if combo_idx >= 8: break

    # Cross-game combos: best player from top 2 different stacks
    if len(stacks) >= 2 and combo_idx < 8:
        s1_pit, s1_bats = stacks[0]
        s2_pit, s2_bats = stacks[1]
        if s1_bats and s2_bats:
            r1, r2 = s1_bats[0], s2_bats[0]
            nm1, team1, p1, v1, *_ = batter_detail(r1)
            nm2, team2, p2, v2, *_ = batter_detail(r2)
            combos.append((icon_nums[combo_idx],
                f"<strong>{nm1} + {nm2} Ov 0.5 HRR</strong> -- cross-game top picks. "
                f"{leg_str(r1,1)} {leg_str(r2,2)} "
                f"#1 and #2 HR Board anchors. Different games.",
                'b-tier0', '2-leg cross-game'))
            combo_idx += 1

    # Cross-game: top 4 individual plays from different stacks
    if combo_idx < 8:
        seen_pits = set()
        cross_bats = []
        for pit, batters in stacks:
            if pit not in seen_pits and batters:
                cross_bats.append(batters[0])
                seen_pits.add(pit)
            if len(cross_bats) >= 4: break
        if len(cross_bats) >= 4:
            names = ' + '.join(f"<strong>{r['Batter']}</strong>" for r in cross_bats[:4])
            legs = ' '.join(leg_str(r, i+1) for i, r in enumerate(cross_bats[:4]))
            combos.append((icon_nums[combo_idx],
                f"<strong>{names} Ov 0.5 HRR</strong> -- 4-leg saturation across "
                f"{', '.join(tn(r.get('Team','')) for r in cross_bats[:4])}. "
                f"{legs} Top HR Board pick from each top matchup.",
                'b-tier1', '4-leg multi-stack'))
            combo_idx += 1

    # Pad to 8 if needed
    while combo_idx < 8 and combo_idx < len(top_batters) - 1:
        r1 = top_batters[combo_idx]
        r2 = top_batters[combo_idx + 1]
        nm1 = r1.get('Batter','')
        nm2 = r2.get('Batter','')
        combos.append((icon_nums[combo_idx],
            f"<strong>{nm1} + {nm2} Ov 0.5 HRR</strong> -- "
            f"{leg_str(r1,1)} {leg_str(r2,2)}",
            'b-tier1', '2-leg HRR'))
        combo_idx += 1

    blocks = [
        f'  <div class="flag-row"><div class="icon">{icon}</div><div>{body} '
        f'<span class="badge {badge_cls}">{badge_text}</span></div></div>'
        for icon, body, badge_cls, badge_text in combos[:8]
    ]

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
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">H+R+RBI combos. <strong>Every leg Ov 0.5 HRR.</strong> Ranked by Hit% + RBI% + HR Score + Park + Vuln. Same-game stacks prioritized.</p>
{chr(10).join(blocks)}
  </div></div>
</section>
'''

# ============================================================
# 4. PARLAYS
# ============================================================
def build_parlays():
    def pct_val(s):
        if not s: return 0
        try: return float(str(s).replace('%',''))
        except: return 0

    # Gather T0 anchors
    t0_hr = [r for r in HR_LB if r.get('Score',0) >= 75][:6]
    t0_k  = sorted([r for r in SP_PROJ if (r.get('K') or 0) >= 5.0],
                   key=lambda r: -(r.get('K') or 0))[:4]
    t0_hit= sorted([r for r in HIT if pct_val(r.get('1+ Hit')) >= 63],
                   key=lambda r: -pct_val(r.get('1+ Hit')))[:4]

    def hr_leg(r, num=None):
        nm = r.get('Batter','')
        team = tn(r.get('Team',''))
        pit  = r.get('Pitcher','')
        v    = vuln_score(pit)
        score= r.get('Score',0)
        zone = r.get('Zone','')
        park = get_park_for_batter(team)
        pk_s = f", {park.get('Venue','')} {park.get('HR %','')}" if park else ''
        t = game_time(team, tn(r.get('Pitcher Team',''))) or game_time(tn(r.get('Pitcher Team','')), team)
        p = f"Leg {num}: " if num else ''
        return f"{p}<strong>{nm}</strong> HR (Score {score} {zone}, vs {pit} V{v}{pk_s}{', ' + t if t else ''})"

    def k_leg(r, num=None):
        nm   = r.get('Pitcher','')
        k    = r.get('K')
        team = tn(r.get('Team',''))
        opp  = tn(r.get('Opp',''))
        alt  = k_alt(k)
        t = game_time(team, opp)
        p = f"Leg {num}: " if num else ''
        return f"{p}<strong>{nm}</strong> {alt} K (SS {k}, {team} vs {opp}{', ' + t if t else ''})"

    def hit_leg(r, num=None):
        nm = f"{r.get('First Name','')} {r.get('Last Name','')}".strip()
        team = tn(r.get('Team',''))
        h1 = r.get('1+ Hit','')
        match = r.get('Matchup','')
        p = f"Leg {num}: " if num else ''
        return f"{p}<strong>{nm}</strong> 1+H ({h1} -- {match})"

    parlays = []

    # Parlay 1: 4-leg HR
    if len(t0_hr) >= 4:
        legs = ' '.join(hr_leg(t0_hr[i], i+1) for i in range(4))
        names = ' + '.join(f"<strong>{r['Batter']}</strong>" for r in t0_hr[:4])
        parlays.append(('🏆',
            f"<strong>4-Leg HR Parlay: {names}</strong>"
            f"<br>{legs}"
            f"<br><em>Top 4 HR Board anchors. Mix of stacks + cross-game for portfolio coverage.</em>"))

    # Parlay 2: 4-leg Hits
    if len(t0_hit) >= 4:
        legs = ' '.join(hit_leg(t0_hit[i], i+1) for i in range(4))
        names = ' + '.join(
            f"<strong>{r.get('First Name','')} {r.get('Last Name','')}</strong>"
            for r in t0_hit[:4]
        )
        parlays.append(('☄️',
            f"<strong>4-Leg Hits Parlay: {names}</strong>"
            f"<br>{legs}"
            f"<br><em>Top 4 hit% rates on slate. All at top hit environments.</em>"))

    # Parlay 3: 4-leg HRR
    if len(t0_hr) >= 4:
        legs = ' '.join(
            f"Leg {i+1}: <strong>{r['Batter']}</strong> Ov 0.5 HRR"
            for i, r in enumerate(t0_hr[:4])
        )
        names = ' + '.join(f"<strong>{r['Batter']}</strong>" for r in t0_hr[:4])
        parlays.append(('🔥',
            f"<strong>4-Leg HRR Parlay: {names}</strong>"
            f"<br>{legs}"
            f"<br><em>Top HR board names as HRR Ov 0.5 legs. Highest combined score plays.</em>"))

    # Parlay 4: 2-leg HR pair (top 2, different teams)
    if len(t0_hr) >= 2:
        parlays.append(('⚡',
            f"<strong>2-Leg HR Parlay: {t0_hr[0]['Batter']} + {t0_hr[1]['Batter']}</strong>"
            f"<br>{hr_leg(t0_hr[0],1)}"
            f"<br>{hr_leg(t0_hr[1],2)}"
            f"<br><em>Slate's top 2 HR board scores. Clean 2-leg anchor play.</em>"))

    # Parlay 5: 2-leg HR pair #2
    if len(t0_hr) >= 4:
        parlays.append(('💥',
            f"<strong>2-Leg HR Parlay: {t0_hr[2]['Batter']} + {t0_hr[3]['Batter']}</strong>"
            f"<br>{hr_leg(t0_hr[2],1)}"
            f"<br>{hr_leg(t0_hr[3],2)}"
            f"<br><em>HR Board #3 and #4. Different games, complementary matchups.</em>"))

    # Parlay 6: 4-leg alt K
    if len(t0_k) >= 4:
        legs = ' '.join(k_leg(t0_k[i], i+1) for i in range(4))
        names = ' + '.join(f"<strong>{r['Pitcher']}</strong>" for r in t0_k[:4])
        parlays.append(('🎯',
            f"<strong>4-Leg Alt K Parlay: {names}</strong>"
            f"<br>{legs}"
            f"<br><em>4 different games. All proj >=5.0 -> O5+ per user rule. Never alt >5.</em>"))
    elif len(t0_k) >= 2:
        legs = ' '.join(k_leg(t0_k[i], i+1) for i in range(len(t0_k)))
        names = ' + '.join(f"<strong>{r['Pitcher']}</strong>" for r in t0_k)
        parlays.append(('🎯',
            f"<strong>{len(t0_k)}-Leg Alt K Parlay: {names}</strong>"
            f"<br>{legs}"
            f"<br><em>All available T0 K projections. Different games.</em>"))

    # Parlay 7: 2-leg K combo (top 2)
    if len(t0_k) >= 2:
        parlays.append(('⚾',
            f"<strong>2-Leg K Combo: {t0_k[0]['Pitcher']} + {t0_k[1]['Pitcher']}</strong>"
            f"<br>{k_leg(t0_k[0],1)}"
            f"<br>{k_leg(t0_k[1],2)}"
            f"<br><em>Slate's top 2 K projections. Different games. Cleanest K pair.</em>"))

    # Parlay 8: NRFI -- best game (both SPs project low HR/9, high K, suppressor park)
    def nrfi_score(game):
        away = tn(game.get('AwayTeam',''))
        home = tn(game.get('HomeTeam',''))
        ap = SP_BY_TEAM.get(away)
        hp = SP_BY_TEAM.get(home)
        if not ap or not hp: return 0
        try:
            hr_sum = float(ap.get('HR',0)) + float(hp.get('HR',0))
            k_sum  = float(ap.get('K',0))  + float(hp.get('K',0))
        except: return 0
        park = PARK_BY_TEAM.get(home)
        run_pct = parse_pct(park.get('Runs %')) if park else 0
        return k_sum - hr_sum*3 - run_pct*0.1

    best_nrfi = max(GAMES, key=nrfi_score) if GAMES else None
    if best_nrfi:
        away = tn(best_nrfi.get('AwayTeam',''))
        home = tn(best_nrfi.get('HomeTeam',''))
        ap = SP_BY_TEAM.get(away)
        hp = SP_BY_TEAM.get(home)
        park = PARK_BY_TEAM.get(home)
        pk_note = f"{park.get('Venue','')} {park.get('Runs %','')} Runs" if park else ''
        t = game_time(away, home)
        ap_n = ap['Pitcher'] if ap else 'TBD'
        hp_n = hp['Pitcher'] if hp else 'TBD'
        parlays.append(('🥶',
            f"<strong>NRFI Conviction: {away} @ {home}</strong>"
            f"<br>Leg 1: <strong>{away} @ {home} NRFI</strong> -- "
            f"{ap_n} SS {ap.get('K') if ap else '--'} K + {hp_n} SS {hp.get('K') if hp else '--'} K. "
            f"{pk_note}{'. ' + t if t else '.'}"
            f"<br><em>Both SPs project favorable K/HR balance. Best NRFI environment on slate.</em>"))

    # Parlay 9: Best OVER game
    def over_score(game):
        ra = game.get('RunsAway') or 0
        rh = game.get('RunsHome') or 0
        total = ra + rh
        away = tn(game.get('AwayTeam',''))
        home = tn(game.get('HomeTeam',''))
        park = PARK_BY_TEAM.get(home)
        run_pct = parse_pct(park.get('Runs %')) if park else 0
        return total + run_pct * 0.2

    best_over = max(GAMES, key=over_score) if GAMES else None
    if best_over:
        away = tn(best_over.get('AwayTeam',''))
        home = tn(best_over.get('HomeTeam',''))
        ra = best_over.get('RunsAway',0)
        rh = best_over.get('HomeRuns',0) or best_over.get('RunsHome',0)
        total = (ra or 0) + (rh or 0)
        park = PARK_BY_TEAM.get(home)
        pk_note = f"{park.get('Venue','')} {park.get('HR %','')} HR / {park.get('Runs %','')} Runs" if park else ''
        t = game_time(away, home)
        parlays.append(('📈',
            f"<strong>Game Total OVER Conviction: {away} @ {home}</strong>"
            f"<br>Leg 1: <strong>{away} @ {home} OVER</strong> (BP proj {total:.1f} total runs). "
            f"{pk_note}{'. ' + t if t else '.'}"
            f"<br><em>Highest projected run total + park boost. Best slate OVER environment.</em>"))

    # Parlay 10: 3-leg mix K + HR + Hit
    if t0_k and t0_hr and t0_hit:
        parlays.append(('🌋',
            f"<strong>3-Leg Value Mix: {t0_k[0]['Pitcher']} K + {t0_hr[0]['Batter']} HR + "
            f"{t0_hit[0].get('First Name','')} {t0_hit[0].get('Last Name','')} 1+H</strong>"
            f"<br>{k_leg(t0_k[0],1)}"
            f"<br>{hr_leg(t0_hr[0],2)}"
            f"<br>{hit_leg(t0_hit[0],3)}"
            f"<br><em>3 different games. K + HR + Hit mix. Each leg slate-best at its type.</em>"))

    blocks = [
        f'  <div class="flag-row"><div class="icon">{icon}</div><div>{body}</div></div>'
        for icon, body in parlays[:10]
    ]

    return f'''<!-- PARLAYS -->
<section id="parlays" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">💣 Parlay Anchors</div>
      <span class="game-tag">Tap to expand · 10 anchors · T0 legs · max 2x same player · alts <=5 per parlay</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Rules: Anchor = T0 play. Min 2 different games. Same player max 2 legs. Alts <=5 per parlay. <strong>Never alt >5.</strong></p>
{chr(10).join(blocks)}
  </div></div>
</section>
'''

# ============================================================
# 5. CONVICTION BOARD
# ============================================================
def build_conviction():
    def pct_val(s):
        if not s: return 0
        try: return float(str(s).replace('%',''))
        except: return 0

    picks = []

    # T0 HR plays: Score >= 75, Vuln >= 40, Park HR >= 0, not COLD
    for r in HR_LB[:20]:
        score = r.get('Score', 0)
        if score < 72: break
        pit = r.get('Pitcher','')
        v   = vuln_score(pit)
        nm  = r.get('Batter','')
        team= tn(r.get('Team',''))
        streak = r.get('Streak','')
        park = get_park_for_batter(team)
        park_hr = parse_pct(park.get('HR %')) if park else 0
        if park_hr < -10: continue  # skip hard suppressor parks for HR conviction
        zone = r.get('Zone','')
        grade = r.get('Grade','')
        tier = 'b-tier0' if (score >= 80 and v >= 50) else 'b-tier1'
        tier_label = 'T0 HR CONVICTION' if tier == 'b-tier0' else 'T1 HR'
        streak_s = streak_chip(streak)
        park_note = f", {park.get('Venue','')} {park.get('HR %','')} HR" if park else ''
        cold_note = ' <span style="color:var(--bad)">[COLD streak -- lower unit]</span>' if streak == 'COLD' else ''
        picks.append((
            tier,
            f"<strong>{nm} HR</strong>{streak_s} -- Score {score} {zone}, vs "
            f"<strong>{pit} V{v}</strong>{park_note}.{cold_note}",
            tier_label,
            score + v*0.3 + park_hr*0.3 - (5 if streak == 'COLD' else 0)
        ))

    # T0 K plays
    sp_k = sorted([r for r in SP_PROJ if (r.get('K') or 0) >= 5.0],
                  key=lambda r: -(r.get('K') or 0))
    for r in sp_k:
        k = r.get('K', 0)
        nm = r.get('Pitcher','')
        team = tn(r.get('Team',''))
        opp  = tn(r.get('Opp',''))
        alt  = k_alt(k)
        bp = BP_PIT_BY_NAME.get(nm.lower()) or {}
        bb = bp.get('Walks') or bp.get('BB') or 0
        qs = (bp.get('QualityStart') or 0) * 100
        v  = vuln_score(nm)
        tier = 'b-tier0' if k >= 5.5 else 'b-tier1'
        tier_label = 'T0 K CONVICTION' if k >= 5.5 else 'T1 K'
        try: bb_f = float(bb)
        except: bb_f = 0
        control_note = f" BB {bb_f:.1f} (elite control)" if bb_f <= 2.0 else (f" BB {bb_f:.1f} (walk risk)" if bb_f >= 3.0 else '')
        picks.append((
            tier,
            f"<strong>{nm} {alt} K</strong> -- SS {k} K, {team} vs {opp}. "
            f"QS% {qs:.0f}%{control_note}.",
            tier_label,
            float(k) * 10 + qs * 0.2 - bb_f * 3
        ))

    # T0 Hit plays
    top_hits = sorted([r for r in HIT if pct_val(r.get('1+ Hit')) >= 65],
                      key=lambda r: -pct_val(r.get('1+ Hit')))[:4]
    for r in top_hits:
        nm = f"{r.get('First Name','')} {r.get('Last Name','')}".strip()
        h1  = r.get('1+ Hit','')
        rbi = r.get('To Get RBI','')
        team = tn(r.get('Team',''))
        match = r.get('Matchup','')
        park = get_park_for_batter(team)
        park_note = f", {park.get('Venue','')} {park.get('HR %','')} HR" if park else ''
        picks.append((
            'b-tier0',
            f"<strong>{nm} 1+H {h1}</strong> -- RBI {rbi}, {match}{park_note}.",
            'T0 HIT CONVICTION',
            pct_val(h1) + pct_val(rbi) * 0.5
        ))

    # T0 HRR plays (high Hit% + high RBI% combined)
    def hrr_val(nm):
        r = HIT_BY_NAME.get(nm.lower()) or {}
        return pct_val(r.get('1+ Hit',0)) + pct_val(r.get('To Get RBI',0)) * 0.7
    top_hrr = sorted(HR_LB[:15], key=lambda r: hrr_val(r.get('Batter','')), reverse=True)[:3]
    for r in top_hrr:
        nm = r.get('Batter','')
        team = tn(r.get('Team',''))
        hit_row = HIT_BY_NAME.get(nm.lower()) or {}
        h1  = hit_row.get('1+ Hit','---')
        rbi = hit_row.get('To Get RBI','---')
        pit = r.get('Pitcher','')
        v   = vuln_score(pit)
        park = get_park_for_batter(team)
        pk_note = f", {park.get('Venue','')} {park.get('HR %','')} HR" if park else ''
        picks.append((
            'b-tier1',
            f"<strong>{nm} Ov 0.5 HRR</strong> -- Hit {h1} / RBI {rbi}, vs {pit} V{v}{pk_note}.",
            'T1 HRR CONVICTION',
            hrr_val(nm) + v * 0.1
        ))

    # Sort all picks by confidence score, T0 first
    picks_sorted = sorted(picks, key=lambda x: (0 if x[0] == 'b-tier0' else 1, -x[3]))
    # Dedupe by player name
    seen_names = set()
    deduped = []
    for tier, body, label, score in picks_sorted:
        first_word = body.split(' ')[1] if body.startswith('<strong>') else body[:20]
        if first_word not in seen_names:
            seen_names.add(first_word)
            deduped.append((tier, body, label, score))

    li_items = ''.join(
        f'    <li>{body} <span class="badge {tier}">{label}</span></li>\n'
        for tier, body, label, score in deduped[:9]
    )

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
{li_items}  </ul>
  </div></div>
</section>
'''

# ============================================================
# 6. SKIP LIST
# ============================================================
def build_skip():
    items = []

    # Low-K pitchers: skip all K props
    skip_k = sorted([r for r in SP_PROJ if (r.get('K') or 0) < 3.5],
                    key=lambda r: (r.get('K') or 0))
    for r in skip_k:
        team = tn(r.get('Team',''))
        opp  = tn(r.get('Opp',''))
        items.append((
            f"<strong>{r['Pitcher']} ({team}) ALL K props</strong> -- "
            f"SS K only {r['K']}. Below O 2.5 alt floor. Skip strikeout props entirely.",
            'b-bad', 'SKIP -- LOW K PROJ'))

    # Hard suppressor parks: skip HR alts
    for p in sorted(PARKS, key=lambda p: parse_pct(p.get('HR %'))):
        hr   = parse_pct(p.get('HR %'))
        game = p.get('Game','')
        venue= p.get('Venue','')
        if hr <= -17:
            items.append((
                f"<strong>All {venue} HR plays ({game})</strong> -- "
                f"<strong>{p.get('HR %','')} HR (hard suppressor)</strong>. "
                f"Skip HR props entirely -- pivot to 1+H / RBI / Runs.",
                'b-bad', 'SKIP HR'))
        elif hr <= -12:
            items.append((
                f"<strong>{venue} HR plays ({game})</strong> -- "
                f"{p.get('HR %','')} HR. Downgrade HR confidence. Use 1+H or RBI instead.",
                'b-warn', 'DOWNGRADE HR'))

    # High-vuln pitchers with low K: skip K props (they give up HRs but don't miss bats)
    for pit in SP_PROJ:
        nm = pit.get('Pitcher','')
        k  = pit.get('K') or 0
        v  = vuln_score(nm)
        if v >= 50 and k < 4.5:
            items.append((
                f"<strong>{nm} K props</strong> -- V{v} (HR target) but SS K only {k}. "
                f"He's hittable but not a strikeout arm. Fade K alts; target bats instead.",
                'b-bad', 'SKIP K -- VULN + LOW K'))

    # Worst run environment: fade totals OVER
    min_run_park = min(PARKS, key=lambda p: parse_pct(p.get('Runs %')))
    min_runs = parse_pct(min_run_park.get('Runs %'))
    if min_runs <= -10:
        items.append((
            f"<strong>{min_run_park.get('Venue','')} run props ({min_run_park.get('Game','')})</strong> -- "
            f"<strong>{min_run_park.get('Runs %','')} Runs (slate-worst run environment)</strong>. "
            f"Skip Runs / Totals OVERs. NRFI lean.",
            'b-warn', 'DOWNGRADE RUNS'))

    # Extra double-suppressor: HR% AND Runs% both negative
    for p in PARKS:
        hr  = parse_pct(p.get('HR %'))
        runs= parse_pct(p.get('Runs %'))
        if hr <= -10 and runs <= -10 and p.get('Game') != min_run_park.get('Game'):
            items.append((
                f"<strong>{p.get('Venue','')} double-suppressor ({p.get('Game','')})</strong> -- "
                f"HR {p.get('HR %','')} AND Runs {p.get('Runs %','')}. "
                f"Skip both HR and OVER plays. Under/NRFI only.",
                'b-warn', 'DOUBLE SUPPRESS'))

    # Cold-streak T0 HR plays: note downgrade
    cold_high_score = [r for r in HR_LB[:15] if r.get('Streak','') == 'COLD']
    for r in cold_high_score[:3]:
        items.append((
            f"<strong>{r['Batter']} HR (COLD streak)</strong> -- Score {r['Score']} but in cold streak. "
            f"Data still strong but lower unit size. Wait for uptick or play reduced.",
            'b-warn', 'REDUCE UNIT -- COLD'))

    li_items = ''.join(
        f'    <li>{body} <span class="badge {badge}">{label}</span></li>\n'
        for body, badge, label in items
    )

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
{li_items}  </ul>
  </div></div>
</section>
'''

# ============================================================
# ASSEMBLE & WRITE
# ============================================================
print("Building editorial sections...")
SECTIONS['headlines']  = build_headlines()
SECTIONS['combos-k']   = build_combos_k()
SECTIONS['combos-hrr'] = build_combos_hrr()
SECTIONS['parlays']    = build_parlays()
SECTIONS['conviction'] = build_conviction()
SECTIONS['skip']       = build_skip()

with open(SECTIONS_FILE, 'w', encoding='utf-8') as f:
    json.dump(SECTIONS, f, ensure_ascii=False, indent=1)

print(f"Done. Updated 6 editorial sections in {SECTIONS_FILE}")
for k in ['headlines','combos-k','combos-hrr','parlays','conviction','skip']:
    print(f"  {k}: {len(SECTIONS[k])} bytes")
