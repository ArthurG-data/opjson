"""Fetch every series page of the official card list into .cache/bandai, then print a summary.

    uv run python tools/crawl_bandai.py [--language en|ja] [--refresh]

The English pages are cached in .cache/bandai, the Japanese ones in .cache/bandai/ja.
"""
from __future__ import annotations

import argparse
import collections
from pathlib import Path

import bandai

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "bandai"
# The series each language's crawl starts from: its OP-01 page, whose selector lists every series.
FIRST_SERIES = {"en": "569101", "ja": "550101"}


def cache(language: str = "en") -> Path:
    return CACHE if language == "en" else CACHE / language


def crawl(refresh: bool = False, language: str = "en") -> tuple[list[bandai.Series], list[bandai.Printing]]:
    index = bandai.fetch(bandai.cardlist(FIRST_SERIES[language], language), cache(language), refresh)
    series = bandai.parse_series(index, language)
    printings = []
    for s in series:
        page = bandai.fetch(bandai.cardlist(s.series_id, language), cache(language), refresh)
        printings += bandai.parse_cards(page, s.series_id, language)
    return series, printings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--language", choices=sorted(FIRST_SERIES), default="en")
    ap.add_argument("--refresh", action="store_true", help="re-fetch pages already cached")
    args = ap.parse_args()
    series, printings = crawl(args.refresh, args.language)
    ids = collections.Counter(p.printing_id for p in printings)
    print(f"{len(series)} series, {len(printings)} printing rows, {len(ids)} distinct printing ids, "
          f"{len({p.number for p in printings})} card numbers")
    print("ids on more than one series page:", sum(1 for n in ids.values() if n > 1))


if __name__ == "__main__":
    main()
