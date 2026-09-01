import unittest

from services.kalshi_client.models import AskSource, TradableState
from services.kalshi_client.pricing import ask_from_orderbook, price_quote, tradable_state
from services.kalshi_client.tests.fixtures.market_fixtures import EMPTY_NO_BOOK, K_MARKET, ORDERBOOK


class PricingTests(unittest.TestCase):
    def test_yes_ask_derives_from_best_no_bid(self):
        self.assertEqual(ask_from_orderbook(ORDERBOOK, "yes"), 0.78)

    def test_no_ask_derives_from_best_yes_bid(self):
        self.assertEqual(ask_from_orderbook(ORDERBOOK, "no"), 0.23)

    def test_agree_source_when_reported_and_derived_match(self):
        quote = price_quote(K_MARKET, ORDERBOOK, intended_side="yes")
        self.assertEqual(quote.ask_source, AskSource.AGREE.value)
        self.assertEqual(quote.intended_side_price, 0.78)
        self.assertEqual(quote.fee_band, "extreme")

    def test_disagreement_over_one_cent_is_stale(self):
        market = dict(K_MARKET)
        market["yes_ask_dollars"] = "0.7500"
        quote = price_quote(market, ORDERBOOK, intended_side="yes")
        self.assertEqual(quote.ask_source, AskSource.DISAGREE.value)
        self.assertEqual(
            tradable_state(market, quote, quote_age_seconds=10, quote_stale_seconds=180),
            TradableState.STALE.value,
        )

    def test_empty_no_book_is_open_no_quote_for_yes(self):
        market = dict(K_MARKET)
        market["yes_ask_dollars"] = "0.0000"
        quote = price_quote(market, EMPTY_NO_BOOK, intended_side="yes")
        self.assertIsNone(quote.intended_side_price)
        self.assertEqual(
            tradable_state(market, quote, quote_age_seconds=10, quote_stale_seconds=180),
            TradableState.OPEN_NO_QUOTE.value,
        )

    def test_last_price_never_substitutes_for_ask(self):
        market = dict(K_MARKET)
        market["yes_ask_dollars"] = "0.0000"
        market["last_price_dollars"] = "0.8800"
        quote = price_quote(market, {}, intended_side="yes")
        self.assertIsNone(quote.intended_side_price)


if __name__ == "__main__":
    unittest.main()
