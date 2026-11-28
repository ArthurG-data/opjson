import copy

import link_twins
import opjson
import twins

ART_A = 0
ART_A_RESCAN = 0b111  # 3 bits from ART_A
ART_A_OTHER_SCAN = 0b11111  # 5 bits from ART_A
ART_B = (1 << 80) - 1  # 80 bits from ART_A


def ja(pid, rarity="R", set_="PRB01"):
    return {"id": pid, "set": set_, "rarity": rarity, "source": "bandai", "language": "ja"}


def en(pid, rarity="R", set_="PRB01"):
    return {"id": pid, "set": set_, "rarity": rarity, "source": "bandai"}


def run(ja_printings, en_printings, hashes, claimed=frozenset()):
    return link_twins.match(ja_printings, en_printings, set(claimed), lambda p: hashes[p["id"]])


def test_a_correction_wins_even_when_it_says_no_twin():
    assert twins.twin_of("OP01-001_p1~ja", "OP01-001_p1", {}, {"OP01-001_p1~ja": None}) is None
    assert twins.twin_of("OP01-001_p1~ja", None, {}, {"OP01-001_p1~ja": "OP01-001_p2"}) == "OP01-001_p2"


def test_the_rule_wins_over_an_image_match():
    settled = {"OP01-001~ja": {"en": "OP01-001_p1", "distance": 3}}
    assert twins.twin_of("OP01-001~ja", "OP01-001", settled, {}) == "OP01-001"


def test_an_image_match_applies_when_the_rule_finds_none():
    settled = {"OP01-001_p1~ja": {"en": "OP01-001_p2", "distance": 3}}
    assert twins.twin_of("OP01-001_p1~ja", None, settled, {}) == "OP01-001_p2"
    assert twins.twin_of("OP01-001_p3~ja", None, settled, {}) is None


def test_match_links_the_one_close_candidate():
    links, review = run([ja("X_p1~ja")], [en("X_p2"), en("X_p1")],
                        {"X_p1~ja": ART_A_RESCAN, "X_p2": ART_A, "X_p1": ART_B})
    assert links == {"X_p1~ja": {"en": "X_p2", "distance": 3}}
    assert review == []


def test_match_reviews_two_close_candidates():
    links, review = run([ja("X_p1~ja")], [en("X_p2"), en("X_p3")],
                        {"X_p1~ja": ART_A_RESCAN, "X_p2": ART_A, "X_p3": ART_A_OTHER_SCAN})
    assert links == {}
    assert review == [{"printing": "X_p1~ja", "reason": "ambiguous", "candidates": [
        {"printing": "X_p3", "distance": 2}, {"printing": "X_p2", "distance": 3}]}]


def test_match_skips_a_candidate_another_japanese_printing_claimed():
    links, review = run([ja("X_p1~ja")], [en("X_p2"), en("X_p3")],
                        {"X_p1~ja": ART_A_RESCAN, "X_p2": ART_A, "X_p3": ART_B}, claimed={"X_p2"})
    assert links == {} and review == []


def test_match_reviews_two_japanese_printings_that_pick_one_english():
    links, review = run([ja("X_p1~ja"), ja("X_p2~ja")], [en("X_p3")],
                        {"X_p1~ja": ART_A_RESCAN, "X_p2~ja": ART_A_OTHER_SCAN, "X_p3": ART_A})
    assert links == {}
    assert [r["printing"] for r in review] == ["X_p1~ja", "X_p2~ja"]
    assert {r["reason"] for r in review} == {"contested"}


def test_match_needs_the_same_rarity():
    links, _ = run([ja("X_p1~ja", rarity="SR")], [en("X_p2", rarity="R")], {"X_p1~ja": ART_A, "X_p2": ART_A})
    assert links == {}


def test_match_reports_a_printing_without_an_image():
    links, review = run([ja("X_p1~ja")], [en("X_p2")], {"X_p1~ja": None, "X_p2": ART_A})
    assert links == {}
    assert review == [{"printing": "X_p1~ja", "reason": "noImage"}]


SETS = [{"id": "OP01", "type": "booster", "releases": [
    {"language": "en", "name": "Romance Dawn", "source": "https://example.com/op01"},
    {"language": "ja", "name": "ROMANCE DAWN", "source": "https://example.com/ja/op01"}]}]


def _printing(pid, **extra):
    lang = {"language": "ja"} if pid.endswith("~ja") else {}
    return {"id": pid, **lang, "set": "OP01", "image": "https://example.com/x.png", "source": "bandai", **extra}


def _cards():
    return {"OP01": {"cards": [
        {"number": "OP01-001", "name": "Zoro", "names": {"en": "Zoro", "ja": "ゾロ"}, "category": "Leader",
         "printings": [_printing("OP01-001"), _printing("OP01-001_p1"),
                       _printing("OP01-001~ja", twinOf="OP01-001"),
                       _printing("OP01-001_p1~ja", twinOf="OP01-001_p1")]},
        {"number": "OP01-002", "name": "Law", "names": {"en": "Law", "ja": "ロー"}, "category": "Leader",
         "printings": [_printing("OP01-002"), _printing("OP01-002~ja")]}]}}


def _twin_errors(cards):
    return [e for e in opjson.validate(SETS, cards) if "twin" in e]


def test_validate_accepts_twins():
    assert opjson.validate(SETS, _cards()) == []


def test_validate_refuses_a_twin_claimed_twice_a_twin_in_japanese_and_a_twin_of_another_card():
    cards = _cards()
    cards["OP01"]["cards"][0]["printings"][3]["twinOf"] = "OP01-001"
    assert any("OP01-001 is the twin of OP01-001_p1~ja and OP01-001~ja" in e for e in _twin_errors(cards))
    cards = _cards()
    cards["OP01"]["cards"][0]["printings"][3]["twinOf"] = "OP01-001~ja"
    assert any("twinOf" in e and "'OP01-001~ja' does not match" in e for e in _twin_errors(cards))  # the schema
    cards = _cards()
    cards["OP01"]["cards"][1]["printings"][1]["twinOf"] = "OP01-001_p1"
    assert any("twinOf OP01-001_p1 is not an English printing of OP01-002" in e for e in _twin_errors(cards))


def test_validate_refuses_twin_of_on_an_english_printing():
    cards = copy.deepcopy(_cards())
    cards["OP01"]["cards"][0]["printings"][1]["twinOf"] = "OP01-001"
    assert any("OP01-001_p1: only a Japanese printing has a twinOf" in e for e in _twin_errors(cards))


ART_A_30 = (1 << 30) - 1  # 30 bits from ART_A: the same art scanned apart, or another printing of it


def test_match_reviews_a_link_when_another_candidate_is_within_review_below():
    links, review = run([ja("X_p1~ja")], [en("X_p2"), en("X_p3")],
                        {"X_p1~ja": ART_A, "X_p2": ART_A_RESCAN, "X_p3": ART_A_30})
    assert links == {}
    assert review[0]["printing"] == "X_p1~ja" and review[0]["reason"] == "close"


def test_match_links_at_twin_same_when_the_rest_are_far():
    near = (1 << link_twins.TWIN_SAME) - 1
    links, _ = run([ja("X_p1~ja")], [en("X_p2"), en("X_p3")], {"X_p1~ja": ART_A, "X_p2": near, "X_p3": ART_B})
    assert links == {"X_p1~ja": {"en": "X_p2", "distance": link_twins.TWIN_SAME}}


def test_a_rule_twin_whose_image_is_far_is_a_suspect():
    hashes = {"X_p2~ja": ART_A, "X_p2": ART_B, "X_p3": ART_A_RESCAN}
    entry = link_twins.suspect(ja("X_p2~ja"), "X_p2", [en("X_p2"), en("X_p3")], lambda p: hashes[p["id"]])
    assert entry == {"printing": "X_p2~ja", "reason": "suspect", "twinOf": "X_p2", "distance": 80,
                     "nearest": {"printing": "X_p3", "distance": 3}}
    hashes["X_p2"] = ART_A_30
    assert link_twins.suspect(ja("X_p2~ja"), "X_p2", [en("X_p2"), en("X_p3")], lambda p: hashes[p["id"]]) is None


def test_match_needs_the_same_set_and_counts_a_combined_english_set():
    links, _ = run([ja("X_p1~ja", set_="OP01")], [en("X_p2", set_="ST01")], {"X_p1~ja": ART_A, "X_p2": ART_A})
    assert links == {}
    links, _ = run([ja("X_p1~ja", set_="OP14")], [en("X_p2", set_="OP14-EB04")], {"X_p1~ja": ART_A, "X_p2": ART_A})
    assert links == {"X_p1~ja": {"en": "X_p2", "distance": 0}}


def test_match_never_links_in_a_catch_all_set_and_reviews_it():
    # P and OTHER hold unrelated promotions: one art on two events' prizes says nothing about the printing.
    for catch_all in ("P", "OTHER"):
        links, review = run([ja("X_p1~ja", set_=catch_all)], [en("X_p2", set_=catch_all)],
                            {"X_p1~ja": ART_A, "X_p2": ART_A})
        assert links == {}
        assert review == [{"printing": "X_p1~ja", "reason": "catchAll",
                           "candidates": [{"printing": "X_p2", "distance": 0}]}]


def test_an_image_match_whose_images_are_not_on_disk_is_kept():
    old = {"X_p1~ja": {"en": "X_p2", "distance": 3}, "X_p3~ja": {"en": "X_p4", "distance": 2}}
    on_disk = {"X_p1~ja": False, "X_p2": True, "X_p3~ja": True, "X_p4": True}
    kept = link_twins.keep_unseen(old, [ja("X_p1~ja"), ja("X_p3~ja")], [en("X_p2"), en("X_p4")],
                                  lambda p: on_disk[p["id"]])
    assert kept == {"X_p1~ja": {"en": "X_p2", "distance": 3}}


def test_check_losses_counts_twins():
    import check_losses
    files = _cards()
    assert check_losses.tally(SETS, files, {})["ja printings with twinOf"] == 2
