"""Limitless TCG's One Piece card database (onepiece.limitlesstcg.com), cached under .cache/limitless.

Limitless lists every printing under Bandai's own printing id (its image is <id>_EN.webp), with the TCGplayer
product and Cardmarket page that sell it, and credits its illustrator. Search results come 50 to a page.
robots.txt allows everything; requests are spaced CRAWL_DELAY_S apart and every page is cached.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import opjson

BASE = "https://onepiece.limitlesstcg.com"
USER_AGENT = opjson.USER_AGENT
CRAWL_DELAY_S = 2.0

_ROW = re.compile(r'<tr data-hover="[^"]*/one-piece/[^/"]+/(?P<file>[^/"]+)\.webp">(?P<body>.*?)</tr>', re.S)
_FILE = re.compile(r"^(?P<id>[A-Z]+[0-9]*-[0-9]{3}(?:_[a-z]+[0-9]*)?)_(?P<lang>EN|JP)$")
_TCGPLAYER = re.compile(r"tcgplayer\.com%2Fproduct%2F(\d+)")
_CARDMARKET = re.compile(r'href="(https://www\.cardmarket\.com/[^"?]+)')
_PAGES = re.compile(r'class="pagination" data-current="(\d+)" data-max="(\d+)"')
# Every search page, one with no results included, opens with "N cards found where ...".
_TOTAL = re.compile(r'class="search-summary">\s*(\d+) cards? found')


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

    def get(self, path: str, valid=lambda body: True) -> str:
        """The page or API response at path, from cache when present. A response valid rejects raises ValueError
        and is not cached, so a rate-limit or maintenance page is asked for again on the next run."""
        file = self.cache / cache_name(path)
        legacy = self.cache / f"{re.sub(r'[^A-Za-z0-9]+', '_', path).strip('_')[:180]}.html"
        if not file.exists() and legacy.exists():
            legacy.replace(file)  # a page cached under the old name, which had no digest
        if file.exists():
            return file.read_text(encoding="utf-8")
        time.sleep(CRAWL_DELAY_S)
        req = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
        if not valid(body):
            raise ValueError(f"{BASE + path}: not the page asked for; not cached")
        opjson.write_atomic(file, body)
        return body

    def api(self, path: str):
        return json.loads(self.get("/api/" + path, valid=_is_json))

    def search(self, query: str) -> list[Row]:
        """Every row of a card search, across all its pages. Raises if the rows fall short of the stated total."""
        q = urllib.parse.quote(query)
        first = self.get(f"/cards?q={q}&display=list", valid=_is_search)
        rows = parse_rows(first)
        for n in range(2, page_count(first) + 1):
            rows += parse_rows(self.get(f"/cards?q={q}&display=list&page={n}", valid=_is_search))
        stated = total(first)
        if stated is None:
            raise ValueError(f"search {query!r}: the page states no total")
        if stated != len(rows):
            raise RuntimeError(f"search {query!r}: page says {stated} cards, read {len(rows)}")
        return rows


def cache_name(path: str) -> str:
    """The cache file for a path: readable, and unique. The readable part drops punctuation, so a digest of the
    whole path keeps !artist:"A.B" and !artist:"A B" apart."""
    readable = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")[:160]
    return f"{readable}_{hashlib.sha256(path.encode('utf-8')).hexdigest()[:12]}.html"


def _is_search(body: str) -> bool:
    return _TOTAL.search(body) is not None


def _is_json(body: str) -> bool:
    try:
        json.loads(body)
    except ValueError:
        return False
    return True
