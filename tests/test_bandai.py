from pathlib import Path

import bandai
import import_bandai

PAGE = (Path(__file__).parent / "fixtures" / "bandai_op01.html").read_text(encoding="utf-8")


def test_parse_series_reads_ids_titles_and_codes():
    series = {s.series_id: s for s in bandai.parse_series(PAGE)}
    assert series["569101"].code == "OP-01"
    assert "ROMANCE DAWN" in series["569101"].title
    assert series["569901"].code is None  # "Promotion card" has no bracketed code
    assert import_bandai.set_code(series["569101"]) == "OP01"
    assert import_bandai.set_code(series["569114"]) == "OP14-EB04"
    assert import_bandai.set_code(series["569901"]) == "P"


def test_parse_cards_reads_leader_life_not_cost():
    leader = next(p for p in bandai.parse_cards(PAGE, "569101") if p.printing_id == "OP01-001")
    assert leader.category == "Leader"
    assert leader.facts["life"] == 5
    assert leader.facts["cost"] is None
    assert leader.facts["power"] == 5000
    assert leader.facts["attributes"] == ["Slash"]
    assert leader.facts["types"] == ["Supernovas", "Straw Hat Crew"]


def test_parse_cards_reads_variant_suffix_and_dashes_as_none():
    shanks = next(p for p in bandai.parse_cards(PAGE, "569101") if p.printing_id == "OP01-120_p1")
    assert (shanks.number, shanks.variant_kind, shanks.variant_n) == ("OP01-120", "p", 1)
    assert shanks.facts["counter"] is None  # the page shows "-"
    assert shanks.image.endswith("/OP01-120_p1.png")
    event = next(p for p in bandai.parse_cards(PAGE, "569101") if p.printing_id == "OP01-026")
    assert event.category == "Event"
    assert event.facts["power"] is None and event.facts["attributes"] == []


def test_build_takes_facts_from_base_and_fails_on_unsettled_conflict():
    series = [s for s in bandai.parse_series(PAGE) if s.series_id == "569101"]
    base = next(p for p in bandai.parse_cards(PAGE, "569101") if p.printing_id == "OP01-120_p1")
    other = bandai.Printing(**{**base.__dict__, "printing_id": "OP01-120", "variant_kind": None, "variant_n": None,
                               "facts": {**base.facts, "power": 9000}})
    try:
        import_bandai.build(series, [base, other], {})
    except ValueError as e:
        assert "OP01-120: power differs" in str(e)
    else:
        raise AssertionError("an unsettled conflict must fail")
    _, files = import_bandai.build(series, [base, other], {"OP01-120": {"facts": {"power": 10000}}})
    card = files["OP01"]["cards"][0]
    assert card["power"] == 10000
    assert [p["id"] for p in card["printings"]] == ["OP01-120", "OP01-120_p1"]
