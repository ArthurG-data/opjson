"""Write the counts paragraph of the README from the data, so it never goes stale.

    uv run --group dev python tools/readme_counts.py

The paragraph that starts with "The data holds " (or the older "Release ") is replaced with counts taken from
sets/, data/ and sealed/. It names no release version. Nothing is printed when the README is already current.
"""
from __future__ import annotations

import re
import textwrap

import opjson

README = opjson.ROOT / "README.md"
PARAGRAPH = re.compile(r"^(?:The data holds |Release )[^\n]*(?:\n[^\n]+)*", re.MULTILINE)


def paragraph(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict]) -> str:
    """The counts as one unwrapped line."""
    cards = [c for body in files.values() for c in body["cards"]]
    printings = [p for c in cards for p in c["printings"]]
    products = [p for body in sealed.values() for p in body["products"]]
    langs = [{r["language"] for r in s["releases"]} for s in sets]
    n = {
        "sets": len(sets),
        "cards": len(cards),
        "printings": len(printings),
        "sealed": len(products),
        "ja_sets": sum("ja" in ls for ls in langs),
        "ja_printings": sum(opjson.language(p) == "ja" for p in printings),
        "ja_sealed": sum(p.get("language") == "ja" for p in products),
        "ja_only_sets": sum(ls == {"ja"} for ls in langs),
        "ja_only_cards": sum(all(opjson.language(p) == "ja" for p in c["printings"]) for c in cards),
    }
    f = {k: f"{v:,}" for k, v in n.items()}
    return (f"The data holds {f['sets']} sets, {f['cards']} cards, {f['printings']} printings and {f['sealed']} "
            f"sealed products. {f['ja_sets']} sets have a Japanese release, {f['ja_printings']} printings and "
            f"{f['ja_sealed']} sealed products are Japanese, and {f['ja_only_sets']} sets and {f['ja_only_cards']} "
            f"cards are only on Bandai's Japanese list.")


def rewrite(readme: str, text: str) -> str:
    """Replace the counts paragraph, wrapped to the README's width. Raises ValueError when it is missing."""
    if not PARAGRAPH.search(readme):
        raise ValueError("README.md has no paragraph starting with 'The data holds ' or 'Release '")
    return PARAGRAPH.sub(lambda _: textwrap.fill(text, width=115), readme, count=1)


def main() -> None:
    old = README.read_text(encoding="utf-8")
    new = rewrite(old, paragraph(opjson.load_sets(), opjson.load_cards(), opjson.load_sealed()))
    if new != old:
        opjson.write_atomic(README, new)


if __name__ == "__main__":
    main()
