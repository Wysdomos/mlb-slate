"""Compatibility pass for editorial build step.

Chapter I and Chapter J moved the page's editorial and parlay surfaces into
build_day46.py. This module intentionally does not rebuild or overwrite those
sections; it remains in the pipeline after build_streaks.py so the hot streak
export can still be audited without reintroducing a second owner.
"""

import json
import os

SECTIONS_FILE = os.environ.get('SECTIONS_FILE', 'built_sections.json')
HOT_STREAKS_FILE = os.environ.get('HOT_STREAKS_FILE', 'hot_streaks.json')

SECTIONS = json.load(open(SECTIONS_FILE, encoding='utf-8'))

try:
    HOT_STREAKS = json.load(open(HOT_STREAKS_FILE, encoding='utf-8'))
    if not isinstance(HOT_STREAKS, dict):
        HOT_STREAKS = {}
except Exception:
    HOT_STREAKS = {}

with open(SECTIONS_FILE, 'w', encoding='utf-8') as f:
    json.dump(SECTIONS, f, ensure_ascii=False, indent=1)

print("build_editorial: Chapter I/J sections owned by build_day46.py; no overrides written")
print(
    "build_editorial: hot_streaks audit "
    f"{len(HOT_STREAKS.get('all', []))} hot batters, "
    f"{len(HOT_STREAKS.get('HR', []))} HR streakers"
)
