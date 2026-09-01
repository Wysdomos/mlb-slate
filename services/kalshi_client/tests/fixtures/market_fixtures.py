"""Kalshi fixture payloads for no-network tests."""

EVENT = {
    "event_ticker": "KXMLBKS-26AUG312140PHIAZ",
    "title": "Philadelphia vs Arizona: Strikeouts",
    "sub_title": "PHI vs AZ (Aug 31)",
}

K_MARKET = {
    "event_ticker": "KXMLBKS-26AUG312140PHIAZ",
    "floor_strike": 5.5,
    "last_price_dollars": "0.8800",
    "no_ask_dollars": "0.2300",
    "rules_primary": "If Test Pitcher records 6+ strikeouts in the Philadelphia vs Arizona professional baseball game originally scheduled for Aug 31, 2026 at 9:40 PM EDT, then the market resolves to Yes.",
    "status": "active",
    "ticker": "KXMLBKS-26AUG312140PHIAZ-AZTPITCHER99-6",
    "title": "Test Pitcher: 6+ strikeouts?",
    "updated_time": "2026-08-31T20:00:00Z",
    "yes_ask_dollars": "0.7800",
    "yes_bid_dollars": "0.7700",
}

UNDER_MARKET = {
    "event_ticker": "KTEST-26AUG312140PHIAZ",
    "floor_strike": 5.5,
    "rules_primary": "If Test Pitcher records fewer than 5.5 strikeouts, then the market resolves to Yes.",
    "status": "active",
    "ticker": "KTEST-26AUG312140PHIAZ-AZTPITCHER99-U55",
    "title": "Test Pitcher under 5.5 strikeouts?",
    "updated_time": "2026-08-31T20:00:00Z",
    "yes_ask_dollars": "0.4200",
}

ORDERBOOK = {
    "orderbook_fp": {
        "no_dollars": [["0.1000", "10.00"], ["0.2200", "4.00"]],
        "yes_dollars": [["0.2000", "5.00"], ["0.7700", "2.00"]],
    }
}

EMPTY_NO_BOOK = {
    "orderbook_fp": {
        "no_dollars": [],
        "yes_dollars": [["0.7700", "2.00"]],
    }
}

LADDER_PAYLOAD = {
    "markets": [
        {**K_MARKET, "ticker": "KXMLBKS-26AUG312140PHIAZ-AZTPITCHER99-5", "title": "Test Pitcher: 5+ strikeouts?", "floor_strike": 4.5},
        {**K_MARKET, "ticker": "KXMLBKS-26AUG312140PHIAZ-AZTPITCHER99-6", "title": "Test Pitcher: 6+ strikeouts?", "floor_strike": 5.5},
        {**K_MARKET, "ticker": "KXMLBKS-26AUG312140PHIAZ-AZTPITCHER99-7", "title": "Test Pitcher: 7+ strikeouts?", "floor_strike": 6.5},
    ],
    "cursor": "",
}
