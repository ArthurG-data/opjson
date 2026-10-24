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


def test_revision_pack_cards_are_reissues_of_their_own_sets_printings():
    # Starter Deck cards reissued with revised text: never on Bandai's list, so never a Bandai printing.
    roles = it.group_roles([{"groupId": 7, "abbreviation": "OP-RP", "name": "Revision Pack Cards"}], set())
    assert roles[7]["role"] == "reissue" and roles[7]["set"] == "OP-RP"
    assert it.copied_set(roles[7], "ST04-002") == "ST04"
    assert it.copied_set({"role": "stamp", "parent": "OP14-EB04"}, "OP14-001") == "OP14-EB04"


def test_only_card_numbers_reach_file_names():
    assert it.CARD_NUMBER.match("OP01-120") and it.CARD_NUMBER.match("P-001")
    for bad in ("../../etc-001", "OP01-120/x", "OP01-12", ""):
        assert not it.CARD_NUMBER.match(bad)


def test_assign_by_name_matches_only_where_the_name_leaves_no_choice():
    rules = json.loads((it.TAGS).read_text(encoding="utf-8"))["rules"]
    base, alt = product(1, "Jewelry Bonney", "EB05-001"), product(2, "Jewelry Bonney (Alternate Art)", "EB05-001")
    got = {m.product.product_id: (m.printing_id, m.evidence)
           for m in it.assign_by_name([base, alt], ["EB05-001", "EB05-001_p1"], "EB05-001", rules)}
    assert got == {1: ("EB05-001", "name"), 2: ("EB05-001_p1", "name")}
    # Two variant products and two variant printings: no guess.
    manga = product(3, "Shirahoshi (Manga)", "EB05-014")
    alt2 = product(4, "Shirahoshi (Alternate Art)", "EB05-014")
    got = it.assign_by_name([manga, alt2], ["EB05-014_p1", "EB05-014_p2"], "EB05-014", rules)
    assert got == []
    # A number in brackets only tells two cards apart; it is not a variant.
    robin = product(5, "Nico Robin (010)", "EB05-010")
    assert [m.printing_id for m in it.assign_by_name([robin], ["EB05-010"], "EB05-010", rules)] == ["EB05-010"]


def test_a_tag_breaks_an_image_tie_between_a_reprint_and_a_foil_pattern_copy():
    jrf, reprint = product(1, "Arlong (Jolly Roger Foil)", "OP06-023"), product(2, "Arlong (Reprint)", "OP06-023")
    dist = {(1, "OP06-023_p2"): 3, (1, "OP06-023_r1"): 8, (2, "OP06-023_p2"): 7, (2, "OP06-023_r1"): 4}
    kind = lambda p: it.product_kind(p, RULES)
    got = {m.product.product_id: (m.printing_id, m.evidence)
           for m in it.assign([jrf, reprint], ["OP06-023_p2", "OP06-023_r1"], dist, kind_of=kind)}
    assert got == {1: ("OP06-023_p2", "image+name"), 2: ("OP06-023_r1", "image+name")}
    # Without tags the tie stays unmatched.
    assert all(m.printing_id is None for m in it.assign([jrf, reprint], ["OP06-023_p2", "OP06-023_r1"], dist))


def test_a_tag_does_not_pick_between_two_printings_of_its_kind():
    drake = product(1, "X.Drake (Reprint)", "OP10-114")
    dist = {(1, "OP10-114_r1"): 5, (1, "OP10-114_r2"): 6}
    m, = it.assign([drake], ["OP10-114_r1", "OP10-114_r2"], dist, kind_of=lambda p: it.product_kind(p, RULES))
    assert m.printing_id is None


def test_a_tie_on_the_art_band_is_settled_on_the_whole_card():
    jack = product(1, "Jack (Premium Card Collection)", "ST04-008")
    dist = {(1, "ST04-008_p2"): 2, (1, "ST04-008_p1"): 20}
    whole = {"ST04-008_p2": 3, "ST04-008_p1": 34}
    m, = it.assign([jack], ["ST04-008_p1", "ST04-008_p2"], dist, whole_dist=lambda p, c: whole[c])
    assert (m.printing_id, m.evidence) == ("ST04-008_p2", "whole-card")
    same = {"ST04-008_p2": 8, "ST04-008_p1": 10}
    m, = it.assign([jack], ["ST04-008_p1", "ST04-008_p2"], dist, whole_dist=lambda p, c: same[c])
    assert m.printing_id is None


def test_a_tag_naming_one_bandai_card_set_settles_identical_art():
    chopper = product(1, "Tony Tony.Chopper (CS 25-26 Top Player Pack)", "OP07-066")
    sets = {"OP07-066_p1": "CS 25-26 Top Player Pack", "OP07-066_p2": "CS 25-26 Finalist Card Set 1"}
    assert it.card_set_pick(chopper, list(sets), sets.get) == "OP07-066_p1"
    plain = product(2, "Tony Tony.Chopper (Parallel)", "OP07-066")
    assert it.card_set_pick(plain, list(sets), sets.get) is None
