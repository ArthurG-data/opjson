import json

import pytest

import build
from test_opjson import CARDS, SETS

META = {"version": "1.2.3", "date": "2026-01-01"}
FORMATS = {"formats": [{"id": "standard", "windows": [{"from": "2022-12-02", "blocks": "all"}]}]}
DESIG = {"source": "https://example.com/blocks", "designations": []}
BANS = {"events": [{"effective": "2024-06-21", "status": "banned", "cards": ["OP01-120"]}]}


def test_a_build_writes_all_five_files_with_one_meta(tmp_path):
    build.write(build.outputs(SETS, CARDS, {}, FORMATS, DESIG, BANS, META), tmp_path)
    docs = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.iterdir()}
    assert sorted(docs) == ["AllCards.json", "AllPrintings.json", "AllProducts.json", "AllSets.json",
                            "Legality.json"]
    assert all(d["meta"] == META for d in docs.values())
    assert set(docs["AllPrintings.json"]["data"]) == {"OP01-120", "OP01-120~tcg9"}
    assert docs["Legality.json"]["data"]["bans"] == BANS["events"]


def test_invalid_legality_data_stops_the_build_before_any_file_is_written(tmp_path):
    bans = {"events": [{"effective": "2024-06-21", "status": "banned", "cards": ["OP99-999"]}]}
    with pytest.raises(build.Invalid, match="OP99-999 is not a card"):
        build.write(build.outputs(SETS, CARDS, {}, FORMATS, DESIG, bans, META), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_invalid_cards_stop_the_build(tmp_path):
    sets = [dict(SETS[0], id="OP02")] + SETS[1:]
    with pytest.raises(build.Invalid, match="not in sets.json"):
        build.outputs(sets, CARDS, {}, FORMATS, DESIG, BANS, META)
