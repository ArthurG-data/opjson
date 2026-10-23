"""Write dist/AllSets.json, dist/AllCards.json and dist/AllPrintings.json. Refuses to build invalid data.

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
    sets, files = opjson.load_sets(), opjson.load_cards()
    errors = opjson.validate(sets, files)
    if errors:
        sys.exit("refusing to build:\n" + "\n".join(errors))
    meta = {"version": args.version, "date": datetime.date.today().isoformat()}
    flat = opjson.flatten(sets, files)
    DIST.mkdir(exist_ok=True)
    for name, key in (("AllSets", "sets"), ("AllCards", "cards"), ("AllPrintings", "printings")):
        (DIST / f"{name}.json").write_text(json.dumps({"meta": meta, "data": flat[key]}, ensure_ascii=False,
                                                      sort_keys=True), encoding="utf-8")
    print(f"dist/ written: {len(flat['sets'])} sets, {len(flat['cards'])} cards, {len(flat['printings'])} printings")


if __name__ == "__main__":
    main()
