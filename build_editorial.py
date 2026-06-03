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

import json, re, os, random
from datetime import datetime, date
random.seed(date.today().isoformat())  # stable per day, varies daily

DATA_FILE     = os.environ.get('DATA_FILE',     'day_data.json')
SECTIONS_FILE = os.environ.get('SECTIONS_FILE', 'built_sections.json')

DATA     = json.load(open(DATA_FILE, encoding='utf-8'))
SECTIONS = json.load(open(SECTIONS_FILE, encoding='utf-8'))

# ---- Data lookups ----
HR_LB    = DATA['HR_Leaderboard']
HR_BY_NAME = { (r.get('Batter') or '').strip().lower(): r for r in HR_LB if r.get('Batter') }
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
# 1. HEADLINES  (color-coded action cards)
# ============================================================
def build_headlines():
    cards = []

    # ---- Story 1 (HERO): Best park environment ----
    parks_sorted = sorted(PARKS, key=lambda p: -parse_pct(p.get('HR %')))
    if parks_sorted:
        top_park = parks_sorted[0]
        top_hr   = parse_pct(top_park.get('HR %'))
        top_runs = parse_pct(top_park.get('Runs %'))
        park_game = top_park.get('Game','')
        park_venue = top_park.get('Venue','')
        is_volcano = top_hr >= 25
        icon = '🌋' if is_volcano else '🔥'
        label = 'HR volcano' if is_volcano else 'top HR environment'
        action_label = '🌋 VOLCANO · STACK HOME' if is_volcano else '🔥 STACK HOME'
        m = re.match(r'\s*(\w+)\s*@\s*(\w+)\s*', park_game)
        details = []
        if m:
            home_t = m.group(2)
            home_sp = SP_BY_TEAM.get(home_t)
            t = game_time(m.group(1), m.group(2))
            pitcher_note = ''
            if home_sp:
                vs = get_vuln(home_sp.get('Pitcher',''))
                if vs: pitcher_note = f" Home SP <strong>{home_sp['Pitcher']} V{vs['VulnScore']}</strong>."
            park_hr_bats = [r for r in HR_LB[:30] if tn(r.get('Team')) in [home_t, m.group(1)]][:5]
            bat_names = ', '.join(f"<strong>{r['Batter']}</strong>" for r in park_hr_bats)
            details.append(f"<strong>{park_game} ({t}).</strong>{pitcher_note}")
            details.append(f"Top bats here: {bat_names}. Park also +{top_runs}% Runs. <strong>Stack the home lineup.</strong>")
        else:
            details.append(f"<strong>+{top_hr}% HR / +{top_runs}% Runs.</strong> Stack the home lineup.")
        cards.append({'hero':True,'icon':icon,'action_class':'stack','action_label':action_label,
            'title':f"{park_venue} +{top_hr}% HR — slate's {label}",
            'details':details,'link_href':'#hr-board','link_text':'→ See HR Board for these bats'})

    # ---- Stories 2 & 3: Best stacks vs vulnerable pitchers ----
    pitcher_stacks = {}
    for r in HR_LB[:25]:
        pit = r.get('Pitcher','')
        if not pit: continue
        pitcher_stacks.setdefault(pit, {'batters':[], 'vuln':vuln_score(pit),
            'team':tn(r.get('Team','')), 'pitcher_team':tn(r.get('Pitcher Team',''))})
        pitcher_stacks[pit]['batters'].append(r)
    best_stack = sorted(pitcher_stacks.items(), key=lambda x: x[1]['vuln']*len(x[1]['batters']), reverse=True)
    max_vuln = max((s[1]['vuln'] for s in best_stack), default=0)

    for rank, (pit_name, stack) in enumerate(best_stack[:2]):
        bats = stack['batters']; v = stack['vuln']; team = stack['team']
        if len(bats) < 2 and rank > 0: break
        bat_str = ', '.join(
            f"<strong>{r['Batter']}</strong> #{r['Rank']} ({r['Score']})" for r in bats[:4])
        park = get_park_for_batter(team)
        park_note = f"{park.get('Venue','')} <strong>{park.get('HR %','')} HR</strong>. " if park else ''
        if rank == 0:
            worst = 'slate-worst SP' if v == max_vuln else 'top target'
            cards.append({'icon':'🔥','action_class':'stack','action_label':'STACK',
                'title':f"{team} stack vs {pit_name} (V{v} — {worst})",
                'details':[f"{park_note}HR Board: {bat_str}. <strong>Best same-game stack of the slate.</strong>"],
                'link_href':'#hr-board','link_text':'→ HR Board'})
        else:
            cards.append({'icon':'🎯','action_class':'stack','action_label':'STACK',
                'title':f"{team} stack vs {pit_name} (V{v})",
                'details':[f"{park_note}HR Board: {bat_str}. Cross-game complement to the top stack."],
                'link_href':'#hr-board','link_text':'→ HR Board'})

    # ---- Story 4: K leader ----
    sp_k_sorted = sorted(SP_PROJ, key=lambda r: -(r.get('K') or 0))
    if sp_k_sorted:
        top_k = sp_k_sorted[0]
        k2 = sp_k_sorted[1] if len(sp_k_sorted) > 1 else None
        name = top_k.get('Pitcher',''); k_val = top_k.get('K')
        team = tn(top_k.get('Team','')); opp = tn(top_k.get('Opp',''))
        alt = k_alt(k_val); v = get_vuln(name)
        vuln_note = f" V{v['VulnScore']}" if v else ''
        k2_str = ''
        if k2:
            k2_str = f" <strong>{k2['Pitcher']}</strong> {k2.get('K')} K ({k_alt(k2.get('K'))}) is slate #2."
        cards.append({'icon':'⚡','action_class':'k-target','action_label':'K TARGET',
            'title':f"{name} {k_val} K leads the slate — Best Line: {alt}",
            'details':[f"{team} vs {opp}{vuln_note}.{k2_str}",
                       '<span style="font-size:12px;color:var(--text-dim)">User rule: ≥5 K → O5+, 4.5–4.99 → O3.5, &lt;4.5 → O2.5. Never alt above 5.</span>'],
            'link_href':'#k-board','link_text':"→ Full K's Board"})

    # ---- Story 5: SP HR-vulnerability ----
    sp_hr_sorted = sorted(SP_PROJ, key=lambda r: -(r.get('HR') or 0))
    top_vuln_arms = [r for r in sp_hr_sorted if (r.get('HR') or 0) >= 0.80][:5]
    if top_vuln_arms:
        arm_str = ', '.join(
            f"<strong>{r['Pitcher']}</strong> {r['HR']} HR/9 (vs {tn(r['Opp'])}, V{vuln_score(r['Pitcher'])})"
            for r in top_vuln_arms)
        cards.append({'icon':'☢️','action_class':'risk','action_label':'HR RISK · STACK OPPS',
            'title':"Pitcher's HR Risk Board — stack opponents on these arms",
            'details':[f"{arm_str}. <strong>All have HR-stack potential.</strong>"],
            'link_href':'#sp-vuln-board','link_text':"→ Pitcher's HR Risk Board"})

    # ---- Story 6: Suppressor parks ----
    suppressors = [(p, parse_pct(p.get('HR %'))) for p in PARKS if parse_pct(p.get('HR %')) <= -17]
    suppressors.sort(key=lambda x: x[1])
    if suppressors:
        sup_str = ' / '.join(f"<strong>{p.get('Venue','')} {pct}% HR</strong> ({p.get('Game','')})"
                             for p, pct in suppressors[:3])
        doubles_parks = [(p, parse_pct(p.get('2B/3B %'))) for p in PARKS if parse_pct(p.get('2B/3B %')) >= 15]
        db_note = ''
        if doubles_parks:
            dp = doubles_parks[0]
            db_note = f" <strong>{dp[0].get('Venue','')} +{dp[1]}% 2B/3B</strong> — pivot to doubles props there."
        cards.append({'icon':'🥶','action_class':'fade','action_label':'FADE HR ALTS',
            'title':"HR-suppressed parks — fade the long ball here",
            'details':[f"{sup_str}. Fade HR alts — pivot to 1+H / RBI / Runs plays.{db_note}"],
            'link_href':'#park-board','link_text':'→ Park Factors Board','link_fade':True})

    # ---- Story 7: Skip arms ----
    skip_arms = [r for r in SP_PROJ if (r.get('K') or 0) < 3.5]
    if skip_arms:
        arm_list = ', '.join(f"<strong>{r['Pitcher']}</strong> ({tn(r['Team'])}, K {r['K']})"
                            for r in sorted(skip_arms, key=lambda r:(r.get('K') or 0))[:4])
        cards.append({'icon':'⛔','action_class':'skip','action_label':'SKIP K PROPS',
            'title':"Arms below the O 2.5 floor — don't bet K props on these",
            'details':[f"{arm_list}. <strong>All below the alt floor.</strong> Pivot to 1+H / RBI plays instead."],
            'link_href':'#skip','link_text':'→ Daily Skip List','link_fade':True})

    # ---- Render ----
    def render(c):
        cls = 'headline-hero' if c.get('hero') else f"headline-card {c['action_class']}"
        details_html = '\n'.join(f'      <p class="card-detail">{d}</p>' for d in c['details'])
        link_html = ''
        if c.get('link_href'):
            lcls = 'card-link fade' if c.get('link_fade') else 'card-link'
            link_html = f'\n      <a class="{lcls}" href="{c["link_href"]}">{c["link_text"]}</a>'
        return (f'  <article class="{cls}">\n'
                f'    <div class="card-icon">{c["icon"]}</div>\n'
                f'    <div class="card-content">\n'
                f'      <span class="card-action {c["action_class"]}">{c["action_label"]}</span>\n'
                f'      <h3 class="card-title">{c["title"]}</h3>\n'
                f'{details_html}{link_html}\n'
                f'    </div>\n'
                f'  </article>')

    cards_html = '\n\n'.join(render(c) for c in cards)
    return f'''<!-- HEADLINES -->
<section id="headlines">
  <h2>📅 Slate Headlines + Flags</h2>

  <div class="beginner-note">
    <strong>What is this?</strong> The top storylines for tonight's slate — where to stack, what to fade, and where the value is. Start here every day. Each card has a color-coded action tag and a link to the relevant board.
  </div>

{cards_html}
</section>
'''


# ============================================================
# 2. ALT K COMBOS  (T1+ only, fall back to T2; random; each pitcher once)
# ============================================================
def build_combos_k():
    def sp_info(r):
        name = r['Pitcher']; k = r.get('K', 0) or 0
        team = tn(r.get('Team','')); opp = tn(r.get('Opp',''))
        alt  = k_alt(k); v = vuln_score(name)
        park = get_park_for_batter(team)
        park_hr = parse_pct(park.get('HR %')) if park else 0
        t = game_time(team, opp) or game_time(opp, team)
        vuln_str = f"V{v}" if v else ''
        park_str = f"{'+' if park_hr>=0 else ''}{park_hr}% HR" if park_hr != 0 else 'neutral park'
        return name, k, team, opp, alt, vuln_str, park_str, t

    def leg(r, num=None):
        n, k, team, opp, alt, v, park, t = sp_info(r)
        prefix = f"Leg {num}: " if num else ''
        return (f"{prefix}<strong>{n}</strong> <strong>{alt}</strong> "
                f"(SS {k} K, {team} vs {opp}{', ' + v if v else ''}, {park}{', ' + t if t else ''})")

    # Pool: T0 (>=5.0) + T1 (4.5-4.99) first; fall back to T2 (4.0-4.49) only if short
    t0t1 = sorted([r for r in SP_PROJ if (r.get('K') or 0) >= 4.5], key=lambda r:-(r.get('K') or 0))
    t2   = sorted([r for r in SP_PROJ if 4.0 <= (r.get('K') or 0) < 4.5], key=lambda r:-(r.get('K') or 0))
    pool = list(t0t1)
    if len(pool) < 9:          # need enough for 4+3+2; top up from T2
        pool += t2[:max(0, 9 - len(pool))]

    random.shuffle(pool)

    combos = []
    idx = 0
    def tier_badge(r):
        k = r.get('K',0) or 0
        return 'b-tier0' if k >= 5 else ('b-tier1' if k >= 4.5 else 'b-tier2')

    # 4-leg
    if len(pool) - idx >= 4:
        grp = pool[idx:idx+4]; idx += 4
        names = ' + '.join(f"<strong>{r['Pitcher']} {k_alt(r['K'])}</strong>" for r in grp)
        legs  = ' '.join(leg(r,i+1) for i,r in enumerate(grp))
        combos.append(('🎯',
            f"<strong>4-Leg Alt K: {names}</strong> {legs} "
            f"Four different arms · T1+ tier · O5+/O3.5 lines only.",
            'b-tier0','4-leg K'))
    # 3-leg
    if len(pool) - idx >= 3:
        grp = pool[idx:idx+3]; idx += 3
        names = ' + '.join(f"<strong>{r['Pitcher']} {k_alt(r['K'])}</strong>" for r in grp)
        legs  = ' '.join(leg(r,i+1) for i,r in enumerate(grp))
        combos.append(('⚡',
            f"<strong>3-Leg Alt K: {names}</strong> {legs} Three-arm K stack.",
            'b-tier1','3-leg K'))
    # 2-legs (consume the rest in pairs)
    pair_icons = ['⚾','💪','🔥','🎲']
    pi = 0
    while len(pool) - idx >= 2:
        grp = pool[idx:idx+2]; idx += 2
        names = ' + '.join(f"<strong>{r['Pitcher']} {k_alt(r['K'])}</strong>" for r in grp)
        legs  = ' '.join(leg(r,i+1) for i,r in enumerate(grp))
        combos.append((pair_icons[pi % len(pair_icons)],
            f"<strong>2-Leg Alt K: {names}</strong> {legs}",
            tier_badge(grp[0]),'2-leg K'))
        pi += 1

    blocks = []
    for icon, body, tier, tag in combos[:8]:
        blocks.append(
            f'  <div class="flag-row"><div class="icon">{icon}</div>'
            f'<div><span class="badge {tier}">{tag}</span> {body}</div></div>')

    return f'''<!-- COMBOS K -->
<section id="combos-k" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">⚡ Alt K Combos</div>
      <span class="game-tag">Tap to expand · T1+ arms only · randomized daily · each arm used once</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Alt-K combos built from <strong>T1 or better</strong> arms (SS K ≥ 4.5 → O5+/O3.5). Falls back to T2 only if short. <strong style="color:var(--good)">Randomized each day · no arm repeats.</strong></p>
{chr(10).join(blocks)}
  </div></div>
</section>
'''

# ============================================================
# 3. HRR COMBOS  (78.5%+ HRR only; random; each batter once)
# ============================================================
def _pct(s):
    try: return float(str(s).replace('%','').strip())
    except: return 0

def get_pitcher_era(pitcher_name):
    ss = SS_BY_NAME.get((pitcher_name or '').strip().lower())
    if ss:
        e = _pct(ss.get('ERA',''))
        if e: return e
    pn = (pitcher_name or '').strip().lower()
    for r in SP_PROJ:
        if (r.get('Pitcher') or '').strip().lower() == pn:
            e = _pct(r.get('ERA',''))
            if e: return e
    return 4.25

def compute_hrr(batter_name, team, pitcher_name):
    """Mirror of build_day46 HRR: 1 - P(no H)·P(no R)·P(no RBI)."""
    hit_row = HIT_BY_NAME.get((batter_name or '').lower()) or {}
    h1  = _pct(hit_row.get('1+ Hit', 0))
    rbi = _pct(hit_row.get('To Get RBI', 0))
    if h1 <= 0 or rbi <= 0: return 0.0
    era = get_pitcher_era(pitcher_name)
    park = get_park_for_batter(team)
    park_runs = parse_pct(park.get('Runs %')) if park else 0
    era_boost = max(0, (era - 4.25) * 1.5)
    run_prob  = min(60, rbi*0.8 + park_runs*0.3 + era_boost)
    hrr = (1 - (1-h1/100)*(1-run_prob/100)*(1-rbi/100)) * 100
    return round(min(99, max(0, hrr)), 1)

def build_combos_hrr():
    HRR_MIN = 78.5
    pool, seen = [], set()

    # From HR board (has Batter + Pitcher + Team)
    for r in HR_LB[:50]:
        nm = (r.get('Batter') or '').strip()
        if not nm or nm.lower() in seen: continue
        team = tn(r.get('Team','')); pit = r.get('Pitcher','')
        hrr = compute_hrr(nm, team, pit)
        if hrr >= HRR_MIN:
            seen.add(nm.lower())
            pool.append({'name':nm,'team':team,'pit':pit,'hrr':hrr,
                         'vuln':vuln_score(pit),'bats':r.get('Bats','')})

    # From hit board (catch batters not on HR board)
    for r in HIT:
        nm = f"{r.get('First Name','')} {r.get('Last Name','')}".strip()
        if not nm or nm.lower() in seen: continue
        bp = BP_BAT_BY_NAME.get(nm.lower()) or {}
        team = tn(bp.get('Team','')); opp_team = tn(bp.get('Opponent',''))
        pit = (SP_BY_TEAM.get(opp_team, {}) or {}).get('Pitcher','')
        hrr = compute_hrr(nm, team, pit)
        if hrr >= HRR_MIN:
            seen.add(nm.lower())
            pool.append({'name':nm,'team':team,'pit':pit,'hrr':hrr,
                         'vuln':vuln_score(pit),'bats':bp.get('BatterStand','')})

    random.shuffle(pool)

    def leg(b, num=None):
        v = f", vs {b['pit']} V{b['vuln']}" if b['pit'] else ''
        p = f"Leg {num}: " if num else ''
        return (f"{p}<strong>{b['name']}</strong> {hand_chip(b['bats'])} Ov 0.5 HRR "
                f"(HRR {b['hrr']:.0f}%{v})")

    combos = []
    idx = 0
    if len(pool) - idx >= 4:
        grp = pool[idx:idx+4]; idx += 4
        names = ' + '.join(f"<strong>{b['name']}</strong>" for b in grp)
        combos.append(('🏆', f"<strong>4-Leg HRR: {names}</strong> "
                       + ' '.join(leg(b,i+1) for i,b in enumerate(grp))
                       + " Four-batter HRR saturation · all ≥78.5%.", 'b-tier0','4-leg HRR'))
    if len(pool) - idx >= 3:
        grp = pool[idx:idx+3]; idx += 3
        names = ' + '.join(f"<strong>{b['name']}</strong>" for b in grp)
        combos.append(('🔥', f"<strong>3-Leg HRR: {names}</strong> "
                       + ' '.join(leg(b,i+1) for i,b in enumerate(grp)), 'b-tier1','3-leg HRR'))
    pair_icons = ['🎯','💥','⚡','🎲']; pi = 0
    while len(pool) - idx >= 2:
        grp = pool[idx:idx+2]; idx += 2
        names = ' + '.join(f"<strong>{b['name']}</strong>" for b in grp)
        combos.append((pair_icons[pi % len(pair_icons)],
                       f"<strong>2-Leg HRR: {names}</strong> "
                       + ' '.join(leg(b,i+1) for i,b in enumerate(grp)), 'b-tier1','2-leg HRR'))
        pi += 1

    blocks = []
    for icon, body, tier, tag in combos[:8]:
        blocks.append(
            f'  <div class="flag-row"><div class="icon">{icon}</div>'
            f'<div><span class="badge {tier}">{tag}</span> {body}</div></div>')
    if not blocks:
        blocks = ['  <div class="flag-row"><div class="icon">🎯</div><div>No batters cleared the 78.5% HRR threshold today.</div></div>']

    return f'''<!-- COMBOS HRR -->
<section id="combos-hrr" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">🎯 H+R+RBI Combos</div>
      <span class="game-tag">Tap to expand · HRR ≥ 78.5% only · randomized daily · each batter once</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Every leg is an <strong>Ov 0.5 H+R+RBI</strong>. Pool is filtered to batters with a <strong>78.5%+ HRR probability</strong>. <strong style="color:var(--good)">Randomized each day · no batter repeats.</strong></p>
{chr(10).join(blocks)}
  </div></div>
</section>
'''

# ============================================================
# 4. PARLAY ANCHORS  (Sweet-Spot DANGER batters only; random; each once)
# ============================================================
# ── COLOR HELPERS (shared convention, slate-wide consistency) ──
def c_vuln(v):
    v = int(v or 0)
    if v >= 50: return f'<span style="color:#ef4444;font-weight:700">V{v} 🔥</span>'
    if v >= 35: return f'<span style="color:#f59e0b;font-weight:700">V{v}</span>'
    return f'<span style="color:#64748b">V{v}</span>'

def c_iso(iso):
    if not iso: return ''
    s = f".{int(round(iso*1000)):03d}"
    if iso >= 0.250: return f'<span style="color:var(--good);font-weight:700">ISO {s}</span>'
    if iso >= 0.200: return f'<span style="color:var(--hot)">ISO {s}</span>'
    return f'<span style="color:#64748b">ISO {s}</span>'

def c_hrpct(p):
    if not p: return ''
    if p >= 18: return f'<span style="color:var(--good);font-weight:700">HR {p:.0f}%</span>'
    if p >= 12: return f'<span style="color:var(--hot)">HR {p:.0f}%</span>'
    return f'<span style="color:#64748b">HR {p:.0f}%</span>'

def c_zone(z):
    if not z: return ''
    if z >= 6: return f'<span style="color:var(--good);font-weight:700">⚡{z}</span>'
    if z >= 4: return f'<span style="color:var(--hot)">⚡{z}</span>'
    return f'<span style="color:#64748b">⚡{z}</span>'

def c_park(p):
    if p >= 10:  return f'<span style="color:var(--good);font-weight:700">+{p}% HR park</span>'
    if p >= 0:   return f'<span style="color:var(--hot)">+{p}% HR park</span>'
    if p >= -7:  return f'<span style="color:#64748b">{p}% HR park</span>'
    return f'<span style="color:var(--bad)">{p}% HR park</span>'

HOT_CHIP = ' <span style="color:var(--good);font-weight:700">HOT 🔥</span>'

# ── HOT STREAKS (from build_streaks export; runs before editorial) ──
def load_hot_streaks():
    try:
        hs = json.load(open(os.environ.get('HOT_STREAKS_FILE', 'hot_streaks.json'), encoding='utf-8'))
        return (set(n.lower() for n in hs.get('all', [])),
                set(n.lower() for n in hs.get('HR', [])))
    except Exception:
        return set(), set()

def _zone_num(z):
    m = re.search(r'(\d+)', str(z or ''))
    return int(m.group(1)) if m else 0

# ── PARLAY ANCHORS (rule-based, not pure random) ──
def get_danger_batters():
    """Sweet-Spot danger bats enriched with vuln, park HR%, ISO, zone, HR%, hot flags."""
    iso_re = re.compile(r'^(.*?)\s*\(ISO\s*\.(\d+)\)\s*$')
    hot_all, hot_hr = load_hot_streaks()
    out, seen = [], set()

    def enrich(nm, iso, pit, vuln, team):
        key = nm.lower()
        hit_row = HIT_BY_NAME.get(key) or {}
        hr_row  = HR_BY_NAME.get(key) or {}
        park    = get_park_for_batter(team) or {}
        return {
            'name': nm, 'iso': iso, 'pit': pit, 'vuln': vuln, 'team': team,
            'park_hr': parse_pct(park.get('HR %', '0')),
            'zone':    _zone_num(hr_row.get('Zone', '')),
            'hr_pct':  parse_pct(hit_row.get('To Hit HR', '0')),
            'h1':      hit_row.get('1+ Hit', '—'),
            'hot':     key in hot_all,
            'hot_hr':  key in hot_hr,
            'autopick': key in hot_hr,   # rule 7
        }

    # Pool 1: Sweet-Spot danger batters
    for sp in SS:
        pit = sp.get('Pitcher','')
        if not pit or pit == 'TBD': continue
        v = vuln_score(pit)
        opp = tn(sp.get('Opponent',''))
        for i in (1, 2, 3):
            raw = sp.get(f'DangerBatter{i}')
            if not raw: continue
            m = iso_re.match(str(raw).strip())
            nm = m.group(1).strip() if m else str(raw).strip()
            iso = float('0.' + m.group(2)) if m else None
            if not nm or nm.lower() in seen: continue
            seen.add(nm.lower())
            out.append(enrich(nm, iso, pit, v, opp))

    # Pool 2 (rule 7): any HR-streak batter not already in pool → auto-pick
    for hr_row in HR_LB:
        nm = (hr_row.get('Batter') or '').strip()
        if not nm or nm.lower() in seen: continue
        if nm.lower() not in hot_hr: continue
        team = tn(hr_row.get('Team',''))
        pit  = hr_row.get('Pitcher','')
        seen.add(nm.lower())
        b = enrich(nm, None, pit, vuln_score(pit), team)
        b['autopick'] = True
        out.append(b)

    return out

def build_parlays():
    pool = get_danger_batters()

    # Rules 1,2,3,5 — qualify (auto-picks bypass the filters)
    def qualifies(b):
        if b['autopick']:
            return True
        return (b['vuln'] >= 35
                and b['park_hr'] >= -7
                and (b['iso'] or 0) >= 0.200
                and b['hr_pct'] >= 10)
    qualified = [b for b in pool if qualifies(b)]
    random.shuffle(qualified)

    # Order so auto-picks + hot bats surface first, and every group can get a zone-4 leg
    qualified.sort(key=lambda b: (not b['autopick'], not b['hot'], -(b['zone'] or 0)))

    def leg(b, num=None):
        p = f"Leg {num}: " if num else ''
        chips = ', '.join(x for x in [c_iso(b['iso']), c_hrpct(b['hr_pct']), c_zone(b['zone'])] if x)
        vs = f", vs {b['pit']} {c_vuln(b['vuln'])}" if b['pit'] else ''
        hot = HOT_CHIP if b['hot'] else ''
        return f"{p}<strong>{b['name']}</strong> HR{hot} ({chips}{vs})"

    # Assemble parlays; enforce rule 4 (≥1 zone≥4 leg) and rule 6 (≥4 parlays with a hot bat)
    sizes = [4, 3, 2, 2, 2, 2, 2]   # up to 7 parlays
    parlays, used = [], set()
    hot_parlays = 0
    icons = ['🏆','🔥','⚡','💥','💣','🎲','🌋']

    avail = [b for b in qualified]
    def take(pred):
        for b in avail:
            if b['name'] not in used and pred(b):
                used.add(b['name']); avail.remove(b); return b
        return None

    for gi, size in enumerate(sizes):
        remaining = [b for b in avail if b['name'] not in used]
        if len(remaining) < size:
            break
        grp = []
        # rule 4: guarantee a zone≥4 leg
        z = take(lambda b: (b['zone'] or 0) >= 4)
        if z: grp.append(z)
        # rule 6: if we still need hot-carrying parlays, seed one hot bat
        need_hot = hot_parlays < 4
        if need_hot and not any(b['hot'] for b in grp):
            h = take(lambda b: b['hot'])
            if h: grp.append(h)
        # fill the rest
        while len(grp) < size:
            b = take(lambda b: True)
            if not b: break
            grp.append(b)
        if len(grp) < 2:
            break
        if any(b['hot'] for b in grp):
            hot_parlays += 1
        names = ' + '.join(f"<strong>{b['name']}</strong>" for b in grp)
        zone_ok = any((b['zone'] or 0) >= 4 for b in grp)
        tag = f"{len(grp)}-Leg Anchor"
        note = []
        if any(b['autopick'] for b in grp): note.append('contains an auto-pick HR streaker')
        if any(b['hot'] for b in grp):       note.append('hot bat included')
        if zone_ok:                          note.append('zone-4+ power leg')
        note_s = (' · '.join(note)).capitalize()
        parlays.append((icons[gi % len(icons)],
            f"<strong>{tag}: {names}</strong><br>"
            + '<br>'.join(leg(b, i+1) for i, b in enumerate(grp))
            + (f"<br><em>{note_s}.</em>" if note_s else '')))

    blocks = [
        f'  <div class="flag-row"><div class="icon">{icon}</div><div>{body}</div></div>'
        for icon, body in parlays
    ]
    if not blocks:
        blocks = ['  <div class="flag-row"><div class="icon">💣</div><div>No batters cleared the parlay-anchor rules today (V35+, park ≥ −7%, ISO ≥ .200, HR ≥ 10%).</div></div>']

    return f'''<!-- PARLAYS -->
<section id="parlays" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">💣 Parlay Anchors</div>
      <span class="game-tag">Tap to expand · rule-screened danger bats · randomized daily · each used once</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
  <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Screened by rule, not pure chance: <strong>V35+</strong>, park HR <strong>≥ −7%</strong>, <strong>ISO ≥ .200</strong>, <strong>HR ≥ 10%</strong>, each parlay carries a <strong style="color:var(--hot)">zone-4+</strong> power leg, and HR-streak bats are <strong style="color:var(--good)">auto-picked</strong>. <strong style="color:var(--good)">Randomized daily · no repeats.</strong></p>
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
