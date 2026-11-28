import copy
import json

import pytest

import build
import uuids
from test_opjson import CARDS, SETS

META = {"version": "1.2.3", "date": "2026-01-01"}
FORMATS = {"formats": [{"id": "standard", "windows": [{"from": "2022-12-02", "blocks": "all"}]}]}
DESIG = {"source": "https://example.com/blocks", "designations": []}
BANS = {"events": [{"effective": "2024-06-21", "status": "banned", "cards": ["OP01-120"]}]}
SEALED = {"OP01": {"products": [{"id": "op01-starter", "set": "OP01", "category": "starter_deck", "name": "Starter",
                                 "contentsStatus": "partial", "contents": {"cards": [{"printing": "OP01-120"}]},
                                 "sources": ["https://example.com/starter"]}]}}


def stamped():
    """SETS, CARDS and SEALED with their UUIDs, and the registry that gave them."""
    sets, cards, sealed, registry = copy.deepcopy(SETS), copy.deepcopy(CARDS), copy.deepcopy(SEALED), uuids.empty()
    uuids.assign(sets, cards, sealed, registry)
    return sets, cards, sealed, registry


def outputs(sets, cards, sealed, registry, bans=BANS):
    return build.outputs(sets, cards, sealed, FORMATS, DESIG, bans, META, registry)


def test_a_build_writes_all_six_files_with_one_meta(tmp_path):
    sets, cards, sealed, registry = stamped()
    build.write(outputs(sets, cards, sealed, registry), tmp_path)
    docs = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.iterdir()}
    assert sorted(docs) == ["AllCards.json", "AllPrintings.json", "AllProducts.json", "AllSets.json",
                            "AllUuids.json", "Legality.json"]
    assert all(d["meta"] == META for d in docs.values())
    assert set(docs["AllPrintings.json"]["data"]) == {"OP01-120", "OP01-120~tcg9"}
    assert docs["Legality.json"]["data"]["bans"] == BANS["events"]


def test_invalid_legality_data_stops_the_build_before_any_file_is_written(tmp_path):
    bans = {"events": [{"effective": "2024-06-21", "status": "banned", "cards": ["OP99-999"]}]}
    with pytest.raises(build.Invalid, match="OP99-999 is not a card"):
        build.write(outputs(*stamped(), bans=bans), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_invalid_cards_stop_the_build(tmp_path):
    sets, cards, sealed, registry = stamped()
    sets[0]["id"] = "OP02"
    with pytest.raises(build.Invalid, match="not in sets.json"):
        outputs(sets, cards, sealed, registry)


def test_a_printing_carries_its_card_uuid_and_oracle_id():
    sets, cards, sealed, registry = stamped()
    printing = outputs(sets, cards, sealed, registry)["AllPrintings.json"]["data"]["OP01-120~tcg9"]
    card = cards["OP01"]["cards"][0]
    assert printing["cardUuid"] == card["uuid"] and printing["oracleId"] == card["oracleId"]
    assert printing["uuid"] == card["printings"][1]["uuid"]


def test_a_product_card_item_carries_its_printing_uuid():
    sets, cards, sealed, registry = stamped()
    product = outputs(sets, cards, sealed, registry)["AllProducts.json"]["data"]["op01-starter"]
    assert product["contents"]["cards"] == [{"printing": "OP01-120",
                                             "printingUuid": cards["OP01"]["cards"][0]["printings"][0]["uuid"]}]
    assert sealed["OP01"]["products"][0]["contents"]["cards"] == [{"printing": "OP01-120"}]  # the input is untouched


def test_outputs_include_all_uuids_and_refuse_a_wrong_uuid():
    sets, cards, sealed, registry = stamped()
    assert outputs(sets, cards, sealed, registry)["AllUuids.json"]["data"] == registry
    cards["OP01"]["cards"][0]["uuid"] = cards["OP01"]["cards"][0]["printings"][0]["uuid"]
    with pytest.raises(build.Invalid, match="card OP01-120: uuid"):
        outputs(sets, cards, sealed, registry)
