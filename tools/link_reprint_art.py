"""Point each Bandai printing that reuses an earlier printing's art at it, through `artOf`.

    uv run --group dev python tools/link_reprint_art.py

Bandai lists a reprint (OP01-120_r1) and some parallels as printings of their own, though many carry the art of
an earlier printing of the same card. Within each card, printings are taken in order (the base, then _pN, then
_rN). A printing whose image hash is at most SAME_ART bits from an earlier art owner gets `artOf` naming that
owner, and the two then share one illustration and one artist credit. Pairs that are close but above the
threshold go to review/reprint-art.json and are left unlinked. Run after images.py fetch; images not downloaded
yet are skipped and reported.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import images
import opjson

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "review" / "reprint-art.json"
# Two Bandai scans of the same art land a few bits apart; different art of one card lands 70+ apart.
SAME_ART = 12
REVIEW_BELOW = 40
_ORDER = re.compile(r"_(?P<kind>[pr])(?P<n>\d+)$")


def order_key(printing_id: str) -> tuple[int, int]:
    m = _ORDER.search(printing_id)
    if not m:
        return (0, 0)
    return (1 if m.group("kind") == "p" else 2, int(m.group("n")))


def link(printings: list[dict], hash_of) -> tuple[dict[str, str], list[dict], list[str]]:
    """({printing id: art owner id}, close pairs for review, ids with no hash) for one card's Bandai printings."""
    owners: list[tuple[str, int]] = []
    links, close, missing = {}, [], []
    for p in sorted(printings, key=lambda p: order_key(p["id"])):
        h = hash_of(p)
        if h is None:
            missing.append(p["id"])
            continue
        scored = sorted((images.distance(h, oh), oid) for oid, oh in owners)
        if scored and scored[0][0] <= SAME_ART:
            links[p["id"]] = scored[0][1]
            continue
        if scored and scored[0][0] < REVIEW_BELOW:
            close.append({"printing": p["id"], "nearest": scored[0][1], "distance": scored[0][0]})
        owners.append((p["id"], h))
    return links, close, missing


def main() -> None:
    files = opjson.load_cards()
    hashes = images.HashCache()

    def hash_of(p: dict) -> int | None:
        path = images.path_for("bandai", p["id"])
        if not path.exists():
            return None  # not downloaded yet; never fetch from here
        return hashes.get("bandai", p["id"], p["image"])

    linked, close, missing = 0, [], []
    for body in files.values():
        for card in body["cards"]:
            bandai = [p for p in card["printings"] if p["source"] == "bandai"]
            for p in bandai:
                p.pop("artOf", None)
            links, c, m = link(bandai, hash_of)
            for p in bandai:
                if p["id"] in links:
                    p["artOf"] = links[p["id"]]
            # A minted copy of a printing that now shares art follows it to the art owner: artOf never chains.
            for p in card["printings"]:
                if p["source"] != "bandai" and p.get("artOf") in links:
                    p["artOf"] = links[p["artOf"]]
            linked += len(links)
            close += c
            missing += m
    hashes.save()
    for stem, body in files.items():
        (opjson.CARDS / f"{stem}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                                                   encoding="utf-8")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps({"close": close, "noImage": missing}, indent=2) + "\n", encoding="utf-8")
    print(f"{linked} Bandai printings share an earlier printing's art; {len(close)} close pairs to review; "
          f"{len(missing)} printings without a downloaded image")


if __name__ == "__main__":
    main()
