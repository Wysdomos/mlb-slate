"""
extract_xlsx.py -- Daily MLB Slate Excel -> JSON extractor
Usage:  python3 extract_xlsx.py <path_to_xlsx> [output_json]

Defaults:
  - Looks for any .xlsx file in current directory if no path given
  - Outputs to day_data.json if no output path given

Works for any slate size (6 games or 15, any number of batters/pitchers).
"""

import sys
import json
import os
import glob
from openpyxl import load_workbook

def find_xlsx():
    if len(sys.argv) >= 2:
        path = sys.argv[1]
        if not os.path.exists(path):
            print(f"ERROR: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        return path
    matches = glob.glob("*.xlsx") + glob.glob("**/*.xlsx", recursive=False)
    if not matches:
        print("ERROR: No .xlsx file found.", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Multiple xlsx found, using: {matches[0]}", file=sys.stderr)
    return matches[0]

def resolve_output():
    return sys.argv[2] if len(sys.argv) >= 3 else "day_data.json"

def sheet_to_rows(ws):
    headers = None
    rows = []
    for row in ws.iter_rows(values_only=True):
        if headers is None:
            if any(c is not None for c in row):
                headers = [str(c).strip() if c is not None else f"Col{i}"
                           for i, c in enumerate(row)]
            continue
        if not any(c is not None for c in row):
            continue
        record = {}
        for i, val in enumerate(row):
            if i < len(headers):
                if isinstance(val, float) and val == int(val):
                    val = int(val)
                record[headers[i]] = val
        rows.append(record)
    return rows

def clean_val(v):
    if v is None:
        return None
    if isinstance(v, float):
        if v != v:
            return None
        if v == int(v):
            return int(v)
    return v

def clean_rows(rows):
    return [{k: clean_val(v) for k, v in r.items()} for r in rows]

def extract(xlsx_path):
    print(f"Reading: {xlsx_path}", file=sys.stderr)
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    print(f"Sheets found: {wb.sheetnames}", file=sys.stderr)

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
            print(f"  WARNING: Sheet '{sheet_name}' not found -- skipping", file=sys.stderr)
            data[json_key] = []
            continue
        ws = wb[sheet_name]
        rows = clean_rows(sheet_to_rows(ws))
        data[json_key] = rows
        cols = len(rows[0]) if rows else 0
        index_rows.append({"Sheet": sheet_name, "Rows": len(rows), "Cols": cols})
        print(f"  {sheet_name}: {len(rows)} rows", file=sys.stderr)

    data["INDEX"] = index_rows
    wb.close()
    return data

if __name__ == "__main__":
    xlsx_path = find_xlsx()
    output_path = resolve_output()
    data = extract(xlsx_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    total_rows = sum(len(v) for v in data.values() if isinstance(v, list))
    print(f"Done. {total_rows} total rows -> {output_path}", file=sys.stderr)
