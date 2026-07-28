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

MARKET_ORDER = [
    'K', 'OUTS', 'OUTS_ALT', 'H_ALLOWED', 'H_ALLOWED_ALT',
    'HR', 'TB', 'HIT', 'HRR', '2B', 'SB', 'NRFI', 'TOTAL',
]
BANDS = [(5, 6, '5-6 lenses'), (4, 4, '4 lenses'), (0, 3, '<=3 lenses')]
ALT_MARGIN_BANDS = [
    (0.0, 1.99, '<2.0 alt margin'),
    (2.0, 2.99, '2.0-2.99 alt margin'),
    (3.0, 99.0, '>=3.0 alt margin'),
]
MIN_PARLAY_SAMPLE = 30


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


def pct(value):
    return f'{value:.1%}'


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


def append_correlation_buckets(md, rows):
    labeled = [g for g in rows if g.get('correlation_type')]
    md.append('\n## Parlay correlation buckets\n')
    if not labeled:
        md.append('No parlay correlation labels have been backfilled yet.\n')
        return
    md.append('| Correlation type | W-L | n | Hit rate | 95% CI |')
    md.append('|---|---|---|---|---|')
    for correlation_type in sorted({g.get('correlation_type') for g in labeled}):
        band = [g for g in labeled if g.get('correlation_type') == correlation_type]
        w = sum(1 for g in band if g['win'])
        md.append(line(w, len(band) - w, correlation_type))

def append_same_game_buckets(md, rows):
    labeled = [g for g in rows if g.get('same_game') is not None]
    md.append('\n## Parlay same-game buckets\n')
    if not labeled:
        md.append('No same-game parlay labels have been backfilled yet.\n')
        return
    md.append('| Same game | W-L | n | Hit rate | 95% CI |')
    md.append('|---|---|---|---|---|')
    for value in (True, False):
        band = [g for g in labeled if bool(g.get('same_game')) is value]
        w = sum(1 for g in band if g['win'])
        md.append(line(w, len(band) - w, str(value)))


def collect_parlays(rows):
    grouped = defaultdict(list)
    for row in rows:
        parlay_id = row.get('parlay_id')
        if parlay_id:
            grouped[parlay_id].append(row)

    parlays = []
    for parlay_id, legs in sorted(grouped.items()):
        wins = [leg.get('win') for leg in legs]
        if any(win is None for win in wins):
            result = None
        else:
            result = all(bool(win) for win in wins)
        correlation_types = {leg.get('correlation_type') for leg in legs if leg.get('correlation_type')}
        same_game_values = {bool(leg.get('same_game')) for leg in legs if leg.get('same_game') is not None}
        parlays.append({
            'parlay_id': parlay_id,
            'legs': legs,
            'result': result,
            'correlation_type': next(iter(correlation_types)) if len(correlation_types) == 1 else 'mixed',
            'same_game': next(iter(same_game_values)) if len(same_game_values) == 1 else None,
            'leg_count': len(legs),
        })
    return parlays


def parlay_bucket_stats(parlays):
    graded = [p for p in parlays if p['result'] is not None]
    wins = sum(1 for p in graded if p['result'])
    ungraded = len(parlays) - len(graded)
    graded_legs = [leg for p in graded for leg in p['legs'] if leg.get('win') is not None]
    leg_wins = sum(1 for leg in graded_legs if leg.get('win'))
    leg_rate = (leg_wins / len(graded_legs)) if graded_legs else None

    rates_by_market = {}
    legs_by_market = defaultdict(list)
    for leg in graded_legs:
        legs_by_market[leg.get('market')].append(leg)
    for market, legs in legs_by_market.items():
        rates_by_market[market] = sum(1 for leg in legs if leg.get('win')) / len(legs)

    expected_values = []
    for parlay in graded:
        product = 1.0
        for leg in parlay['legs']:
            market = leg.get('market')
            product *= rates_by_market.get(market, leg_rate or 0.0)
        expected_values.append(product)
    expected = (sum(expected_values) / len(expected_values)) if expected_values else None
    actual = (wins / len(graded)) if graded else None
    lift = (actual - expected) if actual is not None and expected is not None else None
    return {
        'total': len(parlays),
        'graded': len(graded),
        'won': wins,
        'ungraded': ungraded,
        'leg_wins': leg_wins,
        'leg_total': len(graded_legs),
        'leg_rate': leg_rate,
        'actual': actual,
        'expected': expected,
        'lift': lift,
    }


def parlay_scoreboard_line(label, parlays):
    stats = parlay_bucket_stats(parlays)
    leg_record = f"{stats['leg_wins']}-{stats['leg_total'] - stats['leg_wins']}"
    if stats['graded'] < MIN_PARLAY_SAMPLE:
        return (
            f"| {label} | {stats['graded']} | {stats['won']} | {stats['ungraded']} | "
            f"{leg_record} | insufficient data -- keep accumulating | – | – |"
        )
    return (
        f"| {label} | {stats['graded']} | {stats['won']} | {stats['ungraded']} | "
        f"{leg_record} ({pct(stats['leg_rate'])}) | {pct(stats['actual'])} | "
        f"{pct(stats['expected'])} | {pct(stats['lift'])} |"
    )


def append_parlay_scoreboard(md, rows):
    parlays = collect_parlays(rows)
    md.append('\n## Parlay scoreboard\n')
    md.append(
        'Parlays are graded as full tickets: every leg must win. If any leg is '
        'ungraded, the parlay is ungraded rather than a loss. Expected '
        'independent rate is the average product of each graded parlay\'s '
        'empirical leg-market hit rates inside the same bucket.\n'
    )
    if not parlays:
        md.append('No parlay legs have been backfilled yet.\n')
        return

    for correlation_type in sorted({p['correlation_type'] for p in parlays}):
        section = [p for p in parlays if p['correlation_type'] == correlation_type]
        md.append(f'\n### {correlation_type}\n')
        md.append('| Split | Parlays graded | Parlays won | Ungraded | Leg W-L | Parlay hit rate | Expected independent | Correlation lift |')
        md.append('|---|---:|---:|---:|---:|---|---|---|')
        md.append(parlay_scoreboard_line('all', section))
        for value in (True, False):
            split = [p for p in section if p['same_game'] is value]
            md.append(parlay_scoreboard_line(f'same_game={value}', split))
        for leg_count in (2, 3):
            split = [p for p in section if p['leg_count'] == leg_count]
            md.append(parlay_scoreboard_line(f'{leg_count} legs', split))


def append_conviction_rank_buckets(md, rows):
    labeled = [g for g in rows if g.get('conviction_rank') is not None]
    md.append('\n## Conviction rank buckets\n')
    if not labeled:
        md.append('No conviction ranks have been backfilled yet.\n')
        return
    md.append('| Conviction rank | W-L | n | Hit rate | 95% CI |')
    md.append('|---|---|---|---|---|')
    ranks = sorted({int(g.get('conviction_rank')) for g in labeled})
    for rank in ranks:
        band = [g for g in labeled if int(g.get('conviction_rank')) == rank]
        w = sum(1 for g in band if g['win'])
        md.append(line(w, len(band) - w, f'Rank {rank}'))

def append_alt_margin_buckets(md, rows):
    labeled = [
        g for g in rows
        if g.get('market') in ('H_ALLOWED_ALT', 'OUTS_ALT')
        and g.get('alt_margin') is not None
    ]
    md.append('\n## Pitcher alt margin buckets\n')
    if not labeled:
        md.append('No pitcher alt margins have been backfilled yet.\n')
        return
    for mkt in ('H_ALLOWED_ALT', 'OUTS_ALT'):
        sub = [g for g in labeled if g.get('market') == mkt]
        if not sub:
            continue
        md.append(f'\n### {mkt}\n')
        md.append('| Alt margin | W-L | n | Hit rate | 95% CI |')
        md.append('|---|---|---|---|---|')
        for lo, hi, label_text in ALT_MARGIN_BANDS:
            band = [g for g in sub if lo <= float(g.get('alt_margin')) <= hi]
            w = sum(1 for g in band if g['win'])
            md.append(line(w, len(band) - w, label_text))


def build(store, source_filter=None):
    all_rows = [
        g for g in store['graded']
        if source_filter is None or pick_source(g) == source_filter
    ]
    rows = [g for g in all_rows if g['win'] is not None]
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
            band = [g for g in sub if lo <= g.get('consensus', 0) <= hi]
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
    append_correlation_buckets(md, rows)
    append_same_game_buckets(md, rows)
    append_parlay_scoreboard(md, all_rows)
    append_conviction_rank_buckets(md, rows)
    append_alt_margin_buckets(md, rows)

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
