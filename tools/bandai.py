"""Read the official card list, English (en.onepiece-cardgame.com) or Japanese (www.onepiece-cardgame.com), into
series, cards and printings.

The card list has one page per series. Each printing is a `<dl class="modalCol">` whose id is Bandai's
printing id: the card number for the base printing (`OP01-006`), with `_pN` for a parallel or alternate art
and `_rN` for a reprint. Only facts are read: number, rarity, category, name, cost, power, counter, life,
attribute, colour, block icon, types and the set the page says the printing comes from. Effect text and
art are not copied; the image is kept as a link.

The Japanese list uses the same page template. Its set codes are in full-width brackets (【OP-17】), and its
labels and values are in Japanese: colours, attributes and the SP CARD rarity are read into the English words,
while names, types and card sets stay as Bandai prints them.
"""
from __future__ import annotations

import html
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SITES = {"en": "https://en.onepiece-cardgame.com", "ja": "https://www.onepiece-cardgame.com"}
BASE = SITES["en"]
CARDLIST = BASE + "/cardlist/?series={series}"
USER_AGENT = "opjson/0.1 (+https://github.com/ArthurG-data/opjson)"
# One request every two seconds keeps a full crawl (about 75 pages) under three minutes.
CRAWL_DELAY_S = 2.0

_OPTION = re.compile(r'<option value="(\d{6})"[^>]*>(.*?)(?=<option|</select>)', re.S)
_CARD = re.compile(r'<dl class="modalCol" id="([^"]+)">(.*?)</dl>', re.S)
_INFO = re.compile(r'<div class="infoCol">\s*<span>([^<]*)</span>\s*\|\s*<span>([^<]*)</span>\s*\|\s*<span>([^<]*)</span>')
_NAME = re.compile(r'<div class="cardName">(.*?)</div>', re.S)
_IMAGE = re.compile(r'data-src="\.\./images/cardlist/card/([^"?]+)')
_SET_CODE = {"en": re.compile(r"\[([A-Z0-9-]+)\]\s*$"), "ja": re.compile(r"【([A-Z0-9-]+)】\s*$")}
_PRODUCT = re.compile(r'<a href="(/products/[^"]+)" class="getInfoBtn">')
# The Japanese list's words for the closed vocabularies, and its labels for the box that holds a cost or a life.
JA_COLORS = {"赤": "Red", "緑": "Green", "青": "Blue", "紫": "Purple", "黒": "Black", "黄": "Yellow"}
JA_ATTRIBUTES = {"打": "Strike", "斬": "Slash", "特": "Special", "射": "Ranged", "知": "Wisdom", "？": "?"}
JA_RARITIES = {"SPカード": "SP CARD"}
_COST_LABELS = {"Cost": "Cost", "Life": "Life", "コスト": "Cost", "ライフ": "Life"}
# Bandai's printing id: card number, then _pN (parallel/alternate art) or _rN (reprint). Anything else is
# refused: the id becomes a file name and a cache key.
_VARIANT = re.compile(r"^(?P<number>[A-Z]+[0-9]*-[0-9]{3})(?:_(?P<kind>[pr])(?P<n>\d+))?$")


@dataclass(frozen=True)
class Series:
    series_id: str
    title: str
    code: str | None  # the bracketed code, e.g. "OP-01"; None for "Promotion card" and "Other Product Card"
    language: str = "en"


@dataclass
class Printing:
    printing_id: str
    number: str
    variant_kind: str | None  # "p" (parallel/alternate art), "r" (reprint) or None (base)
    variant_n: int | None
    rarity: str
    category: str
    name: str
    image: str
    series_id: str
    card_set: str | None  # what "Card Set(s)" says, e.g. "-ROMANCE DAWN- [OP01]"
    facts: dict = field(default_factory=dict)
    product: str | None = None  # the Japanese list's link to the product page of the printing's set


def _text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", " ", fragment)
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def cardlist(series: str, language: str = "en") -> str:
    return SITES[language] + "/cardlist/?series=" + series


def parse_series(page: str, language: str = "en") -> list[Series]:
    """Every series offered by the card list's series selector, in page order."""
    select = page[page.find('id="series"'):]
    select = select[:select.find("</select>") + len("</select>")]
    out = []
    for series_id, raw in _OPTION.findall(select):
        title = re.sub(r"\s+", " ", _text(raw.replace("&lt;br", " &lt;br")))
        title = re.sub(r"<br[^>]*>", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        m = _SET_CODE[language].search(title)
        out.append(Series(series_id, title, m.group(1) if m else None, language))
    return out


def _field(block: str, css: str) -> str | None:
    m = re.search(rf'<div class="{css}">\s*<h3>.*?</h3>(.*?)</div>', block, re.S)
    if not m:
        return None
    # The Japanese card set is followed by its buttons (カードリスト, 商品情報), which are not part of it.
    value = _text(m.group(1).split('<div class="getInfoBtnCol">')[0])
    return None if value in ("", "-") else value


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in value.split("/") if v.strip()] if value else []


def _int(value: str | None) -> int | None:
    return int(value) if value is not None and value.isdigit() else None


def _attributes(block: str, language: str) -> list[str]:
    """The English list names the attribute in <i>; the Japanese one only in its icon's alt text."""
    m = re.search(r'<div class="attribute">(.*?)</div>', block, re.S)
    if not m:
        return []
    named = re.search(r"<i>(.*?)</i>", m.group(1), re.S)
    names = _split(_text(named.group(1)) if named else "/".join(re.findall(r'alt="([^"]*)"', m.group(1))))
    return [JA_ATTRIBUTES.get(a, a) for a in names] if language == "ja" else names


def parse_cards(page: str, series_id: str, language: str = "en") -> list[Printing]:
    """Every printing on one series page, in page order."""
    out = []
    for printing_id, block in _CARD.findall(page):
        info = _INFO.search(block)
        if not info:
            raise ValueError(f"series {series_id}: {printing_id} has no infoCol")
        number, rarity, category = (_text(x) for x in info.groups())
        v = _VARIANT.match(printing_id)
        if v is None:
            raise ValueError(f"series {series_id}: {printing_id!r} is not a Bandai printing id")
        if v.group("number") != number:
            raise ValueError(f"series {series_id}: id {printing_id} does not start with its number {number}")
        image = _IMAGE.search(block)
        # A Leader's "cost" box holds its Life instead; the box's heading says which.
        cost_box = re.search(r'<div class="cost"><h3>([^<]*)</h3>([^<]*)</div>', block)
        cost_label, cost_value = (_COST_LABELS[cost_box.group(1)], cost_box.group(2)) if cost_box else ("Cost", None)
        colors = _split(_field(block, "color"))
        product = _PRODUCT.search(block)
        out.append(Printing(
            printing_id=printing_id,
            number=number,
            variant_kind=v.group("kind"),
            variant_n=int(v.group("n")) if v.group("n") else None,
            rarity=JA_RARITIES.get(rarity, rarity) if language == "ja" else rarity,
            category=category.title(),
            name=_text(_NAME.search(block).group(1)),
            image=f"{SITES[language]}/images/cardlist/card/{image.group(1)}" if image else "",
            series_id=series_id,
            card_set=_field(block, "getInfo"),
            facts={
                "cost": _int(cost_value) if cost_label == "Cost" else None,
                "power": _int(_field(block, "power")),
                "counter": _int(_field(block, "counter")),
                "life": _int(cost_value) if cost_label == "Life" else None,
                "attributes": _attributes(block, language),
                "colors": [JA_COLORS[c] for c in "".join(colors)] if language == "ja" else colors,
                "block": _field(block, "block"),
                "types": _split(_field(block, "feature")),
            },
            product=SITES[language] + product.group(1) if product and language == "ja" else None,
        ))
    return out


# The product pages come in several templates: 発売日 in a <dt> or an <h4>, then the date as 2025年7月26日 or
# 2024.07.27, a few times without its 日 (2026年7月11(土)).
_RELEASE_DATE = re.compile(r"発売日</(?:dt|h4)>(?:\s+|<[^>]*>){0,8}(\d{4})[年.](\d{1,2})[月.](\d{1,2})")


def parse_release_date(page: str) -> str | None:
    """The 発売日 (release date) a Japanese product page states, as YYYY-MM-DD."""
    m = _RELEASE_DATE.search(page)
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def fetch(url: str, cache: Path, refresh: bool = False) -> str:
    """The page at url, from cache when present. A fetch waits CRAWL_DELAY_S first."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (re.sub(r"[^A-Za-z0-9]+", "_", url.split("//", 1)[1]) + ".html")
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8")
    time.sleep(CRAWL_DELAY_S)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        page = resp.read().decode("utf-8")
    path.write_text(page, encoding="utf-8")
    return page
