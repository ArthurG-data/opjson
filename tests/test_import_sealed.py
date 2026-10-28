import pytest

import import_sealed


def product(set_id, name, product_id, category="booster_box"):
    return {"id": import_sealed.slug(name), "set": set_id, "category": category, "name": name,
            "identifiers": {"tcgplayerProductIds": [product_id]}, "contentsStatus": "unknown", "contents": {}}


def test_ids_are_unique_across_sets_and_containers_name_the_final_id():
    by_set = {"OP01": [product("OP01", "Box Promotion Pack", 1, "promo_pack")],
              "OP02": [product("OP02", "Box Promotion Pack", 2), product("OP02", "Box Promotion Pack Case", 3, "case")]}
    import_sealed._dedupe_ids([p for _, ps in sorted(by_set.items()) for p in ps])
    import_sealed._link_containers(by_set)
    assert [p["id"] for p in by_set["OP01"]] == ["box-promotion-pack"]
    assert by_set["OP02"][0]["id"] == "box-promotion-pack-2"
    assert by_set["OP02"][1]["contents"]["sealed"] == [{"product": "box-promotion-pack-2"}]


def test_a_products_own_release_date_beats_its_groups():
    group = {"abbreviation": "OP-PR", "publishedOn": "2022-09-30T00:00:00"}
    assert import_sealed.release_date(group, "2023-10-27") == "2023-10-27"


def test_a_set_group_dates_its_products_and_a_catch_all_group_does_not():
    # OP-PR's publishedOn is when TCGplayer opened the group, not when an Illustration Box came out.
    assert import_sealed.release_date({"abbreviation": "OP05", "publishedOn": "2023-12-08T00:00:00"}, None) == "2023-12-08"
    assert import_sealed.release_date({"abbreviation": "OP-PR", "publishedOn": "2022-09-30T00:00:00"}, None) is None
    assert import_sealed.release_date({"abbreviation": "OP-CS", "publishedOn": "2023-11-03T00:00:00"}, None) is None


def test_curated_products_join_their_set_in_id_order_and_never_take_a_used_id():
    by_set = {"P": [product("P", "Tournament Pack Vol. 7", 548440, "promo_pack")]}
    kit = {**product("P", "Tournament Kit Vol. 7", 0, "tournament_kit"), "identifiers": {},
           "contents": {"sealed": [{"product": "tournament-pack-vol-7"}]}}
    import_sealed._add_curated(by_set, [kit])
    assert [p["id"] for p in by_set["P"]] == ["tournament-kit-vol-7", "tournament-pack-vol-7"]
    with pytest.raises(ValueError, match="collides"):
        import_sealed._add_curated(by_set, [kit])


def test_curated_contents_fill_an_empty_product_and_never_replace_what_a_rule_derived():
    uta = {**product("P", "One Piece Film Red Uta Promo Pack", 488903, "promo_pack"), "sources": ["tcgplayer"]}
    by_set = {"P": [uta]}
    entry = {"product": "one-piece-film-red-uta-promo-pack", "contentsStatus": "partial",
             "contents": {"cards": [{"printing": "P-011"}]}, "sources": ["bandai"]}
    import_sealed._add_curated_contents(by_set, [entry])
    assert (uta["contents"], uta["contentsStatus"], uta["sources"]) == (
        {"cards": [{"printing": "P-011"}]}, "partial", ["tcgplayer", "bandai"])
    with pytest.raises(ValueError, match="would replace"):
        import_sealed._add_curated_contents(by_set, [entry])
    with pytest.raises(ValueError, match="not a sealed product"):
        import_sealed._add_curated_contents(by_set, [{**entry, "product": "no-such-product"}])


@pytest.mark.parametrize("set_id,abbreviation,name", [
    ("SD01", "SD01", "Set Sail Deck Set"),
    ("LT01", "LT-01", "Learn Together Deck Set"),
])
def test_import_dedicated_tcgplayer_deck_contents(tmp_path, monkeypatch, set_id, abbreviation, name):
    """The deck's own English printings survive without importing Japanese or unrelated cards."""
    import json

    source = "https://tcgcsv.com/tcgplayer/68/123/products"
    sets = [{"id": set_id, "type": "starter_deck", "source": "tcgplayer",
             "releases": [{"language": "en", "name": name, "source": source}]}]
    cards = {"ST01": {"cards": [{"number": "ST01-001", "printings": [
        {"id": "ST01-001~tcg1", "set": set_id, "source": "tcgplayer"},
        {"id": "ST01-001~ja", "set": set_id, "source": "bandai", "language": "ja"},
        {"id": "ST01-001", "set": "ST01", "source": "bandai"},
    ]}]}}
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "68_groups.json").write_text(json.dumps({"results": [
        {"groupId": 123, "abbreviation": abbreviation, "name": name}]}))
    (cache / "68_123_products.json").write_text(json.dumps({"results": [
        {"productId": 456, "groupId": 123, "name": name},
        {"productId": 457, "groupId": 123, "name": "Unrelated Demo Deck"},
    ]}))
    curated = tmp_path / "curated.json"
    curated.write_text('{"products": [], "contents": []}')
    monkeypatch.setattr(import_sealed, "CACHE", cache)
    monkeypatch.setattr(import_sealed, "SEALED", tmp_path / "sealed")
    monkeypatch.setattr(import_sealed, "CURATED", curated)
    monkeypatch.setattr(import_sealed.opjson, "load_sets", lambda: sets)
    monkeypatch.setattr(import_sealed.opjson, "load_cards", lambda: cards)

    import_sealed.main()
    products = json.loads((tmp_path / "sealed" / f"{set_id}.json").read_text())["products"]
    deck, unrelated = sorted(products, key=lambda p: p["identifiers"]["tcgplayerProductIds"])
    assert deck["contents"] == {"cards": [{"printing": "ST01-001~tcg1"}]}
    assert deck["contentsStatus"] == "partial"
    assert source in deck["sources"]
    assert unrelated["contents"] == {}

    # A collection group is not a dedicated deck, even if its release name matches.
    sets[0]["type"] = "box_set"
    import_sealed.main()
    products = json.loads((tmp_path / "sealed" / f"{set_id}.json").read_text())["products"]
    assert all(p["contents"] == {} for p in products)


@pytest.mark.parametrize("box_name,pack_name", [
    ("Pillars of Strength - Booster Box", "Pillars of Strength - Booster Pack"),
    ("Extra Booster: Anime 25th Collection Box", "Extra Booster: Anime 25th Collection Pack"),
])
def test_booster_box_names_its_matching_unsleeved_pack_without_counts(box_name, pack_name):
    box = product("OP03", box_name, 1)
    pack = product("OP03", pack_name, 2, "booster_pack")
    import_sealed._link_containers({"OP03": [box, pack]})
    assert box["contents"] == {"sealed": [{"product": pack["id"]}]}
    assert box["contentsStatus"] == "partial"


@pytest.mark.parametrize("pack_names,category", [
    (["Pillars of Strength - Booster Pack", "Pillars of Strength - Booster Pack"], "booster_pack"),
    (["Pillars of Strength - Booster Pack"], "sleeved_booster_pack"),
    (["Other Set - Booster Pack"], "booster_pack"),
    (["Pillars of Strength - Booster Pack (Special Edition)"], "booster_pack"),
])
def test_booster_box_does_not_choose_ambiguous_or_wrong_pack(pack_names, category):
    box = product("OP03", "Pillars of Strength - Booster Box", 1)
    packs = [product("OP03", name, i, category) for i, name in enumerate(pack_names, 2)]
    import_sealed._link_containers({"OP03": [box, *packs]})
    assert box["contents"] == {}
    assert box["contentsStatus"] == "unknown"


def test_booster_box_does_not_link_same_name_from_another_set():
    box = product("OP03", "Pillars of Strength - Booster Box", 1)
    pack = product("OP04", "Pillars of Strength - Booster Pack", 2, "booster_pack")
    import_sealed._link_containers({"OP03": [box], "OP04": [pack]})
    assert box["contents"] == {}
