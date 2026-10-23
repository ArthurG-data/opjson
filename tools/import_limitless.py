"""Credit each printing's illustrator from Limitless TCG, and check the TCGplayer matches against Limitless.

    uv run python tools/import_limitless.py

Run after import_tcgplayer.py. Two passes over Limitless's card search, both cached:
- every set: Limitless's TCGplayer product for each Bandai printing. Where Limitless and the image match
  disagree, both are written to review/limitless-crosscheck.json and nothing is changed.
- every artist (from /api/cards/artists): the printings they illustrated, written as `artist`. A printing
  only TCGplayer sells takes the artist of the printing named in its `artOf`.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import limitless
import opjson

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "limitless"
REVIEW = ROOT / "review" / "limitless-crosscheck.json"


def main() -> None:
    client = limitless.Client(CACHE)
    files = opjson.load_cards()
    printings = {p["id"]: p for body in files.values() for c in body["cards"] for p in c["printings"]}

    # Pass 1: TCGplayer ids per Bandai printing, from every Limitless set.
    lim_tcg: dict[str, set[int]] = collections.defaultdict(set)
    unknown_ids = set()
    for s in client.api("cards/sets?lang=en"):
        for row in client.search(f"!set:{s['code']}"):
            if row.language != "EN":
                continue
            if row.printing_id not in printings:
                unknown_ids.add(row.printing_id)
            if row.tcgplayer_product_id:
                lim_tcg[row.printing_id].add(row.tcgplayer_product_id)
    owner = {pid: p for p in printings.values() for pid in p.get("identifiers", {}).get("tcgplayerProductIds", [])}
    agree, disagree, ours_only, theirs_only = 0, [], 0, 0
    for printing_id, products in sorted(lim_tcg.items()):
        mine = set(printings.get(printing_id, {}).get("identifiers", {}).get("tcgplayerProductIds", []))
        for product_id in products:
            if product_id in mine:
                agree += 1
            elif product_id in owner:
                disagree.append({"product": product_id, "limitless": printing_id, "opjson": owner[product_id]["id"],
                                 "opjsonMatch": owner[product_id].get("tcgplayer")})
            else:
                theirs_only += 1
    for p in printings.values():
        if p["source"] == "bandai":
            ours_only += len(set(p.get("identifiers", {}).get("tcgplayerProductIds", [])) - lim_tcg.get(p["id"], set()))

    # Pass 2: illustrators.
    artist_of: dict[str, str] = {}
    clashes = []
    for name in client.api("cards/artists"):
        for row in client.search(f'!artist:"{name}"'):
            if row.language != "EN":
                continue
            if row.printing_id in artist_of and artist_of[row.printing_id] != name:
                clashes.append({"printing": row.printing_id, "artists": [artist_of[row.printing_id], name]})
            artist_of[row.printing_id] = name
    credited = 0
    for p in printings.values():
        p.pop("artist", None)
        name = artist_of.get(p["id"]) or artist_of.get(p.get("artOf", ""))
        if name:
            p["artist"] = name
            credited += 1
    for stem, body in files.items():
        (opjson.CARDS / f"{stem}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                                                   encoding="utf-8")

    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps({"tcgplayerDisagreements": disagree, "artistClashes": clashes,
                                  "limitlessIdsNotInOpjson": sorted(unknown_ids)}, indent=2, ensure_ascii=False)
                      + "\n", encoding="utf-8")
    print(f"TCGplayer ids: {agree} agree, {len(disagree)} disagree, {theirs_only} only on Limitless, "
          f"{ours_only} only in opjson; {len(unknown_ids)} Limitless ids not in opjson")
    print(f"artists: {credited} printings credited from {len(set(artist_of.values()))} artists; "
          f"{len(clashes)} printings credited to two artists")


if __name__ == "__main__":
    main()
