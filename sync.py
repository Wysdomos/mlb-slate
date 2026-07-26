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

# ============================================================================
# PROJECTED MODE -- "INSTRUMENT" overhaul
# ----------------------------------------------------------------------------
# Everything here renders ONLY when PROJECTED_MODE is true. The CSS and the JS
# are both injected after the `if not PROJECTED_MODE: return html` guard in
# apply_projected_theme(), so a workbook-backed build stays byte-identical.
#
# Thesis: the workbook did not arrive, so the slate is flown on instruments.
# The language is a machined panel -- stepped plates, edge light, recessed
# data wells. Depth comes from luminance geometry, never from blur or gloss,
# because blur and gloss are exactly what vanish in sunlight on a phone.
# ============================================================================

PROJECTED_CSS = '''
/* PROJECTED MODE CSS START */

/* ---------------------------------------------------------------- tokens --
   Ice keys the material. --good/--bad/--hot/--warn/--cold/--info are
   deliberately NOT redefined: they live inside cells and carry park and stat
   meaning that has to survive the reskin. Steel is the quiet companion.
   Because the palette is now blue and --info/--cold are blue too, hue alone
   cannot say "projected" -- the mode signal is structural (see below).
   ------------------------------------------------------------------------ */
.projected-mode {
  /* Ice, not sky. The mode key is pushed colder and less saturated than
     --info/--cold (#56a8ff), which already means something inside cells --
     these have to read as two different materials, not one colour twice.
     The brand accent itself is green (#2de38f), so nothing here collides
     with it; the mode signal is carried structurally regardless. */
  --pm-key: #6fd7e9;
  --pm-key-lift: #a8e9f5;
  --pm-steel: #8fa6bd;
  --pm-frost: rgba(190,235,250,0.10);
  --pm-frost-strong: rgba(190,235,250,0.16);
  --pm-edge: rgba(190,235,250,0.09);
  --pm-edge-strong: rgba(190,235,250,0.14);
  --pm-hair: rgba(111,215,233,0.26);
  --pm-stripe: rgba(111,215,233,0.50);
  --pm-stripe-soft: rgba(111,215,233,0.10);
  --pm-spine-bg: #07222c;
  --pm-plate: #0d1621;
  --pm-plate-sunk: rgba(0,0,0,0.58);
  --pm-lip: #14232f;
  --pm-stamp-bg: #08222c;
  --pm-stamp-lift: #0d5f77;
  --pm-stamp-ink: #eefaff;
  --pm-stamp-soft: #a8dbe8;
  --pm-drop: 0 1px 2px rgba(0,0,0,0.46);
  --pm-searchbar-h: 60px;
  --pm-dock-lift: calc(var(--dock-h) + env(safe-area-inset-bottom, 0px));
  --pm-cordon: repeating-linear-gradient(135deg, var(--pm-stripe) 0 5px, transparent 5px 11px);
  --pm-wash: repeating-linear-gradient(135deg, var(--pm-stripe-soft) 0 7px, transparent 7px 17px);

  --bg: #0a1016;
  --bg-grad-1: #0c2029;
  --bg-grad-2: #0d1822;
  --bg-grad-3: #0a1f27;
  --surface: #0e1720;
  --surface-2: #132230;
  --glass: rgba(111,215,233,0.055);
  --glass-strong: rgba(111,215,233,0.11);
  --glass-elev: rgba(111,215,233,0.04);
  --glass-border: rgba(140,200,220,0.17);
  --glass-border-strong: rgba(140,200,220,0.28);
  --border: rgba(140,200,220,0.19);
  --accent: #6fd7e9;
  --accent-soft: rgba(111,215,233,0.13);
  --gold: #a8e9f5;
  --header-bg: rgba(10,16,22,0.92);
  --sheet-bg: #0d1720;

  /* A derived rank is not a graded rank: ice + steel instead of green + gold,
     AND a hairline rail instead of a filled band. */
  --tier0: #6fd7e9;
  --tier0-bg: rgba(111,215,233,0.10);
  --tier0-border: rgba(111,215,233,0.42);
  --tier0-solid: #0d2c38;
  --tier1: #8fa6bd;
  --tier1-bg: rgba(143,166,189,0.085);
  --tier1-border: rgba(143,166,189,0.36);
  --tier1-solid: #16202b;
  --pick-solid: #0d2c38;
}

/* Light gets a full design, not a leftover. Specificity (0,2,0) beats the
   block above regardless of source order, so the projected page stays
   readable in daylight -- which is where this page is actually read. */
[data-theme="light"] .projected-mode {
  --pm-key: #0b6981;
  --pm-key-lift: #085466;
  --pm-steel: #3d5468;
  --pm-frost: rgba(255,255,255,0.92);
  --pm-frost-strong: #ffffff;
  --pm-edge: rgba(255,255,255,0.9);
  --pm-edge-strong: #ffffff;
  --pm-hair: rgba(11,105,129,0.22);
  --pm-stripe: rgba(11,105,129,0.52);
  --pm-stripe-soft: rgba(11,105,129,0.09);
  --pm-spine-bg: #d3e9f0;
  --pm-plate: #ffffff;
  --pm-plate-sunk: rgba(12,52,68,0.14);
  --pm-lip: #eef4f8;
  --pm-stamp-bg: #07323f;
  --pm-stamp-lift: #0b6981;
  --pm-stamp-ink: #f2fbff;
  --pm-stamp-soft: #a8dbe8;
  --pm-drop: 0 1px 2px rgba(12,52,68,0.11);

  --bg: #eaf1f5;
  --bg-grad-1: #d9ecf2;
  --bg-grad-2: #e6eef4;
  --bg-grad-3: #e2f0f4;
  --surface: #ffffff;
  --surface-2: #eef4f8;
  --glass: rgba(255,255,255,0.78);
  --glass-strong: rgba(255,255,255,0.93);
  --glass-elev: rgba(255,255,255,0.68);
  --glass-border: rgba(16,58,76,0.14);
  --glass-border-strong: rgba(16,58,76,0.22);
  --border: rgba(16,58,76,0.16);
  --accent: #0b6981;
  --accent-soft: rgba(11,105,129,0.10);
  --gold: #085466;
  --text-dim: #4d5f6b;
  --header-bg: rgba(236,244,248,0.93);
  --sheet-bg: #f8fcfe;

  --tier0: #0b6981;
  --tier0-bg: rgba(11,105,129,0.09);
  --tier0-border: rgba(11,105,129,0.40);
  --tier0-solid: #dcedf3;
  --tier1: #3d5468;
  --tier1-bg: rgba(61,84,104,0.075);
  --tier1-border: rgba(61,84,104,0.34);
  --tier1-solid: #e4eaef;
  --pick-solid: #dcedf3;
}

/* --------------------------------------------------------- mode signal ---
   The palette is now cold blue, and the site's own --info/--cold are blue
   too, so hue cannot be trusted to say "projected". The signal is carried by
   structure that no colour choice can dilute: a fixed hatched spine down the
   left edge of the viewport, the same hatch closing the sticky header stack
   and marking every provenance chip, plus the stamp at the top.
   ------------------------------------------------------------------------ */
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

/* -------------------------------------------------------------- elevation --
   E1 shell -> E2 header lip (raised) -> E3 data plate (recessed).
   The recess is what reads as three-dimensional without any blur: the plate
   sits BELOW the chrome plane instead of floating above it. In light mode the
   edge light moves from the top of the step to the bottom, so the same
   geometry still reads against a light ground.
   ------------------------------------------------------------------------ */
.projected-mode main > section {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: inset 0 1px 0 var(--pm-edge), var(--pm-drop);
}
[data-theme="light"] .projected-mode main > section {
  box-shadow: inset 0 1px 0 var(--pm-edge-strong),
              inset 0 -1px 0 rgba(38,20,84,0.05),
              var(--pm-drop);
}
.projected-mode .game-header {
  background: var(--pm-lip);
  box-shadow: inset 0 1px 0 var(--pm-edge);
  min-height: 56px;
}
.projected-mode .collapsible.open > .game-header,
.projected-mode .game.open > .game-header {
  border-bottom: 1px solid var(--glass-border);
}
.projected-mode .table-wrap {
  background-color: var(--pm-plate);
  border: 1px solid var(--glass-border);
  box-shadow: inset 0 2px 6px -3px var(--pm-plate-sunk);
  /* local-attachment scroll shadow: the edge shading retracts only once the
     table is scrolled to that end, so a 13-column board announces its extra
     columns instead of hiding them off-screen */
  background-image:
    linear-gradient(to right, var(--pm-plate) 30%, rgba(0,0,0,0)),
    linear-gradient(to left,  var(--pm-plate) 30%, rgba(0,0,0,0)),
    linear-gradient(to right, var(--pm-plate-sunk), rgba(0,0,0,0)),
    linear-gradient(to left,  var(--pm-plate-sunk), rgba(0,0,0,0));
  background-position: left center, right center, left center, right center;
  background-repeat: no-repeat;
  background-size: 26px 100%, 26px 100%, 13px 100%, 13px 100%;
  background-attachment: local, local, scroll, scroll;
}
.projected-mode .game {
  background: var(--surface);
  border: 1px solid var(--glass-border);
  box-shadow: inset 0 1px 0 var(--pm-edge), var(--pm-drop);
}

/* ------------------------------------------------------------- the stamp --
   Inverts against the page in both themes: a lifted ice block on dark, a deep
   one on light. The inversion, not the hue, is what survives a half-second
   glance in the sun.
   ------------------------------------------------------------------------ */
.projected-mode-banner {
  position: relative;
  margin: 0;
  /* the stamp always inverts against the ground -- a lifted ice block on the
     dark theme, a deep one on light. That inversion, not the hue, is what
     survives a half-second glance in the sun now that the palette is blue. */
  background-image: linear-gradient(100deg, var(--pm-stamp-lift) 0%, var(--pm-stamp-bg) 78%);
  padding: calc(env(safe-area-inset-top, 0px) + 12px)
           16px 12px
           calc(env(safe-area-inset-left, 0px) + 17px);
  border-bottom: 2px solid var(--pm-key);
  background: var(--pm-stamp-bg);
  color: var(--pm-stamp-ink);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.10);
}
.projected-mode-banner .pm-stamp {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  margin: 0;
  font-family: var(--font-display);
  font-weight: 400;
  line-height: 0.84;
}
.projected-mode-banner .pm-word {
  font-size: clamp(35px, 10.6vw, 46px);
  letter-spacing: 2.5px;
  color: var(--pm-stamp-ink);
}
.projected-mode-banner .pm-mode {
  font-size: clamp(18px, 5.4vw, 24px);
  letter-spacing: 4px;
  color: var(--pm-key-lift);
}
[data-theme="light"] .projected-mode .pm-mode { color: #a8e9f5; }
.projected-mode-banner .pm-status {
  margin: 7px 0 0;
  font-family: var(--font-mono);
  font-size: 10.5px; letter-spacing: 1.7px; text-transform: uppercase;
  color: var(--pm-stamp-soft);
}
.projected-mode-banner .pm-body {
  margin: 7px 0 0;
  max-width: 62ch;
  font-size: 12.5px; font-weight: 500; line-height: 1.42;
  color: var(--pm-stamp-ink);
}
.projected-mode-banner small {
  display: block;
  margin-top: 5px;
  font-size: 12px; font-weight: 600; line-height: 1.42;
  color: var(--pm-stamp-soft);
}

/* --------------------------------------------- withheld-boards disclosure --
   One collapsed line, never silent: the count is always on screen and the
   names are one tap away. This is the floor that stops a projected page from
   passing itself off as a complete slate.
   ------------------------------------------------------------------------ */
.pm-withheld {
  margin: 9px 0 0;
  border: 1px solid rgba(255,255,255,0.17);
  border-radius: 12px;
  background: rgba(0,0,0,0.20);
  overflow: hidden;
}
[data-theme="light"] .projected-mode .pm-withheld {
  border-color: rgba(255,255,255,0.26);
  background: rgba(0,0,0,0.16);
}
.pm-withheld-btn {
  display: flex; align-items: center; gap: 9px;
  width: 100%; min-height: 44px;
  padding: 10px 13px;
  background: none; border: 0;
  color: var(--pm-stamp-ink);
  font-family: var(--font-body);
  font-size: 13px; font-weight: 700;
  text-align: left; cursor: pointer;
}
.pm-withheld-btn .pm-count {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 25px; height: 25px; padding: 0 7px;
  border-radius: 7px;
  background: var(--pm-key-lift);
  color: #1a0a36;
  font-family: var(--font-display); font-size: 16px; letter-spacing: 0.5px;
}
[data-theme="light"] .projected-mode .pm-withheld-btn .pm-count {
  background: #a8e9f5; color: #04222b;
}
.pm-withheld-btn .pm-caret { margin-left: auto; font-size: 11px; transition: transform .26s; }
.pm-withheld-btn[aria-expanded="true"] .pm-caret { transform: rotate(180deg); }
.pm-withheld-body { display: none; padding: 0 13px 12px; }
.pm-withheld-body.open { display: block; }
.pm-withheld-body ul { margin: 0; padding: 0; list-style: none; }
.pm-withheld-body li {
  position: relative;
  padding: 8px 0 8px 15px;
  font-size: 12.5px; line-height: 1.4;
  color: var(--pm-stamp-ink);
  border-top: 1px solid rgba(255,255,255,0.11);
}
.pm-withheld-body li::before {
  content: ""; position: absolute; left: 2px; top: 15px;
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--pm-key-lift);
}
[data-theme="light"] .projected-mode .pm-withheld-body li::before { background: #a8e9f5; }
.pm-withheld-note {
  margin: 10px 0 0;
  font-size: 12px; line-height: 1.45;
  color: var(--pm-stamp-soft);
}

/* -------------------------------------------------------- board  grammar --
   One grammar: rail + eyebrow + title + summary strip + plate. Only the rail
   and the eyebrow change between families, so board types stay instantly
   distinguishable while obviously belonging to one system.
   ------------------------------------------------------------------------ */
.projected-mode main > section[data-board] > .game-header { position: relative; }
.projected-mode main > section[data-board] > .game-header::before {
  content: "";
  position: absolute; left: 0; top: 10px; bottom: 10px;
  width: 3px; border-radius: 0 3px 3px 0;
}
.projected-mode section[data-board="derived"] > .game-header::before { background: var(--pm-key); }
.projected-mode section[data-board="pitcher"] > .game-header::before {
  background: linear-gradient(180deg, var(--pm-key) 0 50%, var(--pm-steel) 50% 100%);
}
.projected-mode section[data-board="context"] > .game-header::before { background: var(--pm-steel); }

/* The real "PROJECTED MODE" chip is lifted out of the board body and into the
   header by tuckNotes(), so a board is marked derived before you reach a
   single number. It replaces the generated-content eyebrow the previous
   revision used -- real DOM, announced by screen readers, and one label in
   the header instead of two. Board family is carried by the rail colour. */
.projected-mode .game-header-text .pm-chip {
  display: inline-block;
  margin: 0 0 4px;
  padding: 2px 7px;
  border: 1px solid var(--tier0-border);
  border-radius: 5px;
  background: var(--accent-soft);
  color: var(--pm-key);
  font-family: var(--font-mono);
  font-size: 10px; font-weight: 500; letter-spacing: 1.2px;
  white-space: nowrap;
}
.projected-mode .game-title {
  font-family: var(--font-body);
  font-size: 15.5px; font-weight: 700; line-height: 1.25;
}
/* the collapsed header already states what the board holds -- give that line
   room to work so a board can be read without being opened at all */
.projected-mode .game-tag {
  margin-top: 5px;
  font-family: var(--font-mono);
  font-size: 11.5px; line-height: 1.45; letter-spacing: 0.1px;
  color: var(--text-dim);
}

/* headline cards: no shell, no plate. Editorial, not tabular. */
.projected-mode #headlines {
  background: none; border: 0; box-shadow: none;
  border-radius: 0;
}
.projected-mode .headline-card {
  position: relative;
  display: block;
  margin: 0 0 10px;
  padding: 14px 15px 14px 17px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  box-shadow: inset 0 1px 0 var(--pm-edge), var(--pm-drop);
}
.projected-mode .headline-card::before {
  content: ""; position: absolute; left: 0; top: 12px; bottom: 12px;
  width: 3px; border-radius: 0 3px 3px 0;
  background: var(--pm-key);
}
.projected-mode .hc-title {
  margin-bottom: 5px;
  font-family: var(--font-mono);
  font-size: 10.5px; font-weight: 500; letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--pm-key);
}
.projected-mode .headline-card p {
  margin: 0;
  font-size: 14px; line-height: 1.5;
  color: var(--text);
}

/* -------------------------------------------------------------- the plate --
   Density is solved with structure, never by shrinking type: body cells go UP
   from 12.5px to 13px, because 12.5px is not readable in direct sun.
   ------------------------------------------------------------------------ */
.projected-mode tbody td {
  padding: 5px 9px;
  font-size: 13px;
  line-height: 1.26;
  border-bottom: 1px solid var(--glass-border);
}
/* the name cell is the one that wraps; give it room before it does, and keep
   its second line tight, so a row costs two lines instead of three */
.projected-mode table.stick2 td:nth-child(2) { max-width: 168px; }
.projected-mode tbody td span { line-height: 1.25; }
.projected-mode thead th {
  background: var(--pm-lip);
  font-family: var(--font-mono);
  font-size: 10.5px; font-weight: 500; letter-spacing: 0.9px;
  color: var(--text-dim);
  padding: 7px 9px;
  box-shadow: inset 0 -1px 0 var(--glass-border-strong);
}
.projected-mode thead th:first-child,
.projected-mode table.stick2 thead th:nth-child(2) { background: var(--pm-lip); }

/* derived tiers: hairline rail, no filled band */
.projected-mode tr.row-tier0 td,
.projected-mode tr.row-tier1 td { background: transparent; }
.projected-mode tbody tr.row-tier0 td:first-child { background: var(--tier0-bg); }
.projected-mode tbody tr.row-tier1 td:first-child { background: var(--tier1-bg); }
.projected-mode table.stick2 tr.row-tier0 td:nth-child(2) { background: var(--tier0-bg); }
.projected-mode table.stick2 tr.row-tier1 td:nth-child(2) { background: var(--tier1-bg); }
.projected-mode tbody tr:nth-child(even) td { background-color: rgba(255,255,255,0.02); }
[data-theme="light"] .projected-mode tbody tr:nth-child(even) td { background-color: rgba(38,20,84,0.024); }

/* Bebas is reserved for rank numerals -- the one place a display face earns
   its keep here, because a rank is scanned, not read */
.projected-mode section[data-board="derived"] tbody td:first-child {
  font-family: var(--font-display);
  font-size: 19px;
  letter-spacing: 0.5px;
  text-align: center;
  color: var(--text-soft);
}
.projected-mode section[data-board="derived"] tbody tr.row-tier0 td:first-child { color: var(--pm-key); }

/* ----------------------------------------------------------- more rows ----
   The previous revision capped boards at 12 rows behind a "Show all" tap.
   That was wrong for this brief: the plate is already a scroll container with
   its own max-height, so capping shrank the container AND added a tap -- it
   showed strictly less, which is the opposite of what was asked for. The cap
   is gone. Instead the plate is taller and the row rhythm is tighter, so more
   rows land on one screen with nothing hidden.
   ------------------------------------------------------------------------ */
.projected-mode .table-wrap { max-height: min(78vh, 760px); }

/* ---------------------------------------------------------- search dock ---
   Sticky in the thumb zone, directly above the tab dock, always reachable.
   It drives the page's existing filter engine instead of duplicating it.
   ------------------------------------------------------------------------ */
body.projected-mode {
  padding-bottom: calc(var(--dock-h) + var(--pm-searchbar-h) + env(safe-area-inset-bottom, 0px) + 18px);
}
.pm-searchbar {
  position: fixed;
  left: 0; right: 0;
  bottom: var(--pm-dock-lift);
  z-index: 68;
  display: flex; align-items: center; gap: 8px;
  height: var(--pm-searchbar-h);
  padding-left: calc(env(safe-area-inset-left, 0px) + 12px);
  padding-right: calc(env(safe-area-inset-right, 0px) + 12px);
  background: var(--header-bg);
  border-top: 1px solid var(--glass-border);
  box-shadow: 0 -6px 18px -12px rgba(0,0,0,0.7);
}
.pm-search-field { position: relative; flex: 1; display: flex; align-items: center; }
.pm-search-field .pm-mag {
  position: absolute; left: 11px;
  font-size: 14px; pointer-events: none; opacity: 0.8;
}
.pm-searchbar input {
  width: 100%; height: 44px;
  padding: 0 44px 0 34px;
  border: 1px solid var(--glass-border-strong);
  border-radius: 12px;
  background: var(--pm-plate);
  box-shadow: inset 0 2px 5px -3px var(--pm-plate-sunk);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 16px; /* 16px keeps iOS from zooming the page on focus */
  -webkit-appearance: none;
  appearance: none;
}
.pm-searchbar input::placeholder { color: var(--text-dim); }
.pm-searchbar input::-webkit-search-cancel-button { display: none; }
.pm-searchbar input:focus {
  outline: none;
  border-color: var(--pm-key);
  box-shadow: inset 0 2px 5px -3px var(--pm-plate-sunk), 0 0 0 2px var(--accent-soft);
}
.pm-search-clear {
  position: absolute; right: 2px;
  width: 44px; height: 44px;
  display: none; align-items: center; justify-content: center;
  background: none; border: 0;
  color: var(--text-dim); font-size: 15px;
  cursor: pointer;
}
.pm-searchbar.has-q .pm-search-clear { display: flex; }
.pm-search-count {
  flex: 0 0 auto;
  padding: 0 2px;
  font-family: var(--font-mono);
  font-size: 11.5px; letter-spacing: 0.2px;
  white-space: nowrap;
  color: var(--pm-key);
}
.pm-search-count:empty { display: none; }
.pm-search-count::after { content: " hits"; color: var(--text-dim); }
body.sheet-open .pm-searchbar { opacity: 0; pointer-events: none; }

.projected-mode #scroll-thumb {
  background: rgba(111,215,233,0.34);
  border-color: rgba(111,215,233,0.62);
}
.projected-mode #scroll-thumb.dragging { background: rgba(111,215,233,0.85); }
[data-theme="light"] .projected-mode #scroll-thumb {
  background: rgba(11,105,129,0.30);
  border-color: rgba(11,105,129,0.60);
}

/* ------------------------------------------------------------ tap size --
   One thumb, standing up, often gloved. Every control the mode owns is at
   least 44px; the rail grows to fit rather than the chips shrinking to fit.
   ------------------------------------------------------------------------ */
.projected-mode { --rail-h: 54px; }
.projected-mode .rail .chip { height: 44px; min-width: 44px; justify-content: center; }
.projected-mode .icon-btn { width: 44px; height: 44px; }
.projected-mode .chevron { width: 36px; height: 36px; }
.projected-mode .text-btn { min-height: 44px; }

/* the persistent chrome carries the mode too, so it is never off-screen */
.projected-mode .app-bar,
.projected-mode .rail-wrap { border-bottom: 1px solid var(--pm-hair); }
.projected-mode .rail .chip.active {
  box-shadow: 0 0 12px rgba(111,215,233,0.22), inset 0 0 8px rgba(111,215,233,0.07);
  text-shadow: 0 0 12px rgba(111,215,233,0.55);
}
[data-theme="light"] .projected-mode .rail .chip.active {
  box-shadow: inset 0 0 0 1px var(--tier0-border);
  text-shadow: none;
}
@media (prefers-reduced-motion: reduce) {
  .pm-withheld-btn .pm-caret { transition: none; }
}
/* ---------------------------------------------------------- provenance ----
   Every reconstructed board states what it was rebuilt from. That sentence
   matters, but it is not what you opened the board to read -- so it is tucked
   under the plate as a footnote instead of standing between you and the rows.
   ------------------------------------------------------------------------ */
.pm-note {
  margin: 10px 0 2px;
  padding: 11px 12px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--glass-elev);
  box-shadow: inset 0 1px 0 var(--pm-edge);
}
.pm-note > * + * { margin-top: 8px; }
.pm-note p {
  margin: 0 !important;
  font-size: 12.5px !important;
  line-height: 1.5;
  color: var(--text-soft) !important;
}
.pm-note a { font-size: 12.5px; }
.projected-section-badge {
  display: block;
  margin: 0;
  padding: 0;
  border: 0;
  background: none;
  border-radius: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-soft);
}
.projected-section-badge span {
  display: inline-block;
  margin-right: 7px;
  padding: 2px 7px;
  border: 1px solid var(--tier0-border);
  border-radius: 5px;
  background: var(--accent-soft);
  color: var(--pm-key);
  font-family: var(--font-mono);
  font-size: 10px; font-weight: 500; letter-spacing: 1.2px;
  vertical-align: 1px;
}
.projected-section-badge small {
  font-size: 12.5px;
  color: var(--text-soft);
}
/* PROJECTED MODE CSS END */
'''

PROJECTED_JS = '''
<!-- PROJECTED JS START -->
<script>
/* Projected Mode interaction. Vanilla, no dependencies, no network calls. */
(function () {
  var ROW_CAP = 12;

  /* ---- put the data first ---------------------------------------------
     Each board opens with a provenance badge and an explainer paragraph. Both
     are worth keeping, neither is what you tapped the board to see, so they
     move below the plate as a footnote. Text is moved, never altered.
     -------------------------------------------------------------------- */
  function tuckNotes() {
    var inners = document.querySelectorAll('main .game-body-inner');
    for (var i = 0; i < inners.length; i++) {
      var inner = inners[i];
      var plate = inner.querySelector('.table-wrap');
      if (!plate) continue;
      var move = [];
      for (var n = inner.firstElementChild; n && n !== plate; n = n.nextElementSibling) {
        if (n.classList.contains('projected-section-badge') || n.tagName === 'P') move.push(n);
      }
      if (!move.length) continue;

      /* lift the compact PROJECTED MODE chip into the board header, so the
         board is marked derived without scrolling past the numbers */
      var badge = inner.querySelector('.projected-section-badge');
      var chip = badge ? badge.querySelector('span') : null;
      var host = inner.closest ? inner.closest('.collapsible, .game') : null;
      var slot = host ? host.querySelector('.game-header .game-header-text') : null;
      if (chip && slot && !slot.querySelector('.pm-chip')) {
        chip.className = 'pm-chip';
        slot.insertBefore(chip, slot.firstChild);
      }

      var note = document.createElement('div');
      note.className = 'pm-note';
      for (var k = 0; k < move.length; k++) note.appendChild(move[k]);
      inner.appendChild(note);
    }
  }

  /* ---- withheld-boards disclosure ------------------------------------- */
  function wireWithheld() {
    var btn = document.getElementById('pmWithheldBtn');
    if (!btn) return;
    var body = document.getElementById('pmWithheldBody');
    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
      if (body) body.classList.toggle('open', !open);
    });
  }

  /* ---- search bar -----------------------------------------------------
     The page already ships a filter engine behind the dock: it indexes every
     matchable node once, debounces at 130ms, and filters by toggling a single
     class -- it never rebuilds the DOM. Standing up a second engine would put
     two of them in a fight over the same rows, so this bar drives that one.
     Per keystroke the work here is one value copy and one event dispatch; the
     debounce and the filtering pass stay exactly where they already were.
     -------------------------------------------------------------------- */
  function wireSearch() {
    var bar = document.getElementById('pmSearchBar');
    if (!bar) return;
    var input = document.getElementById('pmSearchInput');
    var clear = document.getElementById('pmSearchClear');
    var count = document.getElementById('pmSearchCount');
    var real = document.getElementById('searchInput');
    var realClear = document.getElementById('searchClear');
    var realCount = document.getElementById('searchCount');

    function paint() { bar.classList.toggle('has-q', !!input.value); }

    input.addEventListener('input', function () {
      paint();
      if (!real) return;
      real.value = input.value;
      real.dispatchEvent(new Event('input', { bubbles: true }));
    });

    if (clear) {
      clear.addEventListener('click', function () {
        input.value = '';
        paint();
        if (realClear) { realClear.click(); }
        else if (real) { real.value = ''; real.dispatchEvent(new Event('input', { bubbles: true })); }
        input.focus();
      });
    }

    /* keep both inputs in step if the dock sheet gets used instead */
    if (real) {
      real.addEventListener('input', function () {
        if (input.value !== real.value) { input.value = real.value; paint(); }
      });
    }

    /* mirror the engine's own result count -- observer, not a poll */
    if (realCount && count && window.MutationObserver) {
      new MutationObserver(function () {
        var m = (realCount.textContent || '').match(/^([0-9]+)\\s+match/);
        count.textContent = m ? m[1] : '';
      }).observe(realCount, { childList: true, characterData: true, subtree: true });
    }
  }

  function init() { tuckNotes(); wireWithheld(); wireSearch(); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>
<!-- PROJECTED JS END -->
'''

# Which visual family each board belongs to. Anything not listed keeps the
# base styling -- the explainer sections (alignment, methodology, tip-jar)
# are documentation, not boards, and must not wear a board eyebrow.
BOARD_KIND = {
    'headlines':     'headlines',
    'games':         'games',
    'hr-board':      'derived',
    'oo5-board':     'derived',
    'k-board':       'pitcher',
    'park-board':    'context',
    'totals-board':  'context',
    'nrfi-board':    'context',
    'sb-board':      'context',
    'doubles-board': 'context',
    'dfs-board':     'context',
    'combos-k':      'context',
}


def apply_projected_theme(html):
    # Strip whatever a previous build injected, so switching modes is clean.
    html = re.sub(
        r'\n?/\* PROJECTED MODE CSS START \*/[\s\S]*?/\* PROJECTED MODE CSS END \*/\n?',
        '\n',
        html,
    )
    html = re.sub(
        r'\n?<!-- PROJECTED JS START -->[\s\S]*?<!-- PROJECTED JS END -->\n?',
        '\n',
        html,
    )
    html = re.sub(
        r'\n?<!-- PROJECTED CHROME START -->[\s\S]*?<!-- PROJECTED CHROME END -->\s*',
        '\n',
        html,
    )
    html = re.sub(r'\n?<div class="pm-searchbar" id="pmSearchBar">[\s\S]*?</div>\s*(?=<nav class="dock")', '', html)
    html = re.sub(r'\n?<div class="projected-mode-banner">[\s\S]*?</div>\s*', '\n', html)

    # Everything past this point is projected-only. A workbook build returns
    # here having only stripped markers a workbook build never emits, so its
    # output is byte-identical to a build that never knew about any of this.
    if not PROJECTED_MODE:
        html = re.sub(r'<body class="projected-mode">', '<body>', html, count=1)
        return html

    html = html.replace('</style>', PROJECTED_CSS + '\n</style>', 1)
    html = re.sub(r'<body(?: class="[^"]*")?>', '<body class="projected-mode">', html, count=1)
    html = html.replace('Alignment — Sweet Spot Tier Logic', 'Projected Mode Alignment')
    # The projected builders drop the board emoji that the workbook builders
    # emit. They are wayfinding -- the owner scans for them -- so put them back
    # exactly as the workbook boards carry them.
    for plain, iconed in (
        ('<div class="game-title">Top 50 HR Board</div>',
         '<div class="game-title">🏆 Top 50 HR Board</div>'),
        ('<div class="game-title">Top 50 Hits Board</div>',
         '<div class="game-title">☄️ Top 50 Hits Board</div>'),
    ):
        html = html.replace(plain, iconed, 1)
    html = html.replace('Tap to expand - tier thresholds + ' + f'{month_short} {day_of_mo} park notes', 'Tap to expand - reconstructed board boundaries')

    # -- lift the withheld boards out of the page, keeping their names -----
    withheld = []

    def _drop(m):
        title = re.search(r'<div class="game-title">([^<]*)</div>', m.group(0))
        if title:
            withheld.append(title.group(1).strip())
        return ''

    html = re.sub(
        r'(?:<!-- PROJECTED UNAVAILABLE -->\s*)?'
        r'<section id="[a-z0-9-]+" class="collapsible projected-unavailable">[\s\S]*?</section>\s*',
        _drop,
        html,
    )

    # -- tag each surviving board with its family, for the card grammar ----
    def _tag(m):
        attrs = m.group(1)
        sec_id = re.search(r'id="([^"]+)"', attrs)
        kind = BOARD_KIND.get(sec_id.group(1)) if sec_id else None
        if kind is None or 'data-board=' in attrs:
            return m.group(0)
        return '<section ' + attrs.strip() + f' data-board="{kind}">'

    html = re.sub(r'<section ([^>]*)>', _tag, html)

    print(f"  Projected: {len(withheld)} withheld board(s) folded into one disclosure")

    items = ''.join('<li>%s</li>' % name for name in withheld)
    n = len(withheld)
    plural = 'board' if n == 1 else 'boards'
    chrome = (
        '<!-- PROJECTED CHROME START -->'
        '<div class="projected-mode-banner" role="note" aria-label="Projected Mode">'
        '<p class="pm-stamp"><span class="pm-word">PROJECTED</span><span class="pm-mode">MODE</span></p>'
        '<p class="pm-status">Reconstructed &middot; not graded</p>'
        '<p class="pm-body">No workbook uploaded. Boards are built from BallparkPal + Baseball Savant, '
        'so rankings are model-derived. Sweet Spot / Dimers boards and some columns are unavailable today.</p>'
        '<small>Upload the workbook to restore the full slate and Zone/Sweet Spot surfaces.</small>'
        '<div class="pm-withheld">'
        '<button type="button" class="pm-withheld-btn" id="pmWithheldBtn"'
        ' aria-expanded="false" aria-controls="pmWithheldBody">'
        f'<span class="pm-count">{n}</span>'
        f'<span>{plural} withheld today</span>'
        '<span class="pm-caret" aria-hidden="true">&#9662;</span>'
        '</button>'
        '<div class="pm-withheld-body" id="pmWithheldBody">'
        f'<ul>{items}</ul>'
        '<p class="pm-withheld-note">These need the workbook. They are held back rather than estimated.</p>'
        '</div>'
        '</div>'
        '</div>'
        '<!-- PROJECTED CHROME END -->\n'
    )
    html = html.replace('<body class="projected-mode">', '<body class="projected-mode">' + chrome, 1)

    # -- the search bar lives in the thumb zone, above the tab dock --------
    searchbar = (
        '<div class="pm-searchbar" id="pmSearchBar">'
        '<label class="pm-search-field">'
        '<span class="pm-mag" aria-hidden="true">&#128269;</span>'
        '<input type="search" id="pmSearchInput" placeholder="Filter players, teams, pitchers"'
        ' autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"'
        ' aria-label="Filter the slate">'
        '<button type="button" class="pm-search-clear" id="pmSearchClear" aria-label="Clear filter">&#10005;</button>'
        '</label>'
        '<span class="pm-search-count" id="pmSearchCount" aria-live="polite"></span>'
        '</div>\n'
    )
    html = html.replace('<nav class="dock"', searchbar + '<nav class="dock"', 1)

    return html.replace('</body>', PROJECTED_JS + '\n</body>', 1)

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
