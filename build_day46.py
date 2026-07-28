"""Daily MLB slate builder.

Reads: /home/user/workspace/day46_data.json
Writes: /home/user/workspace/built_sections_d46.json
"""
import hashlib, html, json, re, os
from datetime import datetime
from parlay_rules import (
    FORBIDDEN_MARKETS,
    validate_parlay,
)
from shadow_chips import (
    blank_chip_tiers,
    chip_hall_a,
    chip_hit_a,
    chip_hr_a,
    chip_hr_b,
    chip_k_a,
    percentile_lookup,
)

def _sf(v, default=0.0):
    """Safely convert any SP_PROJ numeric field to float — handles str, None, empty."""
    try: return float(v) if v not in (None, '', 'None') else default
    except (TypeError, ValueError): return default

DATA = json.load(open('/home/user/workspace/day46_data.json'))
PROJECTED_MODE = DATA.get('_mode') == 'projected'
PICK_SOURCE = 'projected' if PROJECTED_MODE else 'workbook'

# Provisional Chapter H recommendation margins. Calibration will replace these.
H_ALLOWED_MAIN_EDGE_MIN = 0.5
H_ALLOWED_ALT_MARGIN_MIN = 1.5
OUTS_MAIN_EDGE_MIN = 1.0
OUTS_ALT_MARGIN_MIN = 2.0

# Cross-game parlays do not get same-park/pitcher/weather correlation lift.
# Calibration will replace this starting +5 percentage-point/score penalty.
CROSS_GAME_STRICTER_DELTA = 5.0
K_ALT_MARGIN_MIN = OUTS_ALT_MARGIN_MIN
# Chapter L funnel showed 0/32 starters reached three independent families and
# 0 same-game pairs survived at two families; one family preserves same-game structure.
TWO_WAY_K_MIN_FAMILIES = 1  # was 3
DOUBLE_BARREL_HIT_MIN = 65.0
# Chapter L funnel showed Double Barrel collapsed at contact vulnerability.
DOUBLE_BARREL_CONTACT_VULN_MIN = 50.0  # was 60.0
CONTACT_HITS_ALLOWED_MIN = 5.0  # was 5.5
YARD_SALE_DRIVER_MIN = 35.0

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

# Real book prop lines. Missing or stale files are non-fatal: boards still render
# projections with no line-driven recommendation.
try:
    K_PROPS_FILE = os.environ.get('K_PROPS_FILE', 'k_props.json')
    K_PROPS = json.load(open(K_PROPS_FILE, encoding='utf-8'))
    if not isinstance(K_PROPS, dict):
        K_PROPS = {}
except Exception:
    K_PROPS = {}

try:
    HOT_STREAKS_FILE = os.environ.get('HOT_STREAKS_FILE', 'hot_streaks.json')
    HOT_STREAKS = json.load(open(HOT_STREAKS_FILE, encoding='utf-8'))
    if not isinstance(HOT_STREAKS, dict):
        HOT_STREAKS = {}
except Exception:
    HOT_STREAKS = {}

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

def prop_entry_for(name):
    if not name:
        return {}
    entry = K_PROPS.get(str(name).strip().lower(), {})
    return entry if isinstance(entry, dict) else {}

def pitcher_prop_line(name, market_key):
    entry = prop_entry_for(name)
    if market_key == 'K':
        return _sf(entry.get('line'), None) if entry.get('line') is not None else None
    nested = entry.get(market_key, {})
    if isinstance(nested, dict) and nested.get('line') is not None:
        return _sf(nested.get('line'), None)
    return None

def batter_prop_line(name, market_key):
    market = K_PROPS.get(f'_batter_{market_key}', {})
    if not isinstance(market, dict):
        return None
    entry = market.get(str(name or '').strip().lower(), {})
    if isinstance(entry, dict) and entry.get('line') is not None:
        return _sf(entry.get('line'), None)
    return None

def average_available(*values):
    nums = []
    for v in values:
        n = _sf(v, None)
        if n is not None:
            nums.append(n)
    return (sum(nums) / len(nums)) if nums else None

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

def bpp_matchup_tier(value):
    if value in (None, '', 'None'): return None
    try: n = int(float(value))
    except (TypeError, ValueError): return None
    if n >= 7: return 'plus'
    if n >= 3: return 'lean-plus'
    if n <= -7: return 'minus'
    if n <= -3: return 'lean-minus'
    return 'neutral'

def numeric_value(value):
    if value in (None, '', 'None'): return None
    try:
        return float(str(value).replace('%', '').replace('+', '').strip())
    except (TypeError, ValueError):
        return None

def avg(values):
    nums = [v for v in (numeric_value(value) for value in values) if v is not None]
    return (sum(nums) / len(nums)) if nums else None

def bpp_percentile_field(field):
    return percentile_lookup({
        name: values.get(field)
        for name, values in BPP_SUMMARY.items()
        if isinstance(values, dict) and values.get(field) is not None
    })

BPP_PERCENTILES = {
    field: bpp_percentile_field(field)
    for field in (
        'hr_prob',
        'walk_prob',
        'matchup_advantage',
        'hr_vs_typical',
        'park_hr_factor',
        'hit_prob',
        'k_prob',
    )
}

def bpp_pct(name, field):
    if not name: return None
    return BPP_PERCENTILES.get(field, {}).get(str(name).strip().lower())

def pitcher_key(name):
    return str(name or '').strip().lower()

def pitcher_metric_maps():
    kbb = {}
    innings = {}
    hits_allowed = {}
    rows = list(BP_PIT) + list(SP_PROJ)
    for row in rows:
        name = row.get('FullName') or row.get('Pitcher')
        key = pitcher_key(name)
        if not key:
            continue
        k = numeric_value(row.get('Strikeouts') if row.get('Strikeouts') is not None else row.get('K'))
        bb = numeric_value(row.get('Walks') if row.get('Walks') is not None else row.get('BB'))
        inn = numeric_value(row.get('Innings') if row.get('Innings') is not None else row.get('Inn'))
        hits = numeric_value(row.get('HitsAllowed') if row.get('HitsAllowed') is not None else row.get('H'))
        if k is not None and bb is not None and bb > 0:
            kbb.setdefault(key, k / bb)
        if inn is not None:
            innings.setdefault(key, inn)
        if hits is not None:
            hits_allowed.setdefault(key, hits)
    return kbb, innings, hits_allowed

PITCHER_KBB, PITCHER_INNINGS, PITCHER_HITS_ALLOWED = pitcher_metric_maps()
PITCHER_KBB_PCT = percentile_lookup(PITCHER_KBB)
PITCHER_INNINGS_PCT = percentile_lookup(PITCHER_INNINGS)
PITCHER_HITS_ALLOWED_PCT = percentile_lookup(PITCHER_HITS_ALLOWED)

def team_contact_percentiles():
    contact = {}
    for row in HR_LB:
        team = tn(row.get('Team'))
        if not team:
            continue
        bucket = contact.setdefault(team, {'barrel': [], 'hard': []})
        barrel = numeric_value(row.get('Barrel%'))
        hard = numeric_value(row.get('HH%'))
        if barrel is not None:
            bucket['barrel'].append(barrel)
        if hard is not None:
            bucket['hard'].append(hard)
    barrel_avg = {team: avg(bucket['barrel']) for team, bucket in contact.items()}
    hard_avg = {team: avg(bucket['hard']) for team, bucket in contact.items()}
    return percentile_lookup(barrel_avg), percentile_lookup(hard_avg)

TEAM_BARREL_PCT, TEAM_HARD_HIT_PCT = team_contact_percentiles()

def pitcher_chip_hall(pitcher_name, opp_team):
    key = pitcher_key(pitcher_name)
    opp = tn(opp_team)
    return chip_hall_a(
        TEAM_BARREL_PCT.get(opp),
        TEAM_HARD_HIT_PCT.get(opp),
        PITCHER_HITS_ALLOWED_PCT.get(key),
    )

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

# ---- BUILD: HEADLINES ----
def build_headlines():
    cards = []
    parks_by_hr = sorted(PARKS, key=lambda p: parse_pct(p.get('HR %')), reverse=True)
    if parks_by_hr and parse_pct(parks_by_hr[0].get('HR %')) >= 10:
        park = parks_by_hr[0]
        cards.append((
            'Top HR Park',
            f"<strong>{html.escape(str(park.get('Venue','—')))}</strong> leads park HR context at "
            f"<strong>{html.escape(str(park.get('HR %','—')))}</strong> for "
            f"{html.escape(str(park.get('Game','')))}."
        ))
    if parks_by_hr and parse_pct(parks_by_hr[-1].get('HR %')) <= -10:
        park = parks_by_hr[-1]
        cards.append((
            'HR Fade Park',
            f"<strong>{html.escape(str(park.get('Venue','—')))}</strong> is the slate HR suppressor at "
            f"<strong>{html.escape(str(park.get('HR %','—')))}</strong> for "
            f"{html.escape(str(park.get('Game','')))}."
        ))
    parks_by_runs = sorted(PARKS, key=lambda p: parse_pct(p.get('Runs %')), reverse=True)
    if parks_by_runs and parse_pct(parks_by_runs[0].get('Runs %')) >= 8:
        park = parks_by_runs[0]
        cards.append((
            'Run Environment',
            f"<strong>{html.escape(str(park.get('Venue','—')))}</strong> carries the top run context at "
            f"<strong>{html.escape(str(park.get('Runs %','—')))}</strong> for "
            f"{html.escape(str(park.get('Game','')))}."
        ))
    vuln_rows = []
    for sp in SP_PROJ:
        v = get_vuln_for_pitcher(sp.get('Pitcher'))
        if v:
            vuln_rows.append((_sf(v.get('VulnScore')), sp, v))
    vuln_rows.sort(key=lambda item: -item[0])
    if vuln_rows and vuln_rows[0][0] >= 50:
        score, sp, v = vuln_rows[0]
        reasons = []
        if _sf(sp.get('HR')) >= 0.8:
            reasons.append(f"{_sf(sp.get('HR')):.2f} HR/9")
        if _sf(sp.get('BB')) >= 2.5:
            reasons.append(f"{_sf(sp.get('BB')):.2f} BB")
        reason = ' and '.join(reasons) if reasons else f"ERA {html.escape(str(v.get('ERA','—')))}"
        cards.append((
            'Starter Vulnerability',
            f"<strong>{html.escape(str(sp.get('Pitcher','—')))}</strong> has the top VulnScore at "
            f"<strong>V{score:.0f}</strong>; board context shows {reason}."
        ))
    k_rows = sorted(SP_PROJ, key=lambda sp: -_sf(sp.get('K')))
    if k_rows and _sf(k_rows[0].get('K')) >= 5.0:
        sp = k_rows[0]
        cards.append((
            'Top K Projection',
            f"<strong>{html.escape(str(sp.get('Pitcher','—')))}</strong> leads the K board at "
            f"<strong>{_sf(sp.get('K')):.2f}</strong> projected strikeouts, mapped to "
            f"<strong>{html.escape(k_alt_for(sp.get('K')))}</strong>."
        ))
    consensus_rows = sorted(SP_PROJ, key=lambda sp: (-k_consensus_for_pitcher(sp), -_sf(sp.get('K'))))
    if consensus_rows and k_consensus_for_pitcher(consensus_rows[0]) >= 4:
        sp = consensus_rows[0]
        votes = k_consensus_for_pitcher(sp)
        cards.append((
            'K Consensus',
            f"<strong>{html.escape(str(sp.get('Pitcher','—')))}</strong> leads K consensus at "
            f"<strong>{votes}/6 lenses</strong> with a "
            f"<strong>{_sf(sp.get('K')):.2f}</strong> strikeout projection."
        ))
    if not cards:
        return empty_parlay_section(
            'headlines',
            'Slate Headlines',
            'No slate-level flags cleared',
            'No park, starter, K, or run-environment signal cleared its headline threshold.',
        )
    body = ''.join(
        f'<div class="headline-card"><div class="hc-title">{title}</div><p>{text}</p></div>'
        for title, text in cards[:6]
    )
    badge = (
        projected_badge("Top cards rebuilt from live sources; workbook-only signals are omitted.") + '\n'
        if PROJECTED_MODE else ''
    )
    return f'''<!-- HEADLINES -->
<section id="headlines" class="headline-grid">
{badge}{body}
</section>
'''

# ---- BUILD: PARK BOARD ----
def build_park_board():
    if not PARKS:
        return empty_market_section(
            'park-board',
            '🏟 Park Factors Board',
            'Park factors unavailable',
            'Park_Factors returned no rows. Park-driven leans are omitted rather than approximated.',
        )
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

    top_hr = parks_sorted[0] if parks_sorted else {}
    top_xbh = max(PARKS, key=lambda p: parse_pct(p.get('2B/3B %')), default={})
    hr_boosters = sum(1 for p in PARKS if parse_pct(p.get('HR %')) >= 5)
    hr_suppressors = sum(1 for p in PARKS if parse_pct(p.get('HR %')) <= -10)
    intro = (
        'Sourced from <strong>Park_Factors</strong> sheet (stadium baseline + day-of weather). '
        f'Top HR context: <strong>{html.escape(str(top_hr.get("Venue","—")))}</strong> '
        f'{html.escape(str(top_hr.get("HR %","—")))} for {html.escape(str(top_hr.get("Game","")))}. '
        f'{hr_boosters} parks are at least +5% HR, and {hr_suppressors} parks are at -10% HR or lower. '
        f'Top extra-base context: <strong>{html.escape(str(top_xbh.get("Venue","—")))}</strong> '
        f'{html.escape(str(top_xbh.get("2B/3B %","—")))}.'
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
      <span class="game-tag">Tap to expand · {len(PARKS)} venues · stadium + day-of weather</span>
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
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">Sorted by <strong>VulnScore desc</strong>. <strong>EDGE</strong> = batter has opposite-hand platoon advantage. ISO color: <strong style="color:var(--bad)">≥.280</strong> elite · <strong style="color:var(--hot)">≥.250</strong> hot · <strong style="color:var(--good)">≥.200</strong> good.</p>
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

# ---- BUILD: K BOARD ----
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

        # K projection display color. Chapter D now sources SP_Projections.K and
        # BP_Pitchers.Strikeouts from the same BPP projection feed, so the board
        # shows one projection column instead of duplicating the number.
        k_cls = 'good' if kf >= 5 else ('hot' if kf >= 4.5 else 'bad')
        k_proj_disp = f'<strong style="color:var(--{k_cls})">{ss_k}</strong>' if ss_k is not None else '—'

        # BPP (BP_Pitchers) — Strikeouts, Innings*3 = Outs, HitsAllowed, QualityStart, HomeRunsAllowed
        bp = BP_PIT_BY_NAME.get(name.lower())
        short_leash = pitcher_is_short_leash(name)
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

        hits_proj = pitcher_hits_projection(r, bp)
        outs_proj = pitcher_outs_projection(r, bp)
        hits_main_line = pitcher_prop_line(name, 'hits_allowed')
        outs_main_line = pitcher_prop_line(name, 'outs')
        hits_rec = recommendation_for_projection(
            hits_proj, hits_main_line, 'H_ALLOWED', short_leash=short_leash,
        )
        outs_rec = recommendation_for_projection(
            outs_proj, outs_main_line, 'OUTS', short_leash=short_leash,
        )
        hits_prop_s = pitcher_prop_cell(hits_proj, hits_main_line, hits_rec, 'H_ALLOWED')
        outs_prop_s = pitcher_prop_cell(outs_proj, outs_main_line, outs_rec, 'OUTS')

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

        # ── Consensus: thresholds preserved pending the K lens independence audit ──
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
        chips = blank_chip_tiers()
        pkey = pitcher_key(name)
        chips['chip_k_a'] = chip_k_a(
            votes,
            PITCHER_KBB_PCT.get(pkey),
            PITCHER_INNINGS_PCT.get(pkey),
        )
        chips['chip_hall_a'] = pitcher_chip_hall(name, opp)
        SLATE_PICKS.append({
            'market': 'K', 'pick': f'{name} {best_line}', 'name': name,
            'pick_source': PICK_SOURCE,
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
            **chips,
        })

        for market_key, rec, projection, label in (
            ('OUTS_ALT', outs_rec, outs_proj, 'outs'),
            ('H_ALLOWED_ALT', hits_rec, hits_proj, 'H allowed'),
        ):
            if not rec or not rec.get('alt_fires'):
                continue
            line_text = f'{rec["direction"]} {format_line_point(rec["alt_line"])} {label}'
            SLATE_PICKS.append({
                'market': market_key,
                'pick': f'{name} {line_text}',
                'name': name,
                'pick_source': PICK_SOURCE,
                'team': team,
                'opp': opp,
                'line': line_text,
                'win_at': rec.get('alt_win_at'),
                'projection': projection,
                'main_line': rec.get('main_line'),
                'direction': rec.get('direction'),
                'alt_margin': rec.get('alt_margin'),
                'consensus': votes,
                'consensus_max': consensus_max,
                **blank_chip_tiers(),
            })

        rows.append((votes, kf,
            f'      <tr class="{tier_cls}">'
            f'<td>{tier_badge}</td>'
            f'<td><strong>{name}</strong></td>'
            f'<td style="text-align:center">{hand_chip(throws,"throws")}</td>'
            f'<td>{team}</td>'
            f'<td>{_conv_cell(votes, consensus_max)}</td>'
            f'<td>{k_proj_disp}</td>'
            f'<td>{outs_prop_s}</td>'
            f'<td>{hits_prop_s}</td>'
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
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;"><strong>Consensus</strong> = how many of 6 K lenses agree: Projection Ks≥5.5 · BP_Pitchers Strikeouts≥5 · K9≥9 · Outs≥17 · opp lineup K's≥9 · BPP API proj K≥5. 🔒 = 5–6. Projection Ks from <strong>SP_Projections</strong>. <strong>Tier:</strong> T0 ≥5.5 · T1 4.5–5.4 · T2 4.0–4.4 · SKIP &lt;4.0. <strong>Best Line:</strong> ≥5 → O 5+, 4.5–4.99 → O 3.5, &lt;4.5 → O 2.5.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Tier</th><th>Pitcher</th><th>B</th><th>Tm</th><th>Conv</th><th>Proj Ks</th><th>Outs<br><small>Proj · Line · Rec</small></th><th>Hits Allowed<br><small>Proj · Line · Rec</small></th><th>ERA</th><th>QS%</th><th>HRA</th><th>Vuln</th><th>Best Line</th><th>Note</th></tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table></div>
    <p style="font-size:11px; color:var(--text-dim); margin-top:10px;">Outs and Hits Allowed projections blend SP_Projections with BP_Pitchers where both exist. Recommendations require a real main line and clear projection edge; short-leash starters show projections only. No alternate price is shown because alternate markets are not fetched.</p>
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

def empty_market_section(sec_id, title, tag, reason):
    return f'''<!-- EMPTY MARKET SECTION -->
<section id="{sec_id}" class="collapsible empty-market">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">{title}</div>
      <span class="game-tag">Tap to expand · {tag}</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <div class="unavailable-card">
      <strong>No qualifying rows</strong>
      <p>{reason}</p>
    </div>
  </div></div>
</section>
'''

def build_projected_headlines():
    return build_headlines()

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
        opp_team = tn(bp.get('Opponent', '')) if bp else ''
        if not opp_team:
            match = str(r.get('Matchup') or '')
            if ' vs. ' in match:
                parts = [tn(part.strip()) for part in match.split(' vs. ', 1)]
                opp_team = parts[1] if team == parts[0] else (parts[0] if team == parts[1] else '')
        hrr_pct = hrr_probability_for_hit_row(r, team, opp_team)
        hrr_cell = hrr_cell_for_pct(hrr_pct)
        tier = 'row-tier0' if hp_val(r, '1+ Hit') >= 60 else ('row-tier1' if hp_val(r, '1+ Hit') >= 55 else '')
        rows.append(
            f'      <tr class="{tier}"><td>{i}</td>'
            f'<td><strong>{nm}</strong> {hand_chip(bats, "bats")}</td>'
            f'<td>{team}</td><td>{r.get("Matchup","—")}</td>'
            f'<td><strong>{r.get("1+ Hit","—")}</strong></td>'
            f'<td>{r.get("2+ Hits","—")}</td>'
            f'<td>{r.get("To Get RBI","—")}</td>'
            f'<td>{hrr_cell}</td>'
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
    {projected_badge("Hit, multi-hit, RBI, HRR, and HR columns reconstructed from live projection inputs.")}
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>Matchup</th><th>1+ Hit</th><th>2+ Hits</th><th>RBI</th><th>HRR</th><th>HR</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
  </div></div>
</section>
'''

def hit_prob_fraction(row, key):
    value = row.get(key)
    if value in (None, '', 'None'):
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).replace('%', '').strip()
        try:
            number = float(text)
        except (TypeError, ValueError):
            return 0.0
    return max(0.0, min(1.0, number / 100 if number > 1 else number))

def two_plus_hits_key():
    if not HIT:
        return None
    matches = sorted({key for row in HIT for key in row if str(key).strip() == '2+ Hits'})
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError("Hit_Probabilities is missing the required 2+ Hits column")
    raise RuntimeError(f"Hit_Probabilities has ambiguous 2+ Hits columns: {matches}")

def normalized_header(name):
    return re.sub(r'[^a-z0-9]+', '', str(name or '').lower())

def required_row_value(row, table_name, label, accepted_keys):
    present = {normalized_header(key): key for key in row.keys()}
    for key in accepted_keys:
        actual = present.get(normalized_header(key))
        if actual is not None:
            return row.get(actual)
    raise RuntimeError(
        f"{table_name} is missing required {label} column; "
        f"accepted spellings: {', '.join(accepted_keys)}"
    )

def total_bases_rows():
    key_2h = two_plus_hits_key()
    if not key_2h:
        return []
    rows = []
    for hit in HIT:
        name = _hit_full(hit)
        if not name:
            continue
        bp = BP_BAT_BY_NAME.get(name.lower())
        if not bp:
            continue
        one_hit = hit_prob_fraction(hit, '1+ Hit')
        two_hits = hit_prob_fraction(hit, key_2h)
        e_hits = one_hit + two_hits
        home_runs = required_row_value(
            bp,
            'BP_Batters',
            'home runs',
            ('HomeRuns', 'HR'),
        )
        e_tb = e_hits + _sf(bp.get('Doubles')) + (3 * _sf(home_runs))
        rows.append({
            'name': name,
            'team': tn(hit.get('Team') or bp.get('Team')),
            'opp': tn(bp.get('Opponent') or hit.get('Opp')),
            'matchup': hit.get('Matchup') or '',
            'one_hit': one_hit,
            'two_hits': two_hits,
            'e_hits': e_hits,
            'e_tb': e_tb,
        })
    rows.sort(key=lambda row: (-row['e_tb'], row['name']))
    return rows

def build_tb_board():
    rows = total_bases_rows()[:30]
    if not rows:
        return empty_market_section(
            'tb-board',
            '📏 Total Bases Board',
            'Total Bases unavailable',
            'Hit probability and batter projection rows are required to derive Total Bases honestly.',
        )
    body = []
    for idx, row in enumerate(rows, 1):
        SLATE_PICKS.append({
            'market': 'TB',
            'pick': f'{row["name"]} Ov 1.5 TB',
            'name': row['name'],
            'pick_source': PICK_SOURCE,
            'team': row['team'],
            'opp': row['opp'],
            'line': 'Ov 1.5',
            'win_at': 2,
            'projection': row['e_tb'],
            'main_line': 1.5,
            'direction': 'Over',
            'alt_margin': None,
            **blank_chip_tiers(),
        })
        body.append(
            f'      <tr>'
            f'<td>{idx}</td>'
            f'<td><strong>{html.escape(row["name"])}</strong></td>'
            f'<td>{html.escape(row["team"])}</td>'
            f'<td>{html.escape(row["opp"])}</td>'
            f'<td><strong>{row["e_tb"]:.2f}</strong></td>'
            f'<td>{row["e_hits"]:.2f}</td>'
            f'<td>Ov 1.5</td>'
            f'<td><small>{html.escape(row["matchup"])}</small></td>'
            f'</tr>'
        )
    return f'''<!-- TB BOARD -->
<section id="tb-board" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">📏 Total Bases Board</div>
      <span class="game-tag">Tap to expand · Daily Slate derived score · Ov 1.5 TB</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;"><strong>Daily Slate derived score</strong> estimates total-base volume from hit tail probabilities plus extra-base lift. It is a derived estimate, not a vendor projection. Phase 1: flat scoring, no tiers.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Batter</th><th>Tm</th><th>Opp</th><th>Daily Slate E_TB</th><th>E Hits</th><th>Line</th><th>Matchup</th></tr></thead>
      <tbody>
{chr(10).join(body)}
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
        chips = blank_chip_tiers()
        chips['chip_hra'] = chip_hr_a(
            bpp_pct(c['nm'], 'hr_prob'),
            bpp_pct(c['nm'], 'walk_prob'),
            bpp_pct(c['nm'], 'matchup_advantage'),
        )
        chips['chip_hrb'] = chip_hr_b(
            c['votes'],
            bpp_pct(c['nm'], 'hr_vs_typical'),
            bpp_pct(c['nm'], 'park_hr_factor'),
        )
        SLATE_PICKS.append({
            'market': 'HR', 'pick': f'{c["nm"]} Ov 0.5 HR', 'name': c['nm'], 'team': c['team'],
            'pick_source': PICK_SOURCE,
            'pitcher': c['pit_name'], 'line': 'Ov 0.5', 'win_at': 1,
            'consensus': c['votes'], 'consensus_max': 7,
            'score': c['score'], 'sim_hr': c['sim_hr'], 'to_hit_hr': c['hr_pct'], 'park_hr': c['park_hr'],
            'bpp_api_hr': round(c['bpp_proj_hr'], 2) if c['bpp_proj_hr'] else None,
            'calibration_tier': bpp_matchup_tier(c['bpp_match_adv']),
            **chips,
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
        hrr_pct = hrr_probability_for_hit_row(r, team, opp_team)
        hrr_cell = hrr_cell_for_pct(hrr_pct)
        park_r2 = park_runs_for_team(team)
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
        hit_chips = blank_chip_tiers()
        hit_chips['chip_hit_a'] = chip_hit_a(
            bpp_pct(nm, 'hit_prob'),
            bpp_pct(nm, 'k_prob'),
        )
        SLATE_PICKS.append({
            'market': 'HIT', 'pick': f'{nm} Ov 0.5 H', 'name': nm, 'team': team,
            'pick_source': PICK_SOURCE,
            'line': 'Ov 0.5', 'win_at': 1, 'consensus': votes, 'consensus_max': 6,
            'h1_pct': h1, 'sim_hit': sim_hit,
            'bpp_api_hits': round(bpp_proj_hits, 2) if bpp_proj_hits else None,
            **hit_chips,
        })
        SLATE_PICKS.append({
            'market': 'HRR', 'pick': f'{nm} Ov 0.5 HRR', 'name': nm, 'team': team,
            'pick_source': PICK_SOURCE,
            'line': 'Ov 0.5', 'win_at': 1, 'win_stat': 'H+R+RBI',
            'consensus': votes, 'consensus_max': 6,
            'hrr_pct': hrr_pct,
            **blank_chip_tiers(),
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
            'pick_source': PICK_SOURCE,
            'lean': lean_dir, 'ref_line': 8.5, 'consensus': conf, 'consensus_max': 4,
            'proj_total': round(total, 2), 'p_over_8_5': round(p_over, 3), 'f5': round(f5, 2),
            **blank_chip_tiers(),
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
            'pick_source': PICK_SOURCE,
            'lean': lean_dir, 'consensus': conf, 'consensus_max': 4,
            'yrfi_prob': round(yrfi, 3) if yrfi else None,
            **blank_chip_tiers(),
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
            'pick_source': PICK_SOURCE,
            'team': team, 'opp': opp, 'line': 'Ov 0.5', 'win_at': 1,
            'consensus': votes, 'consensus_max': 3,
            'sb_prob': round(sbp, 3), 'sb_attempts': round(att, 2),
            'opp_sp_bb': round(opp_bb_v, 2) if opp_sp else None,
            **blank_chip_tiers(),
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
            'pick_source': PICK_SOURCE,
            'team': team, 'opp': opp, 'line': 'Ov 0.5', 'win_at': 1,
            'consensus': votes, 'consensus_max': 3,
            'proj_2b': round(dbls, 2), 'park_2b3b': xbh, 'opp_sp_h': round(opp_h, 2) if opp_sp else None,
            **blank_chip_tiers(),
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

# ---- BUILD: CORRELATION PARLAY BOARDS ----
def empty_parlay_section(sec_id, title, tag, message):
    return f'''<!-- PARLAY EMPTY -->
<section id="{sec_id}" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">{title}</div>
      <span class="game-tag">{tag}</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <div class="unavailable-card">
      <strong>No qualifying correlation stack</strong>
      <p>{message}</p>
    </div>
  </div></div>
</section>
'''

def game_key_for_team(team):
    team = tn(team)
    for game in GAMES_RAW:
        away = tn(game.get('AwayTeam'))
        home = tn(game.get('HomeTeam'))
        if team in (away, home):
            return f'{away}@{home}'
    return ''

def park_runs_for_team(team):
    park = PARK_BY_TEAM.get(tn(team))
    return parse_pct(park.get('Runs %')) if park else 0

def pitcher_bp(name):
    return BP_PIT_BY_NAME.get(str(name or '').strip().lower())

def pitcher_projection(name):
    return SP_BY_NAME.get(str(name or '').strip().lower())

def pitcher_outs_line(bp):
    if not bp:
        return None
    outs = _sf(bp.get('Innings')) * 3
    if outs >= 17:
        return {'line': 'Ov 16.5 outs', 'win_at': 17, 'projection': outs}
    if outs >= 15:
        return {'line': 'Ov 14.5 outs', 'win_at': 15, 'projection': outs}
    return None

def pitcher_hits_allowed_line(bp):
    if not bp:
        return None
    hits = _sf(bp.get('HitsAllowed'))
    if hits >= 6.0:
        return {'line': 'Ov 5.5 H allowed', 'win_at': 6, 'projection': hits}
    if hits >= 5.0:
        return {'line': 'Ov 4.5 H allowed', 'win_at': 5, 'projection': hits}
    return None

def pitcher_runs_allowed_line(bp):
    if not bp:
        return None
    runs = _sf(bp.get('RunsAllowed'))
    if runs >= 3.5:
        return {'line': 'Ov 3.5 ER', 'win_at': 4, 'projection': runs}
    if runs >= 2.5:
        return {'line': 'Ov 2.5 ER', 'win_at': 3, 'projection': runs}
    return None

def pitcher_is_short_leash(name):
    bp = pitcher_bp(name)
    if not bp:
        return True
    innings = _sf(bp.get('Innings'))
    qs = _sf(bp.get('QualityStart'))
    return innings < 4.5 or (qs and qs < 0.15)

def pitcher_hits_projection(sp, bp):
    return average_available(
        sp.get('H') if sp else None,
        bp.get('HitsAllowed') if bp else None,
    )

def pitcher_outs_projection(sp, bp):
    return average_available(
        _sf(sp.get('Inn'), None) * 3 if sp and _sf(sp.get('Inn'), None) is not None else None,
        _sf(bp.get('Innings'), None) * 3 if bp and _sf(bp.get('Innings'), None) is not None else None,
    )

def line_win_at(point, direction):
    if point is None:
        return None
    point = float(point)
    if str(direction).lower() == 'under':
        return int(point)
    return int(point) + 1

def format_line_point(point):
    if point is None:
        return '—'
    return f'{float(point):.1f}'

def recommendation_for_projection(projection, main_line, market_key, short_leash=False):
    if projection is None or main_line is None or short_leash:
        return None
    projection = float(projection)
    main_line = float(main_line)
    edge = projection - main_line
    if edge == 0:
        return None
    if market_key == 'H_ALLOWED':
        min_edge = H_ALLOWED_MAIN_EDGE_MIN
        alt_min = H_ALLOWED_ALT_MARGIN_MIN
        step = 2.0
    elif market_key == 'OUTS':
        min_edge = OUTS_MAIN_EDGE_MIN
        alt_min = OUTS_ALT_MARGIN_MIN
        step = 2.0
    else:
        return None
    if abs(edge) < min_edge:
        return None
    direction = 'Over' if edge > 0 else 'Under'
    alt_line = main_line - step if direction == 'Over' else main_line + step
    alt_margin = (projection - alt_line) if direction == 'Over' else (alt_line - projection)
    alt_fires = alt_margin >= alt_min
    return {
        'direction': direction,
        'main_line': main_line,
        'main_edge': edge,
        'alt_line': alt_line,
        'alt_margin': alt_margin,
        'alt_fires': alt_fires,
        'win_at': line_win_at(main_line, direction),
        'alt_win_at': line_win_at(alt_line, direction),
    }

def pitcher_prop_cell(projection, main_line, rec, market_key):
    proj_s = format_line_point(projection)
    line_s = format_line_point(main_line)
    if not rec:
        return (
            f'<span>{proj_s}</span><br>'
            f'<small>Line {line_s} · no play</small>'
        )
    unit = 'H' if market_key == 'H_ALLOWED' else 'outs'
    alt = ''
    if rec.get('alt_fires'):
        alt = f'<br><small>Alt {rec["direction"]} {format_line_point(rec["alt_line"])} {unit}</small>'
    return (
        f'<span>{proj_s}</span><br>'
        f'<strong>{rec["direction"]} {format_line_point(rec["main_line"])} {unit}</strong>'
        f'{alt}'
    )

def opposing_pitcher_for_hitter(team, opp_team):
    return SP_BY_TEAM.get(tn(opp_team), {}).get('Pitcher', '')

def k_lens_families_for_pitcher(sp):
    name = sp.get('Pitcher', '')
    kf = _sf(sp.get('K'))
    bp = pitcher_bp(name)
    outs_val = (_sf(bp.get('Innings')) * 3) if bp else 0
    v = get_vuln_for_pitcher(name)
    k9 = _sf(v.get('K9')) if v else 0
    opp = tn(sp.get('Opp'))
    opp_row = BP_TEAMS_BY_TEAM.get(opp) or BP_TEAMS_BY_TEAM.get((sp.get('Opp') or '').strip())
    opp_k = _sf(opp_row.get('Strikeouts')) if opp_row else 0
    return {
        'bpp_projection_averages_k': kf >= 5.5,
        'pitcher_k9_skill': k9 >= 9.0,
        'projected_outs_volume': outs_val >= 17,
        'opponent_lineup_k_volume': opp_k >= 9.0,
    }

def k_independent_family_count(sp):
    return sum(1 for active in k_lens_families_for_pitcher(sp).values() if active)

def k_main_alt_recommendation(sp):
    name = sp.get('Pitcher', '')
    projection = _sf(sp.get('K'), None)
    main_line = pitcher_prop_line(name, 'K')
    if projection is None or main_line is None or pitcher_is_short_leash(name):
        return None
    edge = projection - main_line
    if edge == 0:
        return None
    direction = 'Over' if edge > 0 else 'Under'
    if direction == 'Over':
        alt_line = min(main_line - 2.0, 4.5)
    else:
        alt_line = main_line + 2.0
    alt_margin = (projection - alt_line) if direction == 'Over' else (alt_line - projection)
    if alt_margin < K_ALT_MARGIN_MIN:
        return None
    return {
        'direction': direction,
        'main_line': main_line,
        'alt_line': alt_line,
        'alt_margin': alt_margin,
        'win_at': line_win_at(alt_line, direction),
        'projection': projection,
        'line': f'{direction} {format_line_point(alt_line)} K',
    }

def k_consensus_for_pitcher(sp):
    name = sp.get('Pitcher', '')
    kf = _sf(sp.get('K'))
    bp = pitcher_bp(name)
    bpp_val = _sf(bp.get('Strikeouts')) if bp else 0
    outs_val = (_sf(bp.get('Innings')) * 3) if bp else 0
    v = get_vuln_for_pitcher(name)
    k9 = _sf(v.get('K9')) if v else 0
    opp = tn(sp.get('Opp'))
    opp_row = BP_TEAMS_BY_TEAM.get(opp) or BP_TEAMS_BY_TEAM.get((sp.get('Opp') or '').strip())
    opp_k = _sf(opp_row.get('Strikeouts')) if opp_row else 0
    bpp_api = bpp_entry(name)
    bpp_api_k = _sf(bpp_api.get('proj_k')) if bpp_api else 0
    votes = 0
    if kf >= 5.5: votes += 1
    if bpp_val >= 5.0: votes += 1
    if k9 >= 9.0: votes += 1
    if outs_val >= 17: votes += 1
    if opp_k >= 9.0: votes += 1
    if bpp_api_k >= 5.0: votes += 1
    return votes

def k_tier_for_projection(k_proj):
    kf = _sf(k_proj)
    if kf >= 5.5:
        return 0
    if kf >= 4.5:
        return 1
    if kf >= 4.0:
        return 2
    return 3

def hitter_hrr_projection(hit_row, team, opp_team):
    h1 = _sf(str(hit_row.get('1+ Hit', '')).replace('%', ''))
    rbi = _sf(str(hit_row.get('To Get RBI', '')).replace('%', ''))
    sp = SP_BY_TEAM.get(tn(opp_team), {}) if opp_team else {}
    era = _sf(sp.get('ERA', 4.25))
    park_runs = park_runs_for_team(team)
    if h1 <= 0 or rbi <= 0:
        return None
    era_boost = max(0, (era - 4.25) * 1.5)
    run_prob = min(60, rbi * 0.8 + park_runs * 0.3 + era_boost)
    return round(min(99, max(0, (1 - (1 - h1 / 100) * (1 - run_prob / 100) * (1 - rbi / 100)) * 100)), 1)

def hrr_probability_for_hit_row(hit_row, team, opp_team):
    h1 = _sf(str(hit_row.get('1+ Hit', '')).replace('%', ''))
    rbi = _sf(str(hit_row.get('To Get RBI', '')).replace('%', ''))
    sp = SP_BY_TEAM.get(tn(opp_team), {}) if opp_team else {}
    era = _sf(sp.get('ERA', 4.25))
    park_runs = park_runs_for_team(team)
    if h1 <= 0 or rbi <= 0:
        return None
    era_boost = max(0, (era - 4.25) * 1.5)
    run_prob = min(60, rbi * 0.8 + park_runs * 0.3 + era_boost)
    return round(min(99, max(0, (1 - (1 - h1 / 100) * (1 - run_prob / 100) * (1 - rbi / 100)) * 100)), 1)

def hrr_cell_for_pct(hrr_pct):
    if hrr_pct is None:
        return '—'
    if hrr_pct >= 82:
        return f'<strong style="color:var(--good)">{hrr_pct}%</strong>'
    if hrr_pct >= 75:
        return f'<span style="color:var(--hot)">{hrr_pct}%</span>'
    return f'{hrr_pct}%'

def traffic_hitter_candidates():
    out = []
    for row in HIT:
        name = _hit_full(row)
        if not name:
            continue
        team = tn(row.get('Team'))
        bp = BP_BAT_BY_NAME.get(name.lower())
        opp_team = tn(bp.get('Opponent')) if bp else ''
        if not opp_team:
            match = str(row.get('Matchup') or '')
            if ' vs. ' in match:
                parts = [tn(part.strip()) for part in match.split(' vs. ', 1)]
                if team == parts[0]:
                    opp_team = parts[1]
                elif team == parts[1]:
                    opp_team = parts[0]
        opp_sp = SP_BY_TEAM.get(opp_team, {}).get('Pitcher') if opp_team else ''
        park_runs = park_runs_for_team(team)
        hrr = hitter_hrr_projection(row, team, opp_team)
        h1 = _sf(str(row.get('1+ Hit', '')).replace('%', ''))
        if hrr is None or hrr < 78 or park_runs <= 0 or not opp_sp:
            continue
        out.append({
            'name': name,
            'team': team,
            'opp': opp_team,
            'opp_sp': opp_sp,
            'game': game_key_for_team(team),
            'hrr_pct': hrr,
            'hit_pct': h1,
        })
    return out

def parlay_leg_html(leg):
    name = html.escape(str(leg.get('name') or leg.get('game') or ''))
    line = html.escape(str(leg.get('line') or ''))
    detail = html.escape(str(leg.get('detail') or ''))
    role = html.escape(str(leg.get('leg_role') or 'satellite').title())
    parts = [f'<strong>{name}</strong> {line}', f'<span class="badge b-neutral">{role}</span>']
    if detail:
        parts.append(f'<small>{detail}</small>')
    return ' '.join(parts)

def slate_id_for_parlays():
    for row in DATA.get('BP_Games', []):
        raw = str(row.get('GameDate', ''))[:10]
        if raw:
            return raw.replace('-', '')
    return 'slate'

def log_parlay_funnel(section, stages):
    print(f'[{section}] ' + ' -> '.join(f'{name}={count}' for name, count in stages))

def parlay_same_game(parlay):
    games = {str(leg.get('game') or '').strip() for leg in parlay.get('legs', [])}
    games.discard('')
    return bool(games) and len(games) == 1

def emit_parlay_legs(sec_id, parlays):
    for idx, parlay in enumerate(parlays[:5], 1):
        correlation_type = parlay.get('correlation_type', sec_id)
        parlay_id = f'{slate_id_for_parlays()}-{sec_id}-{idx}-{correlation_type}'
        same_game = parlay_same_game(parlay)
        for leg in parlay['legs']:
            name = leg.get('name') or leg.get('game') or ''
            SLATE_PICKS.append({
                'market': leg.get('market'),
                'pick': f'{name} {leg.get("line", "")}'.strip(),
                'name': name,
                'pick_source': PICK_SOURCE,
                'team': leg.get('team'),
                'opp': leg.get('opp'),
                'game': leg.get('game'),
                'line': leg.get('line', ''),
                'win_at': leg.get('win_at'),
                'consensus': leg.get('consensus', 0),
                'consensus_max': leg.get('consensus_max', 1),
                'parlay_id': parlay_id,
                'correlation_type': correlation_type,
                'leg_role': leg.get('leg_role', 'satellite'),
                'same_game': same_game,
                **blank_chip_tiers(),
            })

def render_parlay_board(sec_id, title, tag, intro, parlays, empty_message):
    if not parlays:
        return empty_parlay_section(sec_id, title, tag, empty_message)
    emit_parlay_legs(sec_id, parlays)
    blocks = []
    icons = ['1', '2', '3', '4', '5']
    for idx, parlay in enumerate(parlays[:5]):
        badge = html.escape(parlay.get('badge', 'correlated'))
        note = html.escape(parlay.get('note', ''))
        legs = '<br>'.join(f'Leg {i}: {parlay_leg_html(leg)}' for i, leg in enumerate(parlay['legs'], 1))
        note_html = f'<br><em>{note}</em>' if note else ''
        same_game_tag = ' <span class="badge b-tier0">SAME GAME</span>' if parlay_same_game(parlay) else ''
        blocks.append(
            f'  <div class="flag-row"><div class="icon">{icons[idx]}</div>'
            f'<div>{legs}{note_html} <span class="badge b-tier1">{badge}</span></div></div>'
            .replace(f'<span class="badge b-tier1">{badge}</span>', f'<span class="badge b-tier1">{badge}</span>{same_game_tag}')
        )
    return f'''<!-- PARLAY CORRELATION -->
<section id="{sec_id}" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">{title}</div>
      <span class="game-tag">{tag}</span>
    </div>
    <span class="chevron">▾</span>
  </button>
  <div class="game-body"><div class="game-body-inner">
    <p style="font-size:13px; color:var(--text-soft); margin-bottom:10px;">{intro}</p>
{chr(10).join(blocks)}
  </div></div>
</section>
'''

def build_two_way_ks():
    pool = list(SP_PROJ)
    lens_pool = [sp for sp in pool if k_independent_family_count(sp) >= TWO_WAY_K_MIN_FAMILIES]
    tier_pool = [sp for sp in lens_pool if k_tier_for_projection(sp.get('K')) <= 1]
    games = {}
    for sp in tier_pool:
        games.setdefault(game_key_for_team(sp.get('Team')), []).append(sp)
    same_game_pool = [sp for sp in tier_pool if len(games.get(game_key_for_team(sp.get('Team')), [])) >= 2]
    candidates = []
    for sp in same_game_pool:
        name = sp.get('Pitcher', '')
        families = k_independent_family_count(sp)
        rec = k_main_alt_recommendation(sp)
        if not rec:
            continue
        candidates.append({
            'sp': sp,
            'name': name,
            'team': tn(sp.get('Team')),
            'opp': tn(sp.get('Opp')),
            'game': game_key_for_team(sp.get('Team')),
            'families': families,
            'rec': rec,
        })
    by_game = {}
    for c in candidates:
        by_game.setdefault((c['game'], c['rec']['direction']), []).append(c)
    alt_margin_pool = [c for c in candidates if len(by_game.get((c['game'], c['rec']['direction']), [])) >= 2]
    parlays = []
    for (game, direction), group in sorted(
        by_game.items(),
        key=lambda item: (-sum(g['families'] for g in item[1]), item[0][0], item[0][1]),
    ):
        if not game or len(group) < 2:
            continue
        group = sorted(group, key=lambda c: (-c['families'], -c['rec']['alt_margin'], c['name']))[:2]
        legs = []
        for idx, c in enumerate(group, 1):
            rec = c['rec']
            legs.append({
                'market': 'K',
                'name': c['name'],
                'team': c['team'],
                'opp': c['opp'],
                'game': c['game'],
                'line': rec['line'],
                'win_at': rec['win_at'],
                'consensus': c['families'],
                'consensus_max': 4,
                'leg_role': 'satellite',
                'confidence_rank': idx,
                'detail': f'{direction.lower()} from projection {rec["projection"]:.2f} vs line {rec["main_line"]:.1f}; {c["families"]}/4 independent K families',
            })
        ok, reason = validate_parlay(legs, 'two_way_k', max_legs=3)
        if not ok:
            continue
        parlays.append({
            'correlation_type': 'two_way_k',
            'badge': f'{direction} K pair',
            'note': 'Both starters share the same game environment and the same strikeout direction.',
            'legs': legs,
        })
    log_parlay_funnel('two-way-ks', [
        ('pool', len(pool)),
        (f'after lens>={TWO_WAY_K_MIN_FAMILIES}', len(lens_pool)),
        ('after tier 0-1', len(tier_pool)),
        ('after same-game pairing', len(same_game_pool)),
        ('after alt margin', len(alt_margin_pool)),
        ('emitted', len(parlays)),
    ])
    return render_parlay_board(
        'two-way-ks',
        "Two-Way K's",
        'Tap to expand · same-game alt K pairs · independent K families',
        f'Eligibility: at least {TWO_WAY_K_MIN_FAMILIES} independent K signal families, tier 0-1, no opener/short-leash flag, and a real main line with enough alternate-line margin.',
        parlays,
        'No same-game starter pair cleared the independent K-family, tier, line-direction, and alt-margin gates.',
    )

def build_traffic_jam():
    grouped = {}
    traffic_pool = traffic_hitter_candidates()
    for hitter in traffic_pool:
        key = (hitter['team'], hitter['opp_sp'])
        grouped.setdefault(key, []).append(hitter)
    paired_groups = {key: hitters for key, hitters in grouped.items() if len(hitters) >= 2}
    structured_groups = 0
    valid_groups = 0
    parlays = []
    for (team, opp_sp), hitters in sorted(
        grouped.items(),
        key=lambda item: -sum(h['hrr_pct'] for h in item[1]),
    ):
        hitters = sorted(hitters, key=lambda h: (-h['hrr_pct'], -h['hit_pct']))
        if len(hitters) < 2:
            continue
        bp = pitcher_bp(opp_sp)
        sp = pitcher_projection(opp_sp) or {}
        vuln = get_vuln_for_pitcher(opp_sp)
        vuln_score = _sf(vuln.get('VulnScore')) if vuln else 0
        park_runs = park_runs_for_team(team)
        hits_line = pitcher_hits_allowed_line(bp)
        runs_line = pitcher_runs_allowed_line(bp)
        era = _sf(sp.get('ERA') if sp else (vuln.get('ERA') if vuln else 0))

        structure = None
        pitcher_leg = None
        if vuln_score >= 70:
            structure = 'lineup_stack'
        elif hits_line and hits_line['projection'] >= 5.5:
            structure = 'both_sides'
            pitcher_leg = {
                'market': 'H_ALLOWED',
                'name': opp_sp,
                'team': tn(sp.get('Team')) if sp else '',
                'opp': team,
                'game': game_key_for_team(team),
                'line': hits_line['line'],
                'win_at': hits_line['win_at'],
                'leg_role': 'satellite',
                'confidence_rank': 3,
                'detail': f'projected {hits_line["projection"]:.2f} hits allowed',
            }
        elif runs_line and (era >= 4.5 or park_runs >= 5):
            structure = 'run_environment'
            pitcher_leg = {
                'market': 'ER_ALLOWED',
                'name': opp_sp,
                'team': tn(sp.get('Team')) if sp else '',
                'opp': team,
                'game': game_key_for_team(team),
                'line': runs_line['line'],
                'win_at': runs_line['win_at'],
                'leg_role': 'satellite',
                'confidence_rank': 3,
                'detail': f'projected {runs_line["projection"]:.2f} runs allowed; park runs {park_runs:+d}%',
            }
        if not structure:
            continue
        structured_groups += 1

        legs = []
        for hitter in hitters[:2]:
            legs.append({
                'market': 'HRR',
                'name': hitter['name'],
                'team': hitter['team'],
                'opp': hitter['opp'],
                'game': hitter['game'],
                'line': 'Ov 0.5 HRR',
                'win_at': 1,
                'leg_role': 'satellite',
                'confidence_rank': 1,
                'detail': f'{hitter["hrr_pct"]:.1f}% HRR proxy',
            })
        if pitcher_leg:
            legs.append(pitcher_leg)
        else:
            extra = next((h for h in hitters[2:] if h['name'] not in {leg['name'] for leg in legs}), None)
            if extra and extra['hit_pct'] >= 70:
                legs.append({
                    'market': 'HIT',
                    'name': extra['name'],
                    'team': extra['team'],
                    'opp': extra['opp'],
                    'game': extra['game'],
                    'line': 'Ov 0.5 H',
                    'win_at': 1,
                    'leg_role': 'satellite',
                    'confidence_rank': 2,
                    'detail': f'{extra["hit_pct"]:.1f}% 1+ hit',
                })
        ok, reason = validate_parlay(legs, structure, max_legs=3)
        if not ok:
            continue
        valid_groups += 1
        label = {
            'lineup_stack': 'Lineup Stack',
            'both_sides': 'Both Sides',
            'run_environment': 'Run Environment',
        }[structure]
        parlays.append({
            'correlation_type': structure,
            'badge': label,
            'note': f'{team} traffic correlated against {opp_sp}.',
            'legs': legs,
        })
    log_parlay_funnel('traffic-jam', [
        ('pool', len(traffic_pool)),
        ('after same-lineup pairing', len(paired_groups)),
        ('after structure match', structured_groups),
        ('after validation', valid_groups),
        ('emitted', len(parlays)),
    ])
    return render_parlay_board(
        'traffic-jam',
        'Traffic Jam',
        'Tap to expand · HRR traffic structures · no 2B or SB legs',
        'Eligibility: HRR proxy at least 78%, positive park Runs%, and one matching pitcher vulnerability reason. Hits-allowed and earned-runs legs are mutually exclusive.',
        parlays,
        'No lineup had two HRR legs with positive park run context and a matching pitcher vulnerability reason.',
    )

def hit_candidate_rows(min_hit_pct=DOUBLE_BARREL_HIT_MIN, cross_game=False):
    out = []
    threshold = min_hit_pct + (CROSS_GAME_STRICTER_DELTA if cross_game else 0)
    for row in HIT:
        name = _hit_full(row)
        if not name:
            continue
        hit_pct = _sf(str(row.get('1+ Hit', '')).replace('%', ''))
        if hit_pct < threshold:
            continue
        team = tn(row.get('Team'))
        bp = BP_BAT_BY_NAME.get(name.lower())
        opp = tn(bp.get('Opponent')) if bp else ''
        if not opp:
            match = str(row.get('Matchup') or '')
            if ' vs. ' in match:
                parts = [tn(part.strip()) for part in match.split(' vs. ', 1)]
                opp = parts[1] if team == parts[0] else (parts[0] if team == parts[1] else '')
        opp_sp = opposing_pitcher_for_hitter(team, opp)
        park_runs = park_runs_for_team(team)
        if park_runs < 0 or not opp_sp:
            continue
        vuln = get_vuln_for_pitcher(opp_sp)
        vuln_score = _sf(vuln.get('VulnScore')) if vuln else 0
        sp = pitcher_projection(opp_sp) or {}
        bp_sp = pitcher_bp(opp_sp) or {}
        hits_proj = pitcher_hits_projection(sp, bp_sp) or 0
        if vuln_score < DOUBLE_BARREL_CONTACT_VULN_MIN and hits_proj < CONTACT_HITS_ALLOWED_MIN:
            continue
        out.append({
            'name': name,
            'team': team,
            'opp': opp,
            'opp_sp': opp_sp,
            'game': game_key_for_team(team),
            'hit_pct': hit_pct,
            'park_runs': park_runs,
            'vuln_score': vuln_score,
            'hits_proj': hits_proj,
        })
    return out

def build_double_barrel():
    raw_pool = [_hit_full(row) for row in HIT if _hit_full(row)]
    hit_pool = []
    park_pool = []
    contact_pool = []
    for row in HIT:
        name = _hit_full(row)
        if not name:
            continue
        hit_pct = _sf(str(row.get('1+ Hit', '')).replace('%', ''))
        if hit_pct >= DOUBLE_BARREL_HIT_MIN:
            hit_pool.append(name)
            team = tn(row.get('Team'))
            bp = BP_BAT_BY_NAME.get(name.lower())
            opp = tn(bp.get('Opponent')) if bp else ''
            if not opp:
                match = str(row.get('Matchup') or '')
                if ' vs. ' in match:
                    parts = [tn(part.strip()) for part in match.split(' vs. ', 1)]
                    opp = parts[1] if team == parts[0] else (parts[0] if team == parts[1] else '')
            opp_sp = opposing_pitcher_for_hitter(team, opp)
            if park_runs_for_team(team) >= 0 and opp_sp:
                park_pool.append(name)
                vuln = get_vuln_for_pitcher(opp_sp)
                vuln_score = _sf(vuln.get('VulnScore')) if vuln else 0
                sp = pitcher_projection(opp_sp) or {}
                bp_sp = pitcher_bp(opp_sp) or {}
                hits_proj = pitcher_hits_projection(sp, bp_sp) or 0
                if vuln_score >= DOUBLE_BARREL_CONTACT_VULN_MIN or hits_proj >= CONTACT_HITS_ALLOWED_MIN:
                    contact_pool.append(name)
    parlays = []
    grouped = {}
    for hitter in hit_candidate_rows():
        grouped.setdefault((hitter['team'], hitter['opp_sp']), []).append(hitter)
    paired_groups = {key: hitters for key, hitters in grouped.items() if len(hitters) >= 2}
    valid_groups = 0
    for (team, opp_sp), hitters in sorted(grouped.items(), key=lambda item: -sum(h['hit_pct'] for h in item[1])):
        hitters = sorted(hitters, key=lambda h: (-h['hit_pct'], -h['vuln_score'], h['name']))
        if len(hitters) < 2:
            continue
        legs = []
        for idx, hitter in enumerate(hitters[:2], 1):
            legs.append({
                'market': 'HIT',
                'name': hitter['name'],
                'team': hitter['team'],
                'opp': hitter['opp'],
                'game': hitter['game'],
                'line': 'Ov 0.5 H',
                'win_at': 1,
                'leg_role': 'satellite',
                'confidence_rank': idx,
                'detail': f'{hitter["hit_pct"]:.1f}% 1+ hit; contact vulnerability {hitter["vuln_score"]:.0f}',
            })
        ok, reason = validate_parlay(legs, 'double_barrel_same_game', max_legs=2)
        if ok:
            valid_groups += 1
            parlays.append({
                'correlation_type': 'double_barrel_same_game',
                'badge': 'same lineup',
                'note': f'{team} hit legs share the same opposing starter.',
                'legs': legs,
            })
    cross_emitted = 0
    if not parlays:
        cross = sorted(hit_candidate_rows(cross_game=True), key=lambda h: (-h['hit_pct'], -h['vuln_score'], h['game'], h['name']))
        for first in cross:
            second = next((h for h in cross if h['name'] != first['name'] and h['game'] != first['game']), None)
            if not second:
                continue
            legs = []
            for idx, hitter in enumerate((first, second), 1):
                legs.append({
                    'market': 'HIT',
                    'name': hitter['name'],
                    'team': hitter['team'],
                    'opp': hitter['opp'],
                    'game': hitter['game'],
                    'line': 'Ov 0.5 H',
                    'win_at': 1,
                    'leg_role': 'satellite',
                    'confidence_rank': idx,
                    'detail': f'{hitter["hit_pct"]:.1f}% 1+ hit; cross-game threshold {DOUBLE_BARREL_HIT_MIN + CROSS_GAME_STRICTER_DELTA:.1f}%',
                })
            ok, reason = validate_parlay(legs, 'double_barrel_cross_game', max_legs=2)
            if ok:
                cross_emitted += 1
                parlays.append({
                    'correlation_type': 'double_barrel_cross_game',
                    'badge': 'cross-game stricter',
                    'note': 'Cross-game hit legs clear the stricter threshold because no shared-game lift exists.',
                    'legs': legs,
                })
                break
    log_parlay_funnel('double-barrel', [
        ('pool', len(raw_pool)),
        (f'after hit>={DOUBLE_BARREL_HIT_MIN:.0f}', len(hit_pool)),
        ('after park>=0+opp_sp', len(park_pool)),
        ('after contact vuln', len(contact_pool)),
        ('after same-lineup pairing', len(paired_groups)),
        ('after validation', valid_groups + cross_emitted),
        ('emitted', len(parlays)),
    ])
    return render_parlay_board(
        'double-barrel',
        'Double Barrel',
        'Tap to expand · exactly two 1+ hit legs',
        f'Same-lineup pairs are preferred. Cross-game pairs must clear an added {CROSS_GAME_STRICTER_DELTA:.0f}-point threshold.',
        parlays,
        'No same-lineup or stricter cross-game 1+ hit pair cleared the contact, park, and vulnerability gates.',
    )

def seeded_streak_key(item):
    seed = f'{slate_id_for_parlays()}|{item.get("player","")}|{item.get("type","")}'
    digest = hashlib.sha256(seed.encode('utf-8')).hexdigest()
    return int(digest[:12], 16)

def cruise_leg_from_streak(streak):
    stype = str(streak.get('type') or '').upper()
    if stype == 'HR':
        return None
    streak_len = int(_sf(streak.get('streak')))
    if streak_len < 3:
        return None
    name = str(streak.get('player') or '').strip()
    if not name:
        return None
    team = tn(streak.get('team'))
    opp = tn(streak.get('opp'))
    base = {
        'name': name,
        'team': team,
        'opp': opp,
        'game': game_key_for_team(team),
        'leg_role': 'satellite',
        'confidence_rank': 10 - min(streak_len, 9),
        'detail': f'{streak_len}-game active streak',
    }
    if stype == 'HRR':
        return {**base, 'market': 'HRR', 'line': 'Ov 0.5 HRR', 'win_at': 1}
    if stype == 'HIT':
        return {**base, 'market': 'HIT', 'line': 'Ov 0.5 H', 'win_at': 1}
    if stype == 'K':
        sp = pitcher_projection(name)
        if not sp:
            return None
        kf = _sf(sp.get('K'))
        line = k_alt_for(kf)
        return {**base, 'market': 'K', 'line': line, 'win_at': 5 if '5' in line else (4 if '3.5' in line else 3)}
    if stype == 'HAL':
        bp = pitcher_bp(name)
        line = pitcher_hits_allowed_line(bp)
        if not line:
            return None
        return {**base, 'market': 'H_ALLOWED', 'line': line['line'], 'win_at': line['win_at']}
    return None

def build_cruise_control():
    details = HOT_STREAKS.get('details') if isinstance(HOT_STREAKS, dict) else None
    details_key = isinstance(details, list)
    if not isinstance(details, list):
        details = []
    streak_pool = [s for s in details if int(_sf(s.get('streak'))) >= 3]
    market_pool = [
        s for s in streak_pool
        if str(s.get('type') or '').upper() not in ('HR', 'TWO', 'RBI', 'SB', '2B')
    ]
    candidates = []
    seen = set()
    for streak in details:
        leg = cruise_leg_from_streak(streak)
        if not leg or leg['market'] in FORBIDDEN_MARKETS or leg['market'] == 'HR':
            continue
        key = (leg['name'].lower(), leg['market'])
        if key in seen:
            continue
        seen.add(key)
        candidates.append((streak, leg))
    candidates.sort(key=lambda item: (-int(_sf(item[0].get('streak'))), seeded_streak_key(item[0]), item[1]['name']))
    legs = []
    used_people = set()
    for _, leg in candidates:
        person = leg['name'].strip().lower()
        if person in used_people:
            continue
        used_people.add(person)
        legs.append(leg)
        if len(legs) == 3:
            break
    valid_count = 0
    if len(legs) >= 2:
        ok_probe, reason_probe = validate_parlay(legs, 'streak', max_legs=3)
        valid_count = 1 if ok_probe else 0
    log_parlay_funnel('cruise-control', [
        ('details_key', int(details_key)),
        ('pool', len(details)),
        ('after streak>=3', len(streak_pool)),
        ('after supported non-HR market', len(market_pool)),
        ('after leg build', len(candidates)),
        ('after validation', valid_count),
        ('emitted', 1 if valid_count else 0),
    ])
    if len(legs) < 2:
        return empty_parlay_section(
            'cruise-control',
            'Cruise Control',
            'No qualifying streak stack',
            'Cruise Control needs at least two non-HR legs on active streaks of three or more games.',
        )
    ok, reason = validate_parlay(legs, 'streak', max_legs=3)
    if not ok:
        return empty_parlay_section('cruise-control', 'Cruise Control', 'Streak stack rejected by guard', reason)
    return render_parlay_board(
        'cruise-control',
        'Cruise Control',
        'Tap to expand · stable same-date streak stack',
        'Every leg is tied to an active streak of at least three games. HR streaks are excluded from this section.',
        [{
            'correlation_type': 'streak',
            'badge': 'streak',
            'note': 'Tie-breaking is seeded on the slate date, so the section stays stable during one slate day.',
            'legs': legs,
        }],
        'No non-HR streak stack cleared.',
    )

def batter_hr_projection(name):
    bp = BP_BAT_BY_NAME.get(str(name or '').strip().lower()) or {}
    try:
        return _sf(required_row_value(bp, 'BP_Batters', 'home runs', ('HomeRuns', 'Home Runs', 'HR')))
    except Exception:
        return 0

def park_hr_for_team(team):
    park = PARK_BY_TEAM.get(tn(team))
    return parse_pct(park.get('HR %')) if park else 0

def pitcher_hr_allowed_rate(name):
    sp = pitcher_projection(name) or {}
    bp = pitcher_bp(name) or {}
    return average_available(sp.get('HR'), bp.get('HomeRunsAllowed')) or 0

def handedness_bonus(batter_name, opp_sp):
    bp = BP_BAT_BY_NAME.get(str(batter_name or '').strip().lower()) or {}
    hitter_hand = str(bp.get('Bats') or bp.get('BatterHand') or '').strip().upper()
    sp = pitcher_projection(opp_sp) or {}
    pitcher_hand = str(sp.get('PitcherHand') or sp.get('Throws') or '').strip().upper()
    if hitter_hand == 'S':
        return 5.0
    if hitter_hand and pitcher_hand and hitter_hand != pitcher_hand:
        return 4.0
    return 0.0

def yard_sale_candidates(cross_game=False):
    out = []
    threshold = YARD_SALE_DRIVER_MIN + (CROSS_GAME_STRICTER_DELTA if cross_game else 0)
    for row in HR_LB:
        name = str(row.get('Batter') or row.get('Name') or '').strip()
        if not name:
            continue
        bp = BP_BAT_BY_NAME.get(name.lower()) or {}
        team = tn(row.get('Team') or bp.get('Team'))
        opp = tn(bp.get('Opponent') or row.get('Opp'))
        opp_sp = opposing_pitcher_for_hitter(team, opp)
        park_hr = park_hr_for_team(team)
        if park_hr < 8 or not opp_sp:
            continue
        hr_proj = batter_hr_projection(name)
        pitcher_hra = pitcher_hr_allowed_rate(opp_sp)
        score = park_hr + (pitcher_hra * 18.0) + (hr_proj * 85.0) + handedness_bonus(name, opp_sp)
        if score < threshold:
            continue
        out.append({
            'name': name,
            'team': team,
            'opp': opp,
            'opp_sp': opp_sp,
            'game': game_key_for_team(team),
            'park_hr': park_hr,
            'pitcher_hra': pitcher_hra,
            'hr_proj': hr_proj,
            'score': score,
        })
    return out

def build_yard_sale():
    pool = [row for row in HR_LB if str(row.get('Batter') or row.get('Name') or '').strip()]
    park_pool = []
    for row in pool:
        name = str(row.get('Batter') or row.get('Name') or '').strip()
        bp = BP_BAT_BY_NAME.get(name.lower()) or {}
        team = tn(row.get('Team') or bp.get('Team'))
        opp = tn(bp.get('Opponent') or row.get('Opp'))
        if park_hr_for_team(team) >= 8 and opposing_pitcher_for_hitter(team, opp):
            park_pool.append(row)
    driver_pool = yard_sale_candidates()
    parlays = []
    grouped = {}
    for hitter in driver_pool:
        grouped.setdefault((hitter['game'], hitter['opp_sp']), []).append(hitter)
    paired_groups = {key: hitters for key, hitters in grouped.items() if len(hitters) >= 2}
    valid_groups = 0
    for (game, opp_sp), hitters in sorted(grouped.items(), key=lambda item: -sum(h['score'] for h in item[1])):
        hitters = sorted(hitters, key=lambda h: (-h['score'], -h['park_hr'], h['name']))
        if len(hitters) < 2:
            continue
        legs = []
        for idx, hitter in enumerate(hitters[:2], 1):
            legs.append({
                'market': 'HR',
                'name': hitter['name'],
                'team': hitter['team'],
                'opp': hitter['opp'],
                'game': hitter['game'],
                'line': 'Ov 0.5 HR',
                'win_at': 1,
                'leg_role': 'satellite',
                'confidence_rank': idx,
                'detail': f'park HR {hitter["park_hr"]:+d}%; pitcher HR allowed {hitter["pitcher_hra"]:.2f}; HR projection {hitter["hr_proj"]:.2f}',
            })
        ok, reason = validate_parlay(legs, 'yard_sale_same_game', max_legs=2)
        if ok:
            valid_groups += 1
            parlays.append({
                'correlation_type': 'yard_sale_same_game',
                'badge': 'HR driver pair',
                'note': f'Both HR legs share {game} and the same opposing starter.',
                'legs': legs,
            })
    cross_emitted = 0
    if not parlays:
        cross = sorted(yard_sale_candidates(cross_game=True), key=lambda h: (-h['score'], -h['park_hr'], h['game'], h['name']))
        for first in cross:
            second = next((h for h in cross if h['name'] != first['name'] and h['game'] != first['game']), None)
            if not second:
                continue
            legs = []
            for idx, hitter in enumerate((first, second), 1):
                legs.append({
                    'market': 'HR',
                    'name': hitter['name'],
                    'team': hitter['team'],
                    'opp': hitter['opp'],
                    'game': hitter['game'],
                    'line': 'Ov 0.5 HR',
                    'win_at': 1,
                    'leg_role': 'satellite',
                    'confidence_rank': idx,
                    'detail': f'physical driver score {hitter["score"]:.1f}; cross-game threshold {YARD_SALE_DRIVER_MIN + CROSS_GAME_STRICTER_DELTA:.1f}',
                })
            ok, reason = validate_parlay(legs, 'yard_sale_cross_game', max_legs=2)
            if ok:
                cross_emitted += 1
                parlays.append({
                    'correlation_type': 'yard_sale_cross_game',
                    'badge': 'cross-game stricter',
                    'note': 'Cross-game HR legs clear the stricter physical-driver threshold.',
                    'legs': legs,
                })
                break
    log_parlay_funnel('yard-sale', [
        ('pool', len(pool)),
        ('after park>=8+opp_sp', len(park_pool)),
        ('after driver threshold', len(driver_pool)),
        ('after same-game pairing', len(paired_groups)),
        ('after validation', valid_groups + cross_emitted),
        ('emitted', len(parlays)),
    ])
    return render_parlay_board(
        'yard-sale',
        'Yard Sale',
        'Tap to expand · exactly two HR legs · physical drivers only',
        f'Ranks by park HR context, pitcher HR-allowed profile, BPP HomeRuns projection, and handedness context. Cross-game pairs need +{CROSS_GAME_STRICTER_DELTA:.0f} more driver score.',
        parlays,
        'No same-game or stricter cross-game HR pair cleared the physical-driver gates.',
    )

# ---- BUILD: CONVICTION BOARD ----
def conviction_empty():
    return empty_parlay_section(
        'conviction',
        'Full Conviction Board',
        'No conviction entries cleared',
        'No K, HRR, hit, or HR candidate cleared the conviction thresholds from the live slate data.',
    )

def conviction_candidates():
    candidates = []
    for sp in SP_PROJ:
        name = sp.get('Pitcher', '')
        kf = _sf(sp.get('K'))
        votes = k_consensus_for_pitcher(sp)
        if votes >= 4 and k_tier_for_projection(kf) <= 1 and 'K' not in FORBIDDEN_MARKETS:
            priority = 0 if votes >= 5 else 1
            candidates.append({
                'market': 'K',
                'name': name,
                'team': tn(sp.get('Team')),
                'opp': tn(sp.get('Opp')),
                'game': game_key_for_team(tn(sp.get('Team'))),
                'line': k_alt_for(kf),
                'win_at': 5 if '5' in k_alt_for(kf) else (4 if '3.5' in k_alt_for(kf) else 3),
                'consensus': votes,
                'consensus_max': 6,
                'priority': priority,
                'score': votes * 10 + kf,
                'badge': 'K CONVICTION',
                'badge_cls': 'b-tier0' if votes >= 5 else 'b-tier1',
                'why': f'{votes}/6 K lenses; projected {kf:.2f} strikeouts',
            })
    for hitter in traffic_hitter_candidates():
        candidates.append({
            'market': 'HRR',
            'name': hitter['name'],
            'team': hitter['team'],
            'opp': hitter['opp'],
            'game': hitter['game'],
            'line': 'Ov 0.5 HRR',
            'win_at': 1,
            'consensus': 0,
            'consensus_max': 1,
            'priority': 2,
            'score': hitter['hrr_pct'],
            'badge': 'HRR CONVICTION',
            'badge_cls': 'b-tier1',
            'why': f'{hitter["hrr_pct"]:.1f}% HRR proxy; park Runs {park_runs_for_team(hitter["team"]):+d}%',
        })
    hit_rows = sorted(HIT, key=lambda row: -parse_pct(row.get('1+ Hit')))[:12]
    for row in hit_rows:
        pct = parse_pct(row.get('1+ Hit'))
        if pct < 70:
            continue
        name = _hit_full(row)
        candidates.append({
            'market': 'HIT',
            'name': name,
            'team': tn(row.get('Team')),
            'opp': tn(row.get('Opp')),
            'game': game_key_for_team(tn(row.get('Team'))),
            'line': 'Ov 0.5 H',
            'win_at': 1,
            'consensus': 0,
            'consensus_max': 1,
            'priority': 3,
            'score': pct,
            'badge': 'HIT CONVICTION',
            'badge_cls': 'b-tier1',
            'why': f'{pct}% 1+ hit projection',
        })
    for row in HR_LB[:20]:
        score = _sf(row.get('Score'))
        if score < 80:
            continue
        name = row.get('Batter', '')
        candidates.append({
            'market': 'HR',
            'name': name,
            'team': tn(row.get('Team')),
            'opp': tn(row.get('Opp')),
            'game': game_key_for_team(tn(row.get('Team'))),
            'line': 'Ov 0.5 HR',
            'win_at': 1,
            'consensus': 0,
            'consensus_max': 1,
            'priority': 4,
            'score': score,
            'badge': 'HR SATELLITE',
            'badge_cls': 'b-warn',
            'why': f'HR board score {score:.0f}; HR legs are satellite-only until calibration promotes a replacement',
        })
    candidates = [c for c in candidates if c['market'] not in FORBIDDEN_MARKETS]
    candidates.sort(key=lambda c: (c['priority'], -c['score'], c['name']))
    if candidates and candidates[0]['market'] == 'HR':
        ok, reason = validate_parlay([
            {'market': 'HR', 'name': candidates[0]['name'], 'leg_role': 'satellite', 'confidence_rank': 1}
        ], 'conviction')
        if not ok:
            candidates = [c for c in candidates if c['market'] != 'HR'] + [c for c in candidates if c['market'] == 'HR']
    return candidates[:12]

def emit_conviction_picks(items):
    for rank, item in enumerate(items, 1):
        SLATE_PICKS.append({
            'market': item['market'],
            'pick': f"{item['name']} {item['line']}",
            'name': item['name'],
            'team': item.get('team', ''),
            'opp': item.get('opp', ''),
            'game': item.get('game', ''),
            'line': item['line'],
            'win_at': item['win_at'],
            'consensus': item.get('consensus', 0),
            'consensus_max': item.get('consensus_max', 1),
            'pick_source': PICK_SOURCE,
            'conviction_rank': rank,
            **blank_chip_tiers(),
        })

def build_conviction():
    items = conviction_candidates()
    if not items:
        return conviction_empty()
    emit_conviction_picks(items)
    li_html = ''.join(
        f'    <li><strong>#{i} {html.escape(item["name"])} {html.escape(item["line"])}</strong> '
        f'({html.escape(item["market"])}, {html.escape(item["team"])}) — {html.escape(item["why"])} '
        f'<span class="badge {item["badge_cls"]}">{html.escape(item["badge"])}</span></li>\n'
        for i, item in enumerate(items, 1)
    )
    return f'''<!-- CONVICTION -->
<section id="conviction" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">✅ Full Conviction Board</div>
      <span class="game-tag">Tap to expand · {len(items)} live-ranked conviction entries · K and HRR first</span>
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
def skip_empty():
    return empty_parlay_section(
        'skip',
        'Daily Skip List',
        'No skip or downgrade flags cleared',
        'No starter, park, or matchup crossed the live downgrade thresholds for this slate.',
    )

def build_skip():
    items = []
    for sp in sorted(SP_PROJ, key=lambda row: _sf(row.get('K'))):
        kf = _sf(sp.get('K'))
        if kf < 4.0:
            items.append((
                f'<strong>{html.escape(str(sp.get("Pitcher","")))} K props</strong> — projected '
                f'<strong>{kf:.2f}</strong> strikeouts, below the K board tier threshold.',
                'b-bad',
                'SKIP LOW K',
            ))
        elif pitcher_is_short_leash(sp.get('Pitcher')):
            bp = pitcher_bp(sp.get('Pitcher'))
            innings = _sf(bp.get('Innings')) if bp else 0
            items.append((
                f'<strong>{html.escape(str(sp.get("Pitcher","")))} outs/K ladder</strong> — projected '
                f'<strong>{innings * 3:.1f}</strong> outs, triggering the short-leash downgrade.',
                'b-warn',
                'SHORT LEASH',
            ))
    for park in sorted(PARKS, key=lambda row: parse_pct(row.get('HR %'))):
        hr = parse_pct(park.get('HR %'))
        if hr > -10:
            continue
        badge = 'SKIP HR' if hr <= -17 else 'DOWNGRADE HR'
        cls = 'b-bad' if hr <= -17 else 'b-warn'
        items.append((
            f'<strong>{html.escape(str(park.get("Game","")))} HR props</strong> — '
            f'{html.escape(str(park.get("Venue","Park")))} is showing '
            f'<strong>{html.escape(str(park.get("HR %","—")))}</strong> HR context on the park board.',
            cls,
            badge,
        ))
    top_arms = [
        sp for sp in SP_PROJ
        if k_consensus_for_pitcher(sp) >= 5 or _sf(sp.get('K')) >= 5.5
    ]
    for sp in sorted(top_arms, key=lambda row: (-k_consensus_for_pitcher(row), -_sf(row.get('K')))):
        items.append((
            f'<strong>{html.escape(tn(sp.get("Opp")))} batter props vs {html.escape(str(sp.get("Pitcher","")))}</strong> — '
            f'the opposing starter shows <strong>{k_consensus_for_pitcher(sp)}/6</strong> K lenses and '
            f'<strong>{_sf(sp.get("K")):.2f}</strong> projected strikeouts.',
            'b-warn',
            'TOP ARM',
        ))
    if not items:
        return skip_empty()
    li_html = ''.join(f'    <li>{body} <span class="badge {badge_cls}">{html.escape(badge_text)}</span></li>\n' for body, badge_cls, badge_text in items[:14])
    return f'''<!-- SKIP -->
<section id="skip" class="collapsible">
  <button class="game-header" aria-expanded="false">
    <div class="game-header-text">
      <div class="game-title">📋 Daily Skip List</div>
      <span class="game-tag">Tap to expand · {min(len(items), 14)} live skip and downgrade flags</span>
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
build_sb_board()       # Shadow market: emit picks, do not render board.
build_doubles_board()  # Shadow market: emit picks, do not render board.

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
        'tb-board':          with_projected_badge(build_tb_board(), "Total Bases board uses a Daily Slate derived estimate from live hit and batter projection inputs."),
        'totals-board':      with_projected_badge(build_totals_board(), "Totals rebuilt from live team run projections."),
        'nrfi-board':        with_projected_badge(build_nrfi_board(), "YRFI/NRFI rebuilt from live first-inning probability where available."),
        'dfs-board':         with_projected_badge(build_dfs_board(), "DFS board rebuilt from live DK/FD point projections."),
        'two-way-ks':        build_two_way_ks(),
        'traffic-jam':       build_traffic_jam(),
        'double-barrel':     build_double_barrel(),
        'cruise-control':    build_cruise_control(),
        'yard-sale':         build_yard_sale(),
        'conviction':        build_conviction(),
        'skip':              build_skip(),
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
        'tb-board':          build_tb_board(),
        'totals-board':      build_totals_board(),
        'nrfi-board':        build_nrfi_board(),
        'dfs-board':         build_dfs_board(),
        'two-way-ks':        build_two_way_ks(),
        'traffic-jam':       build_traffic_jam(),
        'double-barrel':     build_double_barrel(),
        'cruise-control':    build_cruise_control(),
        'yard-sale':         build_yard_sale(),
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
