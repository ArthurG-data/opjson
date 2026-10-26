"""Add each set's logo from Bandai's product pages, where the page has one.

    uv run python tools/import_logos.py [--refresh]

Bandai's newer product pages show the set's logo as an image named logo, logo_product, mv_logo or sp_logo. Its alt text
usually ends with the set code in brackets ("BOOSTER PACK -THE DOMINANCE OF GOD- [OP-18]"); when it does not, the
code comes from the page address (/products/boosters/op05/). Older pages have only a banner, and those sets get no
logo; anniversary logos, titles and banners are never taken. A logo goes on a set only when it names exactly one
code, that code is a set in sets.json, and no other image offers that set a different logo; every other logo is
listed in review/logos.json. Run after import_tcgplayer, since import_bandai rewrites sets.json.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import bandai
import opjson

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "bandai_products"
REVIEW = ROOT / "review" / "logos.json"
SITE = "https://en.onepiece-cardgame.com"
INDEX = SITE + "/products/?subcategory={subcategory}&page={page}"
SUBCATEGORIES = ("boosters", "decks", "others")

_PRODUCT_LINK = re.compile(r'href="(?P<url>(?:https://en\.onepiece-cardgame\.com)?/products/[^"?#]+)"')
_IMG = re.compile(r"<img\b[^>]*>", re.I)
_ATTR = re.compile(r'(?P<name>[a-z_-]+)="(?P<value>[^"]*)"', re.I)
_CODES = re.compile(r"\[(?P<codes>[^\]]+)\]\s*$")
_LOGO_NAMES = ("logo", "logo_product", "mv_logo", "sp_logo")
_PAGE_CODE = re.compile(r"/(?P<code>(?:op|st|eb|prb)\d+(?:[-_]eb\d+)?)(?:/|\.\w+$|_?$)", re.I)


def product_links(page: str) -> list[str]:
    """Absolute product page urls on one index page, in page order, without repeats."""
    out = []
    for m in _PRODUCT_LINK.finditer(page):
        url = urljoin(SITE, m.group("url"))
        if url.rstrip("/") != SITE + "/products" and url not in out and not url.endswith((".css", ".js")):
            out.append(url)
    return out


def set_id(code: str) -> str:
    """Bandai's printed code to an opjson set id: OP-18 is OP18, PRB-02 is PRB02, OP14-EB04 stays."""
    return re.sub(r"^([A-Z]+)-(\d+)$", r"\1\2", code.strip().upper())


def page_code(page_url: str) -> str | None:
    """The set code in a product page's address: /products/boosters/op05/ is OP05, op14-eb04.php is OP14-EB04."""
    m = _PAGE_CODE.search(page_url)
    return set_id(m.group("code").replace("_", "-")) if m else None


def find_logos(page: str, page_url: str) -> list[tuple[str, list[str]]]:
    """(logo url, set ids it names) for each distinct logo image on a page. The ids come from the alt text's
    bracket, else from the page address."""
    out: list[tuple[str, list[str]]] = []
    for tag in _IMG.findall(page):
        attrs = {m.group("name").lower(): html.unescape(m.group("value")) for m in _ATTR.finditer(tag)}
        src = attrs.get("src", "")
        stem = src.split("?", 1)[0].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if stem not in _LOGO_NAMES:
            continue
        m = _CODES.search(attrs.get("alt", "").strip())
        if m:
            codes = [set_id(c) for c in m.group("codes").split("/")]
        else:
            code = page_code(page_url)
            codes = [code] if code else []
        url = urljoin(page_url, src)
        if all(url != u for u, _ in out):
            out.append((url, codes))
    return out


def crawl(refresh: bool) -> list[str]:
    urls: list[str] = []
    for subcategory in SUBCATEGORIES:
        for page_no in range(1, 50):
            found = product_links(bandai.fetch(INDEX.format(subcategory=subcategory, page=page_no), CACHE, refresh))
            new = [u for u in found if u not in urls]
            if not new:
                break
            urls += new
    return urls


def apply(sets: list[dict], logos: list[tuple[str, str, list[str]]]) -> tuple[int, list[dict]]:
    """Write each unambiguous logo onto its set's English release. (sets given a logo, logos left for review)."""
    by_id = {s["id"]: s for s in sets}
    claims: dict[str, list[tuple[str, str]]] = {}
    review = []
    for page_url, logo, codes in logos:
        if len(codes) != 1 or codes[0] not in by_id:
            review.append({"page": page_url, "logo": logo, "codes": codes,
                           "reason": "names no set" if not codes else
                           "names several sets" if len(codes) > 1 else "set not in sets.json"})
            continue
        claims.setdefault(codes[0], []).append((page_url, logo))
    applied = 0
    for s in sets:
        for release in s["releases"]:
            if release["language"] == "en":
                release.pop("logo", None)
        pages = claims.get(s["id"], [])
        if len({logo for _, logo in pages}) > 1:
            review.append({"set": s["id"], "reason": "several pages give different logos",
                           "pages": [{"page": p, "logo": logo} for p, logo in pages]})
            continue
        if pages and opjson.has_release(s, "en"):
            release = next(r for r in s["releases"] if r["language"] == "en")
            release["logo"] = {"url": pages[0][1], "source": pages[0][0]}
            applied += 1
    return applied, review


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch pages already cached")
    args = ap.parse_args()
    urls = crawl(args.refresh)
    logos = []
    for url in urls:
        logos += [(url, logo, codes) for logo, codes in find_logos(bandai.fetch(url, CACHE, args.refresh), url)]
    sets = opjson.load_sets()
    applied, review = apply(sets, logos)
    opjson.SETS.write_text(json.dumps(sets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(urls)} product pages, {len(logos)} logo images; {applied} sets given a logo; "
          f"{len(review)} logos to review")


if __name__ == "__main__":
    main()
