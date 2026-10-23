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
