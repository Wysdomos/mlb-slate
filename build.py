"""
build.py -- Path-agnostic wrapper for the full daily pipeline
Reads:  day_data.json         (or DATA_FILE env var)
Writes: built_sections.json   (or SECTIONS_FILE env var)
        k-report.html         (or K_REPORT_FILE env var)
        streaks.html          (or STREAKS_FILE env var)
"""
import os

DATA_FILE     = os.environ.get('DATA_FILE',     'day_data.json')
SECTIONS_FILE = os.environ.get('SECTIONS_FILE', 'built_sections.json')
K_REPORT_FILE = os.environ.get('K_REPORT_FILE', 'k-report.html')
STREAKS_FILE  = os.environ.get('STREAKS_FILE',  'streaks.html')

# Step 1 — build_streaks.py → streaks.html + hot_streaks.json
os.environ['DATA_FILE'] = DATA_FILE
os.environ['STREAKS_FILE'] = STREAKS_FILE
exec(compile(open('build_streaks.py', encoding='utf-8').read(), 'build_streaks.py', 'exec'))

# Step 2 — build_day46.py → built_sections.json
src = open('build_day46.py', encoding='utf-8').read()
src = src.replace(
    "json.load(open('/home/user/workspace/day46_data.json'))",
    f"json.load(open('{DATA_FILE}'))"
)
src = src.replace(
    "open('/home/user/workspace/built_sections_d46.json','w', encoding='utf-8')",
    f"open('{SECTIONS_FILE}','w', encoding='utf-8')"
)
exec(compile(src, 'build_day46.py', 'exec'))
PROJECTED_MODE = globals().get('PROJECTED_MODE', False)

# Step 2b -- build_kalshi_matches.py -> kalshi_matches.json + Kalshi price
# fields on the slate_picks rows. Kalshi must never break the slate build:
# the script always exits 0 on its own failures, and anything unexpected
# (including its argparse/SystemExit plumbing) is caught here, logged, and
# the pipeline continues.
try:
    exec(compile(open('build_kalshi_matches.py', encoding='utf-8').read(),
                 'build_kalshi_matches.py', 'exec'))
except SystemExit as _kalshi_exit:
    if _kalshi_exit.code not in (0, None):
        print(f'build_kalshi_matches exited non-fatally with code {_kalshi_exit.code}')
except Exception as _kalshi_exc:
    print(f'build_kalshi_matches failed non-fatally: {type(_kalshi_exc).__name__}: {_kalshi_exc}')

if PROJECTED_MODE:
    print('build_editorial: skipped in Projected Mode')
else:
    # Step 3 — build_editorial.py → enhances built_sections.json
    os.environ['DATA_FILE']     = DATA_FILE
    os.environ['SECTIONS_FILE'] = SECTIONS_FILE
    exec(compile(open('build_editorial.py', encoding='utf-8').read(), 'build_editorial.py', 'exec'))

# Step 4 — build_k_report.py → k-report.html
os.environ['K_REPORT_FILE'] = K_REPORT_FILE
exec(compile(open('build_k_report.py', encoding='utf-8').read(), 'build_k_report.py', 'exec'))

print(f"Pipeline complete. Sections -> {SECTIONS_FILE}, K Report -> {K_REPORT_FILE}, Streaks -> {STREAKS_FILE}")
