"""Write dist/AllSets.json, AllCards.json, AllPrintings.json, AllProducts.json and Legality.json. Refuses to build invalid data.

    uv run python tools/build.py --version 0.1.0
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import opjson

DIST = opjson.ROOT / "dist"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="0.0.0-dev")
    args = ap.parse_args()
    sets, files, sealed = opjson.load_sets(), opjson.load_cards(), opjson.load_sealed()
    errors = opjson.validate(sets, files, sealed)
    if errors:
        sys.exit("refusing to build:\n" + "\n".join(errors))
    meta = {"version": args.version, "date": datetime.date.today().isoformat()}
    flat = opjson.flatten(sets, files, sealed)
    DIST.mkdir(exist_ok=True)
    for name, key in (("AllSets", "sets"), ("AllCards", "cards"), ("AllPrintings", "printings"),
                      ("AllProducts", "products")):
        (DIST / f"{name}.json").write_text(json.dumps({"meta": meta, "data": flat[key]}, ensure_ascii=False,
                                                      sort_keys=True), encoding="utf-8")
    import legality
    formats, designations, bans = legality.load()
    problems = legality.validate(formats, designations, bans, set(flat["cards"]))
    if problems:
        sys.exit("refusing to build:\n" + "\n".join(problems))
    (DIST / "Legality.json").write_text(json.dumps({"meta": meta, "data": {
        "formats": formats["formats"], "blockDesignations": designations["designations"], "bans": bans["events"]}},
        ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"dist/ written: {len(flat['sets'])} sets, {len(flat['cards'])} cards, {len(flat['printings'])} printings, "
          f"{len(flat['products'])} sealed products")


if __name__ == "__main__":
    main()
