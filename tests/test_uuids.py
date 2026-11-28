import copy
import json
import uuid

import pytest

import opjson
import uuids


def bandai(pid, products=(), **extra):
    p = {"id": pid, "set": "OP01", "image": "https://example.com/x.png", "source": "bandai"}
    if pid.endswith("~ja"):
        p["language"] = "ja"
    if products:
        p["identifiers"] = {"tcgplayerProductIds": list(products)}
    return {**p, **extra}


def minted(pid, product):
    return {"id": pid, "set": "OP01-PRE", "image": "https://example.com/y.jpg", "source": "tcgplayer",
            "identifiers": {"tcgplayerProductIds": [product]}}


def card(number, *printings, name="Nami"):
    return {"number": number, "name": name, "names": {"en": name}, "category": "Character",
            "printings": list(printings)}


def cards(*cs):
    return {"OP01": {"cards": list(cs)}}


SETS = [{"id": "OP01", "type": "booster", "tcgplayerGroupIds": [3188], "bandaiSeriesId": "569101",
         "releases": [{"language": "en", "name": "Romance Dawn", "source": "https://example.com/op01"}]}]


def sealed(*products):
    return {"OP01": {"products": list(products)}}


def product(pid, *tcg):
    p = {"id": pid, "set": "OP01", "category": "booster_box", "name": pid, "contentsStatus": "unknown",
         "contents": {}, "sources": ["https://example.com"]}
    if tcg:
        p["identifiers"] = {"tcgplayerProductIds": list(tcg)}
    return p


def run(files, registry=None, sets=None, sealed_=None):
    registry = registry if registry is not None else uuids.empty()
    sets = copy.deepcopy(sets if sets is not None else SETS)
    sealed_ = sealed_ if sealed_ is not None else {}
    uuids.assign(sets, files, sealed_, registry)
    return sets, files, sealed_, registry


def printing_of(files, pid):
    return next(p for b in files.values() for c in b["cards"] for p in c["printings"] if p["id"] == pid)


def test_a_first_run_gives_uuid5_of_kind_and_id():
    _, files, _, _ = run(cards(card("OP01-001", bandai("OP01-001"))))
    c = files["OP01"]["cards"][0]
    assert c["printings"][0]["uuid"] == str(uuid.uuid5(opjson.NAMESPACE, "printings:OP01-001"))
    assert c["uuid"] == str(uuid.uuid5(opjson.NAMESPACE, "cards:OP01-001"))
    assert c["oracleId"] == str(uuid.uuid5(opjson.NAMESPACE, "oracles:number:OP01-001"))
    assert c["printings"][0]["versionId"] == str(uuid.uuid5(opjson.NAMESPACE, "versions:en:OP01-001"))
    assert list(c)[:3] == ["number", "uuid", "oracleId"]
    assert list(c["printings"][0])[:3] == ["id", "uuid", "versionId"]


def test_opjson_namespace_is_its_repository_url():
    assert opjson.NAMESPACE == uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/ArthurG-data/opjson")


def test_a_rebuild_from_an_empty_registry_gives_the_same_uuids():
    files = cards(card("OP01-001", bandai("OP01-001"), bandai("OP01-001~ja", twinOf="OP01-001")))
    _, first, _, _ = run(copy.deepcopy(files))
    _, again, _, _ = run(copy.deepcopy(files))
    assert first == again


def test_a_second_run_changes_nothing():
    files = cards(card("OP01-001", bandai("OP01-001", [1]), minted("OP01-001~tcg9", 9)))
    sets, files, sealed_, registry = run(files, sealed_=sealed(product("op01-box", 5)))
    before = json.dumps([sets, files, sealed_, registry], sort_keys=True)
    uuids.assign(sets, files, sealed_, registry)
    assert json.dumps([sets, files, sealed_, registry], sort_keys=True) == before


def test_minted_printing_listed_by_bandai_keeps_its_uuid():
    _, files, _, registry = run(cards(card("OP01-001", bandai("OP01-001", [1]), minted("OP01-001~tcg602789", 602789))))
    minted_uuid = printing_of(files, "OP01-001~tcg602789")["uuid"]
    _, files, _, _ = run(cards(card("OP01-001", bandai("OP01-001", [1]), bandai("OP01-001_p5", [602789]))), registry)
    assert printing_of(files, "OP01-001_p5")["uuid"] == minted_uuid


def test_products_swapped_between_live_printings_move_no_uuid():
    _, files, _, registry = run(cards(card("OP03-055", bandai("OP03-055_p2", [10]), bandai("OP03-055_p3", [11]))))
    p2, p3 = printing_of(files, "OP03-055_p2")["uuid"], printing_of(files, "OP03-055_p3")["uuid"]
    _, files, _, _ = run(cards(card("OP03-055", bandai("OP03-055_p2", [11]), bandai("OP03-055_p3", [10]))), registry)
    assert (printing_of(files, "OP03-055_p2")["uuid"], printing_of(files, "OP03-055_p3")["uuid"]) == (p2, p3)


def test_same_bandai_id_in_two_languages_is_two_printings():
    _, files, _, _ = run(cards(card("OP01-001", bandai("OP01-001_p1"), bandai("OP01-001_p1~ja"))))
    en, ja = printing_of(files, "OP01-001_p1"), printing_of(files, "OP01-001_p1~ja")
    assert en["uuid"] != ja["uuid"]
    assert en["versionId"] != ja["versionId"]


def test_twins_share_a_version_id():
    _, files, _, _ = run(cards(card("OP01-001", bandai("OP01-001_p1"), bandai("OP01-001_p2~ja", twinOf="OP01-001_p1"))))
    assert printing_of(files, "OP01-001_p1")["versionId"] == printing_of(files, "OP01-001_p2~ja")["versionId"]


def test_a_japanese_printing_that_finds_its_twin_joins_its_version():
    _, files, _, registry = run(cards(card("OP01-001", bandai("OP01-001_p1"), bandai("OP01-001_p2~ja"))))
    en1 = printing_of(files, "OP01-001_p1")["versionId"]
    _, files, _, _ = run(cards(card("OP01-001", bandai("OP01-001_p1"), bandai("OP01-001_p2~ja", twinOf="OP01-001_p1"))),
                         registry)
    assert printing_of(files, "OP01-001_p2~ja")["versionId"] == printing_of(files, "OP01-001_p1")["versionId"] == en1


def test_a_record_that_leaves_and_returns_gets_its_uuid_back():
    _, files, _, registry = run(cards(card("OP01-001", bandai("OP01-001"), bandai("OP01-001_r1"))))
    r1 = printing_of(files, "OP01-001_r1")["uuid"]
    run(cards(card("OP01-001", bandai("OP01-001"))), registry)
    _, files, _, _ = run(cards(card("OP01-001", bandai("OP01-001"), bandai("OP01-001_r1"))), registry)
    assert printing_of(files, "OP01-001_r1")["uuid"] == r1


def test_each_card_has_its_own_oracle_id():
    _, files, _, _ = run(cards(card("OP01-016", bandai("OP01-016")), card("OP01-017", bandai("OP01-017"))))
    a, b = files["OP01"]["cards"]
    assert a["oracleId"] != b["oracleId"]


def test_a_set_keeps_its_uuid_through_its_tcgplayer_group_when_renamed():
    sets, _, _, registry = run(cards(), sets=SETS)
    renamed = copy.deepcopy(SETS)
    renamed[0]["id"] = "OP-01"
    again, _, _, _ = run(cards(), registry, sets=renamed)
    assert again[0]["uuid"] == sets[0]["uuid"]
    assert list(again[0])[:2] == ["id", "uuid"]


def test_a_relisted_sealed_product_gets_its_old_uuid():
    _, _, s, registry = run(cards(), sealed_=sealed(product("op01-booster-box", 100)))
    old = s["OP01"]["products"][0]["uuid"]
    run(cards(), registry, sealed_=sealed())
    _, _, s, _ = run(cards(), registry, sealed_=sealed(product("op01-booster-box", 200)))
    assert s["OP01"]["products"][0]["uuid"] == old


def test_errors_reports_a_missing_or_wrong_uuid_and_a_shared_one():
    sets, files, sealed_, registry = run(cards(card("OP01-001", bandai("OP01-001"), bandai("OP01-001_p1"))))
    assert uuids.errors(sets, files, sealed_, registry) == []
    ps = files["OP01"]["cards"][0]["printings"]
    del ps[0]["uuid"]
    assert any("printing OP01-001 has no uuid" in e for e in uuids.errors(sets, files, sealed_, registry))
    ps[0]["uuid"] = ps[1]["uuid"]
    found = uuids.errors(sets, files, sealed_, registry)
    assert any("printing OP01-001: uuid" in e and "is not the one data/uuids.json gives" in e for e in found)
    assert any(f"uuid {ps[1]['uuid']} is on 2 records" in e for e in found)
    files["OP01"]["cards"][0]["oracleId"] = str(uuid.uuid4())
    assert any("card OP01-001: oracleId" in e for e in uuids.errors(sets, files, sealed_, registry))


def test_history_errors_reports_a_dropped_or_changed_key():
    *_, before = run(cards(card("OP01-001", bandai("OP01-001"))))
    after = copy.deepcopy(before)
    after["printings"]["keys"]["bandai:en:OP01-001"] = str(uuid.uuid4())
    del after["cards"]["keys"]["id:OP01-001"]
    found = uuids.history_errors(before, after)
    assert any("printing bandai:en:OP01-001: its uuid changed" in e for e in found)
    assert any("card id:OP01-001: its uuid" in e and "was dropped" in e for e in found)


def test_two_live_records_on_one_uuid_is_a_conflict():
    registry = uuids.empty()
    registry["printings"]["keys"] = {"bandai:en:OP01-001": "u1", "bandai:en:OP01-001_p1": "u1"}
    with pytest.raises(uuids.Conflict):
        run(cards(card("OP01-001", bandai("OP01-001"), bandai("OP01-001_p1"))), registry)


def test_save_and_load_round_trip(tmp_path):
    *_, registry = run(cards(card("OP01-001", bandai("OP01-001"))))
    path = tmp_path / "uuids.json"
    uuids.save(registry, path)
    assert uuids.load(path) == registry
    assert path.read_text(encoding="utf-8").endswith("}\n")
