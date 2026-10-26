import copy
import dataclasses
import json
from pathlib import Path

import pytest

import bandai
import import_bandai_ja
import opjson

PAGE = (Path(__file__).parent / "fixtures" / "bandai_ja_op01.html").read_text(encoding="utf-8")


def test_series_codes_come_from_full_width_brackets():
    series = {s.series_id: s for s in bandai.parse_series(PAGE, "ja")}
    assert series["550117"].code == "OP-17"
    assert import_bandai_ja.set_code(series["550117"]) == "OP17"
    assert import_bandai_ja.set_code(series["550302"]) == "PRB02"
    assert import_bandai_ja.set_code(series["550901"]) == "P"
    assert import_bandai_ja.set_code(series["550801"]) == "OTHER"
    assert import_bandai_ja.set_code(series["550701"]) == "FAMILY"


def test_release_names_drop_the_product_line_and_the_code():
    series = {s.series_id: s for s in bandai.parse_series(PAGE, "ja")}
    assert import_bandai_ja.release_name(series["550117"]) == "世界最強の戦士"
    assert import_bandai_ja.release_name(series["550101"]) == "ROMANCE DAWN"
    assert import_bandai_ja.release_name(series["550030"]) == "ルフィ&エース"
    assert import_bandai_ja.release_name(series["550701"]) == "ファミリーデッキセット"
    assert import_bandai_ja.kind(series["550030"]) == "starter_deck"
    assert import_bandai_ja.kind(series["550013"]) == "ultra_deck"
    assert import_bandai_ja.kind(series["550302"]) == "premium_booster"


def test_japanese_values_are_read_into_the_english_vocabularies():
    cards = {p.printing_id: p for p in bandai.parse_cards(PAGE, "550101", "ja")}
    leader = cards["OP01-001"]
    assert (leader.name, leader.category, leader.rarity) == ("ロロノア・ゾロ", "Leader", "L")
    assert leader.facts["life"] == 5 and leader.facts["cost"] is None
    assert leader.facts["colors"] == ["Red"] and leader.facts["attributes"] == ["Slash"]
    assert leader.facts["types"] == ["超新星", "麦わらの一味"]
    assert leader.image == "https://www.onepiece-cardgame.com/images/cardlist/card/OP01-001.png"
    # The card set stops before its buttons; the product page is kept for the release date.
    assert leader.card_set == "ROMANCE DAWN【OP-01】"
    assert leader.product == "https://www.onepiece-cardgame.com/products/boosters/op01.php"
    event = cards["OP01-029"]
    assert event.category == "Event" and event.facts["attributes"] == [] and event.facts["power"] is None


def test_release_date_from_a_product_page():
    page = "<dl>\n  <dt>発売日</dt>\n  <dd>\n    <p>2025年7月26日(土)</p>\n  </dd>\n</dl>"
    assert bandai.parse_release_date(page) == "2025-07-26"
    assert bandai.parse_release_date('<h4 class="prodStatusTit">発売日</h4>\n<div class="prodStatusContents">'
                                     '2024.1.27(土)</div>') == "2024-01-27"
    assert bandai.parse_release_date("<dt>発売日</dt>\n<dd>2026年7月11(土)</dd>") == "2026-07-11"
    assert bandai.parse_release_date("<p>no date</p>") is None


def test_type_dictionary_reads_only_types_whose_pairings_agree():
    pairs = [(["麦わらの一味"], ["Straw Hat Crew"])] * 10 + [(["超新星", "麦わらの一味"], ["Supernovas", "Straw Hat Crew"])]
    pairs += [(["海軍"], ["Navy"])] * 5 + [(["海軍"], ["Marines"])] * 5
    pairs += [(["A", "B"], ["Only one"])]  # lists of different lengths pair nothing
    assert import_bandai_ja.type_dictionary(pairs) == {"麦わらの一味": "Straw Hat Crew", "超新星": "Supernovas"}


# A small dataset: OP01 in both languages, OP14-EB04 English-only, and a Japanese list with OP-01 and OP-14.
SERIES = [bandai.Series("550101", "ブースターパック ROMANCE DAWN【OP-01】", "OP-01", "ja"),
          bandai.Series("550114", "ブースターパック 蒼海の七傑【OP-14】", "OP-14", "ja")]
SETS = [{"id": "OP01", "type": "booster", "bandaiSeriesId": "569101", "block": "1",
         "releases": [{"language": "en", "name": "Romance Dawn", "source": "https://example.com/op01"}]},
        {"id": "OP14-EB04", "type": "booster", "bandaiSeriesId": "569114", "block": "4",
         "releases": [{"language": "en", "name": "The Azure Sea's Seven", "source": "https://example.com/op14"}]}]
FILES = {
    "OP01": {"cards": [{"number": "OP01-001", "name": "Roronoa Zoro", "category": "Leader", "power": 5000,
                        "life": 5, "attributes": ["Slash"], "colors": ["Red"], "types": ["Supernovas", "Straw Hat Crew"],
                        "printings": [
                            {"id": "OP01-001", "set": "OP01", "rarity": "L", "block": "1", "image": "https://e/1.png",
                             "source": "bandai", "finishes": ["foil"], "identifiers": {"tcgplayerProductIds": [1]}},
                            {"id": "OP01-001_p1", "set": "OP01", "rarity": "L", "block": "1", "image": "https://e/2.png",
                             "source": "bandai", "finishes": ["foil"], "identifiers": {"tcgplayerProductIds": [2]}}]}]},
    "OP14": {"cards": [{"number": "OP14-001", "name": "Trafalgar Law", "category": "Leader", "power": 5000, "life": 4,
                        "colors": ["Red"], "types": ["Supernovas"],
                        "printings": [{"id": "OP14-001", "set": "OP14-EB04", "rarity": "L", "block": "4",
                                       "image": "https://e/3.png", "source": "bandai",
                                       "identifiers": {"tcgplayerProductIds": [3]}}]}]},
}


def ja_printing(printing_id, series_id, name, **facts):
    number = printing_id.split("_")[0]
    kind = printing_id.split("_")[1][0] if "_" in printing_id else None
    base = {"cost": None, "power": 5000, "counter": None, "life": 5, "attributes": ["Slash"], "colors": ["Red"],
            "block": "1", "types": ["超新星", "麦わらの一味"]}
    return bandai.Printing(printing_id, number, kind, int(printing_id[-1]) if kind else None, "L", "Leader", name,
                           f"https://ja/{printing_id}.png", series_id, "ROMANCE DAWN【OP-01】", {**base, **facts})


PRINTINGS = [
    ja_printing("OP01-001", "550101", "ロロノア・ゾロ", block="2"),
    ja_printing("OP01-001_p1", "550101", "ロロノア・ゾロ"),
    ja_printing("OP14-001", "550114", "トラファルガー・ロー", life=4, block="4", types=["超新星"]),
    # A Japanese-only promo: types read through the cards both lists have; one type has no English yet.
    dataclasses.replace(ja_printing("P-200", "550101", "ナミ", life=None, cost=1, power=2000, types=["麦わらの一味", "新種"]),
                        category="Character", rarity="P"),
]


def merged(sets=SETS, files=FILES, printings=PRINTINGS, corrections=None):
    sets, files = copy.deepcopy(sets), copy.deepcopy(files)
    review = import_bandai_ja.merge(sets, files, SERIES, printings, {"550101": "2022-07-22"}, corrections or {})
    return sets, files, review


def test_merge_adds_ja_releases_printings_and_names():
    sets, files, review = merged()
    op01 = next(s for s in sets if s["id"] == "OP01")
    assert op01["releases"][1] == {"language": "ja", "name": "ROMANCE DAWN", "releaseDate": "2022-07-22",
                                   "source": "https://www.onepiece-cardgame.com/cardlist/?series=550101"}
    zoro = files["OP01"]["cards"][0]
    assert list(zoro)[:3] == ["number", "name", "names"]
    assert zoro["names"] == {"en": "Roronoa Zoro", "ja": "ロロノア・ゾロ"}
    base_ja = zoro["printings"][2]
    # Block and finishes come from the English printing with the same Bandai id, never a TCGplayer id.
    assert base_ja == {"id": "OP01-001~ja", "language": "ja", "set": "OP01", "rarity": "L", "block": "1",
                       "image": "https://ja/OP01-001.png", "cardSet": "ROMANCE DAWN【OP-01】", "source": "bandai",
                       "finishes": ["foil"]}
    assert opjson.validate(sets, files) == []


def test_a_set_only_japan_has_is_a_set_of_its_own_with_its_block():
    sets, files, _ = merged()
    op14 = next(s for s in sets if s["id"] == "OP14")
    assert op14 == {"id": "OP14", "type": "booster", "releases": [
        {"language": "ja", "name": "蒼海の七傑", "source": "https://www.onepiece-cardgame.com/cardlist/?series=550114"}],
        "block": "4"}
    law = files["OP14"]["cards"][0]["printings"]
    assert [(p["id"], p["set"]) for p in law] == [("OP14-001", "OP14-EB04"), ("OP14-001~ja", "OP14")]


def test_a_card_only_japan_has_takes_its_japanese_name_and_english_types():
    _, files, review = merged()
    nami = next(c for c in files["P"]["cards"] if c["number"] == "P-200")
    assert nami["name"] == "ナミ" and nami["names"] == {"ja": "ナミ"}
    assert nami["types"] == ["Straw Hat Crew", "新種"]
    assert review["untranslatedTypes"] == [{"type": "新種", "cards": 1}]


def test_the_same_id_in_another_set_is_another_printing():
    # Japan's OP01-001_p1 is a collection card filed under OTHER; English's is the OP-01 parallel.
    printings = [PRINTINGS[0], dataclasses.replace(PRINTINGS[1], series_id="550801", facts={**PRINTINGS[1].facts,
                                                                                            "block": "3"})]
    series = SERIES + [bandai.Series("550801", "限定商品収録カード", None, "ja")]
    sets = SETS + [{"id": "OTHER", "type": "box_set", "releases": [
        {"language": "en", "name": "Other Product Cards", "source": "https://example.com/other"}]}]
    files = copy.deepcopy(FILES)
    import_bandai_ja.merge(copy.deepcopy(sets), files, series, printings, {}, {})
    p1 = files["OP01"]["cards"][0]["printings"][3]
    assert p1["id"] == "OP01-001_p1~ja" and p1["set"] == "OTHER"
    assert p1["block"] == "3" and "finishes" not in p1
    # The combined English set counts for the Japanese booster.
    assert import_bandai_ja._twin({"set": "OP14-EB04", "rarity": "L"}, "OP14", "L")
    assert import_bandai_ja._twin({"set": "OP14-EB04", "rarity": "L"}, "EB04", "L")
    assert not import_bandai_ja._twin({"set": "OP14-EB04", "rarity": "L"}, "OP14", "SR")


def test_merge_is_idempotent():
    sets, files, _ = merged()
    again_sets, again_files, _ = merged(sets, files)
    assert json.dumps([again_sets, again_files], ensure_ascii=False) == json.dumps([sets, files], ensure_ascii=False)


def test_attributes_alone_go_to_review_and_other_facts_stop_the_import():
    printings = [dataclasses.replace(PRINTINGS[0], facts={**PRINTINGS[0].facts, "attributes": ["Ranged"]})]
    _, _, review = merged(printings=printings)
    assert [(r["number"], r["ja"], r["en"]) for r in review["attributeDisagreements"]] == [
        ("OP01-001", ["Ranged"], ["Slash"])]
    printings = [dataclasses.replace(PRINTINGS[0], category="キャラクタークター")]
    with pytest.raises(ValueError, match="OP01-001"):
        merged(printings=printings)
    merged(printings=printings, corrections={"OP01-001": {"facts": {"category": "Leader"}}})


def test_validate_checks_the_japanese_fields():
    sets, files, _ = merged()
    zoro = files["OP01"]["cards"][0]

    def broken(change):
        s, f = copy.deepcopy(sets), copy.deepcopy(files)
        change(s, f)
        return opjson.validate(s, f)

    assert any("has a ja printing (OP01-001~ja) but no ja name" in e
               for e in broken(lambda s, f: f["OP01"]["cards"][0]["names"].pop("ja")))
    assert any("a ~ja id must have language ja" in e
               for e in broken(lambda s, f: f["OP01"]["cards"][0]["printings"][2].pop("language")))
    assert any("set OP01 has no ja release" in e
               for e in broken(lambda s, f: s[0]["releases"].pop()))
    assert any("name must be its English name" in e
               for e in broken(lambda s, f: f["OP01"]["cards"][0].update(name="ロロノア・ゾロ")))
    assert any("a Japanese printing has no TCGplayer product" in e
               for e in broken(lambda s, f: f["OP01"]["cards"][0]["printings"][2].update(
                   identifiers={"tcgplayerProductIds": [99]})))
    assert zoro["printings"][2]["id"] == "OP01-001~ja"


def test_set_aside_and_restore_keep_japanese_data_out_of_english_rebuilds():
    _, files, _ = merged()
    before = json.dumps(files, ensure_ascii=False, sort_keys=True)
    aside = opjson.set_aside_japanese(files)
    assert all(opjson.language(p) == "en" for b in files.values() for c in b["cards"] for p in c["printings"])
    assert not any(c["number"] == "P-200" for b in files.values() for c in b["cards"])
    opjson.restore_japanese(files, aside)
    assert json.dumps(files, ensure_ascii=False, sort_keys=True) == before

    # A Japanese-only card that TCGplayer has since minted an English printing for joins that card.
    aside = opjson.set_aside_japanese(files)
    files.setdefault("P", {"cards": []})["cards"].append(
        {"number": "P-200", "name": "Nami", "names": {"en": "Nami"}, "category": "Character", "source": "tcgplayer",
         "printings": [{"id": "P-200~tcg5", "set": "P", "image": "https://t/5.jpg", "source": "tcgplayer"}]})
    opjson.restore_japanese(files, aside)
    nami = [c for c in files["P"]["cards"] if c["number"] == "P-200"]
    assert len(nami) == 1 and nami[0]["names"] == {"en": "Nami", "ja": "ナミ"}
    assert [p["id"] for p in nami[0]["printings"]] == ["P-200~tcg5", "P-200~ja"]
