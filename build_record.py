"""
build_record.py — generates record.html (For The Record) from results.json.
Redesign: "ledger" identity — a markets grid signature, electric cyan->indigo palette,
mono records throughout. Buckets HR by consensus; other markets fill in once API grading runs.
"""
import json, os

RESULTS_FILE = os.environ.get('RESULTS_FILE', 'results.json')
OUT_FILE = os.environ.get('RECORD_OUT', 'record.html')

def load_results():
    try:
        with open(RESULTS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

CSS = """
:root{
  --bg:#070a12;--grad-1:#0a1320;--grad-2:#0f0d1e;--grad-3:#0a1418;
  --surface:#0c1019;--surface-2:#11161f;
  --glass:rgba(122,142,178,0.06);--glass-2:rgba(122,142,178,0.10);
  --glass-border:rgba(132,156,196,0.14);--glass-border-2:rgba(132,156,196,0.24);
  --text:#eef2f8;--text-soft:#aab6c6;--text-dim:#6a7689;
  --cy:#35d6e8;--in:#6d72ff;--cy-soft:rgba(53,214,232,0.13);
  --win:#2fe0a0;--win-bg:rgba(47,224,160,0.12);--win-bd:rgba(47,224,160,0.42);
  --loss:#ff5a6a;--loss-bg:rgba(255,90,106,0.12);--loss-bd:rgba(255,90,106,0.42);
  --gold:#ffc24b;
  --radius:16px;--radius-sm:12px;--appbar-h:52px;
  --grad:linear-gradient(135deg,var(--cy),var(--in));
  --grad-h:linear-gradient(90deg,var(--cy),var(--in));
  --header-bg:rgba(7,10,18,0.8);
  --font-display:"Bebas Neue","Arial Narrow",sans-serif;
  --font-body:"DM Sans",-apple-system,"Segoe UI",sans-serif;
  --font-mono:"DM Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
[data-theme="light"]{
  --bg:#eef1f6;--grad-1:#e6eef7;--grad-2:#eceaf6;--grad-3:#e7f1f2;
  --surface:#ffffff;--surface-2:#f4f6fa;
  --glass:rgba(255,255,255,0.7);--glass-2:rgba(255,255,255,0.9);
  --glass-border:rgba(20,30,45,0.1);--glass-border-2:rgba(20,30,45,0.18);
  --text:#101622;--text-soft:#36424f;--text-dim:#69768a;
  --cy:#0c9fc4;--in:#4b54e0;--cy-soft:rgba(12,159,196,0.1);
  --win:#0aa56a;--win-bg:rgba(10,165,106,0.1);--win-bd:rgba(10,165,106,0.4);
  --loss:#e23a4c;--loss-bg:rgba(226,58,76,0.09);--loss-bd:rgba(226,58,76,0.4);
  --gold:#c4870a;--header-bg:rgba(238,241,246,0.82);
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{scroll-behavior:smooth}html,body{margin:0;padding:0}
body{font-family:var(--font-body);background:var(--bg);
  background-image:radial-gradient(1100px 520px at 88% -130px,var(--grad-1) 0%,transparent 60%),
    radial-gradient(820px 460px at -160px 12%,var(--grad-2) 0%,transparent 56%),
    radial-gradient(1000px 680px at 50% 118%,var(--grad-3) 0%,transparent 54%);
  background-attachment:fixed;color:var(--text);font-size:14px;line-height:1.55;
  padding-bottom:calc(env(safe-area-inset-bottom,0px) + 26px)}
a{color:var(--cy);text-decoration:none}
button{font-family:inherit}
.app-bar{position:sticky;top:0;z-index:60;min-height:calc(var(--appbar-h) + env(safe-area-inset-top,0px));
  display:flex;align-items:center;gap:10px;padding:0 14px;padding-top:env(safe-area-inset-top,0px);
  background:var(--header-bg);-webkit-backdrop-filter:blur(18px) saturate(1.4);backdrop-filter:blur(18px) saturate(1.4);
  border-bottom:1px solid var(--glass-border)}
.back-chip{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:11px;
  background:var(--glass);border:1px solid var(--glass-border);color:var(--text);font-size:17px}
.brand{display:flex;align-items:baseline;gap:7px;color:var(--text)}
.brand .wm{font-family:var(--font-display);font-size:21px;letter-spacing:1.5px;line-height:1}
.brand .wm em{font-style:normal;background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.spacer{flex:1}
.icon-btn{width:38px;height:38px;border-radius:12px;display:inline-flex;align-items:center;justify-content:center;
  background:var(--glass);border:1px solid var(--glass-border);color:var(--text);font-size:16px;cursor:pointer}
.rail-wrap{position:sticky;top:calc(var(--appbar-h) + env(safe-area-inset-top,0px));z-index:55;background:var(--header-bg);
  -webkit-backdrop-filter:blur(18px) saturate(1.4);backdrop-filter:blur(18px) saturate(1.4);border-bottom:1px solid var(--glass-border)}
.rail{display:flex;gap:7px;align-items:center;height:44px;overflow-x:auto;padding:0 12px;scrollbar-width:none}
.rail::-webkit-scrollbar{display:none}
.chip-nav{flex:0 0 auto;display:inline-flex;align-items:center;gap:5px;height:29px;padding:0 11px;border-radius:9px;
  border:1px solid var(--glass-border);background:var(--glass);color:var(--text-dim);
  font-family:var(--font-display);font-size:14px;letter-spacing:1.1px;white-space:nowrap;cursor:pointer}
.chip-nav .e{font-family:var(--font-body);font-size:12px}
.chip-nav.active{color:var(--cy);border-color:var(--cy);background:var(--cy-soft)}
.wrap{max-width:680px;margin:0 auto;padding:0 14px}
.hero{padding:20px 2px 2px}
.eyebrow{font-size:10.5px;letter-spacing:2.6px;text-transform:uppercase;color:var(--cy);font-weight:800}
.title{font-family:var(--font-display);font-size:clamp(42px,13vw,64px);line-height:.9;letter-spacing:1.5px;margin:7px 0 0}
.title em{font-style:normal;background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.bigrec{display:flex;align-items:flex-end;gap:15px;margin:13px 0 0}
.bigrec .rec{font-family:var(--font-mono);font-size:46px;font-weight:500;letter-spacing:1px;line-height:.85}
.bigrec .rec em{font-style:normal;color:var(--text-dim)}
.bigrec .meta{padding-bottom:5px}
.bigrec .meta .p{font-family:var(--font-mono);font-size:17px;color:var(--win);line-height:1}
.bigrec .meta .lbl{font-size:9px;letter-spacing:1.6px;text-transform:uppercase;color:var(--text-dim);margin-top:2px}
.rule{height:3px;border-radius:99px;background:linear-gradient(90deg,var(--cy),var(--in),transparent);margin:11px 0 12px;max-width:230px}
.chips{display:flex;flex-wrap:wrap;gap:7px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:99px;border:1px solid var(--glass-border);
  background:var(--glass);font-family:var(--font-mono);font-size:11px;letter-spacing:.3px;color:var(--text-soft)}
.chip .led{width:6px;height:6px;border-radius:50%;background:var(--cy);box-shadow:0 0 8px var(--cy)}
.banner{margin:12px 0 4px;padding:9px 12px;border-radius:var(--radius-sm);background:var(--cy-soft);
  border:1px solid rgba(53,214,232,.28);font-size:11.5px;color:var(--text-soft);line-height:1.55}
.banner b{color:var(--cy)}
.sec{margin:20px 0;scroll-margin-top:calc(var(--appbar-h) + 54px)}
.sec-hd{font-family:var(--font-display);font-size:21px;letter-spacing:1.1px;margin:0 0 11px;display:flex;align-items:baseline;gap:9px}
.sec-hd span{font-family:var(--font-body);font-size:10px;color:var(--text-dim);font-weight:700;letter-spacing:.3px}
.mkt-grid{display:flex;flex-wrap:wrap;gap:9px}
.mkt{position:relative;flex:1 1 calc(50% - 5px);min-width:140px;padding:13px 14px 12px;border-radius:14px;background:var(--glass);border:1px solid var(--glass-border);overflow:hidden}
.mkt::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--grad)}
.mkt.off{opacity:.6}.mkt.off::before{background:var(--glass-border-2)}
.mkt-top{display:flex;align-items:center;gap:6px;font-size:10.5px;letter-spacing:.8px;text-transform:uppercase;color:var(--text-dim);font-weight:800}
.mkt-ic{font-size:14px}
.mkt-rec{font-family:var(--font-mono);font-size:27px;font-weight:500;letter-spacing:1px;margin:5px 0 1px;line-height:1}
.mkt-rec em{font-style:normal;color:var(--text-dim);font-size:18px}
.mkt-sub{font-size:10px;color:var(--text-soft);font-family:var(--font-mono)}
.mkt-pend{display:inline-block;font-size:9px;letter-spacing:1.2px;text-transform:uppercase;color:var(--text-dim);
  border:1px solid var(--glass-border);border-radius:99px;padding:2px 9px}
.mkt-bar{height:5px;border-radius:99px;background:var(--surface-2);overflow:hidden;margin-top:9px}
.mkt-bar i{display:block;height:100%;background:var(--grad-h)}
.cal{display:flex;align-items:center;gap:10px;margin:9px 0}
.cal .tag{flex:0 0 104px;font-size:11px;font-weight:800}
.cal .bar{flex:1;height:13px;border-radius:99px;background:var(--surface-2);overflow:hidden}
.cal .bar i{display:block;height:100%;border-radius:99px;background:var(--grad-h)}
.cal .bar i.s{background:linear-gradient(90deg,var(--gold),rgba(255,194,75,.45))}
.cal .bar i.f{background:var(--glass-border-2)}
.cal .num{flex:0 0 auto;font-family:var(--font-mono);font-size:12px;color:var(--text-soft);min-width:96px;text-align:right}
.t-e{color:var(--cy)}.t-s{color:var(--gold)}.t-f{color:var(--text-dim)}
.insight{margin:13px 0 0;padding:10px 12px;border-radius:var(--radius-sm);background:rgba(109,114,255,.08);
  border:1px solid rgba(109,114,255,.22);font-size:12px;color:var(--text-soft);line-height:1.55}
.insight b{color:var(--in)}
.spark{display:flex;gap:5px;align-items:flex-end;height:62px}
.spark b{flex:1;border-radius:4px 4px 0 0;background:var(--grad);opacity:.92}
.spark b.dn{background:linear-gradient(var(--loss),rgba(255,90,106,.5))}
.spark-labels{display:flex;gap:5px;margin-top:5px}
.spark-labels span{flex:1;text-align:center;font-family:var(--font-mono);font-size:8.5px;color:var(--text-dim)}
.muted{font-size:11.5px;color:var(--text-dim)}
.row{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:var(--radius-sm);
  background:var(--glass);border:1px solid var(--glass-border);margin:7px 0}
.row .who{flex:1;min-width:0;font-size:12.5px}
.row .who b{font-size:13px}
.row .who small{display:block;color:var(--text-dim);font-size:10.5px;margin-top:1px}
.row .got{font-family:var(--font-mono);font-size:12px;color:var(--text-soft);white-space:nowrap}
.wl{flex:0 0 auto;width:30px;height:30px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;
  font-family:var(--font-display);font-size:15px}
.wl.w{background:var(--win-bg);border:1px solid var(--win-bd);color:var(--win)}
.wl.l{background:var(--loss-bg);border:1px solid var(--loss-bd);color:var(--loss)}
.rules{font-size:11.5px;color:var(--text-dim);line-height:1.7}
.rules b{color:var(--text-soft)}
.foot{max-width:680px;margin:24px auto 6px;text-align:center;font-size:11px;color:var(--text-dim);font-family:var(--font-mono)}
"""

def pct(w, l):
    t = w + l
    return f'{round(100*w/t)}%' if t else '—'

def markets_grid(markets):
    cells = []
    for m in markets:
        graded = m.get('graded'); w, l = m.get('w', 0), m.get('l', 0); t = w + l
        if graded and t:
            rec = f'{w}<em>-</em>{l}'
            sub = f'{pct(w,l)} · {m.get("picks",t)} calls'
            bw = max(4, min(100, round(100*w/t)))
            tail = f'<div class="mkt-bar"><i style="width:{bw}%"></i></div>'
            cls = 'mkt'
        else:
            rec, sub = '<em>&mdash;</em>', f'{m.get("picks",0)} calls'
            tail = '<span class="mkt-pend">pending</span>'
            cls = 'mkt off'
        cells.append(
            f'<div class="{cls}"><div class="mkt-top"><span class="mkt-ic">{m["icon"]}</span>{m["label"]}</div>'
            f'<div class="mkt-rec">{rec}</div><div class="mkt-sub">{sub}</div>{tail}</div>')
    return '\n'.join(cells)

def cal_bars(buckets):
    out = []
    for b in buckets:
        w, l = b.get('w', 0), b.get('l', 0); t = w + l
        bw = max(4, min(100, round(100*w/t))) if t else 0
        cls = b.get('cls', 'f')
        tcls = {'e': 't-e', 's': 't-s', 'f': 't-f'}.get(cls, 't-f')
        out.append(
            f'<div class="cal"><span class="tag {tcls}">{b["name"]}</span>'
            f'<span class="bar"><i class="{cls}" style="width:{bw}%"></i></span>'
            f'<span class="num">{w}-{l} &middot; {pct(w,l)}</span></div>')
    return '\n'.join(out)

def spark(trend, labels):
    bars = ''.join(f'<b style="height:{max(8,min(100,int(v)))}%" class="{"dn" if v<50 else ""}"></b>' for v in trend)
    labs = ''.join(f'<span>{x}</span>' for x in labels)
    return f'<div class="spark">{bars}</div><div class="spark-labels">{labs}</div>'

def grades_list(grades):
    out = []
    for g in grades:
        wl = g.get('wl', 'l')
        out.append(
            f'<div class="row"><span class="wl {wl}">{wl.upper()}</span>'
            f'<span class="who"><b>{g["name"]}</b><small>{g.get("tag","")}</small></span>'
            f'<span class="got">{g.get("got","&mdash;")}</span></div>')
    return '\n'.join(out)

def build():
    R = load_results()
    preview = R.get('is_preview', True)
    sw, sl = (R.get('season') or {}).get('w', 0), (R.get('season') or {}).get('l', 0)
    l7w, l7l = (R.get('last7') or {}).get('w', 0), (R.get('last7') or {}).get('l', 0)
    ydate = R.get('yesterday_date', '—')
    banner = ('<div class="banner"><b>Preview</b> &mdash; HR is graded from the results tab. '
              'K, Hits and the rest grade live from the box score each morning and fill in here.</div>') if preview else ''
    grid = markets_grid(R.get('markets', []))
    cal = cal_bars(R.get('hr_buckets', []))
    trend, tlabels = R.get('trend', []), R.get('trend_labels', [])
    grades = R.get('grades', [])
    insight = f'<div class="insight"><b>Read:</b> {R["hr_insight"]}</div>' if R.get('hr_insight') else ''

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>For The Record 🧾 — The Daily Slate</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Mono:wght@400;500&family=DM+Sans:opsz,wght@9..40,400;9..40,600;9..40,700;9..40,800&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header class="app-bar">
  <a class="back-chip" href="index.html" aria-label="Back to slate">&lsaquo;</a>
  <a class="brand" href="index.html"><span class="wm">FOR THE <em>RECORD</em> 🧾</span></a>
  <div class="spacer"></div>
  <button class="icon-btn" id="themeToggle" aria-label="Toggle theme">&#127769;</button>
</header>
<nav class="rail-wrap"><div class="rail">
  <button class="chip-nav" onclick="window.scrollTo({{top:0,behavior:'smooth'}})"><span class="e">&#8676;</span></button>
  <a class="chip-nav" href="#markets"><span class="e">&#9636;</span>MARKETS</a>
  <a class="chip-nav" href="#cal"><span class="e">&#128202;</span>CALIBRATION</a>
  <a class="chip-nav" href="#trend"><span class="e">&#128200;</span>TREND</a>
  <a class="chip-nav" href="#yesterday"><span class="e">&#128203;</span>GRADES</a>
  <a class="chip-nav" href="#rules"><span class="e">&#129518;</span>RULES</a>
</div></nav>
<div class="wrap">
  <div class="hero">
    <div class="eyebrow">Every call &middot; graded vs the box score</div>
    <div class="title">FOR THE <em>RECORD</em> 🧾</div>
    <div class="bigrec">
      <div class="rec">{sw}<em>-</em>{sl}</div>
      <div class="meta"><div class="p">{pct(sw,sl)}</div><div class="lbl">Season win rate</div></div>
    </div>
    <div class="rule"></div>
    <div class="chips">
      <span class="chip"><span class="led"></span>DAY {R.get('season_day','—')}</span>
      <span class="chip">L7 &middot; {l7w}-{l7l}</span>
      <span class="chip">UPDATED {R.get('updated','—')}</span>
    </div>
    {banner}
  </div>

  <div class="sec" id="markets">
    <h2 class="sec-hd">&#9636; MARKETS <span>record by bet type</span></h2>
    <div class="mkt-grid">{grid}</div>
  </div>

  <div class="sec" id="cal">
    <h2 class="sec-hd">&#128202; CONSENSUS CALIBRATION <span>HR &middot; does agreement convert?</span></h2>
    {cal or '<p class="muted">Pending first graded slate.</p>'}
    {insight}
  </div>

  <div class="sec" id="trend">
    <h2 class="sec-hd">&#128200; DAILY HIT RATE <span>recent slates &middot; &#8805; 50% lifts</span></h2>
    {spark(trend, tlabels) if trend else '<p class="muted">Builds as days are graded.</p>'}
  </div>

  <div class="sec" id="yesterday">
    <h2 class="sec-hd">&#128203; GRADES <span>{ydate} &middot; top calls by consensus</span></h2>
    {grades_list(grades) if grades else '<p class="muted">Pending first graded slate.</p>'}
  </div>

  <div class="sec" id="rules">
    <h2 class="sec-hd">&#129518; HOW IT'S GRADED <span>what counts as a win</span></h2>
    <p class="rules"><b>HR / Hits / SB / 2B:</b> the bat records 1+. <b>HRR:</b> hits + runs + RBIs &#8805; 1.
    <b>K:</b> strikeouts clear the line (a pitcher's hits, earned runs and outs ride along as context).
    <b>Totals / NRFI:</b> the lean vs the actual result. Scratches and postponements are voided.
    Grades pull from the official box score the next morning &mdash; no judgment calls. <b>Losses stay on the board.</b></p>
  </div>
</div>
<div class="foot">For The Record &middot; part of The Daily Slate &#9918;</div>
<script>
(function(){{var c='dark';try{{var s=localStorage.getItem('slateTheme');if(s==='light'||s==='dark')c=s;}}catch(e){{}}
document.documentElement.setAttribute('data-theme',c);
var t=document.getElementById('themeToggle');t.textContent=c==='dark'?'\\uD83C\\uDF19':'\\u2600\\uFE0F';
t.addEventListener('click',function(){{c=c==='dark'?'light':'dark';
document.documentElement.setAttribute('data-theme',c);t.textContent=c==='dark'?'\\uD83C\\uDF19':'\\u2600\\uFE0F';
try{{localStorage.setItem('slateTheme',c);}}catch(e){{}}}});}})();
</script>
</body></html>"""
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Wrote {OUT_FILE} ({len(html):,} bytes)")
    return html

if __name__ == '__main__':
    build()
