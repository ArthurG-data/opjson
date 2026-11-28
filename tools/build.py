"""Write dist/AllSets.json, AllCards.json, AllPrintings.json, AllProducts.json, AllUuids.json and Legality.json.
Refuses to build invalid data, or data whose UUIDs are not the ones data/uuids.json gives (run tools/uuids.py).

AllUuids.json is the UUID registry: a reader that stored an id opjson no longer uses (a printing Bandai listed after
TCGplayer sold it) finds the record's UUID in its bridges.

    uv run python tools/build.py --version 0.1.0
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import legality
import opjson
import uuids

DIST = opjson.ROOT / "dist"


class Invalid(Exception):
    pass


def outputs(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict], formats: dict, designations: dict,
            bans: dict, meta: dict, registry: dict) -> dict[str, dict]:
    """{file name: document} for every file of dist/. Raises Invalid, listing every problem, when the cards, their
    UUIDs or the legality data are invalid, so that a build writes all six files or none."""
    errors = opjson.validate(sets, files, sealed) or uuids.errors(sets, files, sealed, registry)
    flat = opjson.flatten(sets, files, sealed)
    if not errors:
        errors = legality.validate(formats, designations, bans, set(flat["cards"]))
    if errors:
        raise Invalid("\n".join(errors))
    docs = {f"{name}.json": {"meta": meta, "data": flat[key]}
            for name, key in (("AllSets", "sets"), ("AllCards", "cards"), ("AllPrintings", "printings"),
                              ("AllProducts", "products"))}
    docs["AllUuids.json"] = {"meta": meta, "data": registry}
    docs["Legality.json"] = {"meta": meta, "data": {
        "formats": formats["formats"],
        "blockDesignations": [{"source": designations["source"], **d} for d in designations["designations"]],
        "bans": bans["events"]}}
    return docs


def write(docs: dict[str, dict], dist: Path = DIST) -> None:
    dist.mkdir(exist_ok=True)
    for name, doc in docs.items():
        opjson.write_atomic(dist / name, json.dumps(doc, ensure_ascii=False, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="0.0.0-dev")
    args = ap.parse_args()
    meta = {"version": args.version, "date": datetime.date.today().isoformat()}
    try:
        docs = outputs(opjson.load_sets(), opjson.load_cards(), opjson.load_sealed(), *legality.load(), meta,
                       uuids.load())
    except Invalid as e:
        sys.exit(f"refusing to build:\n{e}")
    write(docs)
    data = {name: len(doc["data"]) for name, doc in docs.items()}
    print(f"dist/ written: {data['AllSets.json']} sets, {data['AllCards.json']} cards, "
          f"{data['AllPrintings.json']} printings, {data['AllProducts.json']} sealed products, and AllUuids.json")


if __name__ == "__main__":
    main()
