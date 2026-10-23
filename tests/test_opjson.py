import copy

import opjson

SETS = [{"id": "OP01", "type": "booster", "releases": [{"language": "en", "name": "Romance Dawn",
                                                        "source": "https://example.com/op01"}]},
        {"id": "OP01-PRE", "type": "promo", "parent": "OP01", "source": "tcgplayer",
         "releases": [{"language": "en", "name": "Pre-Release", "source": "https://example.com/pre"}]}]
CARDS = {"OP01": {"cards": [{"number": "OP01-120", "name": "Shanks", "category": "Character", "printings": [
    {"id": "OP01-120", "set": "OP01", "image": "https://example.com/a.png", "source": "bandai",
     "identifiers": {"tcgplayerProductIds": [454664]}},
    {"id": "OP01-120~tcg9", "set": "OP01-PRE", "image": "https://example.com/b.jpg", "source": "tcgplayer",
     "artOf": "OP01-120", "identifiers": {"tcgplayerProductIds": [9]}}]}]}}


def errors(sets=SETS, cards=CARDS):
    return opjson.validate(sets, cards)


def test_valid_data_has_no_errors():
    assert errors() == []


def test_a_product_on_two_printings_is_an_error():
    cards = copy.deepcopy(CARDS)
    cards["OP01"]["cards"][0]["printings"][1]["identifiers"]["tcgplayerProductIds"] = [454664]
    assert any("454664 is on OP01-120 and OP01-120~tcg9" in e for e in errors(cards=cards))


def test_parent_must_exist_and_not_loop():
    sets = copy.deepcopy(SETS)
    sets[0]["parent"] = "OP01-PRE"
    assert any("its own ancestor" in e for e in errors(sets=sets))
    sets = copy.deepcopy(SETS)
    sets[1]["parent"] = "NOPE"
    assert any("not a set" in e for e in errors(sets=sets))


def test_minted_ids_need_tcgplayer_source_and_artof_a_bandai_printing():
    cards = copy.deepcopy(CARDS)
    cards["OP01"]["cards"][0]["printings"][1]["source"] = "bandai"
    assert any("minted id" in e for e in errors(cards=cards))
    cards = copy.deepcopy(CARDS)
    cards["OP01"]["cards"][0]["printings"][1]["artOf"] = "OP01-120~tcg9"
    assert any("artOf must name a Bandai printing" in e for e in errors(cards=cards))


def test_card_must_live_in_its_prefix_file_and_unknown_set_is_an_error():
    cards = {"ST01": copy.deepcopy(CARDS["OP01"])}
    assert any("belongs in cards/OP01.json" in e for e in errors(cards=cards))
    cards = copy.deepcopy(CARDS)
    cards["OP01"]["cards"][0]["printings"][0]["set"] = "OP99"
    assert any("set OP99 is not in sets.json" in e for e in errors(cards=cards))


def test_schema_rejects_unknown_fields():
    cards = copy.deepcopy(CARDS)
    cards["OP01"]["cards"][0]["printings"][0]["colour"] = "Red"
    assert errors(cards=cards)
