import unittest

from services.kalshi_client.matcher import (
    SERIES_BY_MARKET,
    build_match_snapshot,
    coverage_by_market,
    match_candidate,
    missing_exact_strikes,
)
from services.kalshi_client.models import AskSource, TradableState


SLATE_DATE = "2026-08-31"


def candidate(
    market_type="pitcher_strikeouts",
    *,
    game_key="PHI@AZ",
    player="Test Pitcher",
    player_norm="test pitcher",
    team="AZ",
    direction="over",
    threshold=5.5,
    probability_kind="projection_only",
):
    player_token = player_norm.upper().replace(" ", "_") if player_norm else None
    slate_id = f"{SLATE_DATE}_{game_key}_{market_type.upper()}_{direction.upper()}"
    if player_token:
        slate_id = f"{SLATE_DATE}_{game_key}_{player_token}_{team}_{market_type.upper()}_{direction.upper()}_{str(threshold).replace('.', '_')}"
    return {
        "slate_id": slate_id,
        "slate_date": SLATE_DATE,
        "game_key": game_key,
        "away_team": game_key.split("@")[0],
        "home_team": game_key.split("@")[1],
        "player": player,
        "player_norm": player_norm,
        "team": team,
        "market_type": market_type,
        "direction": direction,
        "threshold": threshold,
        "display_line": "O 6+",
        "probability_kind": probability_kind,
        "consensus": 4,
        "matchable": True,
    }


def market(
    market_type="pitcher_strikeouts",
    *,
    game_key="PHI@AZ",
    player_name="Test Pitcher",
    team="AZ",
    threshold=5.5,
    title=None,
    rules=None,
    ticker_suffix="AZTPITCHER99-6",
    status="active",
    yes_ask=0.78,
    yes_bid=None,
    tradable_state=None,
):
    away, home = game_key.split("@")
    series = SERIES_BY_MARKET[market_type]
    event_ticker = f"{series}-26AUG312140{away}{home}"
    title = title or (f"{player_name}: 6+ strikeouts?" if player_name else "Philadelphia vs Arizona total runs")
    rules = rules or (
        f"If {player_name or 'the teams'} records more than {threshold} in the professional baseball game, "
        "then the market resolves to Yes."
    )
    row = {
        "series_ticker": series,
        "event_ticker": event_ticker,
        "market_ticker": f"{event_ticker}-{ticker_suffix}",
        "title": title,
        "market_family": series,
        "slate_date": SLATE_DATE,
        "away_team": away,
        "home_team": home,
        "player_name": player_name,
        "team": team,
        "threshold": threshold,
        "slate_market": market_type,
        "slate_side": "over",
        "kalshi_side": "yes",
        "yes_ask_reported": yes_ask,
        "yes_ask_derived": yes_ask,
        "ask_source": "agree",
        "tradable_state": tradable_state or "",
        "quote_age_seconds": 10,
        "fee_band": "extreme",
        "settlement_note": "fixture settlement note",
        "url": f"https://kalshi.example/{event_ticker}",
        "raw_status": status,
        "rules_primary": rules,
    }
    if yes_bid is not None:
        row["yes_bid_dollars"] = yes_bid
    return row


class MatcherTests(unittest.TestCase):
    def test_exact_match_end_to_end_confidence_100(self):
        result = match_candidate(candidate(), [market()])
        self.assertEqual(result.tradable_state, TradableState.OPEN_TRADABLE.value)
        self.assertEqual(result.match_confidence, 100)
        self.assertEqual(result.kalshi_ticker, "KXMLBKS-26AUG312140PHIAZ-AZTPITCHER99-6")
        self.assertEqual(result.match_gates_passed, ["sport", "date", "game", "family", "player", "threshold", "side"])

    def test_same_player_wrong_game_rejected_before_name_is_trusted(self):
        slate = candidate(
            game_key="LAD@SD",
            player="Max Muncy",
            player_norm="max muncy",
            team="LAD",
            threshold=0.5,
            market_type="batter_home_runs",
        )
        other_muncy = market(
            "batter_home_runs",
            game_key="ATH@SEA",
            player_name="Max Muncy",
            team="ATH",
            threshold=0.5,
            ticker_suffix="ATHMUNCY-1",
        )
        result = match_candidate(slate, [other_muncy])
        self.assertEqual(result.tradable_state, TradableState.NOT_LISTED.value)

    def test_same_game_wrong_market_family_rejected(self):
        slate = candidate(market_type="pitcher_strikeouts", threshold=0.5)
        wrong_family = market("batter_home_runs", player_name="Test Pitcher", team="AZ", threshold=0.5)
        result = match_candidate(slate, [wrong_family])
        self.assertEqual(result.tradable_state, TradableState.NOT_LISTED.value)

    def test_threshold_mismatch_is_not_substituted_and_records_strikes(self):
        slate = candidate(threshold=5.5)
        markets = [
            market(threshold=4.5, ticker_suffix="AZTPITCHER99-5"),
            market(threshold=6.5, ticker_suffix="AZTPITCHER99-7"),
        ]
        result = match_candidate(slate, markets)
        self.assertEqual(result.tradable_state, TradableState.NOT_LISTED.value)
        self.assertEqual(result.reason, "threshold_not_listed")
        self.assertEqual(result.available_strikes, [4.5, 6.5])

    def test_ladder_exact_strike_is_selected(self):
        markets = [
            market(threshold=4.5, ticker_suffix="AZTPITCHER99-5"),
            market(threshold=5.5, ticker_suffix="AZTPITCHER99-6"),
            market(threshold=6.5, ticker_suffix="AZTPITCHER99-7"),
        ]
        result = match_candidate(candidate(threshold=5.5), markets)
        self.assertEqual(result.tradable_state, TradableState.OPEN_TRADABLE.value)
        self.assertTrue(result.kalshi_ticker.endswith("-6"))
        self.assertEqual(result.available_strikes, [5.5])

    def test_nrfi_maps_to_no_side_and_price_comes_from_yes_bid(self):
        slate = candidate(
            "run_first_inning",
            player=None,
            player_norm=None,
            team=None,
            direction="no",
            threshold=None,
            probability_kind="model_probability_unvalidated",
        )
        rfi = market(
            "run_first_inning",
            player_name=None,
            team=None,
            threshold=None,
            title="Will there be a run in the first inning?",
            rules="If a run is scored in the first inning, then the market resolves to Yes.",
            ticker_suffix="RFI",
            yes_ask=None,
            yes_bid="0.6300",
        )
        result = match_candidate(slate, [rfi])
        self.assertEqual(result.kalshi_side, "no")
        self.assertEqual(result.buy_price, 0.37)
        self.assertEqual(result.ask_source, AskSource.DERIVED_ONLY.value)

    def test_game_total_under_phrased_contract_maps_to_yes(self):
        slate = candidate(
            "game_total",
            player=None,
            player_norm=None,
            team=None,
            direction="under",
            threshold=8.5,
        )
        total = market(
            "game_total",
            player_name=None,
            team=None,
            threshold=8.5,
            title="Philadelphia vs Arizona: fewer than 8.5 runs?",
            rules="If the teams score fewer than 8.5 runs, then the market resolves to Yes.",
            ticker_suffix="TOTAL-U85",
        )
        result = match_candidate(slate, [total])
        self.assertEqual(result.tradable_state, TradableState.OPEN_TRADABLE.value)
        self.assertEqual(result.kalshi_side, "yes")

    def test_two_equal_score_survivors_are_ambiguous(self):
        first = market(ticker_suffix="A")
        second = market(ticker_suffix="B")
        result = match_candidate(candidate(), [first, second])
        self.assertEqual(result.tradable_state, TradableState.MATCH_AMBIGUOUS.value)
        self.assertIsNone(result.kalshi_ticker)
        self.assertEqual(len(result.ambiguous_survivors or []), 2)

    def test_no_orderbook_or_ask_is_open_no_quote_never_live(self):
        no_quote = market(yes_ask=None)
        result = match_candidate(candidate(), [no_quote])
        self.assertEqual(result.tradable_state, TradableState.OPEN_NO_QUOTE.value)
        self.assertIsNone(result.buy_price)

    def test_edge_allowed_true_only_for_hrr(self):
        hrr = candidate("batter_hrr", threshold=0.5, probability_kind="calibrated_probability")
        hrr_market = market("batter_hrr", threshold=0.5)
        self.assertTrue(match_candidate(hrr, [hrr_market]).edge_allowed)
        hr = candidate("batter_home_runs", threshold=0.5, probability_kind="model_probability_unvalidated")
        hr_market = market("batter_home_runs", threshold=0.5)
        self.assertFalse(match_candidate(hr, [hr_market]).edge_allowed)

    def test_snapshot_counts_and_helpers(self):
        candidates = [candidate(threshold=5.5), candidate(threshold=7.5)]
        markets = [market(threshold=5.5), market(threshold=4.5), market(threshold=6.5)]
        snapshot = build_match_snapshot(
            candidates,
            {"fetch_ok": True, "slate_date": SLATE_DATE, "markets": markets},
            slate_date=SLATE_DATE,
        )
        self.assertTrue(snapshot["fetch_ok"])
        self.assertEqual(snapshot["counts"]["matched"], 1)
        self.assertEqual(snapshot["counts"]["not_listed"], 1)
        coverage = coverage_by_market(candidates, snapshot["matches"])
        self.assertEqual(coverage["pitcher_strikeouts"]["candidates"], 2)
        self.assertEqual(missing_exact_strikes(snapshot["matches"])[0]["available_strikes"], [4.5, 5.5, 6.5])

    def test_missing_or_stale_snapshot_writes_empty_nonfatal_shape(self):
        snapshot = build_match_snapshot(
            [candidate()],
            {"fetch_ok": True, "slate_date": "2026-08-30", "markets": [market()]},
            slate_date=SLATE_DATE,
        )
        self.assertFalse(snapshot["fetch_ok"])
        self.assertEqual(snapshot["counts"]["matched"], 0)
        self.assertEqual(snapshot["matches"], [])


if __name__ == "__main__":
    unittest.main()
