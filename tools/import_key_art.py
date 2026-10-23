"""Add each set's key art: the main visual on its Bandai product page, cropped to the artwork.

    uv run --group dev python tools/import_key_art.py [--refresh]

Every booster and starter deck page opens on a main visual (an image named mv or mv_01). Older pages use a
990x556 banner with a release-date band along the bottom and a shot of the pack at the right; the crop keeps the
artwork left of the pack and above the band. Newer pages use a square visual that is all artwork, kept whole. The
set comes from the page's logo alt text or its address, as in import_logos. A page that names no set, or several
(st01-04 shows four decks at once), is listed in review/key_art.json instead.

A booster whose page has no single main visual (OP05's is a placeholder, OP09's is four portraits) takes its
booster pack's TCGplayer picture instead, cropped to the illustration on the pack's upper half. Starter decks do
not: their boxes are photographed at an angle. Run after import_logos and import_sealed.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from urllib.parse import urljoin

import bandai
import images
import import_logos
import opjson

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "review" / "key_art.json"
_MV_NAMES = ("mv", "mv_01")
BANNER = (990, 556)
# The banner's artwork: everything left of the pack shot and above the release-date band, inside the dark
# border most banners have along the top (up to 30 px) and some along the left (10 px).
BANNER_CROP = [10, 30, 762, 437]
TCGPLAYER_IMAGE = "https://tcgplayer-cdn.tcgplayer.com/product/{product_id}_in_1000x1000.jpg"
BOOSTER_TYPES = ("booster", "extra_booster", "premium_booster")
# The pack's illustration, as shares of the pack (the picture trimmed of its white padding): below the
# "English Ver." header strip and above the game's logo.
PACK_ART = (0.04, 0.17, 0.96, 0.54)


def find_key_art(page: str, page_url: str) -> str | None:
    """The page's main visual url, or None."""
    for tag in import_logos._IMG.findall(page):
        attrs = {m.group("name").lower(): html.unescape(m.group("value")) for m in import_logos._ATTR.finditer(tag)}
        src = attrs.get("src") or attrs.get("data-src") or ""
        if src.split("?", 1)[0].rsplit("/", 1)[-1].rsplit(".", 1)[0] in _MV_NAMES:
            return urljoin(page_url, src)
    return None


def page_sets(page: str, page_url: str) -> list[str]:
    """The sets a page is about: the codes its logos name, else the code in its address."""
    codes = sorted({c for _, cs in import_logos.find_logos(page, page_url) for c in cs})
    if codes:
        return codes
    code = import_logos.page_code(page_url)
    return [code] if code else []


def key_art(set_id: str, url: str, source: str) -> dict:
    """The keyArt entry for one image: its size, and the crop when it is a banner."""
    from PIL import Image

    path = images.fetch("bandai_art", set_id, url)
    if path is None:
        raise SystemExit(f"{set_id}: {url} is gone")
    with Image.open(path) as im:
        size = list(im.size)
    art = {"url": url, "source": source, "size": size}
    if tuple(size) == BANNER:
        art["crop"] = BANNER_CROP
    return art


def pack_art(set_id: str, sealed: dict) -> dict | None:
    """The keyArt entry cut from the set's booster pack picture on TCGplayer, or None without one."""
    from PIL import Image

    pack = next((p for p in sealed.get("products", []) if p["set"] == set_id and p["category"] == "booster_pack"
                 and (p.get("identifiers") or {}).get("tcgplayerProductIds")), None)
    if pack is None:
        return None
    product_id = pack["identifiers"]["tcgplayerProductIds"][0]
    url = TCGPLAYER_IMAGE.format(product_id=product_id)
    path = images.fetch("tcgplayer_art", str(product_id), url)
    if path is None:
        return None
    with Image.open(path) as im:
        size = list(im.size)
        x0, y0, x1, y1 = im.convert("L").point(lambda v: 255 if v < 245 else 0).getbbox() or (0, 0, *im.size)
    w, h = x1 - x0, y1 - y0
    left, top, right, bottom = PACK_ART
    crop = [x0 + round(w * left), y0 + round(h * top), round(w * (right - left)), round(h * (bottom - top))]
    return {"url": url, "source": pack["sources"][0], "size": size, "crop": crop}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch pages already cached")
    args = ap.parse_args()
    sets = opjson.load_sets()
    by_id = {s["id"]: s for s in sets}
    found: dict[str, tuple[str, str]] = {}
    review = []
    for page_url in import_logos.crawl(args.refresh):
        page = bandai.fetch(page_url, import_logos.CACHE, args.refresh)
        url = find_key_art(page, page_url)
        if url is None:
            continue
        codes = page_sets(page, page_url)
        if "/products/other/" in page_url and not codes:
            continue  # sleeves, play mats and other goods: no set
        if len(codes) != 1 or codes[0] not in by_id:
            review.append({"page": page_url, "keyArt": url, "codes": codes,
                           "reason": "names no set" if not codes else
                           "names several sets" if len(codes) > 1 else "set not in sets.json"})
        elif codes[0] in found and found[codes[0]][0] != url:
            review.append({"set": codes[0], "reason": "several pages give different key art",
                           "pages": [found[codes[0]][1], page_url]})
        else:
            found[codes[0]] = (url, page_url)
    cropped = packs = 0
    sealed = opjson.load_sealed()
    for s in sets:
        release = next(r for r in s["releases"] if r["language"] == "en")
        release.pop("keyArt", None)
        if s["id"] in found:
            release["keyArt"] = key_art(s["id"], *found[s["id"]])
            cropped += "crop" in release["keyArt"]
        elif s["type"] in BOOSTER_TYPES and not s.get("parent"):
            art = pack_art(s["id"], sealed.get(s["id"], {}))
            if art:
                release["keyArt"] = art
                packs += 1
    opjson.SETS.write_text(json.dumps(sets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(found)} sets given key art ({cropped} cropped from a banner), {packs} more from their booster pack; "
          f"{len(review)} pages to review")


if __name__ == "__main__":
    main()
