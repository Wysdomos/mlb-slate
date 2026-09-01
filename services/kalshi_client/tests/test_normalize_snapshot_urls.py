import unittest
import urllib.parse

from services.kalshi_client.client import KALSHI_BASE_URL, KalshiClient
from services.kalshi_client.models import TradableState
from services.kalshi_client.normalize import (
    canonical_player_name,
    canonical_team,
    parse_event_ticker,
    parse_threshold,
    side_mapping,
)
from services.kalshi_client.pricing import price_quote, tradable_state
from services.kalshi_client.snapshot import normalize_market
from services.kalshi_client.tests.fixtures.market_fixtures import EMPTY_NO_BOOK, EVENT, K_MARKET, LADDER_PAYLOAD, ORDERBOOK, UNDER_MARKET
from services.kalshi_client.urls import market_url


class FakeTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, url, headers, timeout):
        parsed = urllib.parse.urlparse(url)
        self.calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        if parsed.path.endswith("/markets"):
            return LADDER_PAYLOAD, {}
        return {"series": []}, {}


class NormalizeSnapshotUrlTests(unittest.TestCase):
    def test_client_sends_no_auth_headers(self):
        fake = FakeTransport()
        client = KalshiClient(transport=fake, min_gap=0)
        client.series(category="Sports", tags="Baseball")
        self.assertEqual(client.base_url, KALSHI_BASE_URL)
        self.assertNotIn("Authorization", fake.calls[0]["headers"])
        self.assertNotIn("X-API-Key", fake.calls[0]["headers"])

    def test_team_aliases_and_player_normalization(self):
        self.assertEqual(canonical_team("OAK"), "ATH")
        self.assertEqual(canonical_team("CWS"), "CHW")
        self.assertEqual(canonical_team("ARI"), "AZ")
        self.assertEqual(canonical_player_name("José Ramírez Jr."), "jose ramirez")

    def test_threshold_mapping(self):
        self.assertEqual(parse_threshold("1+ HR"), 0.5)
        self.assertEqual(parse_threshold("6+ strikeouts"), 5.5)
        self.assertEqual(parse_threshold("more than 8.5 runs"), 8.5)

    def test_event_team_order_is_away_then_home(self):
        parsed = parse_event_ticker("KXMLBHR-26AUG312140PHIAZ")
        self.assertEqual(parsed["slate_date"], "2026-08-31")
        self.assertEqual(parsed["away_team"], "PHI")
        self.assertEqual(parsed["home_team"], "AZ")

    def test_ladder_enumeration_keeps_one_record_per_strike(self):
        records = [normalize_market(market, event=EVENT, orderbook=ORDERBOOK).as_dict() for market in LADDER_PAYLOAD["markets"]]
        self.assertEqual(len(records), 3)
        self.assertEqual([record["threshold"] for record in records], [4.5, 5.5, 6.5])
        self.assertEqual({record["slate_market"] for record in records}, {"K"})
        self.assertEqual({record["team"] for record in records}, {"AZ"})

    def test_side_semantics_for_yes_over_and_yes_under(self):
        over = side_mapping(K_MARKET)
        under = side_mapping(UNDER_MARKET)
        self.assertEqual(over.yes_slate_side, "over")
        self.assertEqual(over.kalshi_side, "yes")
        self.assertEqual(under.yes_slate_side, "under")
        self.assertEqual(under.kalshi_side, "no")

    def test_tradable_state_fixtures(self):
        cases = [
            ("initialized", {}, 10, TradableState.LISTED_UNOPENED.value),
            ("tbd", {}, 10, TradableState.LISTED_TBD.value),
            ("closed", {}, 10, TradableState.CLOSED.value),
            ("active", {"result": "yes"}, 10, TradableState.SETTLED.value),
            ("active", {"yes_ask_dollars": "0.0000", "last_price_dollars": "0.9000", "_book": EMPTY_NO_BOOK}, 10, TradableState.OPEN_NO_QUOTE.value),
            ("active", {}, 300, TradableState.STALE.value),
            ("active", {}, 10, TradableState.OPEN_TRADABLE.value),
        ]
        for status, updates, age, expected in cases:
            with self.subTest(status=status, expected=expected):
                market = dict(K_MARKET)
                market["status"] = status
                market.update(updates)
                book = market.pop("_book", ORDERBOOK)
                quote = price_quote(market, book, intended_side="yes")
                self.assertEqual(tradable_state(market, quote, quote_age_seconds=age, quote_stale_seconds=180), expected)

    def test_match_ambiguous_state(self):
        quote = price_quote(K_MARKET, ORDERBOOK, intended_side="yes")
        self.assertEqual(
            tradable_state(K_MARKET, quote, quote_age_seconds=10, quote_stale_seconds=180, match_ambiguous=True),
            TradableState.MATCH_AMBIGUOUS.value,
        )

    def test_urls_exact_route_and_fallback(self):
        self.assertEqual(
            market_url("KXMLBHR", "KXMLBHR-26MAY121840COLPIT"),
            "https://kalshi.com/markets/kxmlbhr/pro-baseball-home-runs/KXMLBHR-26MAY121840COLPIT",
        )
        self.assertEqual(market_url("", "KXMLBHR-26MAY121840COLPIT"), "COPY TICKER")
        self.assertEqual(market_url("KXMLBHR", "bad/ticker"), "COPY TICKER")


if __name__ == "__main__":
    unittest.main()
