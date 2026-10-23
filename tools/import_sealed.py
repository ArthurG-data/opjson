"""Write data/sealed/<set>.json from TCGplayer's sealed One Piece products (TCGCSV category 68).

    uv run python tools/import_sealed.py

A product's category comes from its name (ordered rules, first match wins, as pkmjson's CATEGORY_RULES).
Contents are written only where a source states them:
- a booster pack's `pool` is its set (the cards it can hold, with no odds);
- a deck lists the printings Bandai's card list files under the deck's series, without counts, because
  the card list gives no quantities;
- a display or case names the product it holds, without a count, because no source in reach gives one.
So `contentsStatus` is `partial` or `unknown`, never `complete`, until a contents source is added.
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
            published = (g.get("publishedOn") or "")[:10]
            if published:
                product["releaseDate"] = published
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


def _dedupe_ids(products: list[dict]) -> None:
    seen = collections.Counter()
    for p in products:
        seen[p["id"]] += 1
        if seen[p["id"]] > 1:
            p["id"] = f"{p['id']}-{p['identifiers']['tcgplayerProductIds'][0]}"


if __name__ == "__main__":
    main()
