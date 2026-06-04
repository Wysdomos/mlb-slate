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
"""

import json, os, time, urllib.request, urllib.parse, urllib.error
from datetime import date

# ── CONFIG ────────────────────────────────────────────────────────
DATA_FILE    = os.environ.get('DATA_FILE',    'day_data.json')
STREAKS_FILE = os.environ.get('STREAKS_FILE', 'streaks.html')
SEASON       = 2026
GAMES_BACK   = 10   # game logs to inspect per player
K_THRESHOLD  = 6    # minimum Ks/start to count for K streak

MINIMUMS = {'HR':2,'HRR':3,'K':3,'HIT':4,'TWO':2,'RBI':4}

TYPE_CFG = {
    'HR':  {'emoji':'💣','label':'HR STREAK', 'color':'#ef4444'},
    'HRR': {'emoji':'🔥','label':'HRR STREAK','color':'#06b6d4'},
    'K':   {'emoji':'⚾','label':'K STREAK',  'color':'#f97316'},
    'HIT': {'emoji':'🎯','label':'HIT STREAK','color':'#22c55e'},
    'TWO': {'emoji':'💥','label':'2+H STREAK','color':'#a855f7'},
    'RBI': {'emoji':'💰','label':'RBI STREAK','color':'#f59e0b'},
}
TYPE_ORDER = {'HR':0,'HRR':1,'K':2,'HIT':3,'TWO':4,'RBI':5}

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
K_CHECK = lambda st: int(st.get('strikeOuts',0) or 0) >= K_THRESHOLD

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
    is_pitcher = s['type'] == 'K'

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
        ok_color  = '#ef4444' if s['opp_k_pct']>=24 else '#f59e0b' if s['opp_k_pct']>=21 else '#64748b'
        kp_color  = '#4ade80' if s['k_proj']>=7 else '#fbbf24' if s['k_proj']>=5 else '#94a3b8'
        pk_color  = '#4ade80' if s['park_r']>=8 else '#f87171' if s['park_r']<=-10 else '#64748b'
        pk_str    = ('+' if s['park_r']>0 else '') + str(int(s['park_r'])) + '%' + (' 🌋' if s['park_r']>=25 else '')
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

    bg = 'rgba(255,255,255,.012)' if idx % 2 == 1 else 'transparent'

    return f'''<div class="streak-row" data-type="{s['type']}" style="border-left:3px solid {color};background:{bg}">
  <div class="row-top">
    <span class="type-badge" style="color:{color};background:{color}18">{tc['emoji']} {tc['label']}</span>
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

    cat_order  = [k for k in ['HR','HRR','K','HIT','TWO','RBI'] if counts.get(k,0)]
    # Default-active tab = the category with the most streaks (so page lands full, not empty)
    first_type = max(cat_order, key=lambda k: counts.get(k,0)) if cat_order else ''
    tabs = []
    for k in cat_order:
        tc = TYPE_CFG[k]
        tabs.append((k, f"{tc['emoji']} {tc['label'].split()[0]} ({counts[k]})"))

    tab_html = ''.join(
        f'<button class="filter-btn{" active" if k==first_type else ""}" '
        f'onclick="filter(\'{k}\',this)" '
        f'style="--type-color:{TYPE_CFG[k]["color"]}'
        f'{(";background:"+TYPE_CFG[k]["color"]+"18") if k==first_type else ""}">'
        f'{label}</button>'
        for k,label in tabs
    )

    rows_html = ''.join(render_row(s,i) for i,s in enumerate(streaks))
    if not rows_html:
        rows_html = '<div style="text-align:center;padding:48px 16px;color:#475569;font-size:14px">No active streaks found for today\'s slate.</div>'

    return f'''<!DOCTYPE html>
<html lang="en">
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
.fab-home{{bottom:22px;background:rgba(30,40,60,.92);}}
.fab-kreport{{bottom:80px;background:linear-gradient(135deg,#0a84ff,#0040dd);}}
</style>
</head>
<body>
<div class="page-header">
  <div class="header-row">
    <div style="display:flex;align-items:center;gap:10px">
      <a href="index.html" class="back-link">← Slate</a>
      <div>
        <div class="header-title">🔥 Hot Streaks</div>
        <div class="header-sub">{len(streaks)} active streak{'s' if len(streaks)!=1 else ''}</div>
      </div>
    </div>
    <div class="header-date">{today}<br>{slate_label}</div>
  </div>
  <details class="streak-guide">
    <summary class="streak-guide-summary">📖 How to read Hot Streaks</summary>
    <div class="streak-guide-body">
      <p><strong>What is a streak?</strong> A player who has hit the qualifying stat in back-to-back or consecutive games — not just good recent form, but an active run confirmed by official game logs.</p>
      <table class="guide-table">
        <tr><td>💣 <strong>HR</strong></td><td>Home run in <strong>≥ 2</strong> consecutive games</td></tr>
        <tr><td>🔥 <strong>HRR</strong></td><td>H+R+RBI ≥ 1 in <strong>≥ 3</strong> consecutive games</td></tr>
        <tr><td>⚾ <strong>K</strong></td><td>Pitcher recorded <strong>6+</strong> K in <strong>≥ 3</strong> consecutive starts</td></tr>
        <tr><td>🎯 <strong>HIT</strong></td><td>At least 1 hit in <strong>≥ 4</strong> consecutive games</td></tr>
        <tr><td>💥 <strong>2+H</strong></td><td>Multi-hit game in <strong>≥ 2</strong> consecutive games</td></tr>
        <tr><td>💰 <strong>RBI</strong></td><td>At least 1 RBI in <strong>≥ 4</strong> consecutive games</td></tr>
      </table>
      <p style="margin-top:8px;font-size:12px;color:#4ade80">Game dots ● = streak stat fired that game. More filled dots = longer active run. Swipe left / right to move between categories.</p>
    </div>
  </details>
  <div class="filter-row">{tab_html}</div>
</div>
<div id="streak-list">{rows_html}</div>
<div class="footer">Filled dots = streak stat fired · MLB Stats API</div>
<script>
function filter(type,btn){{
  document.querySelectorAll('.filter-btn').forEach(b=>{{b.classList.remove('active');b.style.background='';}});
  btn.classList.add('active');
  btn.style.setProperty('background',btn.style.getPropertyValue('--type-color')+'18');
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
</script>
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
                edge=False, h1=0, rbi_pct=0,
            ))
            print(f'  [streak] {pit_name}: K ×{n}')

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
