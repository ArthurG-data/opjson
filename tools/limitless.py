"""Limitless TCG's One Piece card database (onepiece.limitlesstcg.com), cached under .cache/limitless.

Limitless lists every printing under Bandai's own printing id (its image is <id>_EN.webp), with the TCGplayer
product and Cardmarket page that sell it, and credits its illustrator. Search results come 50 to a page.
robots.txt allows everything; requests are spaced CRAWL_DELAY_S apart and every page is cached.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BASE = "https://onepiece.limitlesstcg.com"
USER_AGENT = "opjson/0.1 (+https://github.com/ArthurG-data/opjson)"
CRAWL_DELAY_S = 2.0

_ROW = re.compile(r'<tr data-hover="[^"]*/one-piece/[^/"]+/(?P<file>[^/"]+)\.webp">(?P<body>.*?)</tr>', re.S)
_FILE = re.compile(r"^(?P<id>[A-Z]+[0-9]*-[0-9]{3}(?:_[a-z]+[0-9]*)?)_(?P<lang>EN|JP)$")
_TCGPLAYER = re.compile(r"tcgplayer\.com%2Fproduct%2F(\d+)")
_CARDMARKET = re.compile(r'href="(https://www\.cardmarket\.com/[^"?]+)')
_PAGES = re.compile(r'class="pagination" data-current="(\d+)" data-max="(\d+)"')
_TOTAL = re.compile(r"(\d+) cards?\b")


@dataclass(frozen=True)
class Row:
    printing_id: str
    language: str
    tcgplayer_product_id: int | None
    cardmarket_url: str | None


def parse_rows(page: str) -> list[Row]:
    rows = []
    for m in _ROW.finditer(page):
        f = _FILE.match(m.group("file"))
        if not f:
            raise ValueError(f"unexpected Limitless image name {m.group('file')!r}")
        tcg = _TCGPLAYER.search(m.group("body"))
        cm = _CARDMARKET.search(m.group("body"))
        rows.append(Row(f.group("id"), f.group("lang"), int(tcg.group(1)) if tcg else None,
                        html.unescape(cm.group(1)) if cm else None))
    return rows


def page_count(page: str) -> int:
    m = _PAGES.search(page)
    return int(m.group(2)) if m else 1


def total(page: str) -> int | None:
    m = _TOTAL.search(page)
    return int(m.group(1)) if m else None


class Client:
    def __init__(self, cache: Path):
        self.cache = cache

    def get(self, path: str) -> str:
        """The page or API response at path, from cache when present."""
        self.cache.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")[:180]
        file = self.cache / f"{name}.html"
        if file.exists():
            return file.read_text(encoding="utf-8")
        time.sleep(CRAWL_DELAY_S)
        req = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
        file.write_text(body, encoding="utf-8")
        return body

    def api(self, path: str):
        return json.loads(self.get("/api/" + path))

    def search(self, query: str) -> list[Row]:
        """Every row of a card search, across all its pages. Raises if the rows fall short of the stated total."""
        q = urllib.parse.quote(query)
        first = self.get(f"/cards?q={q}&display=list")
        rows = parse_rows(first)
        for n in range(2, page_count(first) + 1):
            rows += parse_rows(self.get(f"/cards?q={q}&display=list&page={n}"))
        stated = total(first)
        if stated is not None and stated != len(rows):
            raise RuntimeError(f"search {query!r}: page says {stated} cards, read {len(rows)}")
        return rows
