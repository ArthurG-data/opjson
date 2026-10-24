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
