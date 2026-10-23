"""Fetch every English series page of the official card list into .cache/bandai, then print a summary.

    uv run python tools/crawl_bandai.py [--refresh]
"""
from __future__ import annotations

import argparse
import collections
from pathlib import Path

import bandai

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "bandai"


def crawl(refresh: bool = False) -> tuple[list[bandai.Series], list[bandai.Printing]]:
    index = bandai.fetch(bandai.CARDLIST.format(series="569101"), CACHE, refresh)
    series = bandai.parse_series(index)
    printings = []
    for s in series:
        page = bandai.fetch(bandai.CARDLIST.format(series=s.series_id), CACHE, refresh)
        printings += bandai.parse_cards(page, s.series_id)
    return series, printings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch pages already cached")
    args = ap.parse_args()
    series, printings = crawl(args.refresh)
    ids = collections.Counter(p.printing_id for p in printings)
    print(f"{len(series)} series, {len(printings)} printing rows, {len(ids)} distinct printing ids, "
          f"{len({p.number for p in printings})} card numbers")
    print("ids on more than one series page:", sum(1 for n in ids.values() if n > 1))


if __name__ == "__main__":
    main()
