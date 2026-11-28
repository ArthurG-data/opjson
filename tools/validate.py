"""Check sets/sets.json and data/cards against the schemas and each other. Exits 1 on any problem.

    uv run python tools/validate.py [--since REF] [--online [--images]]

Every record must carry the UUID data/uuids.json gives it (run tools/uuids.py after the import tools). --since also
checks that no UUID data/uuids.json gave at git REF was dropped or changed: a UUID, once given, never changes.

--online also asks TCGCSV whether every TCGplayer product id, on a printing or a sealed product, still exists in
category 68. --images also asks Bandai whether every Bandai printing's image is still served: about 5,000
requests, so CI runs it only for a release tag. They go IMAGE_WORKERS at a time, and a 5xx or a dropped connection is retried before it counts.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import opjson
import tcgcsv
import uuids

USER_AGENT = opjson.USER_AGENT
IMAGE_WORKERS = 6
IMAGE_TRIES = 3


def online_errors(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict] | None = None,
                  images: bool = False) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="opjson-online-") as tmp:
        cache = Path(tmp)
        live = {p.product_id for g in tcgcsv.groups(cache) for p in tcgcsv.products(g["groupId"], cache)}
    flat = opjson.flatten(sets, files, sealed)
    errors = gone_products(live, flat)
    if images:
        errors += image_errors(flat["printings"])
    return errors


def gone_products(live: set[int], flat: dict[str, dict]) -> list[str]:
    """A message for each TCGplayer product id, on a printing or a sealed product, that category 68 no longer
    lists."""
    errors = []
    for kind, key in (("printing", "printings"), ("sealed product", "products")):
        for item_id, item in flat[key].items():
            for product_id in item.get("identifiers", {}).get("tcgplayerProductIds", []):
                if product_id not in live:
                    errors.append(f"{kind} {item_id}: TCGplayer product {product_id} is gone from category 68")
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


def registry_at(ref: str) -> dict:
    """data/uuids.json as git ``ref`` has it; empty at a commit from before the registry existed."""
    path = uuids.REGISTRY.relative_to(opjson.ROOT).as_posix()

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=opjson.ROOT, capture_output=True, text=True)
    if git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
        raise SystemExit(f"--since {ref}: git knows no such commit")
    if git("cat-file", "-e", f"{ref}:{path}").returncode != 0:
        return uuids.empty()
    return uuids.parse(git("show", f"{ref}:{path}").stdout)


def offline_errors(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict], registry: dict,
                   before: dict | None = None) -> list[str]:
    """Every problem found without the network: the data and its references, then every record's UUID against
    registry, then, given an earlier registry, any UUID it gave that registry dropped or changed."""
    errors = opjson.validate(sets, files, sealed) or uuids.errors(sets, files, sealed, registry)
    if before is not None:
        errors += uuids.history_errors(before, registry)
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--images", action="store_true", help="with --online, also HEAD every Bandai printing image")
    ap.add_argument("--since", metavar="REF", help="also check that no UUID changed or was dropped since git REF")
    args = ap.parse_args()
    sets, files, sealed = opjson.load_sets(), opjson.load_cards(), opjson.load_sealed()
    errors = offline_errors(sets, files, sealed, uuids.load(), registry_at(args.since) if args.since else None)
    if not errors and args.online:
        errors = online_errors(sets, files, sealed, images=args.images)
    for e in errors:
        print(e)
    flat = opjson.flatten(sets, files)
    print(f"{len(errors)} problems in {len(flat['sets'])} sets, {len(flat['cards'])} cards, "
          f"{len(flat['printings'])} printings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
