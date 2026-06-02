"""
build_day46_patches.py
======================
EXACT code changes to make in build_day46.py via GitHub web editor.
Three separate edits — apply in order.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDIT 1 — Line 875: Fix 2+H trailing space bug
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FIND (line 875):
    h2 = r.get('2+ Hits ','—')

REPLACE WITH:
    h2 = r.get('2+ Hits','—')

(remove the trailing space inside the quotes)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDIT 2 — build_oo5_board(): add RBI+ formula
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FIND this block (around lines 876-878):
    rbi = r.get('To Get RBI','—')
    hr  = r.get('To Hit HR','—')
    match = r.get('Matchup','—')

REPLACE WITH:
    rbi   = r.get('To Get RBI','—')
    hr    = r.get('To Hit HR','—')
    match = r.get('Matchup','—')

    # ── RBI+ adjusted formula ──
    # Inputs: base RBI%, pitcher hits/game, pitcher K9, park Runs%, ERA
    sp_r    = SP_BY_TEAM.get(opp_team, {}) if opp_team else {}
    h_all   = _sf(sp_r.get('Hits', 4.5))
    sp_era  = _sf(sp_r.get('ERA',  4.25))
    sp_k    = _sf(sp_r.get('K',    0))
    sp_outs = _sf(sp_r.get('Outs', 15))
    sp_ip   = max(sp_outs / 3.0, 1.0)
    k9      = (sp_k / sp_ip * 9) if sp_k > 0 else 8.5
    p_runs  = _sf(str(PARK_BY_TEAM.get(team, {}).get('Runs %', '0')))
    base_r  = _sf(str(rbi).replace('%',''))
    if base_r > 0:
        rbi_plus = round(max(0.0, min(99.0,
            base_r
            + (h_all  - 4.5)  * 2.0   # traffic: more H/game = more runners
            - (k9     - 8.5)  * 0.4   # K9 suppressor: high-K arm kills traffic
            + p_runs          * 0.25  # park run environment
            + (sp_era - 4.25) * 0.6   # ERA tendency
        )), 1)
    else:
        rbi_plus = None

    if rbi_plus is not None:
        if rbi_plus >= 32:
            rbi_cell = (f'<strong style="color:var(--good)">{rbi_plus}%</strong>'
                        f'<br><small style="color:var(--text-dim);font-size:9px">{rbi}</small>')
        elif rbi_plus >= 25:
            rbi_cell = (f'<span style="color:var(--hot)">{rbi_plus}%</span>'
                        f'<br><small style="color:var(--text-dim);font-size:9px">{rbi}</small>')
        else:
            rbi_cell = (f'<span style="color:var(--text-dim)">{rbi_plus}%</span>'
                        f'<br><small style="color:var(--text-dim);font-size:9px">{rbi}</small>')
    else:
        rbi_cell = '—'


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDIT 3 — build_oo5_board(): use rbi_cell in table row
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

In rows.append(...), find the RBI column cell:
    f'<td>{rbi}</td>'

REPLACE WITH:
    f'<td>{rbi_cell}</td>'


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDIT 4 — add PARK_BY_TEAM index if not present
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Near the top of build_day46.py where data indexes are built,
add this block if PARK_BY_TEAM doesn't already exist:

    PARK_BY_TEAM = {}
    for r in PARKS_RAW:   # or whatever the park factors list is named
        game = r.get('Game','')
        for tok in game.replace('@',' ').split():
            t = tn(tok.strip())
            if t and len(t)==3 and t.isalpha() and t not in PARK_BY_TEAM:
                PARK_BY_TEAM[t] = r

(Check what the park factors list variable is called in your file —
it may already be PARKS, PF, or PARK_FACTORS. Adjust accordingly.)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDIT 5 — headlines section: add streaks link
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

In build_headlines() or wherever the headlines HTML section ends,
find the closing </section> or the last card/block in the section.
Add this just before it:

    <div style="text-align:center;margin-top:16px;padding:12px 14px;
      background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);
      border-radius:10px;">
      <a href="streaks.html" style="color:#f87171;font-weight:700;
        text-decoration:none;font-size:14px;">
        🔥 See Today's Hot Streaks →
      </a>
    </div>

"""

# This file is documentation only — no code to run.
# Apply the 5 edits above in GitHub's web editor.
