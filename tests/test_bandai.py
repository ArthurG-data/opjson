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


def test_malformed_printing_id_is_refused():
    page = PAGE.replace('id="OP01-001"', 'id="../OP01-001"', 1)
    try:
        bandai.parse_cards(page, "569101")
    except ValueError as e:
        assert "not a Bandai printing id" in str(e)
    else:
        raise AssertionError("a malformed id must be refused")


def test_image_cache_keys_cannot_leave_the_cache():
    import images
    for bad in ("../x", "a/b", ""):
        try:
            images.path_for("bandai", bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} was accepted")


def test_display_name_title_cases_bandai_capitals_and_keeps_stylised_names():
    assert import_bandai.display_name("ROMANCE DAWN") == "Romance Dawn"
    assert import_bandai.display_name("EMPERORS IN THE NEW WORLD") == "Emperors in the New World"
    assert import_bandai.display_name("A FIST OF DIVINE SPEED") == "A Fist of Divine Speed"
    assert import_bandai.display_name("THE WORLD’S STRONGEST WARRIORS") == "The World’s Strongest Warriors"
    assert import_bandai.display_name("500 YEARS IN THE FUTURE") == "500 Years in the Future"
    assert import_bandai.display_name("ONE PIECE CARD THE BEST") == "One Piece Card The Best"
    assert import_bandai.display_name("GEAR5") == "GEAR5"
    assert import_bandai.display_name("3D2Y") == "3D2Y"
    assert import_bandai.display_name("Straw Hat Crew") == "Straw Hat Crew"
    assert import_bandai.display_name("RED/BLACK Sabo") == "Red/Black Sabo"
    assert import_bandai.display_name("PURPLE/BLACK Monkey.D.Luffy") == "Purple/Black Monkey.D.Luffy"
    assert import_bandai.display_name("ONE PIECE HEROINES EDITION vol.2") == "One Piece Heroines Edition Vol.2"
