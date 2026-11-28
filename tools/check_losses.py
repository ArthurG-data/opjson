"""Compare the data with a git ref and fail when it lost more than a few of anything. Exits 1 on a loss.

    uv run python tools/check_losses.py [--base HEAD] [--allow-loss]

The importers rebuild what they own from the sites they read, so a page a site served wrong can drop a set's
cards, its logo or a run of artist credits without an error. Every other check passes on data that is only
missing something. This one counts what the data holds (the printings and sealed products of each set, the
printings with each field, overall and per set, each artist's credits, the releases with a logo or key art) and
compares each count with the same count at --base: a count that fell by more than MIN_LOSS and by more than
LOSS_SHARE of itself is a loss. A gain is never one.

Run it after a pipeline run, before committing (the default base is HEAD). CI runs it on a pull request against
the branch it targets. When a loss is meant (Bandai withdrew a card), --allow-loss prints it and exits 0, and
"[allow-loss]" in a pull request's title skips the CI check.
"""
from __future__ import annotations

import argparse
import collections
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import opjson

MIN_LOSS = 2
LOSS_SHARE = 0.05
# The fields of a printing whose absence nothing else notices.
PRINTING_FIELDS = ("artist", "finishes", "artOf", "twinOf", "block", "treatments", "promoTypes")
DATA = ("sets", "data/cards", "data/sealed")


def tally(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict]) -> collections.Counter:
    """{what: how many} for everything a loss could hide in."""
    count = collections.Counter()
    count["sets"] = len(sets)
    for s in sets:
        for r in s["releases"]:
            count[f"{r['language']} releases"] += 1
            for key in ("logo", "keyArt", "releaseDate"):
                count[f"{r['language']} releases with {key}"] += key in r
    for body in files.values():
        for card in body["cards"]:
            count["cards"] += 1
            for p in card["printings"]:
                lang = opjson.language(p)
                count[f"{lang} printings in {p['set']}"] += 1
                count[f"{lang} printings with a TCGplayer product"] += bool(
                    p.get("identifiers", {}).get("tcgplayerProductIds"))
                for key in PRINTING_FIELDS:
                    count[f"{lang} printings with {key}"] += key in p
                    count[f"{lang} printings in {p['set']} with {key}"] += key in p
                if "artist" in p:
                    # Limitless is read one artist at a time: a page served wrong drops one artist's credits.
                    count[f"printings credited to {p['artist']}"] += 1
    for body in sealed.values():
        for product in body["products"]:
            count[f"sealed products in {product['set']}"] += 1
            # A product whose contents become known moves out of "unknown": only the known ones are counted.
            count["sealed products with contents"] += product["contentsStatus"] != "unknown"
    return count


def losses(base: collections.Counter, now: collections.Counter) -> list[str]:
    """A message for each count that fell by more than MIN_LOSS and by more than LOSS_SHARE of itself."""
    out = []
    for what, was in sorted(base.items()):
        lost = was - now.get(what, 0)
        if lost > MIN_LOSS and lost > LOSS_SHARE * was:
            out.append(f"{what}: {was} -> {now.get(what, 0)} (lost {lost})")
    return out


def load_at(ref: str, into: Path) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    """The sets, cards and sealed products as committed at ref, unpacked into the directory into."""
    present = subprocess.run(["git", "ls-tree", "--name-only", ref, "--", *DATA], cwd=opjson.ROOT, check=True,
                             capture_output=True, text=True).stdout.split()
    archive = into / "base.tar"
    subprocess.run(["git", "archive", "--output", str(archive), ref, "--", *present], cwd=opjson.ROOT, check=True)
    with tarfile.open(archive) as tar:
        tar.extractall(into, filter="data")
    return (opjson.load_sets(into / "sets" / "sets.json"), opjson.load_cards(into / "data" / "cards"),
            opjson.load_sealed(into / "data" / "sealed"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD", help="the git ref to compare with (default HEAD)")
    ap.add_argument("--allow-loss", action="store_true", help="print the losses but exit 0")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="opjson-base-") as tmp:
        base = tally(*load_at(args.base, Path(tmp)))
    now = tally(opjson.load_sets(), opjson.load_cards(), opjson.load_sealed())
    found = losses(base, now)
    for message in found:
        print(message)
    print(f"{len(found)} losses against {args.base}")
    sys.exit(1 if found and not args.allow_loss else 0)


if __name__ == "__main__":
    main()
