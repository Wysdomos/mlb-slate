"""
build.py -- Path-agnostic wrapper for build_day46.py
Reads:  day_data.json
Writes: built_sections.json
"""
import os

DATA_FILE     = os.environ.get('DATA_FILE',     'day_data.json')
SECTIONS_FILE = os.environ.get('SECTIONS_FILE', 'built_sections.json')

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
