"""Card images, cached under .cache/images, and perceptual hashes to compare a TCGplayer product's image
with a Bandai printing's image.

Bandai's images carry a "SAMPLE" mark across the middle and TCGplayer's do not, so the hash is taken
over the top band of the card (the cost, power and upper art), which the mark does not reach.

    uv run --group dev python tools/images.py fetch   # download every image both sources list
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "images"
USER_AGENT = "opjson/0.1 (+https://github.com/ArthurG-data/opjson)"
TCGPLAYER_IMAGE = "https://tcgplayer-cdn.tcgplayer.com/product/{product_id}_in_400x400.jpg"
DELAY_S = {"bandai": 1.0, "tcgplayer": 0.2}
# The share of the card's height, from the top, that the hash covers.
TOP_BAND = 0.38
RETRY_WAITS_S = (5, 20, 60)  # pauses before each retry of a 5xx or a dropped connection
HASH_SIZE = 16


def path_for(source: str, key: str) -> Path:
    if source not in DELAY_S or not re.fullmatch(r"[A-Za-z0-9_~-]+", key):
        raise ValueError(f"not an image cache key: {source}/{key}")
    return CACHE / source / f"{key}.img"


def fetch(source: str, key: str, url: str) -> Path | None:
    """The cached image, downloading it first if needed. None when the source has no image (404)."""
    path = path_for(source, key)
    if path.exists():
        return path if path.stat().st_size else None
    path.parent.mkdir(parents=True, exist_ok=True)
    time.sleep(DELAY_S[source])
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for wait in RETRY_WAITS_S + (None,):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
            break
        except urllib.error.HTTPError as e:
            # TCGplayer's CDN answers 403, not 404, for a product with no scan.
            if e.code in (403, 404):
                path.write_bytes(b"")  # remember the miss
                return None
            if e.code < 500 or wait is None:
                raise
        except (urllib.error.URLError, TimeoutError):
            if wait is None:
                raise
        time.sleep(wait)  # a server error or a dropped connection: try again a little later
    path.write_bytes(body)
    return path


def dhash(path: Path, band: float = TOP_BAND) -> int:
    """A difference hash of the image's top band (the whole card for band=1), as an int of HASH_SIZE * HASH_SIZE
    bits. The top band holds the art and ignores stamps lower down; the whole card tells apart copies whose
    art agrees but whose lower half differs."""
    from PIL import Image

    with Image.open(io.BytesIO(path.read_bytes())) as im:
        im = im.convert("L")
        w, h = im.size
        # TCGplayer pads some scans to a square canvas; crop to the card's 63:88 portrait shape first.
        card_w = min(w, round(h * 63 / 88))
        left = (w - card_w) // 2
        area = im.crop((left, 0, left + card_w, round(h * band)))
        small = area.resize((HASH_SIZE + 1, HASH_SIZE), Image.LANCZOS)
        px = list(small.getdata())
    bits = 0
    for row in range(HASH_SIZE):
        for col in range(HASH_SIZE):
            left_px = px[row * (HASH_SIZE + 1) + col]
            bits = (bits << 1) | (left_px > px[row * (HASH_SIZE + 1) + col + 1])
    return bits


def distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


class HashCache:
    """dhash per (source, key), kept in .cache/images/hashes.json so a rerun does not reopen every image."""

    def __init__(self, path: Path = CACHE / "hashes.json"):
        self.path = path
        self.data: dict[str, int] = json.loads(path.read_text()) if path.exists() else {}

    def get(self, source: str, key: str, url: str, whole: bool = False) -> int | None:
        """The top-band hash, or the whole-card hash when whole is set."""
        k = f"{source}/{key}" + ("#whole" if whole else "")
        if k not in self.data:
            img = fetch(source, key, url)
            if img is None:
                return None
            self.data[k] = dhash(img, 1.0 if whole else TOP_BAND)
        return self.data[k]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data))


def _fetch_all() -> None:
    import tcgcsv

    cards = ROOT / "data" / "cards"
    jobs = [("bandai", p["id"], p["image"]) for f in sorted(cards.glob("*.json"))
            for c in json.loads(f.read_text(encoding="utf-8"))["cards"] for p in c["printings"]
            if p.get("source") == "bandai"]
    tcg_cache = ROOT / ".cache" / "tcgcsv"
    for g in tcgcsv.groups(tcg_cache):
        for p in tcgcsv.products(g["groupId"], tcg_cache):
            if p.is_single:
                jobs.append(("tcgplayer", str(p.product_id), TCGPLAYER_IMAGE.format(product_id=p.product_id)))
    # Interleave the two sources so neither host sees a long burst.
    bandai = [j for j in jobs if j[0] == "bandai"]
    tcg = [j for j in jobs if j[0] == "tcgplayer"]
    order = [j for pair in zip(bandai, tcg) for j in pair] + bandai[len(tcg):] + tcg[len(bandai):]
    misses = 0
    for i, (source, key, url) in enumerate(order, 1):
        # A run of misses means the host is refusing us, not that the images are missing.
        misses = 0 if fetch(source, key, url) else misses + 1
        if misses >= 20:
            raise SystemExit(f"20 misses in a row at {source}/{key}: stopping")
        if i % 250 == 0:
            print(f"{i}/{len(order)}", flush=True)
    print("done", len(order))


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        _fetch_all()
    else:
        sys.exit(__doc__)
