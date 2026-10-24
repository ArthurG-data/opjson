"""Check sets/sets.json and data/cards against the schemas and each other. Exits 1 on any problem.

    uv run python tools/validate.py [--online [--images]]

--online also asks TCGCSV whether every TCGplayer product id still exists in category 68. --images also asks
Bandai whether every Bandai printing's image is still served: about 5,000 requests, so CI runs it only for a
release tag. They go IMAGE_WORKERS at a time, and a 5xx or a dropped connection is retried before it counts.
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import opjson
import tcgcsv

USER_AGENT = "opjson/0.1 (+https://github.com/ArthurG-data/opjson)"
IMAGE_WORKERS = 6
IMAGE_TRIES = 3


def online_errors(sets: list[dict], files: dict[str, dict], images: bool = False) -> list[str]:
    from pathlib import Path
    import tempfile

    errors = []
    cache = Path(tempfile.mkdtemp(prefix="opjson-online-"))
    live = {p.product_id for g in tcgcsv.groups(cache) for p in tcgcsv.products(g["groupId"], cache)}
    printings = opjson.flatten(sets, files)["printings"]
    for pid, p in printings.items():
        for product_id in p.get("identifiers", {}).get("tcgplayerProductIds", []):
            if product_id not in live:
                errors.append(f"printing {pid}: TCGplayer product {product_id} is gone from category 68")
    if images:
        errors += image_errors(printings)
    return errors


def head_status(url: str, tries: int = IMAGE_TRIES) -> int | None:
    """None when the URL answers, else the last status (0 when no answer came). A 4xx is final; a 5xx, a timeout
    or a dropped connection is tried again after a pause that doubles each time."""
    status = 0
    for attempt in range(tries):
        if attempt:
            time.sleep(2 ** attempt)
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        try:
            urllib.request.urlopen(req, timeout=30).close()
            return None
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return e.code
            status = e.code
        except (urllib.error.URLError, TimeoutError):
            status = 0
    return status


def image_errors(printings: dict[str, dict], head=head_status, workers: int = IMAGE_WORKERS) -> list[str]:
    urls = {pid: p["image"] for pid, p in printings.items() if p["source"] == "bandai"}
    with ThreadPoolExecutor(workers) as pool:
        statuses = dict(zip(urls, pool.map(head, urls.values())))
    return [f"printing {pid}: Bandai image answers {status or 'nothing'}"
            for pid, status in sorted(statuses.items()) if status is not None]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--images", action="store_true", help="with --online, also HEAD every Bandai printing image")
    args = ap.parse_args()
    sets, files, sealed = opjson.load_sets(), opjson.load_cards(), opjson.load_sealed()
    errors = opjson.validate(sets, files, sealed)
    if not errors and args.online:
        errors = online_errors(sets, files, images=args.images)
    for e in errors:
        print(e)
    flat = opjson.flatten(sets, files)
    print(f"{len(errors)} problems in {len(flat['sets'])} sets, {len(flat['cards'])} cards, "
          f"{len(flat['printings'])} printings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
