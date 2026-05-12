“””
extract_xlsx.py — Daily MLB Slate Excel → JSON extractor
Usage:  python3 extract_xlsx.py <path_to_xlsx> [output_json]

Defaults:

- Looks for any .xlsx file in current directory if no path given
- Outputs to day_data.json if no output path given

Works for any slate size (6 games or 15, any number of batters/pitchers).
“””

import sys
import json
import os
import glob
from openpyxl import load_workbook

# ── Resolve input / output paths ──────────────────────────────────────────────

def find_xlsx():
“”“Find the xlsx file — arg, or first .xlsx in current dir.”””
if len(sys.argv) >= 2:
path = sys.argv[1]
if not os.path.exists(path):
print(f”ERROR: File not found: {path}”, file=sys.stderr)
sys.exit(1)
return path
matches = glob.glob(”*.xlsx”) + glob.glob(”**/*.xlsx”, recursive=False)
if not matches:
print(“ERROR: No .xlsx file found. Pass path as argument.”, file=sys.stderr)
sys.exit(1)
if len(matches) > 1:
print(f”Multiple xlsx found, using: {matches[0]}”, file=sys.stderr)
return matches[0]

def resolve_output():
return sys.argv[2] if len(sys.argv) >= 3 else “day_data.json”

# ── Sheet reader helpers ───────────────────────────────────────────────────────

def sheet_to_rows(ws):
“”“Convert a worksheet to list of dicts. Skips fully empty rows.”””
headers = None
rows = []
for row in ws.iter_rows(values_only=True):
if headers is None:
# First non-empty row is headers
if any(c is not None for c in row):
headers = [str(c).strip() if c is not None else f”Col{i}”
for i, c in enumerate(row)]
continue
if not any(c is not None for c in row):
continue  # skip blank rows
record = {}
for i, val in enumerate(row):
if i < len(headers):
# Convert floats that are whole numbers to int for cleanliness
if isinstance(val, float) and val == int(val):
val = int(val)
record[headers[i]] = val
rows.append(record)
return rows

def clean_val(v):
“”“Ensure JSON-serialisable value.”””
if v is None:
return None
if isinstance(v, float):
if v != v:  # NaN
return None
if v == int(v):
return int(v)
return v

def clean_rows(rows):
return [{k: clean_val(v) for k, v in r.items()} for r in rows]

# ── Main extraction ────────────────────────────────────────────────────────────

def extract(xlsx_path):
print(f”Reading: {xlsx_path}”, file=sys.stderr)
wb = load_workbook(xlsx_path, read_only=True, data_only=True)
print(f”Sheets found: {wb.sheetnames}”, file=sys.stderr)

```
# Map of expected sheet names → JSON key
# If your xlsx renames a sheet, add the alias here
SHEET_MAP = {
    "HR_Leaderboard":      "HR_Leaderboard",
    "Hit_Probabilities":   "Hit_Probabilities",
    "Sweet_Spot_Analyzer": "Sweet_Spot_Analyzer",
    "Pitcher_Projections": "Pitcher_Projections",
    "SP_Projections":      "SP_Projections",
    "Park_Factors":        "Park_Factors",
    "Sweet_Spot_Slate":    "Sweet_Spot_Slate",
    "BP_Batters":          "BP_Batters",
    "BP_Pitchers":         "BP_Pitchers",
    "BP_Teams":            "BP_Teams",
    "BP_Games":            "BP_Games",
}

data = {}
index_rows = []

for sheet_name, json_key in SHEET_MAP.items():
    if sheet_name not in wb.sheetnames:
        print(f"  WARNING: Sheet '{sheet_name}' not found — skipping", file=sys.stderr)
        data[json_key] = []
        continue

    ws = wb[sheet_name]
    rows = clean_rows(sheet_to_rows(ws))
    data[json_key] = rows

    # Build INDEX entry
    if rows:
        cols = len(rows[0])
    else:
        cols = 0
    index_rows.append({
        "Sheet": sheet_name,
        "Rows": len(rows),
        "Cols": cols,
        "Description": _sheet_desc(sheet_name)
    })
    print(f"  {sheet_name}: {len(rows)} rows", file=sys.stderr)

data["INDEX"] = index_rows
wb.close()
return data
```

def _sheet_desc(name):
descs = {
“HR_Leaderboard”:      “Home run projections ranked by quality score. Barrel%, HH%, xwOBA, Zone.”,
“Hit_Probabilities”:   “Hit probability for all batters. 1+ Hit %, 2+ Hits %, RBI %, HR %.”,
“Sweet_Spot_Analyzer”: “Batter grades (STRONG/MODERATE/BAD) vs specific pitchers with HR zone.”,
“Pitcher_Projections”: “Pitcher projections: earned runs, strikeouts, outs, hits (MLBP format).”,
“SP_Projections”:      “Starting pitcher projections: Inn, BF, R, H, HR, K, BB by team/pitcher.”,
“Park_Factors”:        “Stadium + weather impact on HR, 2B/3B, 1B, Runs for all games.”,
“Sweet_Spot_Slate”:    “Pitcher vulnerability scores (VulnScore) + top 3 danger batters with ISO.”,
“BP_Batters”:          “BallparkPal batter projections: HR prob, hit prob, SB prob, DK/FD points.”,
“BP_Pitchers”:         “BallparkPal pitcher projections: win/loss/ND%, K, hits, runs, DK/FD points.”,
“BP_Teams”:            “BallparkPal team projections: runs, win%, HR and run distributions.”,
“BP_Games”:            “BallparkPal game projections: total runs, first 5 innings, win margins.”,
}
return descs.get(name, “”)

# ── Entry point ────────────────────────────────────────────────────────────────

if **name** == “**main**”:
xlsx_path = find_xlsx()
output_path = resolve_output()

```
data = extract(xlsx_path)

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2, default=str)

total_rows = sum(len(v) for v in data.values() if isinstance(v, list))
print(f"\nDone. {total_rows} total rows → {output_path}", file=sys.stderr)
```
