"""Run the whole import chain, in the order each tool needs, and stop at the first one that fails.

    uv run python tools/refresh.py [--weekly] [--cached] [--fresh-tcgcsv]

The tools share data/ and .cache/, so the order matters: the English tools come first, the Japanese ones after every
English tool, and uuids last. A daily run crawls Bandai's card lists again (--refresh) and reads everything else from
.cache/. --weekly adds the slow sources: the English and Japanese product pages are fetched again, and the cached
Limitless pages are dropped so they are fetched again too. import_key_art gets no --refresh. It reads the English
product pages import_logos has just fetched again into the same cache, and a second fetch would only double the
requests to Bandai. --cached reads the cached Bandai card lists instead of crawling. --fresh-tcgcsv moves the cached
TCGcsv snapshot aside as tcgcsv.<date>, so the next import_tcgplayer fetches a new one.

Before the first tool runs, every zero-byte image in the cache is deleted: fetch writes one for an image the source did
not have, and a refresh asks for it again. The ends of the chain (validate, check_losses, legality, build) are not run
here; a release runs them.
"""
from __future__ import annotations

import argparse
import datetime
import shutil
import subprocess
import sys
from pathlib import Path

import images

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
CACHE = ROOT / ".cache"


def commands(weekly: bool, cached: bool) -> list[list[str]]:
    refresh = [] if cached else ["--refresh"]
    weekly_refresh = ["--refresh"] if weekly else []
    steps = [
        ("crawl_bandai", refresh),
        ("import_bandai", []),
        ("images", ["fetch"]),
        ("check_blocks", []),
        ("import_tcgplayer", []),
        ("link_reprint_art", []),
        ("infer_finishes", []),
        ("import_logos", weekly_refresh),
        ("import_sealed", []),
        ("import_key_art", []),
        ("import_limitless", []),
        ("crawl_bandai", ["--language", "ja", *refresh]),
        ("import_bandai_ja", ["--refresh-products"] if weekly else []),
        ("import_sealed_ja", []),
        ("images", ["fetch"]),
        ("link_twins", []),
        ("uuids", []),
        ("readme_counts", []),
    ]
    return [[sys.executable, str(TOOLS / f"{stem}.py"), *args] for stem, args in steps]


def prepare(weekly: bool, fresh_tcgcsv: bool, cache: Path = CACHE, today: str | None = None) -> None:
    """Forget the images that were missing last time, then clear what this run must fetch again. A directory that is
    not in the cache is nothing to clear."""
    if (cache / "images").is_dir():
        images.forget_misses(cache / "images")
    if weekly:
        shutil.rmtree(cache / "limitless", ignore_errors=True)
    if fresh_tcgcsv and (cache / "tcgcsv").is_dir():
        today = today or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        aside = cache / f"tcgcsv.{today}"
        shutil.rmtree(aside, ignore_errors=True)
        (cache / "tcgcsv").rename(aside)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weekly", action="store_true", help="also fetch the slow sources again (logos, key art, ja products, Limitless)")
    ap.add_argument("--cached", action="store_true", help="read the cached Bandai card lists instead of crawling")
    ap.add_argument("--fresh-tcgcsv", action="store_true", help="move the cached TCGcsv snapshot aside so a new one is fetched")
    args = ap.parse_args()
    prepare(args.weekly, args.fresh_tcgcsv)
    for command in commands(args.weekly, args.cached):
        stem = Path(command[1]).stem
        print(f"== {stem}", flush=True)
        done = subprocess.run(command, cwd=ROOT)
        if done.returncode != 0:
            sys.exit(f"{stem} failed (exit {done.returncode}); the steps after it did not run")


if __name__ == "__main__":
    main()
