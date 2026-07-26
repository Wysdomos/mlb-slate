"""Calibration report from backfilled pick grades. Fully offline.

Reads backtest/graded_picks.json, writes backtest/CALIBRATION.md.
Answers one question per market: when the slate says "play this",
how often does it actually hit -- overall, and by consensus strength?

No odds are invented. A break-even reference table for common American
prices is included so hit rates can be eyeballed against real books.

Usage (from repo root):  python3 backtest/calibration.py
"""
import json
import math
import os
import sys
import argparse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'graded_picks.json')
OUT = os.path.join(HERE, 'CALIBRATION.md')
sys.path.insert(0, os.path.dirname(HERE))
from shadow_chips import CHIP_FIELDS, CHIP_LABELS, TIER_ORDER

MARKET_ORDER = ['K', 'HR', 'HIT', 'HRR', '2B', 'SB', 'NRFI', 'TOTAL']
BANDS = [(5, 6, '5-6 lenses'), (4, 4, '4 lenses'), (0, 3, '<=3 lenses')]


def wilson(w, n, z=1.96):
    """95% Wilson score interval for a hit rate -- honest at small n."""
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def line(w, l, label):
    n = w + l
    if n == 0:
        return f'| {label} | – | – | – | – |'
    lo, hi = wilson(w, n)
    flag = ' ⚠ small n' if n < 30 else ''
    return (f'| {label} | {w}-{l} | {n} | **{w / n:.1%}** | '
            f'{lo:.0%}–{hi:.0%}{flag} |')


def pick_source(row):
    return row.get('pick_source', 'workbook') or 'workbook'


def append_chip_buckets(md, rows):
    md.append('\n## Shadow chip candidates\n')
    md.append('These buckets are shadow-only. Missing historical labels are ignored.\n')
    for field in CHIP_FIELDS:
        labeled = [g for g in rows if g.get(field) is not None]
        status = 'ready for interval review' if len(labeled) >= 100 else 'insufficient data -- keep accumulating'
        md.append(f'\n### {CHIP_LABELS[field]} (`{field}`) -- {status}\n')
        md.append('| Tier | W-L | n | Hit rate | 95% CI |')
        md.append('|---|---|---|---|---|')
        for tier in TIER_ORDER:
            band = [g for g in labeled if g.get(field) == tier]
            w = sum(1 for g in band if g['win'])
            md.append(line(w, len(band) - w, tier))


def build(store, source_filter=None):
    rows = [
        g for g in store['graded']
        if g['win'] is not None
        and (source_filter is None or pick_source(g) == source_filter)
    ]
    dates = store.get('dates', {})
    md = []
    md.append('# The Daily Slate — Calibration Report')
    md.append(f"\n*{len(rows)} graded picks across {len(dates)} slate days "
              f"({min(dates)} → {max(dates)}). Pushes and ungradeable picks "
              f"excluded. Intervals are 95% Wilson.*\n")

    by_mkt = defaultdict(list)
    for g in rows:
        by_mkt[g['market']].append(g)

    md.append('## Overall by market\n')
    md.append('| Market | W-L | n | Hit rate | 95% CI |')
    md.append('|---|---|---|---|---|')
    for mkt in MARKET_ORDER:
        sub = by_mkt.get(mkt, [])
        w = sum(1 for g in sub if g['win'])
        md.append(line(w, len(sub) - w, mkt))

    for mkt in MARKET_ORDER:
        sub = by_mkt.get(mkt, [])
        if not sub:
            continue
        md.append(f'\n## {mkt} — by consensus\n')
        md.append('| Bucket | W-L | n | Hit rate | 95% CI |')
        md.append('|---|---|---|---|---|')
        for lo, hi, label in BANDS:
            band = [g for g in sub if lo <= g['consensus'] <= hi]
            w = sum(1 for g in band if g['win'])
            md.append(line(w, len(band) - w, label))
        if mkt == 'K':
            md.append(f'\n### {mkt} — by line (win_at)\n')
            md.append('| Line | W-L | n | Hit rate | 95% CI |')
            md.append('|---|---|---|---|---|')
            lines = sorted({g.get('win_at') for g in sub if g.get('win_at')})
            for wa in lines:
                band = [g for g in sub if g.get('win_at') == wa]
                w = sum(1 for g in band if g['win'])
                md.append(line(w, len(band) - w, f'O {wa - 0.5}'))

    append_chip_buckets(md, rows)

    md.append('\n## Break-even reference (for eyeballing edge)\n')
    md.append('*Reference math only — historical book prices were not stored, '
              'so no edge is claimed. Compare a bucket\'s hit rate to the '
              'break-even of the price you actually see.*\n')
    md.append('| Price | Break-even hit rate |')
    md.append('|---|---|')
    for am in (-200, -150, -110, 100, 150, 250, 400):
        be = (-am) / (-am + 100) if am < 0 else 100 / (am + 100)
        md.append(f'| {am:+d} | {be:.1%} |')

    md.append('\n## Reading this honestly\n')
    md.append('A bucket only means something once n clears ~30; below that '
              'the interval says more than the point estimate. If a high-'
              'consensus bucket does not clearly beat a low one, the consensus '
              'signal is not separating -- that is a finding, not a failure. '
              'This report is the gate for the XGBoost question: models only '
              'earn a seat if these buckets leave measurable room.\n')
    return '\n'.join(md) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--pick-source', choices=('workbook', 'projected'))
    args = parser.parse_args(argv)

    if not os.path.exists(SRC):
        raise SystemExit('backtest/graded_picks.json missing -- run '
                         'backtest/backfill_grades.py first (needs network).')
    with open(SRC, encoding='utf-8') as f:
        store = json.load(f)
    report = build(store, source_filter=args.pick_source)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'wrote {OUT} ({len(report)} bytes)')


if __name__ == '__main__':
    main()
