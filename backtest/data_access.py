"""pybaseball access layer for backtesting -- The Daily Slate.

This is the project's "pybaseball API": not a server (doctrine: AI writes,
Python runs, GitHub hosts), but one clean module every backtest script goes
through. Runs on the M5 where pybaseball is installed; every pull is cached
to backtest/cache/ as CSV so repeat runs cost zero network and stay
reproducible.

Usage (M5, from repo root):
    pip install pybaseball pandas
    python3 -c "from backtest.data_access import pitcher_game_logs;
                print(pitcher_game_logs(2026).shape)"
"""
import os

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')


def _cached(name, fetch, loader=None, saver=None):
    """Disk-cache a DataFrame pull. fetch() runs only on cache miss."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name + '.csv')
    if os.path.exists(path):
        if loader is None:
            import pandas as pd
            loader = pd.read_csv
        return loader(path)
    df = fetch()
    if saver is None:
        saver = lambda d, p: d.to_csv(p, index=False)
    saver(df, path)
    return df


def _pb():
    try:
        import pybaseball
        pybaseball.cache.enable()
        return pybaseball
    except ImportError:
        raise SystemExit('pybaseball not installed -- run on the M5: '
                         'pip install pybaseball pandas')


def pitcher_game_logs(season):
    """Per-start pitching logs for a season (K, IP, H, ER by date).
    Feeds K-market calibration slices (line difficulty, rest, opponent)."""
    return _cached(f'pitching_{season}',
                   lambda: _pb().pitching_stats_range(
                       f'{season}-03-01', f'{season}-11-30'))


def batter_game_logs(season):
    """Per-game batting logs for a season (HR, H, RBI, SB, 2B by date).
    Feeds HR/HIT/HRR calibration slices."""
    return _cached(f'batting_{season}',
                   lambda: _pb().batting_stats_range(
                       f'{season}-03-01', f'{season}-11-30'))


def statcast_pitcher_percentiles(season):
    """Savant expected stats (xERA, xwOBA, hard-hit) for pitcher context.
    Backs the VulnScore-vs-expected-stats comparison."""
    return _cached(f'statcast_exp_pitch_{season}',
                   lambda: _pb().statcast_pitcher_expected_stats(season))


def statcast_batter_percentiles(season):
    """Savant expected stats (barrel%, xSLG) for batter context.
    Backs the RBI+ and HR-board enrichment work."""
    return _cached(f'statcast_exp_bat_{season}',
                   lambda: _pb().statcast_batter_expected_stats(season))
