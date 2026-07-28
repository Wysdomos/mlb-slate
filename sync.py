"""
sync.py -- Generic daily sync for MLB Slate (any date, any game count)
Reads:   built_sections.json  (or SECTIONS_FILE env var)
         day_data.json         (or DATA_FILE env var)
Updates: index.html            (or INDEX_FILE env var)
"""

import html as html_lib, json, re, os
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

SECTIONS_FILE = os.environ.get('SECTIONS_FILE', 'built_sections.json')
DATA_FILE     = os.environ.get('DATA_FILE',     'day_data.json')
INDEX_FILE    = os.environ.get('INDEX_FILE',    'index.html')
BUILD_STAMP_FILE = os.environ.get('BUILD_STAMP_FILE', 'build-stamp.json')

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

BUILT_AT_UTC = datetime.now(timezone.utc).isoformat(timespec='seconds')
slate_date  = get_slate_date()
day_num     = (slate_date - OPENING_DAY).days + 1
month_short = slate_date.strftime('%b')
day_of_mo   = slate_date.day
weekday     = WEEKDAY_NAMES[slate_date.weekday()]
game_count  = len(DATA.get('BP_Games', []))
build_time  = datetime.now(ZoneInfo('America/New_York')).strftime('%-I:%M %p ET')
BUILD_STAMP = f'{slate_date.isoformat()}|{"projected" if PROJECTED_MODE else "workbook"}|{BUILT_AT_UTC}'

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

def insert_section_after(html, after_sec_id, new_content):
    new_id = None
    id_match = re.search(r'<section id="([^"]+)"', new_content)
    if id_match:
        new_id = id_match.group(1)
    if f'<section id="{after_sec_id}"' not in html:
        return html, False
    if new_id and f'<section id="{new_id}"' in html:
        return html, True
    pattern = re.compile(
        r'(<section id="' + re.escape(after_sec_id) + r'"[\s\S]*?</section>\s*\n?)',
        re.MULTILINE
    )
    m = pattern.search(html)
    if not m:
        return html, False
    return html[:m.end()] + new_content + '\n' + html[m.end():], True

def insert_section_after_main(html, new_content):
    id_match = re.search(r'<section id="([^"]+)"', new_content)
    if id_match and f'<section id="{id_match.group(1)}"' in html:
        return html, True
    m = re.search(r'<main>\s*', html)
    if not m:
        return html, False
    return html[:m.end()] + '\n' + new_content + '\n' + html[m.end():], True

def ensure_board_link(html, sec_id, label, after_sec_id):
    if f'href="#{sec_id}"' in html:
        return html
    anchor = f'        <a href="#{sec_id}"><span>{label}</span> <span class="arrow">›</span></a>\n'
    pattern = re.compile(
        r'(\s*<a href="#' + re.escape(after_sec_id) + r'"><span>[^<]*</span> <span class="arrow">›</span></a>\n?)'
    )
    return pattern.sub(r'\1' + anchor, html, count=1)

def ensure_rail_chip(html, sec_id, emoji, label, after_sec_id):
    if f"['{sec_id}'" in html:
        return html
    line = f"  ['{sec_id}',          '{emoji}', '{label}'],\n"
    pattern = re.compile(
        r"(\s*\['" + re.escape(after_sec_id) + r"',\s*'[^']*',\s*'[^']*'\],\n?)"
    )
    return pattern.sub(r'\1' + line, html, count=1)

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
/* ---------------------------------------------------------------------------
   HEADER FIX (Projected Mode only)

   (a) Safe-area collision. The banner is the first element on the page, so it
       -- not the app bar -- is what sits under the iOS status bar. It had no
       top inset, so "PROJECTED MODE" rendered over the clock and battery.
       Measured at 390px with a 59px inset: banner text began at y=13.

   (b) Dead gap. The app bar carries padding-top: env(safe-area-inset-top) so
       its wordmark clears the notch once the bar sticks to the top. At scroll
       0 the bar is NOT stuck -- the banner is above it -- so that reserve
       renders as a blank band. Measured gap from banner bottom to wordmark: 69px.

       Fix without touching the app bar or adding JS: let the banner overlap
       the bar's reserve. The reserve is empty by definition, so nothing is
       occluded, the gap closes to zero, and the reserve still does its job the
       instant the bar pins to the top and the banner has scrolled away.
   --------------------------------------------------------------------------- */
.projected-mode-banner {
  position: relative;
  z-index: 61;                 /* paints over the app bar's empty inset reserve */
  padding-top: calc(env(safe-area-inset-top, 0px) + 13px);
  padding-left: calc(env(safe-area-inset-left, 0px) + 18px);
  padding-right: calc(env(safe-area-inset-right, 0px) + 18px);
  margin-bottom: calc(-1 * env(safe-area-inset-top, 0px));
}

/* ---------------------------------------------------------------------------
   WITHHELD BOARDS DISCLOSURE
   Replaces the per-section "unavailable" placeholder cards with one aggregate
   row. The count is always on screen and the names are one tap away -- between
   this and the banner, a projected page can never pass as a graded slate.
   Styled with main's projected tokens: cyan on slate, 8px radii.
   --------------------------------------------------------------------------- */
.pm-withheld {
  margin-top: 11px;
  border: 1px solid rgba(125,211,252,0.3);
  border-radius: 8px;
  background: rgba(8,145,178,0.18);
  overflow: hidden;
}
.pm-withheld-btn {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-height: 44px;
  padding: 9px 12px;
  background: none;
  border: 0;
  color: #f8fafc;
  font-family: inherit;
  font-size: 13px;
  font-weight: 800;
  text-align: left;
  cursor: pointer;
}
.pm-withheld-btn .pm-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 7px;
  border-radius: 6px;
  background: #67e8f9;
  color: #06283a;
  font-size: 13px;
  font-weight: 900;
}
.pm-withheld-btn .pm-caret {
  margin-left: auto;
  font-size: 11px;
  color: #cffafe;
  transition: transform .25s;
}
.pm-withheld-btn[aria-expanded="true"] .pm-caret { transform: rotate(180deg); }
.pm-withheld-body { display: none; padding: 0 12px 11px; }
.pm-withheld-body.open { display: block; }
.pm-withheld-body ul { margin: 0; padding: 0; list-style: none; }
.pm-withheld-body li {
  position: relative;
  padding: 7px 0 7px 14px;
  border-top: 1px solid rgba(125,211,252,0.22);
  color: #f1f5f9;
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.4;
}
.pm-withheld-body li::before {
  content: "";
  position: absolute;
  left: 1px;
  top: 14px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #67e8f9;
}
.pm-withheld-note {
  margin: 9px 0 0;
  color: #cffafe;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.45;
}
@media (prefers-reduced-motion: reduce) {
  .pm-withheld-btn .pm-caret { transition: none; }
}
/* ===========================================================================
   LIGHT THEME FOR PROJECTED MODE

   Root cause this fixes: the block above defines ONE fixed palette with no
   theme selectors at all. The site runs on data-theme="light"/"dark" driven by
   slateTheme in localStorage, and because `.projected-mode` (0,1,0) is
   injected after `[data-theme="light"]` (0,1,0), it won the cascade in BOTH
   themes -- so toggling to light flipped the site's text to near-black while
   these overrides held the surfaces dark. Table cells measured 1.0:1.

   Scoped as `[data-theme="light"] .projected-mode` (0,2,0) so it beats the
   dark block regardless of source order, and driven by the same attribute the
   in-app toggle writes. Deliberately NOT prefers-color-scheme: that follows
   the OS rather than the user's toggle and would desync all over again.

   These values are designed, not auto-inverted. The ground is a cold blue-white
   (blue channel runs 10-32 above red) rather than the muddy grey an inversion
   produces, so the icy character survives into light. Cyan deepens to #0e7490
   and amber to #8a5406 -- both clear WCAG AA on white and on the page ground,
   which is what daylight on a phone actually needs.
   =========================================================================== */
[data-theme="light"] .projected-mode {
  --bg: #eaf2f7;
  --bg-grad-1: #d5ecf5;
  --bg-grad-2: #e4edf6;
  --bg-grad-3: #f7f1e4;
  --surface: #ffffff;
  --surface-2: #f1f7fb;
  --glass: rgba(14,116,144,0.055);
  --glass-strong: rgba(14,116,144,0.11);
  --glass-elev: rgba(255,255,255,0.66);
  --glass-border: rgba(12,74,110,0.16);
  --glass-border-strong: rgba(161,98,7,0.34);
  --border: rgba(12,74,110,0.18);
  --accent: #0e7490;
  --accent-soft: rgba(14,116,144,0.10);
  --gold: #a16207;
  --tier0: #0e7490;
  --tier0-bg: rgba(14,116,144,0.10);
  --tier0-border: rgba(14,116,144,0.42);
  --tier0-solid: #dcf0f7;
  --tier1: #8a5406;
  --tier1-bg: rgba(161,98,7,0.11);
  --tier1-border: rgba(161,98,7,0.42);
  --tier1-solid: #f6edd8;
  --pick-solid: #dcf0f7;
  --header-bg: rgba(234,242,247,0.88);
  --sheet-bg: #f7fbfd;
  /* one step darker than the stock light theme's #5d6e79: dim text still has
     to survive being read in direct sun */
  --text-dim: #4e5f6b;
}

/* The rules below hard-code colours rather than reading a variable, so each
   one needs its own light value or it stays dark on a light page. */
[data-theme="light"] .projected-mode .app-bar {
  border-bottom: 1px solid rgba(12,74,110,0.22);
  background: rgba(234,242,247,0.9);
}
[data-theme="light"] .projected-mode .hero {
  border-bottom: 1px solid rgba(12,74,110,0.16);
  background: linear-gradient(180deg, rgba(14,116,144,0.07), rgba(161,98,7,0.035));
}
[data-theme="light"] .projected-mode .game-header {
  border-color: rgba(12,74,110,0.16);
  background: linear-gradient(90deg, rgba(14,116,144,0.08), rgba(161,98,7,0.035));
}
[data-theme="light"] .projected-mode .collapsible,
[data-theme="light"] .projected-mode .game {
  border-color: rgba(12,74,110,0.16);
  box-shadow: 0 10px 26px -20px rgba(12,74,110,0.5);
}
[data-theme="light"] .projected-section-badge {
  border-color: rgba(12,74,110,0.22);
  background: rgba(14,116,144,0.08);
}
[data-theme="light"] .projected-section-badge span { color: #0b5f78; }
[data-theme="light"] .unavailable-card {
  border-color: rgba(161,98,7,0.5);
  background: rgba(161,98,7,0.09);
}
[data-theme="light"] .unavailable-card strong { color: #8a5406; }

/* The banner and its disclosure keep the same deep teal block in BOTH themes.
   That is deliberate: it inverts against the light page exactly as it stands
   out on the dark one, so the single loudest "this is Projected Mode" mark
   never changes character when the theme is toggled. */
/* PROJECTED MODE CSS END */
'''

PROJECTED_JS = '''
<!-- PROJECTED JS START -->
<script>
/* Withheld-boards disclosure. Vanilla, no dependencies, no network. */
(function () {
  function wire() {
    var btn = document.getElementById('pmWithheldBtn');
    if (!btn) return;
    var body = document.getElementById('pmWithheldBody');
    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
      if (body) body.classList.toggle('open', !open);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
</script>
<!-- PROJECTED JS END -->
'''


def apply_projected_theme(html):
    workbook_alignment_title = 'Alignment — Sweet Spot Tier Logic'
    projected_alignment_title = 'Projected Mode Alignment'
    workbook_alignment_tag = 'Tap to expand - tier thresholds + ' + f'{month_short} {day_of_mo} park notes'
    projected_alignment_tag = 'Tap to expand - reconstructed board boundaries'
    html = re.sub(
        r'\n?/\* PROJECTED MODE CSS START \*/[\s\S]*?/\* PROJECTED MODE CSS END \*/\n?',
        '\n',
        html,
    )
    html = re.sub(
        r'\n?<!-- PROJECTED CHROME START -->[\s\S]*?<!-- PROJECTED CHROME END -->\s*',
        '\n',
        html,
    )
    html = re.sub(
        r'\n?<!-- PROJECTED JS START -->[\s\S]*?<!-- PROJECTED JS END -->\n?',
        '\n',
        html,
    )
    html = re.sub(r'\n?<div class="projected-mode-banner">[\s\S]*?</div>\s*', '\n', html)
    if not PROJECTED_MODE:
        html = re.sub(r'<body class="projected-mode">', '<body>', html, count=1)
        html = html.replace(projected_alignment_title, workbook_alignment_title)
        html = html.replace(projected_alignment_tag, workbook_alignment_tag)
        return html
    html = html.replace('</style>', PROJECTED_CSS + '\n</style>', 1)
    html = re.sub(r'<body(?: class="[^"]*")?>', '<body class="projected-mode">', html, count=1)
    html = html.replace(workbook_alignment_title, projected_alignment_title)
    html = html.replace(workbook_alignment_tag, projected_alignment_tag)

    # -- Pull the workbook-only placeholder sections out of the page, keeping
    #    their names for the aggregate disclosure. Only sections marked
    #    `projected-unavailable` are removed: those are the boards that cannot
    #    be reconstructed without the workbook. Boards that ran and simply had
    #    no qualifying output (the correlation parlay boards' "No qualifying
    #    correlation stack" cards) are a different statement and are left alone
    #    -- folding them in here would report a working board as missing.
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
    print(f"  Projected: {len(withheld)} withheld board(s) -> one disclosure")

    items = ''.join('<li>%s</li>' % name for name in withheld)
    n = len(withheld)
    disclosure = (
        '<div class="pm-withheld">'
        '<button type="button" class="pm-withheld-btn" id="pmWithheldBtn"'
        ' aria-expanded="false" aria-controls="pmWithheldBody">'
        f'<span class="pm-count">{n}</span>'
        f'<span>{"board" if n == 1 else "boards"} withheld today</span>'
        '<span class="pm-caret" aria-hidden="true">&#9662;</span>'
        '</button>'
        '<div class="pm-withheld-body" id="pmWithheldBody">'
        f'<ul>{items}</ul>'
        '<p class="pm-withheld-note">These need the workbook. They are held back '
        'rather than estimated.</p>'
        '</div>'
        '</div>'
    ) if n else ''

    banner = (
        '<!-- PROJECTED CHROME START -->'
        '<div class="projected-mode-banner">'
        '⚡ PROJECTED MODE — no workbook uploaded. Boards are built from BallparkPal + Baseball Savant. '
        'Rankings are model-derived; Sweet Spot / Dimers boards and some columns are unavailable today.'
        '<small>Upload the workbook to restore the full slate and Zone/Sweet Spot surfaces.</small>'
        + disclosure +
        '</div>'
        '<!-- PROJECTED CHROME END -->\n'
    )
    html = html.replace('<body class="projected-mode">', '<body class="projected-mode">' + banner, 1)
    return html.replace('</body>', PROJECTED_JS + '\n</body>', 1)

STALE_CSS = '''
<style id="cache-refresh-css">
.stale-banner {
  position: fixed; left: 12px; right: 12px; bottom: calc(var(--dock-h) + env(safe-area-inset-bottom, 0px) + 12px);
  z-index: 75; display: none; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 12px; border: 1px solid var(--tier0-border); border-radius: 12px;
  background: var(--header-bg); color: var(--text); box-shadow: var(--shadow);
  -webkit-backdrop-filter: blur(18px) saturate(1.4); backdrop-filter: blur(18px) saturate(1.4);
  cursor: pointer;
}
.stale-banner.show { display: flex; }
.stale-banner button { min-width: 44px; min-height: 44px; }
.stale-banner .stale-dismiss {
  width: 44px; border: 0; background: transparent; color: var(--text-dim); font-size: 20px; cursor: pointer;
}
</style>
'''

STALE_JS = '''
<script id="cache-refresh-js">
(function(){
  var stampMeta = document.querySelector('meta[name="daily-slate-build-stamp"]');
  var currentStamp = stampMeta ? stampMeta.getAttribute('content') : '';
  function refreshWithBust() {
    window.location.href = window.location.pathname + '?v=' + Date.now();
  }
  var brandRefresh = document.getElementById('brandRefresh');
  if (brandRefresh) {
    brandRefresh.addEventListener('click', function(event){
      event.preventDefault();
      event.stopPropagation();
      refreshWithBust();
    });
  }
  var banner = document.getElementById('staleBanner');
  var dismiss = document.getElementById('staleDismiss');
  if (banner) banner.addEventListener('click', function(event){
    if (event.target && event.target.id === 'staleDismiss') return;
    refreshWithBust();
  });
  if (dismiss && banner) dismiss.addEventListener('click', function(event){
    event.stopPropagation();
    banner.classList.remove('show');
  });
  if (!currentStamp || !banner || !window.fetch) return;
  fetch('build-stamp.json?v=' + Date.now(), { cache: 'no-store' })
    .then(function(resp){ return resp.ok ? resp.json() : null; })
    .then(function(data){
      if (data && data.stamp && data.stamp !== currentStamp) banner.classList.add('show');
    })
    .catch(function(){});
})();
</script>
'''

def apply_cache_refresh(html):
    stamp_meta = f'<meta name="daily-slate-build-stamp" content="{html_lib.escape(BUILD_STAMP, quote=True)}">'
    html = re.sub(r'\s*<meta name="daily-slate-build-stamp" content="[^"]*">\n?', '\n', html)
    html = html.replace('</head>', stamp_meta + '\n</head>', 1)

    html = re.sub(r'\s*<style id="cache-refresh-css">[\s\S]*?</style>\n?', '\n', html)
    html = html.replace('</head>', STALE_CSS + '\n</head>', 1)

    stale_banner = (
        '<div class="stale-banner" id="staleBanner" role="status" aria-live="polite">'
        '<span>Updated slate — tap to reload</span>'
        '<button class="stale-dismiss" id="staleDismiss" type="button" aria-label="Dismiss">×</button>'
        '</div>'
    )
    html = re.sub(r'\s*<div class="stale-banner" id="staleBanner"[\s\S]*?</div>\n?', '\n', html)
    html = html.replace('<nav class="dock" aria-label="App actions">', stale_banner + '\n<nav class="dock" aria-label="App actions">', 1)

    html = re.sub(r'\s*<button class="dock-btn refresh-btn" id="dockRefresh"[\s\S]*?</button>\n?', '\n', html)

    html = re.sub(r'\s*<script id="cache-refresh-js">[\s\S]*?</script>\n?', '\n', html)
    return html.replace('</body>', STALE_JS + '\n</body>', 1)

SECTION_ORDER = [
    'headlines', 'park-board', 'games', 'matchup-spotlight',
    'k-board', 'sp-vuln-board', 'hr-board', 'oo5-board',
    'tb-board', 'totals-board', 'nrfi-board',
    'dfs-board', 'two-way-ks', 'traffic-jam', 'double-barrel',
    'cruise-control', 'yard-sale',
    'conviction', 'skip'
]
SECTION_INSERT_AFTER = {
    'headlines': None,
    'park-board': 'headlines',
    'games': 'park-board',
    'matchup-spotlight': 'games',
    'k-board': 'matchup-spotlight',
    'sp-vuln-board': 'k-board',
    'hr-board': 'sp-vuln-board',
    'oo5-board': 'hr-board',
    'tb-board': 'oo5-board',
    'totals-board': 'tb-board',
    'nrfi-board': 'totals-board',
    'dfs-board': 'nrfi-board',
    'two-way-ks': 'dfs-board',
    'traffic-jam': 'two-way-ks',
    'double-barrel': 'traffic-jam',
    'cruise-control': 'double-barrel',
    'yard-sale': 'cruise-control',
    'conviction': 'yard-sale',
    'skip': 'conviction',
}
RETIRED_SECTION_IDS = ('sb-board', 'doubles-board', 'combos-k', 'combos-hrr', 'parlays')

def remove_section(html, sec_id):
    pattern = re.compile(
        r'(?:<!--[^>]*-->\s*)?<section id="' + re.escape(sec_id) + r'"[\s\S]*?</section>\s*\n?',
        re.MULTILINE
    )
    return pattern.sub('', html)

def remove_retired_nav(html, sec_id):
    html = re.sub(
        r'\s*<a href="#' + re.escape(sec_id) + r'"><span>[^<]*</span> <span class="arrow">›</span></a>\n?',
        '\n',
        html,
    )
    html = re.sub(
        r"\s*\['" + re.escape(sec_id) + r"',\s*'[^']*',\s*'[^']*'\],\n?",
        '\n',
        html,
    )
    return html

for sec_id in SECTION_ORDER:
    if sec_id not in SECTIONS:
        print(f"  No built section for #{sec_id} -- skipping")
        continue
    html, ok = replace_section(html, sec_id, SECTIONS[sec_id])
    if not ok:
        anchor = SECTION_INSERT_AFTER.get(sec_id)
        if anchor is None:
            html, ok = insert_section_after_main(html, SECTIONS[sec_id])
            anchor_label = '<main>'
        else:
            html, ok = insert_section_after(html, anchor, SECTIONS[sec_id])
            anchor_label = f'#{anchor}'
        if ok:
            print(f"::warning::sync.py restored missing section #{sec_id} after {anchor_label}")
        else:
            print(f"::warning::sync.py could not restore missing section #{sec_id}; insert anchor {anchor_label} was unavailable")
    print(f"  {'OK' if ok else 'MISS'} #{sec_id}")

html = ensure_board_link(html, 'tb-board', '📏 Total Bases Board', 'oo5-board')
html = ensure_rail_chip(html, 'tb-board', '📏', 'TB', 'oo5-board')
html = ensure_board_link(html, 'two-way-ks', "⚡ Two-Way K's", 'dfs-board')
html = ensure_board_link(html, 'traffic-jam', '🚦 Traffic Jam', 'two-way-ks')
html = ensure_board_link(html, 'double-barrel', '🎯 Double Barrel', 'traffic-jam')
html = ensure_board_link(html, 'cruise-control', '🛳️ Cruise Control', 'double-barrel')
html = ensure_board_link(html, 'yard-sale', '💣 Yard Sale', 'cruise-control')
html = ensure_rail_chip(html, 'two-way-ks', '⚡', 'K2', 'dfs-board')
html = ensure_rail_chip(html, 'traffic-jam', '🚦', 'Jam', 'two-way-ks')
html = ensure_rail_chip(html, 'double-barrel', '🎯', 'Hit2', 'traffic-jam')
html = ensure_rail_chip(html, 'cruise-control', '🛳️', 'Cruise', 'double-barrel')
html = ensure_rail_chip(html, 'yard-sale', '💣', 'Yard', 'cruise-control')

for sec_id in RETIRED_SECTION_IDS:
    html = remove_section(html, sec_id)
    html = remove_retired_nav(html, sec_id)
    print(f"  retired #{sec_id}: removed rendered section and nav links")

html = apply_projected_theme(html)
html = apply_cache_refresh(html)

tmp = INDEX_FILE + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(html)
os.replace(tmp, INDEX_FILE)

with open(BUILD_STAMP_FILE, 'w', encoding='utf-8') as f:
    json.dump({
        'stamp': BUILD_STAMP,
        'slate_date': slate_date.isoformat(),
        'mode': 'projected' if PROJECTED_MODE else 'workbook',
        'built_at_utc': BUILT_AT_UTC,
    }, f, ensure_ascii=False, indent=2)

print(f"Done -- wrote {len(html):,} bytes to {INDEX_FILE}")
print(f"Wrote build stamp -> {BUILD_STAMP_FILE}: {BUILD_STAMP}")
print(f"Day {day_num} - {month_short} {day_of_mo} - {weekday} - {game_count} games")
