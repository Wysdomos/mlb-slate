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

# Step 1 — build_day46.py → built_sections.json
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

# Step 2 — build_streaks.py → streaks.html + hot_streaks.json (must precede editorial)
os.environ['STREAKS_FILE'] = STREAKS_FILE
exec(compile(open('build_streaks.py', encoding='utf-8').read(), 'build_streaks.py', 'exec'))

if PROJECTED_MODE:
    print('build_editorial: skipped in Projected Mode')
else:
    # Step 3 — build_editorial.py → enhances built_sections.json (uses hot_streaks.json)
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
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>SSJ The Zone - Projected Mode</title>
<style>
/* Matches the Projected Mode withheld treatment on the slate: same language,
   same ice palette, same hatched cordon marking a reconstructed surface. */
:root{
  --pm-key:#6fd7e9; --pm-key-lift:#a8e9f5; --pm-steel:#8fa6bd;
  --pm-stripe:rgba(111,215,233,.50); --pm-spine:#07222c;
  --bg:#0a1016; --surface:#0e1720; --lip:#14232f;
  --text:#eaf3f7; --text-soft:#b6c8d3; --text-dim:#8aa0ad;
  --border:rgba(140,200,220,.19);
  --cordon:repeating-linear-gradient(135deg,var(--pm-stripe) 0 5px,transparent 5px 11px);
}
@media (prefers-color-scheme: light){
  :root{
    --pm-key:#0b6981; --pm-key-lift:#085466; --pm-steel:#3d5468;
    --pm-stripe:rgba(11,105,129,.52); --pm-spine:#d3e9f0;
    --bg:#eaf1f5; --surface:#fff; --lip:#eef4f8;
    --text:#0d1b24; --text-soft:#3c4d59; --text-dim:#4d5f6b;
    --border:rgba(16,58,76,.16);
  }
}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;
  padding:calc(env(safe-area-inset-top,0px) + 24px) calc(env(safe-area-inset-right,0px) + 20px)
          calc(env(safe-area-inset-bottom,0px) + 24px) calc(env(safe-area-inset-left,0px) + 28px);
  background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5}
body::before{content:"";position:fixed;top:0;bottom:0;left:env(safe-area-inset-left,0px);
  width:8px;background:var(--cordon),var(--pm-spine);pointer-events:none}
.card{position:relative;max-width:560px;width:100%;padding:22px 20px;
  border:1px solid var(--border);border-radius:16px;background:var(--surface);
  box-shadow:inset 0 1px 0 rgba(190,235,250,.09),0 1px 2px rgba(0,0,0,.42);overflow:hidden}
.card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;
  background:var(--cordon),var(--pm-spine)}
.chip{display:inline-block;margin-bottom:12px;padding:3px 8px;
  border:1px solid rgba(111,215,233,.42);border-radius:5px;
  background:rgba(111,215,233,.13);color:var(--pm-key);
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:10.5px;font-weight:500;letter-spacing:1.2px}
h1{margin:0 0 8px;font-size:21px;line-height:1.25;letter-spacing:.2px}
p{margin:0 0 10px;color:var(--text-soft);font-size:14px}
p:last-of-type{margin-bottom:0}
.back{display:inline-flex;align-items:center;justify-content:center;gap:8px;
  margin-top:18px;min-height:44px;padding:0 16px;
  border:1px solid rgba(111,215,233,.42);border-radius:11px;
  background:rgba(111,215,233,.13);box-shadow:inset 0 1px 0 rgba(190,235,250,.09);
  color:var(--pm-key);font-size:14px;font-weight:700;text-decoration:none}
.back:active{background:rgba(111,215,233,.22)}
</style></head><body><main class="card">
<span class="chip">PROJECTED MODE</span>
<h1>SSJ The Zone is withheld today</h1>
<p>No workbook was uploaded, so The Zone, Sweet Spot grades, Best Spots and the
Scout core tabs have no honest source. They are held back rather than estimated.</p>
<p>Today&rsquo;s slate still carries reconstructed HR and Hits boards built from live
BallparkPal and Baseball Savant inputs.</p>
<a class="back" href="index.html">&larr;&nbsp; Back to the top of the slate</a>
</main></body></html>''')
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
