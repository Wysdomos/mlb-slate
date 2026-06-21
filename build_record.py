"""
build_record.py — generates record.html (For The Record) from results.json.
Tabbed design: one tab per market (HR, K, Hits, HRR, Totals, NRFI, SB, 2B). Each panel shows
the market's record, a cross-market comparison, per-pick rows, and added context (K peripherals).
Electric cyan->indigo base with a distinct accent color per market.
"""
import json, os

RESULTS_FILE = os.environ.get('RESULTS_FILE', 'results.json')
OUT_FILE = os.environ.get('RECORD_OUT', 'record.html')

META = [('HR','HR','🏆'),('K','K','⚡'),('HIT','Hits','🎯'),('HRR','HRR','💥'),
        ('TOTAL','Totals','📈'),('NRFI','NRFI','🥶'),('SB','SB','🏃'),('2B','2B','💎')]
ACC = {'HR':('#ffc24b','rgba(255,194,75,.45)'), 'K':('#35d6e8','rgba(53,214,232,.45)'),
       'HIT':('#2fe0a0','rgba(47,224,160,.45)'), 'HRR':('#ff8a4a','rgba(255,138,74,.45)'),
       'TOTAL':('#56a8ff','rgba(86,168,255,.45)'), 'NRFI':('#8ab4ff','rgba(138,180,255,.45)'),
       'SB':('#2ad6c0','rgba(42,214,192,.45)'), '2B':('#9b7cff','rgba(155,124,255,.45)')}

def load_results():
    try:
        with open(RESULTS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def pct(w, l):
    t = w + l
    return f'{round(100*w/t)}%' if t else '—'

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
  --grad:linear-gradient(135deg,var(--cy),var(--in));--grad-h:linear-gradient(90deg,var(--cy),var(--in));
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
.wrap{max-width:680px;margin:0 auto;padding:0 14px}
.hero{padding:20px 2px 6px}
.eyebrow{font-size:10.5px;letter-spacing:2.6px;text-transform:uppercase;color:var(--cy);font-weight:800}
.title{font-family:var(--font-display);font-size:clamp(42px,13vw,64px);line-height:.9;letter-spacing:1.5px;margin:7px 0 0}
.title em{font-style:normal;background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.bigrec{display:flex;align-items:flex-end;gap:15px;margin:13px 0 0}
.bigrec .rec{font-family:var(--font-mono);font-size:44px;font-weight:500;letter-spacing:1px;line-height:.85}
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
.sec{margin:18px 0;scroll-margin-top:calc(var(--appbar-h) + 54px)}
.sec-hd{font-family:var(--font-display);font-size:21px;letter-spacing:1.1px;margin:0 0 11px;display:flex;align-items:baseline;gap:9px}
.sec-hd span{font-family:var(--font-body);font-size:10px;color:var(--text-dim);font-weight:700;letter-spacing:.3px}
/* ---- tabs ---- */
.tabbar{position:sticky;top:calc(var(--appbar-h) + env(safe-area-inset-top,0px));z-index:40;
  display:flex;gap:7px;overflow-x:auto;padding:8px 0;scrollbar-width:none;
  background:var(--header-bg);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)}
.tabbar::-webkit-scrollbar{display:none}
.tab{flex:0 0 auto;display:flex;flex-direction:column;gap:2px;align-items:flex-start;padding:8px 13px;border-radius:12px;
  background:var(--glass);border:1px solid var(--glass-border);cursor:pointer;min-width:76px}
.tab .t-ic{font-size:15px;line-height:1}
.tab .t-l{font-family:var(--font-display);font-size:15px;letter-spacing:.8px;color:var(--text-soft);line-height:1}
.tab .t-r{font-family:var(--font-mono);font-size:10px;color:var(--text-dim);line-height:1}
.tab.active{border-color:var(--accg);background:var(--glass-2);box-shadow:0 0 18px -8px var(--accg)}
.tab.active .t-l,.tab.active .t-r{color:var(--acc)}
.tab.active .t-ic{filter:drop-shadow(0 0 5px var(--accg))}
.panel{display:none}
.panel.active{display:block;animation:fade .22s ease}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.panel-head{display:flex;align-items:flex-end;gap:14px;padding:15px;border-radius:14px;background:var(--glass);
  border:1px solid var(--glass-border);border-left:3px solid var(--acc);margin-bottom:13px;box-shadow:inset 0 0 60px -42px var(--acc)}
.ph-rec{font-family:var(--font-mono);font-size:40px;font-weight:500;letter-spacing:1px;line-height:.82;color:var(--text)}
.ph-rec em{font-style:normal;color:var(--text-dim)}
.ph-meta{padding-bottom:4px}
.ph-pct{font-family:var(--font-mono);font-size:18px;color:var(--acc);line-height:1}
.ph-lbl{font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--text-dim);margin-top:3px}
.block-h{font-size:10px;letter-spacing:1.6px;text-transform:uppercase;color:var(--text-dim);font-weight:800;margin:0 2px 8px}
.cmp{padding:12px 13px;border-radius:13px;background:var(--glass);border:1px solid var(--glass-border);margin-bottom:13px}
.cmp-row{display:flex;align-items:center;gap:9px;margin:6px 0;opacity:.62}
.cmp-row.on{opacity:1}
.cmp-n{flex:0 0 70px;font-size:10.5px;color:var(--text-soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cmp-row.on .cmp-n{color:var(--acc);font-weight:700}
.cmp-bar{flex:1;height:8px;border-radius:99px;background:var(--surface-2);overflow:hidden}
.cmp-bar i{display:block;height:100%;border-radius:99px;background:var(--acc)}
.cmp-v{flex:0 0 auto;font-family:var(--font-mono);font-size:10.5px;color:var(--text-dim);min-width:34px;text-align:right}
.note{font-size:11px;color:var(--text-soft);background:var(--cy-soft);border:1px solid rgba(53,214,232,.2);
  border-radius:11px;padding:9px 11px;margin-bottom:13px;line-height:1.5}
.cal{display:flex;align-items:center;gap:10px;margin:8px 0}
.cal .tag{flex:0 0 100px;font-size:11px;font-weight:800}
.cal .bar{flex:1;height:12px;border-radius:99px;background:var(--surface-2);overflow:hidden}
.cal .bar i{display:block;height:100%;border-radius:99px;background:var(--acc)}
.cal .bar i.s{background:linear-gradient(90deg,var(--gold),rgba(255,194,75,.45))}
.cal .bar i.f{background:var(--glass-border-2)}
.cal .num{flex:0 0 auto;font-family:var(--font-mono);font-size:11.5px;color:var(--text-soft);min-width:92px;text-align:right}
.t-e{color:var(--acc)}.t-s{color:var(--gold)}.t-f{color:var(--text-dim)}
.cal-wrap{padding:12px 13px;border-radius:13px;background:var(--glass);border:1px solid var(--glass-border);margin-bottom:13px}
.pk-list{display:flex;flex-direction:column;gap:7px}
.pk{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:11px;background:var(--glass);border:1px solid var(--glass-border)}
.pk-who{flex:1;min-width:0}
.pk-who b{font-size:12.5px}
.pk-who small{display:block;color:var(--text-dim);font-size:10px;margin-top:1px}
.pk-ctx{font-family:var(--font-mono);font-size:9.5px;color:var(--text-soft);margin-top:3px;opacity:.85}
.pk .got{font-family:var(--font-mono);font-size:11px;color:var(--text-soft);white-space:nowrap}
.wl{flex:0 0 auto;width:28px;height:28px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;font-family:var(--font-display);font-size:14px}
.wl.w{background:var(--win-bg);border:1px solid var(--win-bd);color:var(--win)}
.wl.l{background:var(--loss-bg);border:1px solid var(--loss-bd);color:var(--loss)}
.wl.p{background:var(--glass);border:1px solid var(--glass-border-2);color:var(--text-dim)}
.spark{display:flex;gap:5px;align-items:flex-end;height:60px}
.spark b{flex:1;border-radius:4px 4px 0 0;background:var(--grad);opacity:.92}
.spark b.dn{background:linear-gradient(var(--loss),rgba(255,90,106,.5))}
.spark-labels{display:flex;gap:5px;margin-top:5px}
.spark-labels span{flex:1;text-align:center;font-family:var(--font-mono);font-size:8.5px;color:var(--text-dim)}
.muted{font-size:11.5px;color:var(--text-dim)}
.rules{font-size:11.5px;color:var(--text-dim);line-height:1.7}
.rules b{color:var(--text-soft)}
.foot{max-width:680px;margin:22px auto 6px;text-align:center;font-size:11px;color:var(--text-dim);font-family:var(--font-mono)}
"""

def cmp_strip(markets, active_key):
    rows = []
    for m in markets:
        acc, _ = ACC.get(m['key'], ('#35d6e8', ''))
        t = m['w'] + m['l']
        graded = m.get('graded') and t
        rate = round(100*m['w']/t) if t else 0
        bw = max(3, rate) if graded else 0
        val = f'{rate}%' if graded else '—'
        cls = 'cmp-row on' if m['key'] == active_key else 'cmp-row'
        rows.append(
            f'<div class="{cls}" style="--acc:{acc}"><span class="cmp-n">{m["icon"]} {m["label"]}</span>'
            f'<span class="cmp-bar"><i style="width:{bw}%"></i></span><span class="cmp-v">{val}</span></div>')
    return f'<div class="cmp"><div class="block-h">vs other markets</div>{"".join(rows)}</div>'

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
            f'<span class="num">{w}-{l} · {pct(w,l)}</span></div>')
    return '\n'.join(out)

def rows_html(rows, key):
    out = []
    for r in rows:
        wl = r.get('wl', 'p'); d = r.get('detail') or {}
        line = f' {r["line"]}' if r.get('line') else ''
        ctx = ''
        if key == 'K':
            parts = [d[k] for k in ('proj', 'actual') if d.get(k)]
            parts = [('actual ' + d['actual']) if (p == d.get('actual')) else p for p in parts]
            if parts:
                ctx = f'<div class="pk-ctx">{" · ".join(parts)}</div>'
        elif d.get('actual'):
            ctx = f'<div class="pk-ctx">{d["actual"]}</div>'
        got = r.get('got', '—') if wl != 'p' else 'pending'
        mark = wl.upper() if wl != 'p' else '·'
        out.append(
            f'<div class="pk"><span class="wl {wl}">{mark}</span>'
            f'<div class="pk-who"><b>{r["name"]}{line}</b>'
            f'<small>{r.get("consensus",0)}/{r.get("max",6)} consensus</small>{ctx}</div>'
            f'<span class="got">{got}</span></div>')
    return '\n'.join(out) or '<p class="muted">No calls on the board.</p>'

def build():
    R = load_results()
    preview = R.get('is_preview', True)
    sw, sl = (R.get('season') or {}).get('w', 0), (R.get('season') or {}).get('l', 0)
    l7w, l7l = (R.get('last7') or {}).get('w', 0), (R.get('last7') or {}).get('l', 0)
    markets = R.get('markets', [{'key': k, 'label': lb, 'icon': ic, 'w': 0, 'l': 0, 'graded': False, 'picks': 0}
                                for k, lb, ic in META])
    detail = R.get('market_detail', {})
    hr_buckets = R.get('hr_buckets', [])
    trend, tlabels = R.get('trend', []), R.get('trend_labels', [])
    banner = ('<div class="banner"><b>Preview</b> — HR is graded from the results tab. '
              'K, Hits and the rest grade live from the box score each morning and light up here.</div>') if preview else ''

    # tab bar
    tabs = []
    for i, m in enumerate(markets):
        acc, accg = ACC.get(m['key'], ('#35d6e8', 'rgba(53,214,232,.45)'))
        t = m['w'] + m['l']
        sub = f'{m["w"]}-{m["l"]}' if (m.get('graded') and t) else 'pend'
        tabs.append(
            f'<button class="tab {"active" if i == 0 else ""}" data-m="{m["key"]}" style="--acc:{acc};--accg:{accg}">'
            f'<span class="t-ic">{m["icon"]}</span><span class="t-l">{m["label"]}</span><span class="t-r">{sub}</span></button>')
    tabbar = f'<div class="tabbar" id="tabbar">{"".join(tabs)}</div>'

    # panels
    panels = []
    for i, (key, label, icon) in enumerate(META):
        acc, accg = ACC[key]
        md = detail.get(key, {})
        w, l = md.get('w', 0), md.get('l', 0); t = w + l
        graded = md.get('graded') and t
        rec = f'{w}<em>-</em>{l}' if graded else '<em>—</em>'
        pctv = pct(w, l) if graded else 'pending'
        head = (f'<div class="panel-head"><div class="ph-rec">{rec}</div>'
                f'<div class="ph-meta"><div class="ph-pct">{pctv}</div>'
                f'<div class="ph-lbl">{icon} {label} · {md.get("picks", 0)} calls</div></div></div>')
        extra = ''
        if key == 'K':
            extra += ('<div class="note">Each K call carries its <b>pitcher context</b> — projected hits / runs / ERA, '
                      'and the actual line once graded. The strikeout result decides the W; the rest is the "why".</div>')
        if key == 'HR' and hr_buckets:
            extra += f'<div class="cal-wrap"><div class="block-h">by consensus — does agreement convert?</div>{cal_bars(hr_buckets)}</div>'
        body = (f'{head}{cmp_strip(markets, key)}{extra}'
                f'<div class="block-h">calls</div><div class="pk-list">{rows_html(md.get("rows", []), key)}</div>')
        panels.append(f'<section class="panel {"active" if i == 0 else ""}" id="p-{key}" style="--acc:{acc};--accg:{accg}">{body}</section>')

    spark_html = ''
    if trend:
        bars = ''.join(f'<b style="height:{max(8,min(100,int(v)))}%" class="{"dn" if v<50 else ""}"></b>' for v in trend)
        labs = ''.join(f'<span>{x}</span>' for x in tlabels)
        spark_html = f'<div class="spark">{bars}</div><div class="spark-labels">{labs}</div>'

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>For The Record 💿 — The Daily Slate</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Mono:wght@400;500&family=DM+Sans:opsz,wght@9..40,400;9..40,600;9..40,700;9..40,800&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header class="app-bar">
  <a class="back-chip" href="index.html" aria-label="Back to slate">&lsaquo;</a>
  <a class="brand" href="index.html"><span class="wm">FOR THE <em>RECORD</em> 💿</span></a>
  <div class="spacer"></div>
  <button class="icon-btn" id="themeToggle" aria-label="Toggle theme">&#127769;</button>
</header>
<div class="wrap">
  <div class="hero">
    <div class="eyebrow">Every call · graded vs the box score</div>
    <div class="title">FOR THE <em>RECORD</em> 💿</div>
    <div class="rule"></div>
    <div class="chips">
      <span class="chip"><span class="led"></span>DAY {R.get('season_day','—')}</span>
      <span class="chip">L7 · {l7w}-{l7l}</span>
      <span class="chip">UPDATED {R.get('updated','—')}</span>
    </div>
    {banner}
  </div>

  {tabbar}
  <div class="panels">
{"".join(panels)}
  </div>

  <div class="sec">
    <h2 class="sec-hd">&#128200; DAILY HIT RATE <span>recent slates · &#8805; 50% lifts</span></h2>
    {spark_html or '<p class="muted">Builds as days are graded.</p>'}
  </div>

  <div class="sec">
    <h2 class="sec-hd">&#129518; HOW IT'S GRADED <span>what counts as a win</span></h2>
    <p class="rules"><b>HR / Hits / SB / 2B:</b> the bat records 1+. <b>HRR:</b> hits + runs + RBIs &#8805; 1.
    <b>K:</b> strikeouts clear the line (pitcher hits / ER / outs ride along as context). <b>Totals / NRFI:</b> the lean
    vs the actual result. Scratches and postponements are voided. Grades pull from the official box score &mdash;
    no judgment calls. <b>Losses stay on the board.</b></p>
  </div>
</div>
<div class="foot">For The Record &middot; part of The Daily Slate &#9918;</div>
<script>
document.querySelectorAll('.tab').forEach(function(t){{
  t.addEventListener('click',function(){{
    var m=t.getAttribute('data-m');
    document.querySelectorAll('.tab').forEach(function(x){{x.classList.remove('active');}});
    document.querySelectorAll('.panel').forEach(function(x){{x.classList.remove('active');}});
    t.classList.add('active');
    var p=document.getElementById('p-'+m); if(p) p.classList.add('active');
    t.scrollIntoView({{inline:'center',block:'nearest',behavior:'smooth'}});
  }});
}});
(function(){{var c='dark';try{{var s=localStorage.getItem('slateTheme');if(s==='light'||s==='dark')c=s;}}catch(e){{}}
document.documentElement.setAttribute('data-theme',c);
var t=document.getElementById('themeToggle');t.textContent=c==='dark'?'\\uD83C\\uDF19':'\\u2600\\uFE0F';
t.addEventListener('click',function(){{c=c==='dark'?'light':'dark';
document.documentElement.setAttribute('data-theme',c);t.textContent=c==='dark'?'\\uD83C\\uDF19':'\\u2600\\uFE0F';
try{{localStorage.setItem('slateTheme',c);}}catch(e){{}}}});}})();
</script>
<nav style="position:fixed;left:0;right:0;bottom:0;z-index:70;display:flex;justify-content:space-around;align-items:stretch;height:calc(62px + env(safe-area-inset-bottom,0px));padding:6px 8px calc(env(safe-area-inset-bottom,0px) + 6px);background:rgba(7,9,15,.88);-webkit-backdrop-filter:blur(20px) saturate(1.5);backdrop-filter:blur(20px) saturate(1.5);border-top:1px solid rgba(255,255,255,.1)"><a href="index.html" style="flex:1;max-width:120px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;text-decoration:none;color:#8696a3;font-size:9.5px;font-weight:700;letter-spacing:.6px"><span style="font-size:19px;line-height:1">⚾</span>SLATE</a><a href="k-report.html" style="flex:1;max-width:120px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;text-decoration:none;color:#8696a3;font-size:9.5px;font-weight:700;letter-spacing:.6px"><span style="font-size:19px;line-height:1">📰</span>K REPORT</a><a href="streaks.html" style="flex:1;max-width:120px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;text-decoration:none;color:#8696a3;font-size:9.5px;font-weight:700;letter-spacing:.6px"><span style="font-size:19px;line-height:1">🔥</span>STREAKS</a><a href="scout.html" style="flex:1;max-width:120px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;text-decoration:none;color:#8696a3;font-size:9.5px;font-weight:700;letter-spacing:.6px"><span style="font-size:19px;line-height:1">⚡</span>SSJ</a></nav>
</body></html>"""
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Wrote {OUT_FILE} ({len(html):,} bytes)")
    return html

if __name__ == '__main__':
    build()
