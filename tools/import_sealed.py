"""Write data/sealed/<set>.json from TCGplayer's sealed One Piece products (TCGCSV category 68).

    uv run python tools/import_sealed.py

A product's category comes from its name (ordered rules, first match wins, as pkmjson's CATEGORY_RULES).
Contents are written only where a source states them:
- a booster pack's `pool` is its set (the cards it can hold, with no odds);
- a deck lists the printings Bandai's card list files under the deck's series, without counts, because
  the card list gives no quantities;
- a display or case names the product it holds, without a count, because no source in reach gives one.
So `contentsStatus` is `partial` or `unknown`, never `complete`, until a contents source is added.

Products TCGplayer does not sell (the Tournament Kits Bandai supplies to stores) come from
mappings/sealed_curated.json, each with the Bandai page that states it, and are added after TCGplayer's. The same
file gives contents to a TCGplayer product where a Bandai page states them (the FILM RED cards in TCGplayer's
"One Piece Film Red Uta Promo Pack").
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import opjson
import tcgcsv
from import_tcgplayer import group_roles

ROOT = Path(__file__).resolve().parents[1]
SEALED = ROOT / "data" / "sealed"
CACHE = ROOT / ".cache" / "tcgcsv"
CURATED = ROOT / "mappings" / "sealed_curated.json"

# (regex on the product name, category). First match wins, so containers come before what they contain.
CATEGORY_RULES = [
    (r"\b(box case|display case|booster case)\b|\bcase$", "case"),
    (r"\bdisplay$|\[set of \d+\]", "display"),
    (r"sleeved booster pack", "sleeved_booster_pack"),
    (r"booster box|premium booster.*box|^extra booster:.*\bbox$", "booster_box"),
    (r"double pack", "double_pack"),
    (r"ultra deck|ultimate deck", "ultra_deck"),
    (r"starter deck|deck set|demo deck|learn together", "starter_deck"),
    (r"premium card collection", "premium_card_collection"),
    (r"gift collection", "gift_collection"),
    (r"tin pack", "tin"),
    (r"illustration box", "illustration_box"),
    (r"anniversary set|sealed promotional bundle|special goods set|binder|playmat|devil fruits collection|"
     r"treasure booster set", "collection"),
    (r"pre-release pack|release event pack|tournament pack|winner pack|event pack|celebration pack|judge pack|"
     r"participation pack|welcome pack|promotion pack|dash pack|bonus pack|battle pack|top player|anniversary "
     r"tournament|don!! (card )?(pack|set)|campaign pack|promo pack|battle kit|^revision pack$", "promo_pack"),
    (r"booster pack|\bbooster$|^extra booster:.*\bpack$", "booster_pack"),
]
_SLUG = re.compile(r"[^a-z0-9]+")
# Catch-all groups: their publishedOn is when TCGplayer opened the group, years before most of what is in it.
UNDATED_GROUPS = {"OP-PR", "OP-CS"}


def release_date(group: dict, released_on: str | None) -> str | None:
    """TCGplayer's own date for the product, else its group's, except in a catch-all group, where a wrong date
    would be worse than none."""
    if released_on:
        return released_on
    if group.get("abbreviation") in UNDATED_GROUPS:
        return None
    return (group.get("publishedOn") or "")[:10] or None


def classify(name: str) -> str:
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, name, re.I):
            return category
    return "other"


def slug(name: str) -> str:
    return _SLUG.sub("-", name.lower().replace("!!", "")).strip("-")


def main() -> None:
    sets = opjson.load_sets()
    set_ids = {s["id"] for s in sets}
    flat = opjson.flatten(sets, opjson.load_cards())
    printings_in_set = collections.defaultdict(list)
    for pid, p in flat["printings"].items():
        if p["source"] == "bandai":
            printings_in_set[p["set"]].append(pid)
    groups = tcgcsv.groups(CACHE)
    roles = group_roles(groups, set_ids)
    by_set: dict[str, list[dict]] = collections.defaultdict(list)
    skipped = []
    for g in groups:
        role = roles[g["groupId"]]
        if role["role"] == "pending":
            skipped.append(g["abbreviation"])
            continue
        for p in tcgcsv.products(g["groupId"], CACHE):
            if p.is_single:
                continue
            category = classify(p.name)
            product = {"id": slug(p.name), "set": role["set"], "category": category, "name": p.name,
                       "identifiers": {"tcgplayerProductIds": [p.product_id]},
                       "contentsStatus": "unknown", "contents": {},
                       "sources": [f"https://www.tcgplayer.com/product/{p.product_id}"]}
            if released := release_date(g, p.released_on):
                product["releaseDate"] = released
            if category in ("booster_pack", "sleeved_booster_pack") and role["role"] == "set":
                product["contents"]["pool"] = [{"set": role["set"]}]
                product["contentsStatus"] = "partial"
            if category in ("starter_deck", "ultra_deck") and printings_in_set.get(role["set"]):
                product["contents"]["cards"] = [{"printing": pid} for pid in sorted(printings_in_set[role["set"]])]
                product["contentsStatus"] = "partial"
            by_set[role["set"]].append(product)
    for products in by_set.values():
        products.sort(key=lambda x: x["id"])
    # Ids are unique across every set, and settled before containers name the product they hold.
    _dedupe_ids([p for _, products in sorted(by_set.items()) for p in products])
    _link_containers(by_set)
    curated = json.loads(CURATED.read_text(encoding="utf-8"))
    _add_curated(by_set, curated["products"])
    _add_curated_contents(by_set, curated["contents"])
    SEALED.mkdir(parents=True, exist_ok=True)
    for old in SEALED.glob("*.json"):
        old.unlink()
    total = 0
    for set_id, products in sorted(by_set.items()):
        total += len(products)
        (SEALED / f"{set_id}.json").write_text(json.dumps({"products": products}, indent=2, ensure_ascii=False)
                                               + "\n", encoding="utf-8")
    counts = collections.Counter(p["category"] for ps in by_set.values() for p in ps)
    print(f"{total} sealed products in {len(by_set)} sets; skipped groups {skipped}; {dict(counts)}")


def _link_containers(by_set: dict[str, list[dict]]) -> None:
    """A display or case names the product it holds when exactly one product in its set has the same name
    without the container word. The count stays unstated (see the module docstring)."""
    for products in by_set.values():
        by_name = {p["name"].lower(): p for p in products}
        for p in products:
            if p["category"] not in ("display", "case"):
                continue
            inner = re.sub(r"\s*-?\s*(booster box case|box case|display case|display|case|booster case)$", "",
                           p["name"], flags=re.I).strip(" -")
            candidates = [inner, inner + " booster box", inner + " - booster box", inner + " display"]
            held = next((by_name[c.lower()] for c in candidates if c.lower() in by_name and by_name[c.lower()] is not p),
                        None)
            if held:
                p["contents"]["sealed"] = [{"product": held["id"]}]
                p["contentsStatus"] = "partial"


def _add_curated(by_set: dict[str, list[dict]], curated: list[dict]) -> None:
    """Add the curated products to their sets, keeping each set's products in id order. A curated id that is
    already taken is an error: renaming it would break the contents that name it."""
    taken = {p["id"] for products in by_set.values() for p in products}
    for product in curated:
        if product["id"] in taken:
            raise ValueError(f"curated sealed product {product['id']} collides with a TCGplayer product's id")
        taken.add(product["id"])
        by_set[product["set"]].append(product)
        by_set[product["set"]].sort(key=lambda x: x["id"])


def _add_curated_contents(by_set: dict[str, list[dict]], entries: list[dict]) -> None:
    """Give a product the contents a curated entry states, and cite the entry's sources. The product must exist and
    have no contents yet, so a curated entry never overwrites what a rule derived."""
    by_id = {p["id"]: p for products in by_set.values() for p in products}
    for entry in entries:
        product = by_id.get(entry["product"])
        if product is None:
            raise ValueError(f"curated contents name {entry['product']}, which is not a sealed product")
        if product["contents"]:
            raise ValueError(f"curated contents for {entry['product']} would replace contents it already has")
        product["contents"] = entry["contents"]
        product["contentsStatus"] = entry["contentsStatus"]
        product["sources"] = product["sources"] + entry["sources"]


def _dedupe_ids(products: list[dict]) -> None:
    seen = collections.Counter()
    for p in products:
        seen[p["id"]] += 1
        if seen[p["id"]] > 1:
            p["id"] = f"{p['id']}-{p['identifiers']['tcgplayerProductIds'][0]}"


if __name__ == "__main__":
    main()
