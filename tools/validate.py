"""Check sets/sets.json and data/cards against the schemas and each other. Exits 1 on any problem.

    uv run python tools/validate.py [--online]

--online also asks TCGCSV whether every TCGplayer product id still exists in category 68, and Bandai whether
every Bandai printing's image is still served.
"""
from __future__ import annotations

import argparse
import sys
import urllib.request

import opjson
import tcgcsv

USER_AGENT = "opjson/0.1 (+https://github.com/ArthurG-data/opjson)"


def online_errors(sets: list[dict], files: dict[str, dict]) -> list[str]:
    from pathlib import Path
    import tempfile

    errors = []
    cache = Path(tempfile.mkdtemp(prefix="opjson-online-"))
    live = {p.product_id for g in tcgcsv.groups(cache) for p in tcgcsv.products(g["groupId"], cache)}
    flat = opjson.flatten(sets, files)
    for pid, p in flat["printings"].items():
        for product_id in p.get("identifiers", {}).get("tcgplayerProductIds", []):
            if product_id not in live:
                errors.append(f"printing {pid}: TCGplayer product {product_id} is gone from category 68")
        if p["source"] == "bandai":
            req = urllib.request.Request(p["image"], method="HEAD", headers={"User-Agent": USER_AGENT})
            try:
                urllib.request.urlopen(req, timeout=30).close()
            except urllib.error.HTTPError as e:
                errors.append(f"printing {pid}: Bandai image answers {e.code}")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true")
    args = ap.parse_args()
    sets, files = opjson.load_sets(), opjson.load_cards()
    errors = opjson.validate(sets, files)
    if not errors and args.online:
        errors = online_errors(sets, files)
    for e in errors:
        print(e)
    flat = opjson.flatten(sets, files)
    print(f"{len(errors)} problems in {len(flat['sets'])} sets, {len(flat['cards'])} cards, "
          f"{len(flat['printings'])} printings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
