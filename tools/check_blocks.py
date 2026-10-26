"""Read the block icon printed on each Bandai printing's image and correct the block the card list gives.

    uv run --group dev python tools/check_blocks.py

Bandai's card list states a block per printing, but it is not always the number printed on the card: every OP-05
card prints block 2, while the list gives 1 for most of them. The icon sits in the same corner on every frame, so
each image's icon is compared with reference icons averaged from sets whose list block nobody disputes (OP01-OP04
are block 1, and so on). Every icon is a disc with a digit on it, so the block is chosen on what the references do
not share (each reference minus their mean); the plain correlation only checks that the crop looks like an icon. A printing whose icon reads clearly as another block takes that block; an icon that does
not read clearly keeps the list's block and goes to review/blocks.json with the corrections. Run after images.py
fetch and before link_reprint_art; printings without a downloaded image are skipped and reported.

It then gives each Bandai set its block: the block of its own base printings (cards numbered in the set, not
reprints or parallels), X aside, when SET_SHARE of them agree. Blocks follow Bandai's release year, not a count of
boosters (block 4 is OP-13 to OP-15, block 5 starts at OP-16), so no booster number rule is applied. Promo and
other-product sets span blocks and get none; a
stamp set added later by import_tcgplayer has a parent and takes the parent's block where it is loaded.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

import images
import opjson

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "review" / "blocks.json"
SIZE = (600, 838)
CENTER = (555, 797)  # the icon's centre on a 600x838 Bandai image
HALF = 8  # half the crop's side: the digit and the disc just around it
SHIFT = 3  # the icon moves a pixel or two between frames
# Sets whose list block is the block printed on their own base printings (checked by eye on samples).
REFERENCE = {"1": ("OP01", "OP02", "OP03", "OP04"), "2": ("OP06", "OP07", "OP08"),
             "3": ("OP09", "OP10", "OP11", "OP12"), "4": ("OP13",), "5": ("OP16", "OP17"), "X": ("OP16", "OP17")}
MIN_SCORE = 0.8  # correlation with the nearest reference icon; correct corrections score 0.9+, an SP frame 0.61
SET_SHARE = 0.9  # of a set's own base printings that must share its block
MIN_MARGIN = 0.15  # lead of the best block over the runner-up; reference cards all lead by 0.2 or more


def _normalise(patch: np.ndarray) -> np.ndarray | None:
    """Zero-mean, unit-norm patch with the digit always darker than the disc behind it."""
    z = patch - np.median(patch)
    if np.mean(z ** 3) > 0:  # a few bright pixels on a dark disc: a light digit
        z = -z
    norm = np.linalg.norm(z)
    return z / norm if norm else None


def icon_patches(path: Path) -> dict[tuple[int, int], np.ndarray]:
    """The normalised icon crop at each shift around CENTER, keyed by the shift."""
    gray = np.asarray(Image.open(path).convert("L").resize(SIZE), dtype=np.float64)
    out = {}
    for dx in range(-SHIFT, SHIFT + 1):
        for dy in range(-SHIFT, SHIFT + 1):
            x, y = CENTER[0] + dx, CENTER[1] + dy
            p = _normalise(gray[y - HALF:y + HALF, x - HALF:x + HALF])
            if p is not None:
                out[(dx, dy)] = p
    return out


def read(patches: dict[tuple[int, int], np.ndarray], refs: dict[str, np.ndarray]) -> tuple[str, float, float]:
    """(block, how much the crop looks like an icon, the block's lead over the runner-up), taken at the shift
    where the best block scores highest."""
    mean = sum(refs.values()) / len(refs)
    distinct = {b: (r - mean) / np.linalg.norm(r - mean) for b, r in refs.items()}
    best = None
    for patch in patches.values():
        scores = sorted(((float(np.sum(patch * d)), b) for b, d in distinct.items()), reverse=True)
        if best is None or scores[0][0] > best[0]:
            looks = max(float(np.sum(patch * r)) for r in refs.values())
            best = (scores[0][0], scores[0][1], looks, scores[0][0] - scores[1][0])
    _, block, looks, margin = best
    return block, looks, margin


def build_references(printings: list[dict]) -> dict[str, np.ndarray]:
    sums: dict[str, np.ndarray] = {}
    counts = collections.Counter()
    for p in printings:
        block = p.get("block")
        if p["id"] != p["card"] or block not in REFERENCE or p["set"] not in REFERENCE[block]:
            continue
        path = images.path_for("bandai", p["id"])
        if not path.exists():
            continue
        patch = icon_patches(path)[(0, 0)]
        sums[block] = sums.get(block, 0) + patch
        counts[block] += 1
    missing = set(REFERENCE) - set(sums)
    if missing:
        raise SystemExit(f"no reference icons for block {sorted(missing)}: download the images first")
    return {b: s / np.linalg.norm(s) for b, s in sums.items()}


def set_blocks(sets: list[dict], printings: list[dict]) -> list[dict]:
    """Write each Bandai set's block onto it, or drop it; return the sets left without one, with why."""
    own = collections.defaultdict(collections.Counter)
    for p in printings:
        if p["source"] == "bandai" and opjson.language(p) == "en" and p["id"] == p["card"] and p["card"].split("-")[0] == p["set"].split("-")[0] \
                and p.get("block") not in (None, "X"):
            own[p["set"]][p["block"]] += 1
    left = []
    for s in sets:
        if not opjson.has_release(s, "en"):
            continue  # a Japanese-only set takes its block from import_bandai_ja
        s.pop("block", None)
        if s.get("source") == "tcgplayer" or s["type"] in ("promo", "box_set"):
            continue
        counts = own.get(s["id"])
        if not counts:
            left.append({"set": s["id"], "reason": "no base printings with a block"})
            continue
        block, n = counts.most_common(1)[0]
        if n < SET_SHARE * sum(counts.values()):
            left.append({"set": s["id"], "reason": "base printings disagree", "blocks": dict(counts)})
        else:
            s["block"] = block
    return left


def main() -> None:
    files = opjson.load_cards()
    flat = opjson.flatten(opjson.load_sets(), files)
    bandai = [p for p in flat["printings"].values() if p["source"] == "bandai" and opjson.language(p) == "en"]
    refs = build_references(bandai)
    reading: dict[str, tuple[str, float, float]] = {}
    no_image = []
    for p in bandai:
        path = images.path_for("bandai", p["id"])
        if path.exists():
            reading[p["id"]] = read(icon_patches(path), refs)
        else:
            no_image.append(p["id"])
    corrected, unclear = [], []
    for body in files.values():
        for card in body["cards"]:
            for p in card["printings"]:
                if p["id"] not in reading:
                    continue
                block, score, margin = reading[p["id"]]
                if score < MIN_SCORE or margin < MIN_MARGIN:
                    unclear.append({"printing": p["id"], "listed": p.get("block"), "read": block,
                                    "score": round(score, 3), "margin": round(margin, 3)})
                elif block != p.get("block"):
                    corrected.append({"printing": p["id"], "listed": p.get("block"), "printed": block,
                                      "score": round(score, 3), "evidence": p["image"]})
                    p["block"] = block
    sets = opjson.load_sets()
    no_block = set_blocks(sets, list(opjson.flatten(sets, files)["printings"].values()))
    opjson.SETS.write_text(json.dumps(sets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for stem, body in files.items():
        (opjson.CARDS / f"{stem}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                                                   encoding="utf-8")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps({"corrected": corrected, "unclear": unclear, "noImage": no_image, "setsWithoutBlock": no_block}, indent=2,
                                 ensure_ascii=False) + "\n", encoding="utf-8")
    by_set = collections.Counter(re.sub(r"-\d+.*$", "", c["printing"]) for c in corrected)
    print(f"{len(reading)} icons read: {len(corrected)} blocks corrected {dict(by_set.most_common(12))}; "
          f"{len(unclear)} unclear; {len(no_image)} printings without a downloaded image; "
          f"{sum('block' in s for s in sets)} sets given a block, {len(no_block)} left without")


if __name__ == "__main__":
    main()
