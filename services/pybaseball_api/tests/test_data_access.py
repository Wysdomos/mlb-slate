"""Tests for the one shared PyBaseball and CSV data-access layer."""

import json

import numpy as np
import pandas as pd
import pytest

from backtest.data_access import (
    IncompleteDatasetError,
    PyBaseballDataAccess,
    frame_page,
    load_complete_dataset,
)


class CountingBackend:
    def __init__(self):
        self.player_lookup_calls = 0

    def playerid_lookup(self, last, first=None, fuzzy=False):
        self.player_lookup_calls += 1
        return pd.DataFrame(
            [
                {
                    "name_last": last,
                    "name_first": first,
                    "key_mlbam": 592450,
                    "fuzzy": fuzzy,
                }
            ]
        )


def test_second_identical_call_makes_zero_new_upstream_requests(tmp_path):
    backend = CountingBackend()
    data_access = PyBaseballDataAccess(
        backend=backend,
        cache_dir=tmp_path,
        cache_ttl_seconds=3_600,
    )

    first = data_access.player_lookup("judge", "aaron", False)
    calls_after_first = backend.player_lookup_calls
    second = data_access.player_lookup("judge", "aaron", False)

    assert calls_after_first == 1
    assert backend.player_lookup_calls - calls_after_first == 0
    assert len(list(tmp_path.glob("*.csv"))) == 1
    assert first.iloc[0]["key_mlbam"] == second.iloc[0]["key_mlbam"]


def test_non_finite_and_missing_values_round_trip_as_valid_json():
    frame = pd.DataFrame(
        {
            "metric": [np.inf, -np.inf, np.nan, 1.25],
            "recorded_at": [pd.NaT, pd.Timestamp("2026-07-13"), pd.NaT, pd.NaT],
        }
    )

    page = frame_page(frame, offset=0, limit=10)
    encoded = json.dumps(page.records, allow_nan=False)
    decoded = json.loads(encoded)

    assert [row["metric"] for row in decoded] == [None, None, None, 1.25]
    assert decoded[0]["recorded_at"] is None
    assert decoded[1]["recorded_at"].startswith("2026-07-13")


def test_complete_loader_paginates_until_truncated_is_false():
    all_records = [{"id": 1}, {"id": 2}, {"id": 3}]
    calls = []

    def fetch_page(offset, limit):
        calls.append((offset, limit))
        records = all_records[offset : offset + limit]
        next_offset = offset + len(records)
        truncated = next_offset < len(all_records)
        return {
            "records": records,
            "row_count": len(records),
            "total_rows": len(all_records),
            "offset": offset,
            "next_offset": next_offset if truncated else None,
            "truncated": truncated,
        }

    complete = load_complete_dataset(fetch_page, page_size=2)

    assert calls == [(0, 2), (2, 2)]
    assert complete.records == all_records
    assert complete.total_rows == 3


def test_complete_loader_refuses_truncated_page_without_progress():
    def stuck_page(offset, limit):
        return {
            "records": [],
            "row_count": 0,
            "total_rows": 3,
            "offset": offset,
            "next_offset": offset,
            "truncated": True,
        }

    with pytest.raises(
        IncompleteDatasetError,
        match="forward next_offset",
    ):
        load_complete_dataset(stuck_page, page_size=2)
