"""Check the credited illustrators (from Limitless, see import_limitless.py) against the cards themselves.

    uv run --group ocr python tools/ocr_artists.py [--limit N]

The credit is printed vertically down the card's right edge. The strip is cropped, turned upright, enlarged and
read with RapidOCR three times at different crops and contrasts. OCR drops or keeps the gap between words
unpredictably, so names are compared by their letters without spaces. A printing counts as read only when at
least two readings agree with confidence of at least MIN_CONFIDENCE and the reading is not a near-miss of a far
commoner one. Every confident reading that disagrees with the credited artist goes to
review/artists-ocr-check.json. Readings are cached in .cache/ocr.json. This tool writes no data.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

import images
import opjson

ROOT = Path(__file__).resolve().parents[1]
OCR_CACHE = ROOT / ".cache" / "ocr.json"
REVIEW = ROOT / "review" / "artists-ocr-check.json"
MIN_CONFIDENCE = 0.90
# (left edge of the crop as a share of the card's width, enlargement, contrast cut-off in percent). The strip
# runs to 99.5% of the width and down 70% of the card: anime-art credits ("TV animation ONE PIECE Key
# Animation: Katsumi Ishizuka") run further down the edge than an illustrator's name.
VARIANTS = ((0.95, 3, 0), (0.955, 5, 0), (0.955, 4, 2))
STRIP_BOTTOM = 0.70
# A credit has at least three letters; shorter reads are bits of the frame (a power digit, a symbol).
_NAME = re.compile(r"[A-Za-z][A-Za-z .,'&:\-]{2,}")
# Anime-art cards credit the key animator after this label.
_KEY_ANIMATION = re.compile(r"key\s*animation\s*:?\s*(.+)$", re.I)
# A spelling seen on few cards that is this close to a far more common one is likely a misread of it.
NEAR_KEY_DISTANCE = 2
NEAR_KEY_RATIO = 3


def key(name: str) -> str:
    return re.sub(r"[^A-Z]", "", name.upper())


def read(path: Path, engine) -> list[tuple[str, float]]:
    """The best name-like reading for each crop variant, as (text, confidence); ("", 0) when none."""
    import numpy as np
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        im = im.convert("L")
        w, h = im.size
        out = []
        for x0, scale, cutoff in VARIANTS:
            strip = im.crop((int(w * x0), int(h * 0.04), int(w * 0.995), int(h * STRIP_BOTTOM)))
            strip = strip.rotate(-90, expand=True)
            big = ImageOps.autocontrast(strip.resize((strip.width * scale, strip.height * scale), Image.LANCZOS),
                                        cutoff=cutoff)
            result, _ = engine(np.array(big.convert("RGB")))
            names = [(credit_name(t), float(c)) for _, t, c in (result or []) if _NAME.fullmatch(t.strip())]
            names = [(t, c) for t, c in names if key(t)]
            out.append(max(names, key=lambda tc: tc[1]) if names else ("", 0.0))
    return out


def credit_name(text: str) -> str:
    """The artist's name in a credit line: the name itself, or what follows "Key Animation:"."""
    text = re.sub(r"\s+", " ", text.strip())
    m = _KEY_ANIMATION.search(text)
    return m.group(1).strip() if m else text


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def spell(readings: list[list[tuple[str, float]]]) -> tuple[dict[str, str], set[str]]:
    """({letters key: spelling}, keys that look like misreads of a commoner key).

    OCR drops a gap between words far more often than it invents one, so among spellings of one key the most
    common one that keeps the most gaps wins."""
    spellings: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    cards = collections.Counter()
    for card in readings:
        seen = set()
        for text, conf in card:
            if conf >= MIN_CONFIDENCE and key(text):
                spellings[key(text)][text] += 1
                seen.add(key(text))
        cards.update(seen)
    spelled = {k: max(c.items(), key=lambda kv: (kv[0].count(" "), kv[1]))[0] for k, c in spellings.items()}
    suspect = {k for k in cards for other in cards
               if other != k and cards[other] >= NEAR_KEY_RATIO * cards[k]
               and edit_distance(k, other) <= NEAR_KEY_DISTANCE}
    return spelled, suspect


def main() -> None:
    from rapidocr_onnxruntime import RapidOCR

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="read at most N uncached images (for trying the crop)")
    args = ap.parse_args()
    cache = json.loads(OCR_CACHE.read_text()) if OCR_CACHE.exists() else {}
    files = opjson.load_cards()
    bandai = [p for body in files.values() for c in body["cards"] for p in c["printings"] if p["source"] == "bandai"]
    engine = RapidOCR()
    fresh = 0
    for p in bandai:
        if p["id"] in cache:
            continue
        img = images.path_for("bandai", p["id"])
        if not img.exists() or not img.stat().st_size:
            continue
        if args.limit is not None and fresh >= args.limit:
            break
        cache[p["id"]] = read(img, engine)
        fresh += 1
        if fresh % 200 == 0:
            OCR_CACHE.write_text(json.dumps(cache))
            print(f"read {fresh}", flush=True)
    OCR_CACHE.write_text(json.dumps(cache))

    spelled, suspect = spell(list(cache.values()))
    agree, near, disagree, unread, no_credit = 0, [], [], 0, 0
    for p in bandai:
        readings = cache.get(p["id"])
        if readings is None:
            continue
        confident = [key(t) for t, c in readings if c >= MIN_CONFIDENCE and key(t)]
        keys = set(confident)
        if not (len(keys) == 1 and len(confident) >= 2) or keys & suspect:
            unread += 1
            continue
        ocr = keys.pop()
        credited = p.get("artist")
        if credited is None:
            no_credit += 1
            continue
        if ocr == key(credited):
            agree += 1
        elif edit_distance(ocr, key(credited)) <= NEAR_KEY_DISTANCE:
            near.append({"printing": p["id"], "credited": credited, "ocr": spelled[ocr]})
        else:
            disagree.append({"printing": p["id"], "image": p["image"], "credited": credited, "ocr": spelled[ocr]})
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps({"disagree": disagree, "near": near}, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(f"read {fresh} new images; of printings OCR reads confidently: {agree} agree with the credited artist, "
          f"{len(near)} differ by a letter or two (OCR slips), {len(disagree)} disagree; {no_credit} have no credit; "
          f"{unread} not read confidently; {len(bandai) - len(cache)} images not read yet")


if __name__ == "__main__":
    main()
