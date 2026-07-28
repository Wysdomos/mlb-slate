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

# Step 5 — build_scout.py → scout.html
try:
    if PROJECTED_MODE:
        with open('scout.html', 'w', encoding='utf-8') as f:
            f.write('''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SSJ The Zone - Projected Mode</title>
<style>
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#111827;color:#f8fafc;display:grid;min-height:100vh;place-items:center;padding:24px}
.card{max-width:720px;border:1px solid rgba(125,211,252,.35);background:linear-gradient(135deg,rgba(14,165,233,.16),rgba(20,184,166,.12));padding:28px;border-radius:8px;box-shadow:0 24px 60px rgba(0,0,0,.35)}
h1{margin:0 0 10px;font-size:28px}p{color:#cbd5e1;line-height:1.55}.badge{display:inline-block;margin-bottom:14px;padding:5px 9px;border:1px solid rgba(125,211,252,.45);border-radius:999px;color:#7dd3fc;font-size:12px;font-weight:800;letter-spacing:.08em}
a{color:#67e8f9}
</style></head><body><main class="card"><div class="badge">PROJECTED MODE</div>
<h1>SSJ The Zone is unavailable without the workbook</h1>
<p>The Zone, Sweet Spot grades, Best Spots, and Scout core tabs require the uploaded workbook. Today's main slate still includes reconstructed HR and Hits boards built from live BallparkPal and Baseball Savant inputs.</p>
<p><a href="index.html">Back to The Daily Slate</a></p></main></body></html>''')
        print('build_scout: wrote Projected Mode unavailable page')
    else:
        import datetime as _dt_mod
        # Derive readable date from BP_Games GameDate (TODAY_STR/DAY_NUM not set by build_day46)
        _scout_date = 'Today'
        for _g in DATA.get('BP_Games', []):
            _raw = str(_g.get('GameDate', ''))[:10]
            try:
                _d = _dt_mod.datetime.strptime(_raw, '%Y-%m-%d').date()
                _scout_date = _d.strftime('%B') + ' ' + str(_d.day) + ', ' + str(_d.year)
                break
            except Exception:
                pass
        _scout_ns = {}
        exec(compile(open('build_scout.py', encoding='utf-8').read(), 'build_scout.py', 'exec'), _scout_ns)
        _scout_ns['set_data'](
            HR_LB, SP_PROJ, SS_BY_NAME, BP_BAT, GAMES_RAW,
            _scout_date, '',
            ssa     = DATA.get('Sweet_Spot_Analyzer', []),
            scout   = DATA.get('Scout', []),
            streaks = DATA.get('Streaks', [])
        )
        _scout_ns['build']()
        print('build_scout: scout.html written OK')
except Exception as _e:
    import traceback; traceback.print_exc()
    print(f'build_scout error (non-fatal): {_e}')

print(f"Pipeline complete. Sections -> {SECTIONS_FILE}, K Report -> {K_REPORT_FILE}, Streaks -> {STREAKS_FILE}")
