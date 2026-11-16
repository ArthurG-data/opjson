import copy
import json

import bandai
import opjson
from test_opjson import CARDS, SETS


def _data():
    sets, cards = copy.deepcopy(SETS), copy.deepcopy(CARDS)
    sets[0]["releases"].append({"language": "ja", "name": "ROMANCE DAWN", "source": "https://example.com/ja"})
    return sets, cards


def _product(pid="op01-pack-ja", **extra):
    return {"id": pid, "set": "OP01", "language": "ja", "name": "ROMANCE DAWN", "category": "booster_pack",
            "contentsStatus": "partial", "contents": {"pool": [{"set": "OP01"}]},
            "sources": ["https://www.onepiece-cardgame.com/products/boosters/op01.php"], **extra}


def test_japanese_products_and_their_language_are_valid():
    sets, cards = _data()
    assert opjson.validate(sets, cards, {"OP01": {"products": [_product()]}}) == []


def test_a_japanese_product_requires_a_japanese_set_release():
    assert any("no ja release" in e for e in opjson.validate(SETS, CARDS, {"OP01": {"products": [_product()]}}))


def test_a_japanese_product_cannot_hold_english_cards_or_english_products():
    sets, cards = _data()
    pack = _product("english-pack", language="en")
    deck = _product(category="starter_deck", contents={"cards": [{"printing": "OP01-120"}],
                                                     "sealed": [{"product": "english-pack"}]})
    errors = opjson.validate(sets, cards, {"OP01": {"products": [pack, deck]}})
    assert any("printing OP01-120 has another language" in e for e in errors)
    assert any("product english-pack has another language" in e for e in errors)


def test_products_come_from_the_japanese_series_product_links_and_exact_japanese_cards():
    from import_sealed_ja import build_products

    sets = [{"id": "OP01", "type": "booster", "releases": [
        {"language": "ja", "name": "ROMANCE DAWN", "releaseDate": "2022-07-22"}]},
        {"id": "ST01", "type": "starter_deck", "releases": [{"language": "ja", "name": "麦わらの一味"}]}]
    series = [bandai.Series("550101", "ROMANCE DAWN【OP-01】", "OP-01", "ja"),
              bandai.Series("550001", "麦わらの一味【ST-01】", "ST-01", "ja")]

    def printing(pid, sid, label, product):
        return bandai.Printing(pid, pid, None, None, "C", "Character", "name", "", sid, label, product=product)

    pack_url = "https://www.onepiece-cardgame.com/products/boosters/op01.php"
    deck_url = "https://www.onepiece-cardgame.com/products/decks/st01-04.php"
    printings = [printing("OP01-120", "550101", "ROMANCE DAWN【OP-01】", pack_url),
                 printing("ST01-001", "550001", "麦わらの一味【ST-01】", deck_url),
                 printing("ST01-002", "550001", "麦わらの一味【ST-01】", deck_url),
                 printing("ST01-003_p1", "550001", "Other product", "https://www.onepiece-cardgame.com/products/other.php")]
    products = build_products(sets, series, printings, {"ST01-001~ja", "ST01-002~ja", "ST01-003_p1~ja"})
    assert [p["id"] for p in products] == ["op01-booster-pack-ja", "st01-starter-deck-ja"]
    pack, deck = products
    assert pack["language"] == deck["language"] == "ja"
    assert pack["releaseDate"] == "2022-07-22" and pack["contents"] == {"pool": [{"set": "OP01"}]}
    assert deck["contents"] == {"cards": [{"printing": "ST01-001~ja"}, {"printing": "ST01-002~ja"}]}
    assert pack_url in pack["sources"] and deck_url in deck["sources"]
    assert all(p["contentsStatus"] == "partial" and "identifiers" not in p for p in products)


def test_writing_japanese_products_preserves_english_and_is_idempotent(tmp_path):
    from import_sealed_ja import write_products

    english = _product("english", language="en")
    curated = tmp_path / "curated.json"
    curated.write_text(json.dumps({"products": [english], "contents": [{"product": "english"}]}))
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "OP01.json").write_text(json.dumps({"products": [english]}))
    write_products([_product()], curated, sealed)
    first = (curated.read_text(), (sealed / "OP01.json").read_text())
    write_products([_product()], curated, sealed)
    assert first == (curated.read_text(), (sealed / "OP01.json").read_text())
    assert json.loads(first[0])["contents"] == [{"product": "english"}]
    assert {p["id"] for p in json.loads(first[1])["products"]} == {"english", "op01-pack-ja"}


def test_deck_series_with_bonus_parallels_does_not_guarantee_every_candidate():
    from import_sealed_ja import build_products

    url = "https://www.onepiece-cardgame.com/products/decks/st21.php"
    sets = [{"id": "ST21", "type": "starter_deck", "releases": [{"language": "ja", "name": "EX GEAR5"}]}]
    series = [bandai.Series("550021", "EX GEAR5【ST-21】", "ST-21", "ja")]
    printings = [bandai.Printing(pid, "ST21-001", kind, n, "L", "Leader", "Luffy", "", "550021",
                                "EX GEAR5【ST-21】", product=url)
                 for pid, kind, n in [("ST21-001", None, None), ("ST21-001_p1", "p", 1)]]
    [deck] = build_products(sets, series, printings, {"ST21-001~ja", "ST21-001_p1~ja"})
    assert deck["contents"] == {}
    assert deck["contentsStatus"] == "unknown"
