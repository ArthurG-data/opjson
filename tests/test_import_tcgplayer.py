import json

import import_tcgplayer as it
import tcgcsv

RULES = json.loads(it.TAGS.read_text(encoding="utf-8"))["rules"]


def product(pid, name, number="OP01-120"):
    return tcgcsv.Product(pid, 1, name, name, "", "", {"Number": number, "Rarity": "SEC"})


def test_tags_split_from_the_name_end():
    assert product(1, "Shanks (Parallel) (Manga) (Alternate Art)").base_name_and_tags() == (
        "Shanks", ["Parallel", "Manga", "Alternate Art"])
    assert product(2, "DON!! Card // One Piece Film RED Promo").base_name_and_tags()[1] == []


def test_classify_tags_maps_treatments_and_reuses_mtg_promo_names():
    treatments, promos = it.classify_tags(["Parallel", "Manga", "Alternate Art"], RULES)
    assert treatments == ["alternate_art", "manga", "parallel"] and promos == []
    _, promos = it.classify_tags(["CS 2023 Event Pack Finalist Ver."], RULES)
    assert ("event_pack", "event") in promos and ("placement", "placement") in promos
    _, promos = it.classify_tags(["Judge Pack Vol. 2"], RULES)
    assert promos == [("judgegift", "program")]
    _, promos = it.classify_tags(["Textured Foil"], RULES)
    assert promos == [("textured", "foil-pattern")]
    assert it.classify_tags(["Daz.Bonez", "004"], RULES) == ([], [])  # disambiguators label nothing


def test_assign_follows_images_not_name_order():
    # OP09-004: Bandai's _p1 is TCGplayer's (Alternate Art), _p2 its (Manga); distances from the real images.
    prods = [product(596924, "Shanks (004)"), product(596925, "Shanks (004) (Manga)"),
             product(596926, "Shanks (004) (Alternate Art)"), product(596927, "Shanks (004) (Wanted Poster)")]
    cands = ["OP09-004", "OP09-004_p1", "OP09-004_p2", "OP09-004_p3"]
    rows = {"OP09-004": [5, 130, 117, 134], "OP09-004_p1": [120, 137, 8, 123],
            "OP09-004_p2": [126, 3, 134, 123], "OP09-004_p3": [134, 125, 118, 5]}
    dist = {(p.product_id, c): rows[c][i] for c in cands for i, p in enumerate(prods)}
    got = {m.product.product_id: m.printing_id for m in it.assign(prods, cands, dist)}
    assert got == {596924: "OP09-004", 596925: "OP09-004_p2", 596926: "OP09-004_p1", 596927: "OP09-004_p3"}


def test_assign_refuses_a_close_call_and_a_far_match():
    prods = [product(1, "Radical Beam!! (Jolly Roger Foil)"), product(2, "Radical Beam!! (Textured Foil)")]
    cands = ["OP01-029_p2", "OP01-029_p3"]
    tie = {(1, "OP01-029_p2"): 6, (1, "OP01-029_p3"): 9, (2, "OP01-029_p2"): 7, (2, "OP01-029_p3"): 8}
    assert all(m.printing_id is None for m in it.assign(prods, cands, tie))
    far = {(1, "OP01-029_p2"): 90, (1, "OP01-029_p3"): 130, (2, "OP01-029_p2"): 120, (2, "OP01-029_p3"): 95}
    assert all(m.printing_id is None and "bits away" in m.evidence for m in it.assign(prods, cands, far))


def test_assign_reports_missing_images_and_extra_products():
    prods = [product(1, "A"), product(2, "A (Parallel)")]
    out = it.assign(prods, ["OP01-001"], {(1, "OP01-001"): 4, (2, "OP01-001"): None})
    assert [m.printing_id for m in out] == ["OP01-001", None]
    assert out[1].evidence == "more products than Bandai printings"


def test_group_roles():
    groups = [{"groupId": 1, "abbreviation": "OP01", "name": "Romance Dawn"},
              {"groupId": 2, "abbreviation": "OP02 PRE", "name": "Paramount War Pre-Release Cards"},
              {"groupId": 3, "abbreviation": "OP14 RE", "name": "x"},
              {"groupId": 4, "abbreviation": "OP-PR", "name": "Promos"},
              {"groupId": 5, "abbreviation": "OP18", "name": "Not on Bandai yet"},
              {"groupId": 6, "abbreviation": "ST-01", "name": "Starter"}]
    roles = it.group_roles(groups, {"OP01", "OP02", "OP14-EB04", "P", "ST01"})
    assert roles[1] == {"role": "set", "set": "OP01"}
    assert roles[2]["role"] == "stamp" and roles[2]["parent"] == "OP02" and roles[2]["set"] == "OP02-PRE"
    assert roles[2]["promo"] == "prerelease"
    assert roles[3]["parent"] == "OP14-EB04"
    assert roles[4] == {"role": "promo", "set": "P"}
    assert roles[5]["role"] == "pending"
    assert roles[6] == {"role": "set", "set": "ST01"}


def test_only_card_numbers_reach_file_names():
    assert it.CARD_NUMBER.match("OP01-120") and it.CARD_NUMBER.match("P-001")
    for bad in ("../../etc-001", "OP01-120/x", "OP01-12", ""):
        assert not it.CARD_NUMBER.match(bad)
