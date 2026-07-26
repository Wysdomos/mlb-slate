"""
sync.py -- Generic daily sync for MLB Slate (any date, any game count)
Reads:   built_sections.json  (or SECTIONS_FILE env var)
         day_data.json         (or DATA_FILE env var)
Updates: index.html            (or INDEX_FILE env var)
"""

import json, re, os
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

SECTIONS_FILE = os.environ.get('SECTIONS_FILE', 'built_sections.json')
DATA_FILE     = os.environ.get('DATA_FILE',     'day_data.json')
INDEX_FILE    = os.environ.get('INDEX_FILE',    'index.html')

OPENING_DAY = date(2026, 3, 28)

WEEKDAY_NAMES = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

SECTIONS = json.load(open(SECTIONS_FILE, encoding='utf-8'))
DATA     = json.load(open(DATA_FILE,     encoding='utf-8'))
PROJECTED_MODE = DATA.get('_mode') == 'projected'

with open(INDEX_FILE, encoding='utf-8') as f:
    html = f.read()

print(f"Loaded {INDEX_FILE}: {len(html):,} bytes")

def get_slate_date():
    for row in DATA.get('BP_Games', []):
        raw = str(row.get('GameDate', ''))[:10]
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date()
        except:
            pass
    for row in DATA.get('Park_Factors', []):
        raw = str(row.get('Date', ''))[:10]
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date()
        except:
            pass
    return date.today()

slate_date  = get_slate_date()
day_num     = (slate_date - OPENING_DAY).days + 1
month_short = slate_date.strftime('%b')
day_of_mo   = slate_date.day
weekday     = WEEKDAY_NAMES[slate_date.weekday()]
game_count  = len(DATA.get('BP_Games', []))
build_time  = datetime.now(ZoneInfo('America/New_York')).strftime('%-I:%M %p ET')

print(f"Slate: {month_short} {day_of_mo} - Day {day_num} - {weekday} - {game_count} games")

def parse_hr_pct(val):
    if val is None: return 0
    s = str(val).replace('%','').replace('+','').strip()
    try: return int(float(s))
    except: return 0

def build_park_summary():
    parks = DATA.get('Park_Factors', [])
    if not parks:
        return "<p>Park data unavailable.</p>"
    ranked = sorted(parks, key=lambda p: parse_hr_pct(p.get('HR %')), reverse=True)
    boosters    = [(p, parse_hr_pct(p.get('HR %'))) for p in ranked if parse_hr_pct(p.get('HR %')) >= 6]
    suppressors = [(p, parse_hr_pct(p.get('HR %'))) for p in ranked if parse_hr_pct(p.get('HR %')) <= -12]
    lines = []
    volcanos = [(p, pct) for p, pct in boosters if pct >= 25]
    if volcanos:
        v_parts = [f"<strong>{p.get('Venue', p.get('Game','?'))} +{pct}% HR</strong> ({p.get('Game','')})" for p, pct in volcanos]
        lines.append("HR Volcano(s): " + ", ".join(v_parts) + ".")
    sec = [(p, pct) for p, pct in boosters if 6 <= pct < 25]
    if sec:
        sec_parts = [f"{p.get('Venue','?')} +{pct}% ({p.get('Game','')})" for p, pct in sec]
        lines.append("HR Boosters: " + ", ".join(sec_parts) + ".")
    if suppressors:
        sup_parts = [f"{p.get('Venue','?')} {pct}% ({p.get('Game','')})" for p, pct in suppressors]
        lines.append("HR Suppressed: " + ", ".join(sup_parts) + " -- fade HR alts here.")
    if not lines:
        lines.append("Neutral park slate -- no extreme HR environments today.")
    return (f"<p><strong>{game_count}-game {weekday} card (Day {day_num}).</strong> " + " ".join(lines) + "</p>")

def build_method_intro():
    if PROJECTED_MODE:
        return (
            f'<strong>Projected Mode is active for Day {day_num} ({month_short} {day_of_mo}).</strong> '
            'No workbook was uploaded, so the page is rebuilt from live BallparkPal projections, '
            'MLB schedule data, live streaks, and Baseball Savant contact metrics. '
            'Reconstructed boards carry a Projected Mode badge. Workbook-only Sweet Spot, Dimers, '
            'Best Spots, and Zone signals are withheld rather than approximated.'
        )
    parks = DATA.get('Park_Factors', [])
    ranked = sorted(parks, key=lambda p: parse_hr_pct(p.get('HR %')), reverse=True)
    top_venue = ranked[0].get('Venue','') if ranked else ''
    top_pct   = parse_hr_pct(ranked[0].get('HR %')) if ranked else 0
    top_game  = ranked[0].get('Game','') if ranked else ''
    volcano   = top_pct >= 25
    volcano_label = f"<strong>{top_venue} +{top_pct}% HR</strong> as the slate volcano ({top_game})" if volcano else f"<strong>{top_venue} +{top_pct}% HR</strong> as the top HR environment ({top_game})"
    suppressors = [(p, parse_hr_pct(p.get('HR %'))) for p in ranked if parse_hr_pct(p.get('HR %')) <= -15]
    sup_text = ""
    if suppressors:
        names = " / ".join(p.get('Venue','?') for p, _ in suppressors[:3])
        worst_pct = suppressors[-1][1] if suppressors else 0
        sup_text = f", and <strong>{names} all suppressed ({worst_pct}% HR or worse)</strong>"
    return (
        f'Every play on this site goes through a two-input filter. '
        f'<strong>Sweet Spot</strong> answers "is this a great HR environment for this hitter, right now?" '
        f'-- it does not care about price. '
        f'<strong>Dimers</strong> answers "what does the market think the chance is?" '
        f'-- it does not care about quality. '
        f'The app uses one to validate the other. Sweet Spot is the <strong>gate</strong>; '
        f'Dimers is the <strong>ranker</strong>. '
        f'Park Factors (stadium + day-of weather) act as a third overlay. '
        f'<strong>Day {day_num} ({month_short} {day_of_mo})</strong> is a full {game_count}-game '
        f'{weekday} card with {volcano_label}{sup_text}.'
    )

def replace_section(html, sec_id, new_content):
    pattern = re.compile(
        r'(?:<!--[^>]*-->\s*)?<section id="' + re.escape(sec_id) + r'"[\s\S]*?</section>\s*\n?',
        re.MULTILINE
    )
    m = pattern.search(html)
    if not m:
        return html, False
    return html[:m.start()] + new_content + '\n' + html[m.end():], True

html = re.sub(r'<title>MLB Slate[^<]*</title>', f'<title>MLB Slate - {month_short} {day_of_mo} - Day {day_num}</title>', html)
html = re.sub(r'<meta property="og:title" content="[^"]*">', f'<meta property="og:title" content="The Daily Slate -- {month_short} {day_of_mo} Day {day_num}">', html)
html = re.sub(r'<meta name="twitter:title" content="[^"]*">', f'<meta name="twitter:title" content="The Daily Slate -- {month_short} {day_of_mo} Day {day_num}">', html)
html = re.sub(r'<h1>\u26be[^<]*</h1>', f'<h1>\u26be {month_short} {day_of_mo} -- {weekday} Slate</h1>', html)
subtitle = (
    f'{game_count} Games - Day {day_num} - Projected Mode'
    if PROJECTED_MODE
    else f'{game_count} Games - Day {day_num} - Sweet Spot + Park Factors'
)
html = re.sub(r'<div class="subtitle-block">[^<]*</div>', f'<div class="subtitle-block">{subtitle}</div>', html)
html = re.sub(r'<div class="last-updated">.*?</div>', f'<div class="last-updated">{month_short} {day_of_mo} - <b>{build_time}</b> - Day {day_num} - {weekday} slate</div>', html)
html = re.sub(r'(<a href="#games">\U0001F3AE All )\d+( Game Write-Ups)', rf'\g<1>{game_count}\2', html)
html = re.sub(r'(Tap to expand - tier thresholds \+ )[A-Za-z]+ \d+ park notes', rf'\g<1>{month_short} {day_of_mo} park notes', html)
html = re.sub(r'<h4>[A-Za-z]+ \d+ Park Summary</h4>', f'<h4>{month_short} {day_of_mo} Park Summary</h4>', html)
html = re.sub(r'(<div class="tldr-box">)\s*<h4>[^<]*</h4>\s*<p>[\s\S]*?</p>\s*(</div>)', rf'<div class="tldr-box"><h4>{month_short} {day_of_mo} Park Summary</h4>{build_park_summary()}\2', html)
html = re.sub(r'<p class="method-intro">[\s\S]*?</p>', f'<p class="method-intro">{build_method_intro()}</p>', html, count=1)

print("  Updated header, titles, park summary")

PROJECTED_CSS = '''
/* PROJECTED MODE CSS START */
.projected-mode {
  --bg: #0d1117;
  --bg-grad-1: #102a35;
  --bg-grad-2: #172033;
  --bg-grad-3: #241f10;
  --surface: #101720;
  --surface-2: #14202b;
  --glass: rgba(103,232,249,0.08);
  --glass-strong: rgba(103,232,249,0.14);
  --glass-border: rgba(125,211,252,0.24);
  --glass-border-strong: rgba(251,191,36,0.32);
  --border: rgba(125,211,252,0.2);
  --accent: #22d3ee;
  --accent-soft: rgba(34,211,238,0.14);
  --gold: #fbbf24;
  --tier0: #67e8f9;
  --tier0-bg: rgba(103,232,249,0.13);
  --tier0-border: rgba(103,232,249,0.44);
  --tier0-solid: #102a35;
  --tier1: #fbbf24;
  --tier1-bg: rgba(251,191,36,0.12);
  --tier1-border: rgba(251,191,36,0.42);
  --tier1-solid: #2b2412;
}
.projected-mode .app-bar {
  border-bottom: 1px solid rgba(125,211,252,0.28);
  background: rgba(13,17,23,0.9);
}
.projected-mode .hero {
  border-bottom: 1px solid rgba(125,211,252,0.22);
  background: linear-gradient(180deg, rgba(34,211,238,0.08), rgba(251,191,36,0.04));
}
.projected-mode .game-header {
  border-color: rgba(125,211,252,0.22);
  background: linear-gradient(90deg, rgba(34,211,238,0.11), rgba(251,191,36,0.05));
}
.projected-mode .collapsible,
.projected-mode .game {
  border-radius: 8px;
  border-color: rgba(125,211,252,0.22);
  box-shadow: 0 16px 40px -26px rgba(34,211,238,0.55);
}
.projected-mode-banner {
  margin: 0;
  padding: 13px 18px;
  border-bottom: 1px solid rgba(251,191,36,0.35);
  background: linear-gradient(90deg, rgba(8,145,178,0.9), rgba(30,41,59,0.96));
  color: #f8fafc;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.35;
}
.projected-mode-banner small {
  display: block;
  margin-top: 2px;
  color: #cffafe;
  font-weight: 600;
}
.projected-section-badge {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 0 0 12px;
  padding: 9px 11px;
  border: 1px solid rgba(125,211,252,0.28);
  border-radius: 8px;
  background: rgba(8,145,178,0.1);
}
.projected-section-badge span {
  color: #67e8f9;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.08em;
}
.projected-section-badge small {
  color: var(--text-soft);
  font-size: 12px;
}
.unavailable-card {
  border: 1px dashed rgba(251,191,36,0.45);
  border-radius: 8px;
  background: rgba(251,191,36,0.08);
  padding: 16px;
}
.unavailable-card strong {
  color: #fbbf24;
  font-size: 14px;
}
.unavailable-card p {
  margin: 6px 0 0;
  color: var(--text-soft);
}
/* PROJECTED MODE CSS END */
'''

def apply_projected_theme(html):
    html = re.sub(
        r'\n?/\* PROJECTED MODE CSS START \*/[\s\S]*?/\* PROJECTED MODE CSS END \*/\n?',
        '\n',
        html,
    )
    html = re.sub(r'\n?<div class="projected-mode-banner">[\s\S]*?</div>\s*', '\n', html)
    if not PROJECTED_MODE:
        html = re.sub(r'<body class="projected-mode">', '<body>', html, count=1)
        return html
    html = html.replace('</style>', PROJECTED_CSS + '\n</style>', 1)
    html = re.sub(r'<body(?: class="[^"]*")?>', '<body class="projected-mode">', html, count=1)
    html = html.replace('Alignment — Sweet Spot Tier Logic', 'Projected Mode Alignment')
    html = html.replace('Tap to expand - tier thresholds + ' + f'{month_short} {day_of_mo} park notes', 'Tap to expand - reconstructed board boundaries')
    banner = (
        '<div class="projected-mode-banner">'
        '⚡ PROJECTED MODE — no workbook uploaded. Boards are built from BallparkPal + Baseball Savant. '
        'Rankings are model-derived; Sweet Spot / Dimers boards and some columns are unavailable today.'
        '<small>Upload the workbook to restore the full slate and Zone/Sweet Spot surfaces.</small>'
        '</div>\n'
    )
    return re.sub(r'(<body class="projected-mode">\s*)', r'\1' + banner, html, count=1)

SECTION_ORDER = [
    'headlines', 'park-board', 'games', 'matchup-spotlight',
    'k-board', 'sp-vuln-board', 'hr-board', 'oo5-board',
    'totals-board', 'nrfi-board', 'sb-board', 'doubles-board',
    'dfs-board', 'combos-k', 'combos-hrr', 'parlays',
    'conviction', 'skip'
]

for sec_id in SECTION_ORDER:
    if sec_id not in SECTIONS:
        print(f"  No built section for #{sec_id} -- skipping")
        continue
    html, ok = replace_section(html, sec_id, SECTIONS[sec_id])
    print(f"  {'OK' if ok else 'MISS'} #{sec_id}")

if 'sp-vuln-board' in SECTIONS and '<section id="sp-vuln-board"' not in html:
    pattern = re.compile(r'(<section id="k-board"[\s\S]*?</section>\s*\n)', re.MULTILINE)
    m = pattern.search(html)
    if m:
        html = html[:m.end()] + SECTIONS['sp-vuln-board'] + '\n' + html[m.end():]

html = apply_projected_theme(html)

tmp = INDEX_FILE + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(html)
os.replace(tmp, INDEX_FILE)

print(f"Done -- wrote {len(html):,} bytes to {INDEX_FILE}")
print(f"Day {day_num} - {month_short} {day_of_mo} - {weekday} - {game_count} games")
