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


def test_a_bracketed_role_labels_a_printing_but_plays_no_part_in_matching():
    sanji = product(1, "Sanji (Online Regional 2024) [Participant]", "OP03-102")
    assert sanji.base_name_and_tags() == ("Sanji (Online Regional 2024) [Participant]", [])
    assert sanji.label_tags() == ["Online Regional 2024", "Participant"]
    assert product(2, "Shanks (Parallel) (Manga)").label_tags() == ["Parallel", "Manga"]
    assert product(3, "Shanks").label_tags() == []
    _, promos = it.classify_tags(sanji.label_tags(), RULES)
    assert promos == [("championship", "championship"), ("event_pack", "event")]
    zoro = product(4, "Roronoa Zoro (OP-06 Pre-Release Tournament) [Participant]", "P-045")
    _, promos = it.classify_tags(zoro.label_tags(), RULES)
    assert promos == [("event_pack", "event"), ("prerelease", "event")]
    winner = product(5, "Sanji (Offline Regional 2024) [Winner]", "OP03-102")
    _, promos = it.classify_tags(winner.label_tags(), RULES)
    assert promos == [("championship", "championship"), ("placement", "placement")]


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


def test_the_sole_plain_product_takes_the_base_printing_the_images_rejected():
    # Denjiro in OP01: TCGplayer's scan is cropped to the frame and Bandai's keeps its border, 89 bits apart.
    denjiro = product(1, "Denjiro", "OP01-046")
    dist = {(1, "OP01-046"): 89}
    m, = it.assign_by_name([denjiro], ["OP01-046"], "OP01-046", RULES, group=[denjiro], dist=dist)
    assert (m.printing_id, m.evidence, m.distance) == ("OP01-046", "name-sole-plain", 89)
    # A number in brackets only tells two cards apart, so "X.Drake (114)" is still plain.
    drake = product(2, "X.Drake (114)", "OP01-114")
    m, = it.assign_by_name([drake], ["OP01-114"], "OP01-114", RULES, group=[drake], dist={(2, "OP01-114"): 64})
    assert m.evidence == "name-sole-plain"
    # Without distances the product counts as imageless and the old rule applies.
    m, = it.assign_by_name([denjiro], ["OP01-046"], "OP01-046", RULES)
    assert (m.printing_id, m.evidence, m.distance) == ("OP01-046", "name", None)


def test_name_sole_plain_needs_every_condition():
    luffy = product(1, "Monkey.D.Luffy (109)", "OP07-109")
    parallel = product(2, "Monkey.D.Luffy (109) (Parallel)", "OP07-109")
    base, p1 = "OP07-109", "OP07-109_p1"
    far = {(1, base): 54, (1, p1): 125}

    def run(products, candidates, dist, group=None):
        return it.assign_by_name(products, candidates, base, RULES, group=group or products, dist=dist)

    assert [m.printing_id for m in run([luffy], [base], far)] == [base]
    # A tagged product beside it does not matter; a second plain product of the number does.
    assert [m.printing_id for m in run([luffy], [base], far, group=[luffy, parallel])] == [base]
    assert run([luffy], [base], far, group=[luffy, parallel, product(3, "Monkey.D.Luffy", base)]) == []
    # The base printing is already claimed.
    assert run([luffy], [p1], far) == []
    # Another printing of the number is as close, or closer.
    assert run([luffy], [base], {(1, base): 54, (1, p1): 54}) == []
    assert run([luffy], [base], {(1, base): 54, (1, p1): 40}) == []
    # Within ACCEPT the images did not reject it: that is a tie or a miss for assign, not for the name.
    assert run([luffy], [base], {(1, base): 20, (1, p1): 60}) == []
    # A tagged product is not the plain one.
    assert run([parallel], [base], {(2, base): 90}, group=[luffy, parallel]) == []


def test_two_products_the_images_barely_separate_pair_up_with_their_printings():
    # Shanks (SP) in OP13 (distances from the real images): Gold is 2 bits from _p5 and 15 from _p6, Silver 12 and 1.
    # One at a time each sees both printings within reach; together only one pairing is close.
    gold, silver = product(1, "Shanks - OP09-004 (SP) (Gold)", "OP09-004"), \
        product(2, "Shanks - OP09-004 (SP) (Silver)", "OP09-004")
    cands = ["OP09-004_p5", "OP09-004_p6"]
    dist = {(1, "OP09-004_p5"): 2, (1, "OP09-004_p6"): 15, (2, "OP09-004_p5"): 12, (2, "OP09-004_p6"): 1}
    got = {m.product.product_id: (m.printing_id, m.evidence)
           for m in it.assign([gold, silver], cands, dist, pairing=True)}
    assert got == {1: ("OP09-004_p5", "image+pairing"), 2: ("OP09-004_p6", "image+pairing")}
    assert all(m.printing_id is None for m in it.assign([gold, silver], cands, dist))
    assert it.assign([gold], cands, dist, pairing=True)[0].printing_id is None
    # Kyo in OP17: 1 and 11 bits each way, so the pairs total 2 against 22: exactly MARGIN is enough.
    kyo, pandaman = product(3, "Kyo", "OP17-045"), product(4, "Kyo (Pandaman Art)", "OP17-045")
    cands = ["OP17-045", "OP17-045_p1"]
    dist = {(3, "OP17-045"): 1, (3, "OP17-045_p1"): 11, (4, "OP17-045"): 11, (4, "OP17-045_p1"): 1}
    got = {m.product.product_id: m.printing_id for m in it.assign([kyo, pandaman], cands, dist, pairing=True)}
    assert got == {3: "OP17-045", 4: "OP17-045_p1"}


def test_pairing_needs_a_clear_margin_in_total_and_a_printing_for_every_product():
    # Zoro-Juurou: the best pairing totals 9 bits and the other 19, which is 10 short of MARGIN.
    event, finalist = product(1, "Zoro-Juurou (CS 25-26 Event Pack)", "OP05-067"), \
        product(2, "Zoro-Juurou (CS 25-26 Event Pack Finalist Ver.)", "OP05-067")
    cands = ["OP05-067_p5", "OP05-067_p6"]
    dist = {(1, "OP05-067_p5"): 5, (1, "OP05-067_p6"): 8, (2, "OP05-067_p5"): 11, (2, "OP05-067_p6"): 4}
    assert all(m.printing_id is None for m in it.assign([event, finalist], cands, dist, pairing=True))
    # Identical distances (Spandine's Regional products): nothing tells the pairings apart.
    same = {(1, "OP05-067_p5"): 1, (1, "OP05-067_p6"): 1, (2, "OP05-067_p5"): 1, (2, "OP05-067_p6"): 1}
    assert all(m.printing_id is None for m in it.assign([event, finalist], cands, same, pairing=True))
    # A pairing that leaves a product without a printing is not taken, whatever the totals.
    third = product(3, "Zoro-Juurou (CS 25-26 3rd Place)", "OP05-067")
    gold_silver = {(1, "OP05-067_p5"): 2, (1, "OP05-067_p6"): 15, (2, "OP05-067_p5"): 12, (2, "OP05-067_p6"): 1,
                   (3, "OP05-067_p5"): 90, (3, "OP05-067_p6"): 90}
    assert {m.product.product_id: m.printing_id
            for m in it.assign([event, finalist], cands, gold_silver, pairing=True)} == {
        1: "OP05-067_p5", 2: "OP05-067_p6"}
    assert all(m.printing_id is None for m in it.assign([event, finalist, third], cands, gold_silver, pairing=True))


def test_tied_products_are_settled_together_only_when_each_has_a_printing_in_reach():
    gold, silver = product(1, "Shanks (SP) (Gold)", "OP09-004"), product(2, "Shanks (SP) (Silver)", "OP09-004")
    cands = ["OP09-004_p5", "OP09-004_p6"]
    dist = {(1, "OP09-004_p5"): 2, (1, "OP09-004_p6"): 15, (2, "OP09-004_p5"): 12, (2, "OP09-004_p6"): 1}
    assert {pid: m.printing_id for pid, m in it.settle_tied([gold, silver], cands, dist).items()} == {
        1: "OP09-004_p5", 2: "OP09-004_p6"}
    # One product alone stays as it is, however clear the pairing would look.
    assert it.settle_tied([gold], cands, dist) == {}
    # Six Sanji products for one free printing: the images cannot say which of them it is.
    sanji = [product(10 + i, f"Sanji (Regional 2024) [{who}]", "OP03-102") for i, who in
             enumerate(["Participant", "Finalist", "Winner", "Participant", "Finalist", "Winner"])]
    assert it.settle_tied(sanji, ["OP03-102_p1"], {(p.product_id, "OP03-102_p1"): 4 for p in sanji}) == {}


def test_promos_tied_on_fewer_printings_than_there_are_products_become_printings_of_their_own():
    # Sanji in OP-PR: six Regional prizes, one Bandai printing left within reach (the other went to a card set).
    sanji = [product(10 + i, f"Sanji ({kind} Regional 2024) [{who}]", "OP03-102")
             for i, (kind, who) in enumerate([("Online", "Participant"), ("Online", "Finalist"), ("Online", "Winner"),
                                              ("Offline", "Participant"), ("Offline", "Finalist"),
                                              ("Offline", "Winner")])]
    dist = {(p.product_id, "OP03-102_p1"): 4 for p in sanji}
    assert it.mint_tied("promo", sanji, {}, dist) == [p.product_id for p in sanji]
    # Zoro's Pre-Release prize: both printings it was tied between went to other products.
    zoro = product(1, "Roronoa Zoro (OP-06 Pre-Release Tournament) [Participant]", "P-045")
    assert it.mint_tied("promo", [zoro], {}, {}) == [1]
    # A set's product is never minted this way, and a promo that settle_tied placed keeps its printing.
    assert it.mint_tied("set", sanji, {}, dist) == []
    placed = {10: it.Match(sanji[0], "OP03-102_p1", 4, "image+pairing")}
    assert it.mint_tied("promo", sanji, placed, dist) == [p.product_id for p in sanji[1:]]


def test_promos_that_pair_up_with_the_printings_in_reach_stay_in_review():
    # Spandine's five Regional 2025 products and five printings within 2 bits of all of them: as many printings as
    # products, so no product is without one, and the images do not say which is which.
    spandine = [product(20 + i, f"Spandine ({where} Regional {what} 2025 Vol.1)", "EB01-043")
                for i, (where, what) in enumerate([("Offline", "Finalist"), ("Online", "Champion"),
                                                   ("Online", "Participation"), ("Online", "Finalist"),
                                                   ("Offline", "Champion")])]
    printings = [f"EB01-043_p{n}" for n in range(2, 7)]
    dist = {(p.product_id, c): 1 for p in spandine for c in printings}
    assert not it.surplus(spandine, dist)
    assert it.mint_tied("promo", spandine, {}, dist) == []
    assert it.settle_tied(spandine, printings, dist) == {}


def test_a_promo_tag_marks_a_copy_from_elsewhere_but_a_foil_pattern_does_not():
    assert it.promo_copy(product(1, "Speed Jil (Dash Pack)", "OP03-006"), RULES)
    assert it.promo_copy(product(2, "Nami (CS26-27 Regionals Season 2 Top 64)", "OP15-108"), RULES)
    assert not it.promo_copy(product(3, "Two-Hundred Million Volts Amaru (Jolly Roger Foil)", "OP05-115"), RULES)
    assert not it.promo_copy(product(4, "Shanks (004) (Alternate Art)", "OP09-004"), RULES)
    assert not it.promo_copy(product(5, "Shanks (004)", "OP09-004"), RULES)


def test_a_tag_breaks_an_image_tie_between_a_reprint_and_a_foil_pattern_copy():
    jrf, reprint = product(1, "Arlong (Jolly Roger Foil)", "OP06-023"), product(2, "Arlong (Reprint)", "OP06-023")
    dist = {(1, "OP06-023_p2"): 3, (1, "OP06-023_r1"): 8, (2, "OP06-023_p2"): 7, (2, "OP06-023_r1"): 4}
    kind = lambda p: it.product_kind(p, RULES)
    got = {m.product.product_id: (m.printing_id, m.evidence)
           for m in it.assign([jrf, reprint], ["OP06-023_p2", "OP06-023_r1"], dist, kind_of=kind)}
    assert got == {1: ("OP06-023_p2", "image+name"), 2: ("OP06-023_r1", "image+name")}
    # Without tags the tie stays unmatched.
    assert all(m.printing_id is None for m in it.assign([jrf, reprint], ["OP06-023_p2", "OP06-023_r1"], dist))


def test_a_perfect_image_match_counts_in_a_tie():
    # Belo Betty in PRB-01: the Jolly Roger Foil is OP05-015_p3 at 0 bits, the plain reprint 3 bits off.
    jrf = product(1, "Belo Betty (Jolly Roger Foil)", "OP05-015")
    dist = {(1, "OP05-015_p3"): 0, (1, "OP05-015_p4"): 46, (1, "OP05-015_r1"): 3}
    m, = it.assign([jrf], sorted(c for _, c in dist), dist, kind_of=lambda p: it.product_kind(p, RULES))
    assert (m.printing_id, m.evidence) == ("OP05-015_p3", "image+name")


def test_tied_foil_patterns_take_bandais_order():
    # Gum-Gum Giant Gavel in PRB-01 (distances from the real images): one art on _p2, _p3 and _r1.
    jrf, tex = product(1, "Gum-Gum Giant Gavel (Jolly Roger Foil)", "OP03-055"), \
        product(2, "Gum-Gum Giant Gavel (Textured Foil)", "OP03-055")
    cands = ["OP03-055_p2", "OP03-055_p3", "OP03-055_r1"]
    dist = {(1, "OP03-055_p2"): 3, (1, "OP03-055_p3"): 16, (1, "OP03-055_r1"): 23,
            (2, "OP03-055_p2"): 15, (2, "OP03-055_p3"): 4, (2, "OP03-055_r1"): 23}
    pattern = lambda p: it.foil_pattern(p, RULES)
    got = {m.product.product_id: (m.printing_id, m.evidence)
           for m in it.assign([tex, jrf], cands, dist, kind_of=lambda p: it.product_kind(p, RULES), pattern_of=pattern)}
    assert got == {1: ("OP03-055_p2", "image+order"), 2: ("OP03-055_p3", "image+order")}
    # Without the order the tie stays unmatched.
    assert all(m.printing_id is None for m in it.assign([tex, jrf], cands, dist))


def test_a_foil_pattern_copy_takes_its_printing_though_the_other_copy_sits_far_from_it():
    # Amaru in PRB-01 (distances from the real images): the Textured Foil is 30 bits from the Jolly Roger Foil's
    # printing _p2, so no printing carries the art of both, and the plain reprint _r1 is 1 bit nearer the Jolly
    # Roger Foil than _p2 is.
    alt, jrf, tex = (product(1, "Two-Hundred Million Volts Amaru (Alternate Art)", "OP05-115"),
                     product(2, "Two-Hundred Million Volts Amaru (Jolly Roger Foil)", "OP05-115"),
                     product(3, "Two-Hundred Million Volts Amaru (Textured Foil)", "OP05-115"))
    cands = ["OP05-115_p2", "OP05-115_p3", "OP05-115_p4", "OP05-115_r1"]
    rows = {1: [115, 116, 3, 114], 2: [7, 30, 115, 6], 3: [30, 3, 114, 29]}
    dist = {(pid, c): rows[pid][i] for pid in rows for i, c in enumerate(cands)}
    pattern = lambda p: it.foil_pattern(p, RULES)
    kind = lambda p: it.product_kind(p, RULES)
    got = {m.product.product_id: (m.printing_id, m.evidence)
           for m in it.assign([alt, jrf, tex], cands, dist, kind_of=kind, pattern_of=pattern)}
    assert got == {1: ("OP05-115_p4", "image"), 2: ("OP05-115_p2", "image+order"), 3: ("OP05-115_p3", "image")}
    # A copy the images put beyond ACCEPT of every printing is not placed by the order.
    far = {**dist, (2, "OP05-115_p2"): 40, (2, "OP05-115_r1"): 45}
    assert {m.product.product_id: m.printing_id
            for m in it.assign([alt, jrf, tex], cands, far, kind_of=kind, pattern_of=pattern)}[2] is None


def test_the_order_places_nothing_it_cannot_count():
    pattern = lambda p: it.foil_pattern(p, RULES)
    jrf = product(1, "Hound Blaze (Jolly Roger Foil)", "OP05-057")
    # Two printings of the art for one pattern: which one is not settled.
    two = {(1, "OP05-057_p2"): 2, (1, "OP05-057_p3"): 14, (1, "OP05-057_r1"): 2}
    m, = it.assign([jrf], sorted(c for _, c in two), two, pattern_of=pattern)
    assert m.printing_id is None
    # A copy the images placed against the order voids it for the card.
    tex = product(2, "Hound Blaze (Textured Foil)", "OP05-057")
    swapped = {**two, (1, "OP05-057_p3"): 3, (2, "OP05-057_p2"): 1, (2, "OP05-057_p3"): 25, (2, "OP05-057_r1"): 70}
    got = {m.product.product_id: m.printing_id
           for m in it.assign([jrf, tex], ["OP05-057_p2", "OP05-057_p3"], swapped, pattern_of=pattern)}
    assert got == {1: None, 2: "OP05-057_p2"}


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


def test_a_full_art_tag_names_a_variant_printing():
    # Bartolomeo in PRB-01: the Full Art is P-029_p4 at 0 bits, the plain reprint 14 bits off.
    full = product(1, "Bartolomeo (P-029) (Full Art)", "P-029")
    m, = it.assign([full], ["P-029_p4", "P-029_r2"], {(1, "P-029_p4"): 0, (1, "P-029_r2"): 14},
                   kind_of=lambda p: it.product_kind(p, RULES))
    assert (m.printing_id, m.evidence) == ("P-029_p4", "image+name")


def test_a_tag_names_a_card_set_by_its_title():
    nami = product(1, "Nami - OP01-016 (Ultra Deck: The Three Captains)", "OP01-016")
    assert it.names_card_set(nami, "-The Three Captains-[ST-10]")
    judge = product(2, "Three Thousand Worlds (Judge Pack Vol. 2)", "OP03-057")
    assert not it.names_card_set(judge, "-ONE PIECE CARD THE BEST- [PRB-01]")
    assert not it.names_card_set(judge, None)


def test_a_tag_naming_one_bandai_card_set_settles_identical_art():
    chopper = product(1, "Tony Tony.Chopper (CS 25-26 Top Player Pack)", "OP07-066")
    sets = {"OP07-066_p1": "CS 25-26 Top Player Pack", "OP07-066_p2": "CS 25-26 Finalist Card Set 1"}
    assert it.card_set_pick(chopper, list(sets), sets.get) == "OP07-066_p1"
    plain = product(2, "Tony Tony.Chopper (Parallel)", "OP07-066")
    assert it.card_set_pick(plain, list(sets), sets.get) is None
