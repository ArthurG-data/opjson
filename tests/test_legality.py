import legality

FORMATS = {"formats": [{"id": "standard", "windows": [
    {"from": "2022-12-02", "to": "2026-03-31", "blocks": "all"},
    {"from": "2026-04-01", "to": "2027-03-31", "minBlock": 2, "maxBlock": 5}]}]}
STD = FORMATS["formats"][0]
DESIG = {"designations": [
    {"kind": "always", "from": "2026-04-01", "cards": ["OP01-120"]},
    {"kind": "block", "block": "4", "from": "2026-04-01", "to": "2029-03-31", "cards": ["OP01-039"]},
    {"kind": "reprinted", "from": "2026-04-01", "cards": ["OP01-016"]}]}
BANS = {"events": [
    {"effective": "2024-06-21", "status": "banned", "cards": ["OP05-041"]},
    {"effective": "2025-08-30", "status": "legal", "cards": ["OP05-041"]},
    {"effective": "2025-08-30", "status": "banned", "pairs": [["OP11-040", "OP11-067"]]}]}


def legal(number, block, as_of, card_blocks=None, bans=BANS):
    state = legality.ban_state(bans, as_of)
    return legality.printing_legality({"card": number, "block": block}, card_blocks or [block], DESIG, STD, state,
                                      as_of)


def test_ban_replay_bans_then_unbans():
    assert legal("OP05-041", "2", "2025-01-01") == "banned"
    assert legal("OP05-041", "2", "2025-09-01") == "legal"
    assert legality.ban_state(BANS, "2025-09-01").pairs == {frozenset(("OP11-040", "OP11-067"))}


def test_block_window_after_rotation():
    assert legal("OP02-001", "1", "2026-03-31") == "legal"  # before the block system everything is allowed
    assert legal("OP02-001", "1", "2026-04-01") == "not_legal"
    assert legal("OP05-001", "2", "2026-04-01") == "legal"
    assert legal("OP02-001", "X", "2026-04-01") == "legal"


def test_designations_override_the_printed_block():
    assert legal("OP01-120", "1", "2026-04-01") == "legal"          # super parallel rare number
    assert legal("OP01-039", "1", "2026-04-01") == "legal"          # treated as block 4
    assert legal("OP01-016", "1", "2026-04-01", ["1", "3"]) == "legal"  # reprinted with a newer block
    assert legal("OP01-016", "1", "2026-04-01", ["1"]) == "not_legal"


def test_bandai_page_parser_reads_lists_and_pairs():
    page = ("Cards with Active Restrictions <h3>Banned Cards</h3><ul><li><a href='?freewords=OP06-047'>x</a></li>"
            "</ul><h3>Restricted Cards</h3><p>none</p><h3>Banned Pair Cards</h3>"
            "<ul><li><a href='?freewords=OP11-040'></a></li><li><a href='?freewords=OP11-067'></a></li></ul>"
            "<ul><li><a href='?freewords=OP11-040'></a></li><li><a href='?freewords=OP08-069'></a></li></ul>"
            "Banned/Restricted Cards effective from April 1, 2026")
    page = page.replace("'", '"')
    state = legality.bandai_current(page)
    assert state.status == {"OP06-047": "banned"}
    assert state.pairs == {frozenset(("OP11-040", "OP11-067")), frozenset(("OP11-040", "OP08-069"))}


def test_validate_flags_unknown_cards_and_overlapping_windows():
    bad = {"formats": [{"id": "s", "windows": [{"from": "2026-01-01", "to": "2026-12-31", "blocks": "all"},
                                               {"from": "2026-06-01", "blocks": "all"}]}]}
    errors = legality.validate(bad, DESIG, BANS, {"OP01-120", "OP01-039", "OP01-016", "OP05-041", "OP11-040"})
    assert any("overlap" in e for e in errors)
    assert any("OP11-067 is not a card" in e for e in errors)
