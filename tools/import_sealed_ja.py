"""Add Japanese packs and decks from Bandai's Japanese card list and its product links.

    uv run python tools/import_sealed_ja.py [--refresh]

Run after import_bandai_ja.py. Reuses the Japanese crawl cache. Product pages come from the
series' own printings, as in import_bandai_ja.product_pages; no English product is translated
or used for its identifiers. Deck cards must link to that same product page and already be
Japanese printings in the dataset. Counts are unknown, so coverage stays partial.

The generated products join mappings/sealed_curated.json, which import_sealed.py preserves,
and data/sealed. Existing English products and curated contents stay intact.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import bandai
import crawl_bandai
import import_bandai_ja
import opjson

CURATED = opjson.ROOT / "mappings" / "sealed_curated.json"
_CATEGORIES = {"booster": "booster_pack", "extra_booster": "booster_pack", "premium_booster": "booster_pack",
               "starter_deck": "starter_deck", "ultra_deck": "ultra_deck", "box_set": "starter_deck"}


def build_products(
    sets: list[dict], series: list[bandai.Series], printings: list[bandai.Printing], catalog_printings: set[str],
) -> list[dict]:
    """Verified Japanese products for the series whose own card list links one product page."""
    by_set = {s["id"]: s for s in sets}
    pages = import_bandai_ja.product_pages(series, printings)
    products = []
    for s in series:
        code = import_bandai_ja.set_code(s)
        have, url = by_set.get(code), pages.get(s.series_id)
        if have is None or url is None or have["type"] not in _CATEGORIES:
            continue
        release = next((r for r in have["releases"] if r["language"] == "ja"), None)
        if release is None:
            continue
        category = _CATEGORIES[have["type"]]
        product = {"id": f"{code.lower()}-{category.replace('_', '-')}-ja", "set": code,
                   "language": "ja", "category": category, "name": release["name"],
                   "contentsStatus": "partial", "contents": {},
                   "sources": [url, bandai.cardlist(s.series_id, "ja")]}
        if release.get("releaseDate"):
            product["releaseDate"] = release["releaseDate"]
        if category == "booster_pack":
            product["contents"] = {"pool": [{"set": code}]}
        else:
            own = [p for p in printings if p.series_id == s.series_id and p.product == url]
            variants = defaultdict(set)
            for p in own:
                variants[p.number].add(p.printing_id)
            # ST13/ST21 and similar series mix the fixed deck with random bonus parallels.
            # A shared product link alone cannot establish which printing is guaranteed.
            if any(len(ids) > 1 for ids in variants.values()):
                product["contentsStatus"] = "unknown"
                products.append(product)
                continue
            ids = sorted({p.printing_id + "~ja" for p in own if p.printing_id + "~ja" in catalog_printings})
            if not ids:
                continue
            product["contents"] = {"cards": [{"printing": pid} for pid in ids]}
        products.append(product)
    return sorted(products, key=lambda p: p["id"])


def write_products(products: list[dict], curated_path: Path = CURATED, sealed_dir: Path = opjson.SEALED) -> None:
    """Replace generated Japanese products, preserving English products and curated contents."""
    curated = json.loads(curated_path.read_text(encoding="utf-8"))
    english = [p for p in curated["products"] if opjson.language(p) != "ja"]
    curated["products"] = [*english, *sorted(products, key=lambda p: p["id"])]
    curated_path.write_text(json.dumps(curated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    by_set = {code: body for code, body in opjson.load_sealed(sealed_dir).items()}
    for body in by_set.values():
        body["products"] = [p for p in body["products"] if opjson.language(p) != "ja"]
    for product in products:
        by_set.setdefault(product["set"], {"products": []})["products"].append(product)
    sealed_dir.mkdir(parents=True, exist_ok=True)
    for code, body in sorted(by_set.items()):
        body["products"].sort(key=lambda p: p["id"])
        (sealed_dir / f"{code}.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    series, printings = crawl_bandai.crawl(args.refresh, "ja")
    sets, files = opjson.load_sets(), opjson.load_cards()
    products = build_products(sets, series, printings, set(opjson.flatten(sets, files)["printings"]))
    if not products:
        raise ValueError("Japanese crawl resolved no sealed products; existing products were preserved")
    write_products(products)
    print(f"{len(products)} Japanese sealed products")


if __name__ == "__main__":
    main()
