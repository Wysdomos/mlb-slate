"""
build_streaks.py  —  Hot Streaks page builder
Reads:   day_data.json  (DATA_FILE env var)
Fetches: MLB Stats API game logs for slate players
Writes:  streaks.html   (STREAKS_FILE env var)

Streak types & minimums:
  💣 HR   — HR in 2+ consecutive games
  🔥 HRR  — H+R+RBI ≥1 in 3+ consecutive games
  ⚾ K    — 6+ Ks in 3+ consecutive starts (pitchers)
  🎯 HIT  — hit in 4+ consecutive games
  💥 2+H  — 2+ hits in 2+ consecutive games
  💰 RBI  — RBI in 4+ consecutive games
  🔻 HA   — 6+ hits ALLOWED in 3+ consecutive starts (pitchers, fade)
"""

import json, os, time, re, urllib.request, urllib.parse, urllib.error
from datetime import date

# ── CONFIG ────────────────────────────────────────────────────────
DATA_FILE    = os.environ.get('DATA_FILE',    'day_data.json')
STREAKS_FILE = os.environ.get('STREAKS_FILE', 'streaks.html')
SEASON       = 2026
GAMES_BACK   = 10   # game logs to inspect per player
K_THRESHOLD  = 6    # minimum Ks/start to count for K streak
HA_THRESHOLD = 6    # minimum hits ALLOWED/start to count for Hits Allowed streak

MINIMUMS = {'HR':2,'HRR':3,'K':3,'HIT':4,'TWO':2,'RBI':4,'HAL':3}

TYPE_CFG = {
    'HR':  {'emoji':'💣','label':'HR STREAK', 'color':'#ef4444'},
    'HRR': {'emoji':'🔥','label':'HRR STREAK','color':'#06b6d4'},
    'K':   {'emoji':'⚾','label':'K STREAK',  'color':'#f97316'},
    'HIT': {'emoji':'🎯','label':'HIT STREAK','color':'#22c55e'},
    'TWO': {'emoji':'💥','label':'2+H STREAK','color':'#a855f7'},
    'RBI': {'emoji':'💰','label':'RBI STREAK','color':'#f59e0b'},
    'HAL': {'emoji':'🔻','label':'HA STREAK', 'color':'#e11d48'},
}
TYPE_ORDER = {'HR':0,'HRR':1,'K':2,'HAL':3,'HIT':4,'TWO':5,'RBI':6}

# ── LOAD DATA ─────────────────────────────────────────────────────
DATA    = json.load(open(DATA_FILE, encoding='utf-8'))
HIT     = DATA.get('Hit_Probabilities', [])
HR_LB   = DATA.get('HR_Leaderboard', [])
SP_PROJ = DATA.get('SP_Projections', [])
PARKS   = DATA.get('Park_Factors', [])
BP_BAT  = DATA.get('BP_Batters', [])
BP_PIT  = DATA.get('BP_Pitchers', [])
SS      = DATA.get('Sweet_Spot_Slate', [])
BP_GAM  = DATA.get('BP_Games', [])

TEAM_FIX = {'WSH':'WAS','AZ':'ARI','CWS':'CHW','TB ':'TB','SF ':'SF','SD ':'SD','KC ':'KC'}
def tn(t): return TEAM_FIX.get((t or '').strip(),(t or '').strip())

def _sf(v, d=0.0):
    try: return float(str(v).replace('%','').replace('+','').strip())
    except: return d

# ── INDEXES ──────────────────────────────────────────────────────
SP_BY_TEAM = {tn(r.get('Team','')): r for r in SP_PROJ if r.get('Team')}

BP_BAT_BY_NAME = {}
for r in BP_BAT:
    nm = (r.get('FullName') or '').strip().lower()
    if nm: BP_BAT_BY_NAME[nm] = r

HIT_BY_NAME = {}
for r in HIT:
    nm = f"{r.get('First Name','')} {r.get('Last Name','')}".strip().lower()
    if nm: HIT_BY_NAME[nm] = r

PARK_BY_TEAM = {}
for r in PARKS:
    game = r.get('Game','')
    for tok in game.replace('@',' ').split():
        t = tn(tok.strip())
        if t and len(t) == 3 and t.isalpha():
            if t not in PARK_BY_TEAM:
                PARK_BY_TEAM[t] = r

# ── BATTER ISO + ZONE LOOKUPS ──────────────────────────────────────────────
HR_BY_NAME_S = {(r.get('Batter') or '').strip().lower(): r for r in HR_LB if r.get('Batter')}
_ISO_RE = re.compile(r'\(ISO\s*\.?(\d+)\)')

def get_batter_iso(name):
    nm = (name or '').strip().lower()
    for sp in SS:
        for i in (1, 2, 3):
            raw = str(sp.get(f'DangerBatter{i}') or '')
            if nm in raw.lower():
                m = _ISO_RE.search(raw)
                if m:
                    return float('0.' + m.group(1))
    return None

def get_batter_zone(name):
    r = HR_BY_NAME_S.get((name or '').strip().lower())
    if not r:
        return 0
    z = str(r.get('Zone') or '')
    m = re.search(r'(\d+)', z)
    return int(m.group(1)) if m else 0

# VulnScore lives in Sweet_Spot_Slate (NOT BP_Pitchers) — key by pitcher name
VULN_BY_PIT = {}
for r in SS:
    nm = (r.get('Pitcher') or '').strip().lower()
    if nm: VULN_BY_PIT[nm] = r

# ── MLB STATS API ─────────────────────────────────────────────────
MLB_API          = 'https://statsapi.mlb.com/api/v1'
PLAYER_CACHE     = 'mlb_players_cache.json'
_player_index    = {}

def load_player_index():
    global _player_index
    if os.path.exists(PLAYER_CACHE):
        try:
            _player_index = json.load(open(PLAYER_CACHE))
            print(f'[streaks] Player index: {len(_player_index)} from cache')
            return
        except: pass
    print('[streaks] Fetching MLB player list...')
    try:
        params = urllib.parse.urlencode({'season': SEASON, 'gameType': 'R'})
        url = f'{MLB_API}/sports/1/players?{params}'
        with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for p in data.get('people', []):
            full = (p.get('fullName') or '').strip().lower()
            if full: _player_index[full] = p['id']
        json.dump(_player_index, open(PLAYER_CACHE, 'w'))
        print(f'[streaks] Cached {len(_player_index)} players')
    except Exception as e:
        print(f'[streaks] Player index error: {e}')

def player_id(name):
    return _player_index.get((name or '').strip().lower())

def fetch_logs(pid, group='hitting'):
    try:
        params = urllib.parse.urlencode({
            'stats': 'gameLog', 'season': SEASON,
            'group': group, 'gameType': 'R'
        })
        url = f'{MLB_API}/people/{pid}/stats?{params}'
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        stats = data.get('stats', [])
        if not stats: return []
        splits = stats[0].get('splits', [])
        splits.sort(key=lambda s: s.get('date', ''), reverse=True)
        return splits[:GAMES_BACK]
    except: return []

# ── STREAK DETECTION ──────────────────────────────────────────────
def count_streak(splits, fn):
    n = 0
    for s in splits:
        if fn(s.get('stat',{})): n += 1
        else: break
    return n

def dot_list(splits, fn, size=5):
    out = [bool(fn(s.get('stat',{}))) for s in splits[:size]]
    while len(out) < size: out.append(False)
    return out

BATTER_CHECKS = {
    'HR':  lambda st: int(st.get('homeRuns',0) or 0) > 0,
    'HRR': lambda st: (int(st.get('hits',0) or 0) +
                       int(st.get('runs',0) or 0) +
                       int(st.get('rbi',0) or 0)) >= 1,
    'HIT': lambda st: int(st.get('hits',0) or 0) > 0,
    'TWO': lambda st: int(st.get('hits',0) or 0) >= 2,
    'RBI': lambda st: int(st.get('rbi',0) or 0) > 0,
}
def compute_hrr(h1, rbi_pct, park_r, era=4.25):
    """HRR% (H+R+RBI ≥1 probability) — matches Hits Board formula."""
    era_boost = max(0, (era - 4.25) * 1.5)
    run_prob  = min(60, rbi_pct*0.8 + park_r*0.3 + era_boost)
    hrr = 1 - (1-h1/100)*(1-run_prob/100)*(1-rbi_pct/100)
    return hrr * 100

K_CHECK  = lambda st: int(st.get('strikeOuts',0) or 0) >= K_THRESHOLD
HAL_CHECK = lambda st: int(st.get('hits',0) or 0) >= HA_THRESHOLD

# ── CONTEXT HELPERS ───────────────────────────────────────────────
def get_vuln(pitcher_name):
    v = VULN_BY_PIT.get((pitcher_name or '').strip().lower(), {})
    try: return int(float(v.get('VulnScore',0) or 0))
    except: return 0

def get_park_runs(team):
    park = PARK_BY_TEAM.get(tn(team), {})
    return _sf(park.get('Runs %','0'))

def platoon_edge(throws, bats):
    t = (throws or '').upper(); b = (bats or '').upper()
    return b == 'S' or (bool(t) and bool(b) and t != b)

def hand_span(h, size=12):
    c = {'L':'#3b82f6','R':'#ef4444','S':'#a855f7'}.get((h or '').upper().strip(),'#94a3b8')
    return f'<span style="color:{c};font-weight:700;font-size:{size}px">{(h or "").strip().upper()}</span>'

def k_alt_line(k_proj):
    try: k = float(k_proj)
    except: return 'O 2.5'
    if k >= 5.0: return 'O 5+'
    if k >= 4.5: return 'O 3.5'
    return 'O 2.5'

# ── INSIGHT GENERATION ───────────────────────────────────────────
def batter_insight(nm, stype, streak, opp_sp, vuln, park_r, h1, edge):
    openers = {
        'HR':  f"{nm} has gone deep in {streak} straight game{'s' if streak>1 else ''}",
        'HRR': f"{nm} has contributed H+R+RBI in {streak} consecutive game{'s' if streak>1 else ''}",
        'HIT': f"{nm} has recorded a hit in {streak} consecutive game{'s' if streak>1 else ''}",
        'TWO': f"{nm} has gone multi-hit in {streak} consecutive game{'s' if streak>1 else ''}",
        'RBI': f"{nm} has driven in a run in {streak} straight game{'s' if streak>1 else ''}",
    }
    parts = [openers.get(stype, f"{nm} is on a {streak}-game streak")]
    if opp_sp:
        if vuln >= 50: parts.append(f"and draws one of today's most vulnerable arms in {opp_sp} (V{vuln} 🔥)")
        elif vuln >= 32: parts.append(f"facing a moderately vulnerable {opp_sp} (V{vuln})")
        else: parts.append(f"but faces a tough arm in {opp_sp} (V{vuln})")
    if park_r >= 15: parts.append(f"The volcano park (+{int(park_r)}% runs 🌋) amplifies every at-bat.")
    elif park_r >= 8: parts.append(f"A run-friendly park (+{int(park_r)}%) lifts the floor.")
    elif park_r <= -10: parts.append(f"The run-suppressor environment ({int(park_r)}%) is a headwind.")
    if edge: parts.append("Platoon edge is active.")
    if h1 >= 65: parts.append(f"Leads the slate at {h1:.0f}% hit probability today.")
    elif h1 >= 60: parts.append(f"Strong {h1:.0f}% hit probability backs continuation.")
    elif 0 < h1 < 50: parts.append(f"Below-average {h1:.0f}% hit probability is a caution flag.")
    return ' '.join(parts)

def pitcher_insight(nm, streak, opp_team, opp_k_pct, k_proj, alt_line):
    parts = [f"{nm} has recorded {K_THRESHOLD}+ Ks in {streak} straight start{'s' if streak>1 else ''}"]
    if opp_k_pct >= 24: parts.append(f"The {opp_team} lineup punches out {opp_k_pct:.1f}% of the time — elite K environment.")
    elif opp_k_pct >= 21: parts.append(f"The {opp_team} lineup is K-vulnerable at {opp_k_pct:.1f}%.")
    else: parts.append(f"The {opp_team} lineup is disciplined ({opp_k_pct:.1f}% K rate) — tougher draw today.")
    parts.append(f"Projecting {k_proj} Ks — {alt_line} is the target line.")
    return ' '.join(parts)

def calc_verdict(vuln, park_r, edge, h1, stype, opp_k_pct=0, k_proj=0):
    if stype == 'K':
        sc = (2 if opp_k_pct>=24 else 1 if opp_k_pct>=21 else 0) + \
             (1 if k_proj>=7 else -1 if k_proj<5 else 0)
        return 'continue' if sc>=2 else 'neutral' if sc>=1 else 'fade'
    sc = (2 if vuln>=50 else 1 if vuln>=32 else 0) + \
         (2 if park_r>=15 else 1 if park_r>=8 else -2 if park_r<=-10 else 0) + \
         (1 if edge else 0) + \
         (1 if h1>=65 else -1 if 0<h1<50 else 0) + \
         (-1 if stype=='HR' and vuln<30 else 0)
    return 'continue' if sc>=3 else 'fade' if sc<=0 else 'neutral'

# ── HTML RENDERER ─────────────────────────────────────────────────
CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{background:#07090f;color:#dde3f0;min-height:100vh}
body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.page-header{position:sticky;top:0;z-index:100;background:rgba(7,9,15,.97);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid rgba(255,255,255,.05)}
.header-row{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;padding:calc(env(safe-area-inset-top) + 18px) 16px 0}
.header-date{font-size:11px;color:#4a5568;text-align:right;line-height:1.5;flex-shrink:0;padding-top:2px;font-weight:600}
.back-link{color:#6366f1;font-size:13px;font-weight:600;text-decoration:none;flex-shrink:0}
.header-title{font-size:20px;font-weight:900;letter-spacing:-.5px;background:linear-gradient(90deg,#f97316,#ef4444,#f97316);background-size:200%;-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header-sub{font-size:10.5px;color:#4ade80;margin-top:1px}
.filter-row{display:flex;gap:5px;overflow-x:auto;padding:9px 16px 11px;-webkit-overflow-scrolling:touch}
.filter-row::-webkit-scrollbar{display:none}
.filter-btn{{
  border:1.5px solid var(--type-color,#64748b);
  color:var(--type-color,#94a3b8);
  background:transparent;
  padding:6px 14px;border-radius:20px;font-size:13px;font-weight:700;
  cursor:pointer;transition:all .2s;white-space:nowrap;
}}
.filter-btn.active{{
  background:var(--type-color,#22c55e);
  color:#000;
  border-color:var(--type-color,#22c55e);
}}
.filter-btn:not(.active):hover{{background:color-mix(in srgb,var(--type-color) 15%,transparent)}}
.streak-row{border-bottom:1px solid rgba(255,255,255,.04);padding:10px 14px 10px 13px}
.streak-row:nth-child(even){background:rgba(255,255,255,.012)}
.row-top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px;margin-bottom:5px}
.type-badge{font-size:10px;font-weight:800;letter-spacing:.6px;padding:2px 6px;border-radius:3px}
.player-row{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px;margin-bottom:5px}
.player-name{font-size:15.5px;font-weight:800;letter-spacing:-.2px}
.team-badge{font-size:11px;font-weight:700;color:#64748b;background:rgba(255,255,255,.06);padding:1px 6px;border-radius:4px}
.dots-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.dots{display:flex;gap:3px;align-items:center}
.dot{display:inline-block;width:10px;height:10px;border-radius:2px}
.dot-label{font-size:10px;color:#4ade80;margin-left:2px}
.streak-count{font-size:11.5px;font-weight:800}
.min-badge{font-size:10px;font-weight:700;padding:1px 6px;border-radius:3px;color:#4ade80;background:#052e16}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:7px}
.chip{font-size:11px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.07);border-radius:5px;padding:2px 7px;color:#94a3b8}
.dim{color:#8b9ab0}
.insight{font-size:11.5px;line-height:1.65;color:#dde3f0;margin:0 0 7px}
.verdict{display:inline-flex;align-items:center;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700}
.footer{padding:10px 0 80px;text-align:center;font-size:10.5px;color:#4ade80}
@supports(padding-bottom:env(safe-area-inset-bottom)){.footer{padding-bottom:calc(60px + env(safe-area-inset-bottom))}}
"""

VERDICT_CFG = {
    'continue': {'icon':'✅','label':'Continue','fg':'#4ade80','bg':'#052e16'},
    'fade':     {'icon':'⚠️','label':'Fade',    'fg':'#fca5a5','bg':'#2d0a0a'},
    'neutral':  {'icon':'➡️','label':'Neutral', 'fg':'#94a3b8','bg':'#0f1829'},
}

def streak_iso_chip(iso):
    """Colored ISO chip — matches slate-wide convention (≥.280 red, ≥.250 orange, ≥.200 green)."""
    if not iso: return ''
    col = '#ef4444' if iso>=0.280 else ('#f59e0b' if iso>=0.250 else ('#22c55e' if iso>=0.200 else '#64748b'))
    s = f'.{int(round(iso*1000)):03d}'
    return f'<span class="chip"><span class="dim">ISO </span><span style="color:{col};font-weight:700">{s}</span></span>'

def streak_zone_chip(zone):
    """Colored Zone chip — ≥6 green, ≥4 orange, else gray."""
    if not zone: return ''
    col = '#22c55e' if zone>=6 else ('#f59e0b' if zone>=4 else '#64748b')
    return f'<span class="chip"><span class="dim">Zone </span><span style="color:{col};font-weight:700">⚡{zone}</span></span>'


def render_row(s, idx):
    tc = TYPE_CFG[s['type']]
    vc = VERDICT_CFG[s['verdict']]
    color = tc['color']
    is_pitcher = s['type'] in ('K','HAL')
    is_hal     = s['type'] == 'HAL'

    # dots
    dots_html = ''
    for gi, fired in enumerate(s['dots']):
        in_streak = gi < s['streak']
        if fired:
            glow = f'box-shadow:0 0 5px {color}80;' if in_streak else ''
            opacity = '1' if in_streak else '.35'
            dots_html += f'<span class="dot" style="background:{color};opacity:{opacity};{glow}"></span>'
        else:
            dots_html += '<span class="dot" style="background:rgba(255,255,255,.07)"></span>'

    label_word = 'starts' if is_pitcher else 'G'
    min_badge  = ''
    streak_label = f'{s["streak"]} {label_word} streak'

    # context chips
    if is_pitcher:
        pk_color  = '#4ade80' if s['park_r']>=8 else '#f87171' if s['park_r']<=-10 else '#64748b'
        pk_str    = ('+' if s['park_r']>0 else '') + str(int(s['park_r'])) + '%' + (' 🌋' if s['park_r']>=25 else '')
        if is_hal:
            chips = (
                f'<span class="chip"><span class="dim">vs </span><strong style="color:#dde3f0">{s["opp"]}</strong></span>'
                f'<span class="chip" style="background:{color}15;border-color:{color}30">'
                f'<span class="dim">Hits/start </span><span style="color:{color};font-weight:800">{s.get("hits_avg",0)}</span></span>'
                f'<span class="chip"><span class="dim">Park </span><span style="color:{pk_color};font-weight:700">{pk_str}</span></span>'
            )
        else:
            ok_color  = '#ef4444' if s['opp_k_pct']>=24 else '#f59e0b' if s['opp_k_pct']>=21 else '#64748b'
            kp_color  = '#4ade80' if s['k_proj']>=7 else '#fbbf24' if s['k_proj']>=5 else '#94a3b8'
            chips = (
                f'<span class="chip"><span class="dim">vs </span><strong style="color:#dde3f0">{s["opp"]}</strong>'
                f' <span class="dim">K% </span><span style="color:{ok_color};font-weight:700">{s["opp_k_pct"]:.1f}%</span></span>'
                f'<span class="chip"><span class="dim">Proj </span><span style="color:{kp_color};font-weight:700">{s["k_proj"]}</span></span>'
                f'<span class="chip" style="background:{color}15;border-color:{color}30">'
                f'<span class="dim">Alt </span><span style="color:{color};font-weight:800">{s["alt_line"]}</span></span>'
                f'<span class="chip"><span class="dim">Park </span><span style="color:{pk_color};font-weight:700">{pk_str}</span></span>'
            )
        name_hand = f'{s["player"]} {hand_span(s.get("throws",""))}'
    else:
        vc_color  = '#ef4444' if s['vuln']>=50 else '#f59e0b' if s['vuln']>=32 else '#64748b'
        fire      = ' 🔥' if s['vuln']>=50 else ''
        pk_color  = '#4ade80' if s['park_r']>=8 else '#f87171' if s['park_r']<=-10 else '#64748b'
        pk_str    = ('+' if s['park_r']>0 else '') + str(int(s['park_r'])) + '%' + (' 🌋' if s['park_r']>=25 else '')
        h1_color  = '#4ade80' if s['h1']>=65 else '#fbbf24' if s['h1']>=60 else '#94a3b8'
        edge_color= '#4ade80' if s['edge'] else '#4a5568'
        edge_txt  = 'EDGE ✓' if s['edge'] else 'same'
        chips = (
            f'<span class="chip"><span class="dim">vs </span><strong style="color:#dde3f0">{s["opp_sp"] or "—"}</strong>'
            f' {hand_span(s.get("sp_throws",""))}'
            f' <span style="color:{vc_color};font-weight:700">V{s["vuln"]}{fire}</span></span>'
            f'<span class="chip"><span class="dim">Park </span><span style="color:{pk_color};font-weight:700">{pk_str}</span></span>'
            f'<span class="chip"><span class="dim">Platoon </span><span style="color:{edge_color};font-weight:700">{edge_txt}</span></span>'
            f'<span class="chip"><span class="dim">1+H </span><span style="color:{h1_color};font-weight:700">{s["h1"]:.0f}%</span></span>'
            + streak_iso_chip(s.get('iso'))
            + streak_zone_chip(s.get('zone'))
        )
        if s['type'] == 'HRR' and s.get('rbi_pct'):
            chips += f'<span class="chip"><span class="dim">RBI% </span><span style="color:#fbbf24;font-weight:700">{s["rbi_pct"]:.0f}%</span></span>'
        name_hand = f'{s["player"]} {hand_span(s.get("bats",""))}'

    # HRR% tag (Hits Board cut: ≥82 green, ≥75 orange) — only ≥78.5
    hrr_tag = ''
    if s['type']=='HRR' and s.get('hrr_pct',0) >= 78.5:
        hp = s['hrr_pct']
        hc = '#22c55e' if hp>=82 else '#f59e0b'
        hrr_tag = f'<span class="hrr-tag" style="color:{hc};border:1px solid {hc}55;background:{hc}15">{hp:.0f}% HRR</span>'

    bg = 'rgba(255,255,255,.012)' if idx % 2 == 1 else 'transparent'

    return f'''<div class="streak-row" data-type="{s['type']}" style="border-left:3px solid {color};background:{bg}">
  <div class="row-top">
    <span class="type-badge" style="color:{color};background:{color}18">{tc['emoji']} {tc['label']}</span>
    {hrr_tag}
  </div>
  <div class="player-row">
    <span class="player-name">{name_hand}</span>
    <span class="team-badge">{s['team']}</span>
  </div>
  <div class="dots-row">
    <div class="dots">{dots_html}<span class="dot-label">last 5 {label_word}</span></div>
    <span class="streak-count" style="color:{color}">{streak_label}</span>
  </div>
  <div class="chips">{chips}</div>
  <p class="insight">{s['insight']}</p>
</div>'''

def render_html(streaks, today, slate_label=''):
    counts = {}
    for s in streaks: counts[s['type']] = counts.get(s['type'],0)+1
    streaks.sort(key=lambda s: (TYPE_ORDER.get(s['type'],9), -s['streak']))

    cat_order  = [k for k in ['HR','HRR','K','HAL','HIT','TWO','RBI'] if counts.get(k,0)]
    # Default-active tab = the category with the most streaks (so page lands full, not empty)
    first_type = max(cat_order, key=lambda k: counts.get(k,0)) if cat_order else ''
    tabs = []
    for k in cat_order:
        tc = TYPE_CFG[k]
        tabs.append((k, f"{tc['emoji']} {tc['label'].split()[0]} ({counts[k]})"))

    def _tab_btn(k, label):
        c = TYPE_CFG[k]["color"]
        active = (k == first_type)
        if active:
            style = f'--type-color:{c};background:{c};color:#000;border-color:{c}'
            cls = 'filter-btn active'
        else:
            style = f'--type-color:{c};background:transparent;color:{c};border-color:{c}'
            cls = 'filter-btn'
        return f'<button class="{cls}" onclick="filter(\'{k}\',this)" data-color="{c}" style="{style}">{label}</button>'
    tab_html = ''.join(_tab_btn(k, label) for k, label in tabs)

    rows_html = ''.join(render_row(s,i) for i,s in enumerate(streaks))
    if not rows_html:
        rows_html = '<div style="text-align:center;padding:48px 16px;color:#475569;font-size:14px">No active streaks found for today\'s slate.</div>'

    return f'''<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>🔥 Hot Streaks · {today}</title>
<style>{CSS}
.streak-guide{{margin:0;background:rgba(255,255,255,.04);border-bottom:1px solid rgba(255,255,255,.07)}}
.streak-guide-summary{{padding:10px 16px;font-size:12px;font-weight:700;color:#94a3b8;
  cursor:pointer;list-style:none;user-select:none;}}
.streak-guide-summary::-webkit-details-marker{{display:none}}
.streak-guide-body{{padding:0 16px 14px;font-size:12px;color:#94a3b8;line-height:1.6}}
.streak-guide-body p{{margin:0 0 8px}}
.guide-table{{width:100%;border-collapse:collapse;font-size:12px}}
.guide-table td{{padding:3px 6px;border-bottom:1px solid rgba(255,255,255,.05)}}
.guide-table td:first-child{{white-space:nowrap;width:100px;color:#dde3f0}}

.page-fab{{position:fixed;right:16px;z-index:200;width:48px;height:48px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;font-size:24px;text-decoration:none;
  border:1px solid rgba(255,255,255,0.18);box-shadow:0 4px 16px rgba(0,0,0,.4);
  transition:transform .2s;-webkit-tap-highlight-color:transparent;}}
.page-fab:active{{transform:scale(0.92);}}
.fab-home{{bottom:80px;background:rgba(30,40,60,.92);}}
.fab-kreport{{bottom:138px;background:linear-gradient(135deg,#0a84ff,#0040dd);}}
.collapse-tag{{margin-left:auto;color:#4ade80;font-size:11px;font-weight:700;border:1px solid #4ade8055;background:#4ade8015;border-radius:6px;padding:2px 8px}}
.collapse-tag::after{{content:"expand ▼"}}
.streak-guide[open] .collapse-tag::after{{content:"collapse ▲"}}
.hrr-tag{{font-size:11px;font-weight:800;border-radius:6px;padding:2px 8px;margin-left:auto}}
.streak-guide-summary{{display:flex;align-items:center}}
.theme-toggle-fab{{position:fixed;bottom:22px;right:16px;z-index:200;width:48px;height:48px;
  border-radius:50%;background:rgba(30,40,60,.92);color:#fff;border:1px solid rgba(255,255,255,0.18);
  display:flex;align-items:center;justify-content:center;font-size:20px;cursor:pointer;
  box-shadow:0 4px 16px rgba(0,0,0,.4);transition:transform .2s;-webkit-tap-highlight-color:transparent}}
.theme-toggle-fab:active{{transform:scale(0.92)}}
/* ---- LIGHT MODE ---- */
[data-theme="light"] html,[data-theme="light"] body{{background:#f1f5f3;color:#0f1a16}}
[data-theme="light"] .page-header{{background:rgba(241,245,243,.95);border-bottom:1px solid rgba(15,23,42,.08)}}
[data-theme="light"] .header-date{{color:#5b6b65}}
[data-theme="light"] .header-sub{{color:#15803d}}
[data-theme="light"] .streak-row{{border-bottom:1px solid rgba(15,23,42,.06)}}
[data-theme="light"] .streak-row:nth-child(even){{background:rgba(15,23,42,.02)}}
[data-theme="light"] .team-badge{{color:#5b6b65;background:rgba(15,23,42,.06)}}
[data-theme="light"] .chip{{background:rgba(15,23,42,.04);border:1px solid rgba(15,23,42,.10);color:#5b6b65}}
[data-theme="light"] .chip strong{{color:#0f1a16 !important}}
[data-theme="light"] .dim{{color:#6b7a72}}
[data-theme="light"] .insight{{color:#1f2a26}}
[data-theme="light"] .dot-label{{color:#15803d}}
[data-theme="light"] .footer{{color:#15803d}}
[data-theme="light"] .streak-guide{{background:rgba(15,23,42,.03);border-bottom:1px solid rgba(15,23,42,.08)}}
[data-theme="light"] .streak-guide-summary{{color:#2c3935}}
[data-theme="light"] .streak-guide-body{{color:#5b6b65}}
[data-theme="light"] .guide-table td{{border-bottom:1px solid rgba(15,23,42,.06)}}
[data-theme="light"] .guide-table td:first-child{{color:#0f1a16}}
[data-theme="light"] .back-link{{color:#4f46e5}}
[data-theme="light"] .theme-toggle-fab{{background:rgba(255,255,255,.9);color:#0f1a16;border-color:rgba(15,23,42,.15)}}
[data-theme="light"] .fab-home{{background:rgba(255,255,255,.9) !important;color:#0f1a16}}
</style>
</head>
<body>
<div class="page-header">
  <div class="header-row">
    <div style="display:flex;align-items:center;gap:10px">
      <a href="index.html" class="back-link">← Daily Slate</a>
      <div>
        <div class="header-title">🔥 Hot Streaks</div>
        <div class="header-sub">{len(streaks)} active streak{'s' if len(streaks)!=1 else ''}</div>
      </div>
    </div>
    <div class="header-date">{today}<br>{slate_label}</div>
  </div>
  <details class="streak-guide" open>
    <summary class="streak-guide-summary">📖 How The Streaks Work<span class="collapse-tag"></span></summary>
    <div class="streak-guide-body">
      <p><strong>What is a streak?</strong> A player who has hit the qualifying stat in back-to-back or consecutive games — not just good recent form, but an active run confirmed by official game logs.</p>
      <table class="guide-table">
        <tr><td>💣 <strong>HR</strong></td><td>Home run in <strong>≥ 2</strong> consecutive games</td></tr>
        <tr><td>🔥 <strong>HRR</strong></td><td>H+R+RBI ≥ 1 in <strong>≥ 3</strong> consecutive games</td></tr>
        <tr><td>⚾ <strong>K</strong></td><td>Pitcher recorded <strong>6+</strong> K in <strong>≥ 3</strong> consecutive starts</td></tr>
        <tr><td>🎯 <strong>HIT</strong></td><td>At least 1 hit in <strong>≥ 4</strong> consecutive games</td></tr>
        <tr><td>💥 <strong>2+H</strong></td><td>Multi-hit game in <strong>≥ 2</strong> consecutive games</td></tr>
        <tr><td>💰 <strong>RBI</strong></td><td>At least 1 RBI in <strong>≥ 4</strong> consecutive games</td></tr>
        <tr><td>🔻 <strong>HA</strong></td><td>Pitcher allowed <strong>6+</strong> hits in <strong>≥ 3</strong> consecutive starts (fade)</td></tr>
      </table>
      <p style="margin-top:8px;font-size:12px;color:#4ade80">Tap a category tab or swipe a card left / right to move between streak types.</p>
    </div>
  </details>
  <div class="filter-row">{tab_html}</div>
</div>
<div id="streak-list">{rows_html}</div>
<div class="footer">Tap a tab or swipe a card to navigate · MLB Stats API</div>
<script>
function filter(type,btn){{
  document.querySelectorAll('.filter-btn').forEach(b=>{{
    b.classList.remove('active');
    var c=b.getAttribute('data-color')||'#64748b';
    b.style.background='transparent';b.style.color=c;b.style.borderColor=c;
  }});
  btn.classList.add('active');
  var ac=btn.getAttribute('data-color')||'#22c55e';
  btn.style.background=ac;btn.style.color='#000';btn.style.borderColor=ac;
  document.querySelectorAll('.streak-row').forEach(r=>{{
    r.style.display=(r.dataset.type===type)?'':'none';
  }});
}}
// init: show only the first category on load (no ALL tab)
(function(){{
  var t='{first_type}';
  if(!t)return;
  document.querySelectorAll('.streak-row').forEach(function(r){{
    r.style.display=(r.dataset.type===t)?'':'none';
  }});
}})();
// Touch swipe to navigate between category tabs
(function(){{
  var el=document.getElementById('streak-list')||document.body;
  var sx=0,sy=0;
  el.addEventListener('touchstart',function(e){{sx=e.touches[0].clientX;sy=e.touches[0].clientY;}},{{passive:true}});
  el.addEventListener('touchend',function(e){{
    var dx=e.changedTouches[0].clientX-sx, dy=e.changedTouches[0].clientY-sy;
    if(Math.abs(dx)>Math.abs(dy)&&Math.abs(dx)>45){{
      var btns=Array.from(document.querySelectorAll('.filter-btn'));
      var ai=btns.findIndex(function(b){{return b.classList.contains('active');}});
      var ni=dx<0?Math.min(ai+1,btns.length-1):Math.max(ai-1,0);
      if(ni!==ai)btns[ni].click();
    }}
  }},{{passive:true}});
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
<a class="page-fab fab-home" href="index.html" title="Daily Slate">⚾️</a>
<a class="page-fab fab-kreport" href="k-report.html" title="Safe K Report">📰</a>
</body>
</html>'''

# ── MAIN BUILD ────────────────────────────────────────────────────
def build():
    today = date.today().strftime('%B %-d, %Y')
    _weekday = date.today().strftime('%A')
    _games   = len(BP_GAM) if BP_GAM else len(SP_PROJ)
    slate_label = f'{_games}-Game {_weekday} Slate'
    load_player_index()

    streaks = []

    # ── BATTER STREAKS ────────────────────────────────────────────
    seen_batters = set()
    batter_names = []
    for r in HIT:
        nm = f"{r.get('First Name','')} {r.get('Last Name','')}".strip()
        if nm and nm not in seen_batters:
            batter_names.append(nm); seen_batters.add(nm)
    for r in HR_LB[:20]:
        nm = (r.get('Batter') or '').strip()
        if nm and nm not in seen_batters:
            batter_names.append(nm); seen_batters.add(nm)

    print(f'[streaks] Checking {len(batter_names)} batters...')
    for nm in batter_names:
        pid = player_id(nm)
        if not pid:
            print(f'  [skip] {nm} — no MLB ID'); time.sleep(0.2); continue
        splits = fetch_logs(pid, 'hitting')
        if not splits:
            print(f'  [skip] {nm} — no logs'); time.sleep(0.2); continue

        # context
        bp       = BP_BAT_BY_NAME.get(nm.lower(), {})
        bats     = bp.get('BatterStand','') or bp.get('Bats','')
        team     = tn(bp.get('Team','') or '')
        opp_team = tn(bp.get('Opponent','') or '')
        sp_row   = SP_BY_TEAM.get(opp_team, {})
        opp_sp   = sp_row.get('Pitcher','')
        sp_throws= sp_row.get('PitcherHand','')
        vuln     = get_vuln(opp_sp)
        park_r   = get_park_runs(team)
        edge     = platoon_edge(sp_throws, bats)
        hit_row  = HIT_BY_NAME.get(nm.lower(), {})
        h1       = _sf(str(hit_row.get('1+ Hit','')).replace('%',''))
        rbi_pct  = _sf(str(hit_row.get('To Get RBI','')).replace('%',''))
        opp_era  = _sf(sp_row.get('ERA', 4.25)) or 4.25
        hrr_pct  = compute_hrr(h1, rbi_pct, park_r, opp_era)

        for stype, fn in BATTER_CHECKS.items():
            n = count_streak(splits, fn)
            if n >= MINIMUMS[stype]:
                dots = dot_list(splits, fn)
                v    = calc_verdict(vuln, park_r, edge, h1, stype)
                ins  = batter_insight(nm, stype, n, opp_sp, vuln, park_r, h1, edge)
                streaks.append(dict(
                    type=stype, player=nm, bats=bats, team=team, streak=n,
                    dots=dots, opp_sp=opp_sp, sp_throws=sp_throws,
                    vuln=vuln, park_r=park_r, edge=edge, h1=h1,
                    rbi_pct=rbi_pct if stype=='HRR' else 0,
                    hrr_pct=hrr_pct if stype=='HRR' else 0,
                    verdict=v, insight=ins,
                    # K-streak fields (blank for batters)
                    opp='', opp_k_pct=0, k_proj=0, alt_line='', throws='',
                ))
                print(f'  [streak] {nm}: {stype} ×{n}')

        time.sleep(0.25)

    # ── PITCHER K STREAKS ─────────────────────────────────────────
    pitcher_names = [(r.get('Pitcher',''), tn(r.get('Team','')), tn(r.get('Opp','')))
                     for r in SP_PROJ if r.get('Pitcher') and r.get('Pitcher') != 'TBD']
    print(f'[streaks] Checking {len(pitcher_names)} pitchers for K streaks...')

    for pit_name, team, opp_team in pitcher_names:
        pid = player_id(pit_name)
        if not pid:
            print(f'  [skip] {pit_name} — no MLB ID'); time.sleep(0.2); continue
        splits = fetch_logs(pid, 'pitching')
        if not splits:
            print(f'  [skip] {pit_name} — no logs'); time.sleep(0.2); continue

        n = count_streak(splits, K_CHECK)
        if n >= MINIMUMS['K']:
            dots     = dot_list(splits, K_CHECK)
            sp_row   = SP_BY_TEAM.get(team, {})
            throws   = sp_row.get('PitcherHand','')
            k_proj   = _sf(sp_row.get('K', 0))
            alt_line = k_alt_line(k_proj)
            park_r   = get_park_runs(team)

            # Rough opp lineup K% (approximated from BP data if available)
            opp_k_pct = 22.0  # league average fallback
            for r in BP_BAT:
                if tn(r.get('Team','')) == opp_team:
                    k_rate = _sf(r.get('KRate','') or r.get('StrikeoutRate','') or 0)
                    if k_rate > 0:
                        opp_k_pct = k_rate * 100 if k_rate < 1 else k_rate
                        break

            v   = calc_verdict(0, park_r, False, 0, 'K', opp_k_pct, k_proj)
            ins = pitcher_insight(pit_name, n, opp_team, opp_k_pct, k_proj, alt_line)
            streaks.append(dict(
                type='K', player=pit_name, throws=throws, team=team, streak=n,
                dots=dots, opp=opp_team, opp_k_pct=opp_k_pct,
                k_proj=k_proj, alt_line=alt_line, park_r=park_r,
                verdict=v, insight=ins,
                # Batter fields (blank for pitchers)
                bats='', opp_sp='', sp_throws='', vuln=0,
                edge=False, h1=0, rbi_pct=0, hrr_pct=0, hits_avg=0,
            ))
            print(f'  [streak] {pit_name}: K ×{n}')

        # ── HITS ALLOWED streak (same pitching logs) ──
        nh = count_streak(splits, HAL_CHECK)
        if nh >= MINIMUMS['HAL']:
            dots_h   = dot_list(splits, HAL_CHECK)
            sp_row   = SP_BY_TEAM.get(team, {})
            throws   = sp_row.get('PitcherHand','')
            park_r   = get_park_runs(team)
            # average hits allowed across the streak games
            ha_vals  = [int(s.get('stat',{}).get('hits',0) or 0) for s in splits[:nh]]
            hits_avg = round(sum(ha_vals)/len(ha_vals), 1) if ha_vals else 0
            ins_h    = f"{pit_name} has allowed {HA_THRESHOLD}+ hits in {nh} straight starts ({hits_avg} avg) — target opposing bats vs {opp_team}"
            streaks.append(dict(
                type='HAL', player=pit_name, throws=throws, team=team, streak=nh,
                dots=dots_h, opp=opp_team, opp_k_pct=0,
                k_proj=0, alt_line='', park_r=park_r,
                verdict='neutral', insight=ins_h, hits_avg=hits_avg,
                bats='', opp_sp='', sp_throws='', vuln=0,
                edge=False, h1=0, rbi_pct=0, hrr_pct=0,
            ))
            print(f'  [streak] {pit_name}: HA ×{nh} ({hits_avg} avg)')

        time.sleep(0.25)

    html = render_html(streaks, today, slate_label)
    with open(STREAKS_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'[streaks] ✓ Wrote {STREAKS_FILE} — {len(streaks)} streaks')

    # Export hot players for cross-module use (parlay anchors in build_editorial)
    hot_export = {
        'HR':  sorted({s['player'] for s in streaks if s.get('type') == 'HR'}),
        'all': sorted({s['player'] for s in streaks if s.get('type') in ('HR','HRR','HIT','TWO','RBI')}),
    }
    hot_file = os.environ.get('HOT_STREAKS_FILE', 'hot_streaks.json')
    with open(hot_file, 'w', encoding='utf-8') as f:
        json.dump(hot_export, f)
    print(f'[streaks] ✓ Wrote {hot_file} — {len(hot_export["HR"])} HR streakers, {len(hot_export["all"])} hot batters')

if __name__ == '__main__':
    build()


# ════════════════════════════════════════════════════════════════════════════
# Daily Slate v4.1 theme — applied automatically after every build.
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


if __name__ == '__main__':
    try:
        _v41_path = os.environ.get('STREAKS_FILE', 'streaks.html')
        _v41_html = open(_v41_path, encoding='utf-8').read()
        if '<!--V41THEME-->' not in _v41_html:
            open(_v41_path, 'w', encoding='utf-8').write(v41_streaks(_v41_html))
            print(f'[streaks] v4.1 theme applied -> {_v41_path}')
    except Exception as _v41_e:
        print('[streaks] v4.1 theme SKIPPED:', _v41_e)
