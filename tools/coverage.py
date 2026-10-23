"""Report how much of TCGplayer's One Piece catalogue the data accounts for, and how each product got there.

    uv run python tools/coverage.py [--strict]

Every TCGplayer product in category 68 must end up in exactly one place: on a Bandai printing (matched by
image), on a printing minted for it, on a sealed product, in review/tcgplayer-68.json, or in a set Bandai has
not published yet (pending). --strict exits 1 if any product is unaccounted for or still in review.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys

import opjson
import tcgcsv
from import_tcgplayer import CACHE, REVIEW


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    flat = opjson.flatten(opjson.load_sets(), opjson.load_cards(), opjson.load_sealed())
    review = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {"unmatched": [], "pending": []}

    where: dict[int, str] = {}
    for p in flat["printings"].values():
        for product_id in p.get("identifiers", {}).get("tcgplayerProductIds", []):
            where[product_id] = "printing:" + p.get("tcgplayer", {}).get("match", "?")
    for p in flat["products"].values():
        for product_id in p.get("identifiers", {}).get("tcgplayerProductIds", []):
            where[product_id] = "sealed"
    for r in review["unmatched"]:
        where.setdefault(r["productId"], "review")
    for r in review["pending"]:
        where.setdefault(r["productId"], "pending")

    tally = collections.Counter()
    missing = []
    for g in tcgcsv.groups(CACHE):
        for p in tcgcsv.products(g["groupId"], CACHE):
            kind = "single" if p.is_single else "sealed"
            place = where.get(p.product_id)
            if place is None:
                missing.append((p.product_id, p.name))
                place = "UNACCOUNTED"
            tally[(kind, place)] += 1
    for (kind, place), n in sorted(tally.items()):
        print(f"{kind:7} {place:32} {n:6}")

    bandai = [p for p in flat["printings"].values() if p["source"] == "bandai"]
    unsold = [p["id"] for p in bandai if not p.get("identifiers", {}).get("tcgplayerProductIds")]
    print(f"\nBandai printings: {len(bandai)}, without a TCGplayer product: {len(unsold)}")
    by_set = collections.Counter(flat["printings"][i]["set"] for i in unsold)
    print("  by set:", ", ".join(f"{s} {n}" for s, n in by_set.most_common()))
    for product_id, name in missing[:20]:
        print(f"UNACCOUNTED {product_id} {name}")
    if args.strict and (missing or review["unmatched"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
