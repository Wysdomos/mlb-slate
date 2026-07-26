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
/* ==========================================================================
   PROJECTED MODE -- "Cordon" skin
   --------------------------------------------------------------------------
   Thesis: this page is a reconstruction, so it is CORDONED, not recolored.
   One hazard hatch, drawn at four scales, marks every reconstructed surface:
     8px  fixed spine down the left edge of the viewport (never scrolls away)
     ---  the iOS status-bar inset, filled rather than left blank
     4px  rule closing the sticky header stack
     5px  edge on every projected badge and every held-back card
   Violet carries the mode because no other signal on this page uses it --
   green/gold/red/orange all already mean something about a play.
   Tiers drop to violet + steel: these ranks are derived, so they must not
   wear the same green a Sweet Spot grade wears.
   ========================================================================== */
.projected-mode {
  /* --- mode tokens --- */
  --pm-key: #b98cff;
  --pm-key-2: #8ea6c8;
  --pm-stripe: rgba(185,140,255,0.58);
  --pm-stripe-soft: rgba(185,140,255,0.10);
  --pm-spine-bg: #170a2c;
  --pm-edge: rgba(185,140,255,0.30);
  --pm-stamp-bg: #2a1152;
  --pm-stamp-ink: #f4eeff;
  --pm-stamp-soft: #d9c6ff;
  --pm-badge-bg: rgba(185,140,255,0.07);
  --pm-held-bg: #150f24;
  --pm-cordon: repeating-linear-gradient(135deg, var(--pm-stripe) 0 5px, transparent 5px 11px);
  --pm-wash: repeating-linear-gradient(135deg, var(--pm-stripe-soft) 0 7px, transparent 7px 17px);

  /* --- system tokens re-pointed at the mode palette --- */
  --bg: #0a0713;
  --bg-grad-1: #1b0f31;
  --bg-grad-2: #120c22;
  --bg-grad-3: #1d1233;
  --surface: #120d1d;
  --surface-2: #181128;
  --glass: rgba(185,140,255,0.07);
  --glass-strong: rgba(185,140,255,0.13);
  --glass-elev: rgba(185,140,255,0.05);
  --glass-border: rgba(185,140,255,0.18);
  --glass-border-strong: rgba(185,140,255,0.30);
  --border: rgba(185,140,255,0.20);
  --accent: #b98cff;
  --accent-soft: rgba(185,140,255,0.14);
  --gold: #c8a6ff;
  --tier0: #b98cff;
  --tier0-bg: rgba(185,140,255,0.13);
  --tier0-border: rgba(185,140,255,0.44);
  --tier0-solid: #1e1236;
  --tier1: #8ea6c8;
  --tier1-bg: rgba(142,166,200,0.12);
  --tier1-border: rgba(142,166,200,0.40);
  --tier1-solid: #161c26;
  --pick-solid: #1e1236;
  --header-bg: rgba(10,7,19,0.82);
  --sheet-bg: #100b1c;
}

/* Light theme keeps its own surfaces. Specificity (0,2,0) beats (0,1,0),
   so this wins over the block above regardless of source order -- the
   projected page stays readable in daylight instead of inheriting dark
   panels underneath light-theme text. */
[data-theme="light"] .projected-mode {
  --pm-key: #5b21b6;
  --pm-key-2: #3f5570;
  --pm-stripe: rgba(91,33,182,0.55);
  --pm-stripe-soft: rgba(91,33,182,0.09);
  --pm-spine-bg: #e4d8f8;
  --pm-edge: rgba(91,33,182,0.24);
  --pm-stamp-bg: #4c1d95;
  --pm-stamp-ink: #f7f3ff;
  --pm-stamp-soft: #d6c4f5;
  --pm-badge-bg: rgba(91,33,182,0.06);
  --pm-held-bg: #f4f0fa;

  /* one step darker than the stock light theme's #5d6e79: the projected
     ground is a touch deeper, and dim text has to stay legible in sun */
  --text-dim: #55646e;

  --bg: #efeaf7;
  --bg-grad-1: #e5daf7;
  --bg-grad-2: #eae5f4;
  --bg-grad-3: #f2ecfa;
  --surface: #ffffff;
  --surface-2: #f7f3fc;
  --glass: rgba(255,255,255,0.74);
  --glass-strong: rgba(255,255,255,0.9);
  --glass-elev: rgba(255,255,255,0.62);
  --glass-border: rgba(48,20,92,0.14);
  --glass-border-strong: rgba(48,20,92,0.22);
  --border: rgba(48,20,92,0.16);
  --accent: #5b21b6;
  --accent-soft: rgba(91,33,182,0.10);
  --gold: #6d28d9;
  --tier0: #5b21b6;
  --tier0-bg: rgba(91,33,182,0.10);
  --tier0-border: rgba(91,33,182,0.40);
  --tier0-solid: #e9e0f9;
  --tier1: #3f5570;
  --tier1-bg: rgba(63,85,112,0.10);
  --tier1-border: rgba(63,85,112,0.38);
  --tier1-solid: #e4e9ef;
  --pick-solid: #e9e0f9;
  --header-bg: rgba(243,239,250,0.84);
  --sheet-bg: #fbf9fe;
}

/* --- Signature: the cordon spine. Fixed, so it is on screen at every
       scroll position. Sits above the sticky header (60) and below the
       dock (70) and the sheet layers (80/90). --- */
.projected-mode::before {
  content: "";
  position: fixed;
  top: 0;
  bottom: 0;
  left: env(safe-area-inset-left, 0px);
  width: 8px;
  z-index: 65;
  pointer-events: none;
  background: var(--pm-cordon), var(--pm-spine-bg);
}

/* The status-bar inset is dead space on an iPhone. Fill it with the hatch so
   the cordon is the very first thing on the screen, above even the wordmark.
   Collapses to 0 height where there is no inset, so nothing is drawn on
   desktop. Only the banner does this -- the app bar reserves the same inset
   but is not pinned to the top at scroll 0, and hatching its reserve would
   paint a stray band mid-page. */
.projected-mode-banner::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: env(safe-area-inset-top, 0px);
  background: var(--pm-cordon), var(--pm-spine-bg);
  pointer-events: none;
}

/* Close the sticky header stack with the same hatch, so the cordon reads
   as an L even when the banner has scrolled away. */
.projected-mode .rail-wrap { border-bottom: none; }
.projected-mode .rail-wrap::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: -4px;
  height: 4px;
  background: var(--pm-cordon), var(--pm-spine-bg);
  pointer-events: none;
}
.projected-mode .app-bar {
  position: sticky;
  border-bottom: 1px solid var(--pm-edge);
}
.projected-mode .rail .chip.active {
  box-shadow: 0 0 14px rgba(185,140,255,0.25), inset 0 0 8px rgba(185,140,255,0.08);
  text-shadow: 0 0 12px rgba(185,140,255,0.6);
}
[data-theme="light"] .projected-mode .rail .chip.active {
  box-shadow: inset 0 0 0 1px var(--tier0-border);
  text-shadow: none;
}
.projected-mode #scroll-thumb {
  background: rgba(185,140,255,0.35);
  border-color: rgba(185,140,255,0.65);
}
.projected-mode #scroll-thumb.dragging { background: rgba(185,140,255,0.85); }
[data-theme="light"] .projected-mode #scroll-thumb {
  background: rgba(91,33,182,0.30);
  border-color: rgba(91,33,182,0.6);
}
[data-theme="light"] .projected-mode #scroll-thumb.dragging { background: rgba(91,33,182,0.85); }

/* --- The stamp. It always inverts against the page: a light block on the
       dark theme, a deep block on the light theme. That inversion, not the
       hue, is what survives half a second in sunlight. --- */
.projected-mode-banner {
  position: relative;
  margin: 0;
  padding: calc(env(safe-area-inset-top, 0px) + 13px)
           16px 13px
           calc(env(safe-area-inset-left, 0px) + 18px);
  border-bottom: 2px solid var(--pm-key);
  background-color: var(--pm-stamp-bg);
  background-image: var(--pm-wash);
  color: var(--pm-stamp-ink);
}
.projected-mode-banner .pm-stamp {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  margin: 0;
  font-family: var(--font-display);
  font-weight: 400;
  line-height: 0.84;
}
.projected-mode-banner .pm-word {
  font-size: clamp(36px, 11vw, 48px);
  letter-spacing: 2.5px;
  color: var(--pm-stamp-ink);
}
.projected-mode-banner .pm-mode {
  font-size: clamp(19px, 5.6vw, 25px);
  letter-spacing: 4px;
  color: var(--pm-key);
}
[data-theme="light"] .projected-mode .pm-mode { color: #c4a5ff; }
.projected-mode-banner .pm-status {
  margin: 7px 0 0;
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 1.7px;
  text-transform: uppercase;
  color: var(--pm-stamp-soft);
}
.projected-mode-banner .pm-body {
  margin: 8px 0 0;
  max-width: 62ch;
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.45;
  color: var(--pm-stamp-ink);
}
.projected-mode-banner small {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--pm-stamp-soft);
}

/* --- Per-section marks. Same hatch, 5px, on the leading edge. --- */
.projected-section-badge {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 0 0 12px;
  padding: 9px 12px 9px 17px;
  border: 1px solid var(--pm-edge);
  border-left: 0;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: var(--pm-badge-bg);
  overflow: hidden;
}
.projected-section-badge::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 5px;
  background: var(--pm-cordon), var(--pm-spine-bg);
}
.projected-section-badge span {
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 1.5px;
  color: var(--pm-key);
}
.projected-section-badge small {
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-soft);
}

/* Header tags: mono for the machine-built boards, mono for the held ones.
   The board itself keeps the house shape -- only the mode chrome changes. */
.projected-mode .reconstructed-board .game-tag,
.projected-mode .projected-unavailable .game-tag {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 1.1px;
  text-transform: uppercase;
}
.projected-mode .reconstructed-board .game-tag { color: var(--pm-key); }
.projected-mode .projected-unavailable .game-tag { color: var(--pm-key-2); }
.projected-mode .projected-unavailable .game-title { color: var(--text-soft); }

/* --- Held-back sections. Not an error state: no dashed border, no warning
       colour, no apology. A solid, fully built panel wearing the same cordon
       edge as every other reconstructed surface -- the slot is reserved for
       the workbook, not broken. The panel is deliberately left un-hatched
       inside: hatching the field would read as struck through. --- */
.unavailable-card {
  position: relative;
  padding: 16px 16px 16px 20px;
  border: 1px solid var(--pm-edge);
  border-radius: var(--radius-sm);
  background: var(--pm-held-bg);
  overflow: hidden;
}
.unavailable-card::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 5px;
  background: var(--pm-cordon), var(--pm-spine-bg);
}
.unavailable-card strong {
  display: block;
  margin-bottom: 5px;
  font-size: 13.5px;
  font-weight: 800;
  letter-spacing: 0.2px;
  color: var(--text);
}
.unavailable-card p {
  margin: 0;
  max-width: 62ch;
  font-size: 13px;
  line-height: 1.6;
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
    html = re.sub(
        r'\n?<!-- PROJECTED BANNER START -->[\s\S]*?<!-- PROJECTED BANNER END -->\s*',
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
    # Stamp, then status, then the facts, then the one action that fixes it.
    # No nested <div> -- keeps the banner strippable by a non-greedy match.
    banner = (
        '<!-- PROJECTED BANNER START -->'
        '<div class="projected-mode-banner" role="note" aria-label="Projected Mode">'
        '<p class="pm-stamp"><span class="pm-word">PROJECTED</span><span class="pm-mode">MODE</span></p>'
        '<p class="pm-status">Reconstructed &middot; not graded</p>'
        '<p class="pm-body">No workbook uploaded. Boards are built from BallparkPal + Baseball Savant, '
        'so rankings are model-derived. Sweet Spot / Dimers boards and some columns are unavailable today.</p>'
        '<small>Upload the workbook to restore the full slate and Zone/Sweet Spot surfaces.</small>'
        '</div>'
        '<!-- PROJECTED BANNER END -->\n'
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
