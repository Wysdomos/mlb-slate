“””
sync.py — Generic daily sync for MLB Slate (any date, any game count)

Reads:   built_sections.json  (or SECTIONS_FILE env var)
day_data.json         (or DATA_FILE env var)
Updates: index.html            (or INDEX_FILE env var)

What it does:

1. Detects today’s date and game count from the data
1. Updates all day-specific text (title, meta, h1, subtitle, last-updated)
1. Generates a dynamic park summary from Park_Factors
1. Replaces all 18 data-driven sections with freshly built content
   “””

import json, re, os
from datetime import datetime, date, timezone

# ── Config ────────────────────────────────────────────────────────────────────

SECTIONS_FILE = os.environ.get(‘SECTIONS_FILE’, ‘built_sections.json’)
DATA_FILE     = os.environ.get(‘DATA_FILE’,     ‘day_data.json’)
INDEX_FILE    = os.environ.get(‘INDEX_FILE’,    ‘index.html’)

# MLB 2026 Opening Day — used to compute “Day N”

OPENING_DAY = date(2026, 3, 28)

WEEKDAY_NAMES = [‘Monday’,‘Tuesday’,‘Wednesday’,‘Thursday’,‘Friday’,‘Saturday’,‘Sunday’]

# ── Load files ────────────────────────────────────────────────────────────────

SECTIONS = json.load(open(SECTIONS_FILE, encoding=‘utf-8’))
DATA     = json.load(open(DATA_FILE,     encoding=‘utf-8’))

with open(INDEX_FILE, encoding=‘utf-8’) as f:
html = f.read()

print(f”Loaded {INDEX_FILE}: {len(html):,} bytes”)

# ── Derive slate date ─────────────────────────────────────────────────────────

def get_slate_date():
for row in DATA.get(‘BP_Games’, []):
raw = str(row.get(‘GameDate’, ‘’))[:10]
try:
return datetime.strptime(raw, ‘%Y-%m-%d’).date()
except:
pass
for row in DATA.get(‘Park_Factors’, []):
raw = str(row.get(‘Date’, ‘’))[:10]
try:
return datetime.strptime(raw, ‘%Y-%m-%d’).date()
except:
pass
return date.today()

slate_date  = get_slate_date()
day_num     = (slate_date - OPENING_DAY).days + 1
month_short = slate_date.strftime(’%b’)         # “May”
day_of_mo   = slate_date.day                    # 12
weekday     = WEEKDAY_NAMES[slate_date.weekday()]
game_count  = len(DATA.get(‘BP_Games’, []))
build_time  = datetime.now(timezone.utc).strftime(’%-I:%M %p UTC’)

print(f”Slate: {month_short} {day_of_mo} · Day {day_num} · {weekday} · {game_count} games”)

# ── Park factor helpers ───────────────────────────────────────────────────────

def parse_hr_pct(val):
“”“Parse ‘+29%’ or -23 → integer.”””
if val is None: return 0
s = str(val).replace(’%’,’’).replace(’+’,’’).strip()
try: return int(float(s))
except: return 0

def build_park_summary():
parks = DATA.get(‘Park_Factors’, [])
if not parks:
return “<p>Park data unavailable.</p>”

```
# Sort by HR%
ranked = sorted(parks, key=lambda p: parse_hr_pct(p.get('HR %')), reverse=True)

boosters   = [(p, parse_hr_pct(p.get('HR %'))) for p in ranked if parse_hr_pct(p.get('HR %')) >= 6]
suppressors= [(p, parse_hr_pct(p.get('HR %'))) for p in ranked if parse_hr_pct(p.get('HR %')) <= -12]
neutrals   = [(p, parse_hr_pct(p.get('HR %'))) for p in ranked
              if -12 < parse_hr_pct(p.get('HR %')) < 6]

lines = []

# Volcanos first
volcanos = [(p, pct) for p, pct in boosters if pct >= 25]
if volcanos:
    v_parts = []
    for p, pct in volcanos:
        v_parts.append(f"<strong>{p.get('Venue', p.get('Game','?'))} +{pct}% HR 🌋</strong> ({p.get('Game','')})")
    lines.append("🌋 <strong>HR Volcano(s):</strong> " + ", ".join(v_parts) + ".")

# Secondary boosters
sec = [(p, pct) for p, pct in boosters if 6 <= pct < 25]
if sec:
    sec_parts = [f"{p.get('Venue','?')} +{pct}% ({p.get('Game','')})" for p, pct in sec]
    lines.append("⬆️ <strong>HR Boosters:</strong> " + ", ".join(sec_parts) + ".")

# Suppressors
if suppressors:
    sup_parts = [f"{p.get('Venue','?')} {pct}% ({p.get('Game','')})"
                 for p, pct in suppressors]
    lines.append("⬇️ <strong>HR Suppressed:</strong> " + ", ".join(sup_parts) + " — fade HR alts here.")

if not lines:
    lines.append(f"Neutral park slate — no extreme HR environments today.")

return (f"<p><strong>{game_count}-game {weekday} card (Day {day_num}).</strong> "
        + " ".join(lines) + "</p>")
```

# ── Build methodology intro ───────────────────────────────────────────────────

def build_method_intro():
parks = DATA.get(‘Park_Factors’, [])
ranked = sorted(parks, key=lambda p: parse_hr_pct(p.get(‘HR %’)), reverse=True)

```
top_venue = ranked[0].get('Venue','') if ranked else ''
top_pct   = parse_hr_pct(ranked[0].get('HR %')) if ranked else 0
top_game  = ranked[0].get('Game','') if ranked else ''
volcano   = top_pct >= 25
volcano_label = f"<strong>{top_venue} +{top_pct}% HR</strong> as the slate volcano ({top_game})" if volcano \
                else f"<strong>{top_venue} +{top_pct}% HR</strong> as the top HR environment ({top_game})"

suppressors = [(p, parse_hr_pct(p.get('HR %'))) for p in ranked if parse_hr_pct(p.get('HR %')) <= -15]
sup_text = ""
if suppressors:
    names = " / ".join(p.get('Venue','?') for p, _ in suppressors[:3])
    pcts  = " to ".join(str(pct)+"%" for _, pct in suppressors[-1:] + suppressors[:1] if _ is not None)
    # just list names and lowest pct
    worst_pct = suppressors[-1][1] if suppressors else 0
    sup_text = (f", and <strong>{names} all suppressed"
                f" ({worst_pct}% HR or worse)</strong>")

return (
    f'Every play on this site goes through a two-input filter. '
    f'<strong>Sweet Spot</strong> answers "is this a great HR environment for this hitter, right now?" '
    f'— it doesn\'t care about price. '
    f'<strong>Dimers</strong> answers "what does the market think the chance is?" '
    f'— it doesn\'t care about quality. '
    f'The app uses one to validate the other. Sweet Spot is the <strong>gate</strong>; '
    f'Dimers is the <strong>ranker</strong>. '
    f'Park Factors (stadium + day-of weather) act as a third overlay. '
    f'<strong>Day {day_num} ({month_short} {day_of_mo})</strong> is a full {game_count}-game '
    f'{weekday} card with {volcano_label}{sup_text}.'
)
```

# ── Section replacement ───────────────────────────────────────────────────────

def replace_section(html, sec_id, new_content):
“”“Replace <section id="X">…</section> with new content.”””
pattern = re.compile(
r’(?:<!--[^>]*-->\s*)?<section id=”’ + re.escape(sec_id) + r’”[\s\S]*?</section>\s*\n?’,
re.MULTILINE
)
m = pattern.search(html)
if not m:
return html, False
return html[:m.start()] + new_content + ‘\n’ + html[m.end():], True

# ── 1. Update <title> and meta titles ─────────────────────────────────────────

html = re.sub(
r’<title>MLB Slate[^<]*</title>’,
f’<title>MLB Slate · {month_short} {day_of_mo} · Day {day_num}</title>’,
html
)
html = re.sub(
r’<meta property=“og:title” content=”[^”]*”>’,
f’<meta property="og:title" content="The Daily Slate — {month_short} {day_of_mo} Day {day_num}">’,
html
)
html = re.sub(
r’<meta name=“twitter:title” content=”[^”]*”>’,
f’<meta name="twitter:title" content="The Daily Slate — {month_short} {day_of_mo} Day {day_num}">’,
html
)
print(”  ✓ Updated title + meta”)

# ── 2. Update header H1 and subtitle ─────────────────────────────────────────

html = re.sub(
r’<h1>⚾[^<]*</h1>’,
f’<h1>⚾ {month_short} {day_of_mo} — {weekday} Slate</h1>’,
html
)
html = re.sub(
r’<div class="subtitle-block">[^<]*</div>’,
f’<div class="subtitle-block">{game_count} Games · Day {day_num} · Sweet Spot + Park Factors</div>’,
html
)
print(”  ✓ Updated header H1 + subtitle”)

# ── 3. Update last-updated line ───────────────────────────────────────────────

html = re.sub(
r’<div class="last-updated">.*?</div>’,
f’<div class="last-updated">{month_short} {day_of_mo} · <b>{build_time}</b> · Day {day_num} • {weekday} slate</div>’,
html
)
print(”  ✓ Updated last-updated”)

# ── 4. Update TOC game count ──────────────────────────────────────────────────

html = re.sub(
r’(<a href="#games">🎮 All )\d+( Game Write-Ups)’,
rf’\g<1>{game_count}\2’,
html
)
print(”  ✓ Updated TOC game count”)

# ── 5. Update alignment section date tag ─────────────────────────────────────

html = re.sub(
r’(Tap to expand · tier thresholds + )[A-Za-z]+ \d+ park notes’,
rf’\g<1>{month_short} {day_of_mo} park notes’,
html
)

# Update the park summary h4 date

html = re.sub(
r’<h4>[A-Za-z]+ \d+ Park Summary</h4>’,
f’<h4>{month_short} {day_of_mo} Park Summary</h4>’,
html
)

# Replace the tldr-box park summary paragraph

html = re.sub(
r’(<div class="tldr-box">)\s*<h4>[^<]*</h4>\s*<p>[\s\S]*?</p>\s*(</div>)’,
rf’<div class="tldr-box"><h4>{month_short} {day_of_mo} Park Summary</h4>{build_park_summary()}\2’,
html
)
print(”  ✓ Updated alignment park summary”)

# ── 6. Update methodology intro ───────────────────────────────────────────────

html = re.sub(
r’<p class="method-intro">[\s\S]*?</p>’,
f’<p class="method-intro">{build_method_intro()}</p>’,
html, count=1
)
print(”  ✓ Updated methodology intro”)

# ── 7. Replace all data-driven sections ──────────────────────────────────────

SECTION_ORDER = [
‘headlines’, ‘park-board’, ‘games’, ‘matchup-spotlight’,
‘k-board’, ‘sp-vuln-board’, ‘hr-board’, ‘oo5-board’,
‘totals-board’, ‘nrfi-board’, ‘sb-board’, ‘doubles-board’,
‘dfs-board’, ‘combos-k’, ‘combos-hrr’, ‘parlays’,
‘conviction’, ‘skip’
]

for sec_id in SECTION_ORDER:
if sec_id not in SECTIONS:
print(f”  ⚠ No built section for #{sec_id} — skipping”)
continue
html, ok = replace_section(html, sec_id, SECTIONS[sec_id])
print(f”  {‘✓’ if ok else ‘✗’} Replaced #{sec_id}”)

# Handle sp-vuln-board insertion if it doesn’t exist yet

if ‘sp-vuln-board’ in SECTIONS and ‘<section id=“sp-vuln-board”’ not in html:
pattern = re.compile(r’(<section id=“k-board”[\s\S]*?</section>\s*\n)’, re.MULTILINE)
m = pattern.search(html)
if m:
html = html[:m.end()] + SECTIONS[‘sp-vuln-board’] + ‘\n’ + html[m.end():]
print(”  ✓ Inserted new #sp-vuln-board after #k-board”)

# ── 8. Write output ───────────────────────────────────────────────────────────

tmp = INDEX_FILE + ‘.tmp’
with open(tmp, ‘w’, encoding=‘utf-8’) as f:
f.write(html)
os.replace(tmp, INDEX_FILE)

print(f”\n✅ Done — wrote {len(html):,} bytes to {INDEX_FILE}”)
print(f”   Day {day_num} · {month_short} {day_of_mo} · {weekday} · {game_count} games”)
