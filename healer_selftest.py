"""
healer_selftest.py — TEMPORARY stress probe for the self-healing pipeline.

A small multi-function MLB slate stat builder with a non-obvious bug: the crash
surfaces a few call-frames deep, so a fix requires tracing the data flow rather
than patching the raising line in isolation. Safe to delete.
"""


def parse_lineup(raw_entries):
    """Each entry is 'Name:AVG:HR'. Returns a list of player dicts."""
    players = []
    for entry in raw_entries:
        name, avg, hr = entry.split(":")
        players.append({"name": name, "avg": float(avg), "hr": int(hr)})
    return players


def weighted_score(player, weights):
    # Rank value = batting average weighted + home-run power weighted.
    return player["avg"] * weights["avg"] + player["hr"] * weights["hr"]


def build_slate(raw_lineups, weights):
    slate = {}
    for team, raw_entries in raw_lineups.items():
        players = parse_lineup(raw_entries)
        slate[team] = sorted(
            players,
            key=lambda p: weighted_score(p, weights),
            reverse=True,
        )
    return slate


if __name__ == "__main__":
    lineups = {
        "NYY": ["Judge:0.310:52", "Soto:0.288:41"],
        "LAD": ["Betts:0.307:39", "Freeman:0.331:29"],
    }
    # The keys here must line up with what weighted_score() reads.
    weights = {"avg": 2.0, "hr": 0.5}
    slate = build_slate(lineups, weights)
    for team, players in slate.items():
        top = players[0]
        print(f"{team} top bat: {top['name']} (AVG {top['avg']}, {top['hr']} HR)")