"""Give a finish to the Bandai printings TCGplayer does not price, where a rule says what it is.

    uv run python tools/infer_finishes.py

`finishes` come from TCGplayer's price subtypes (import_tcgplayer.py), so a printing TCGplayer does not sell or
price has none. A rule here fills that gap only for a kind of printing whose priced copies all share one finish.
Each run checks this first: if any priced printing of the kind disagrees, the tool stops and changes nothing.
Run after import_tcgplayer.py, which clears every finish before it writes TCGplayer's again. A printing this tool
fills is listed in review/inferred-finishes.json.

The one rule so far: a Bandai reprint (`_rN`) of a Common or Uncommon, with no art treatment, is nonfoil. Starter
decks reprint earlier cards this way, and TCGplayer sells most of them as the original card, not separately.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import opjson

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "review" / "inferred-finishes.json"
_REPRINT = re.compile(r"_r\d+$")


@dataclass(frozen=True)
class Rule:
    name: str
    applies: Callable[[dict], bool]
    finishes: tuple[str, ...]


def _plain_common_reprint(p: dict) -> bool:
    return (p["source"] == "bandai" and bool(_REPRINT.search(p["id"])) and p.get("rarity") in ("C", "UC")
            and not set(p.get("treatments") or []) - {"reprint"})


RULES = (Rule("plain_common_reprint", _plain_common_reprint, ("nonfoil",)),)


class RuleContradicted(Exception):
    pass


def infer(printings: list[dict], rules=RULES) -> list[dict]:
    """Fill the finishes of printings that have none, in place. Returns one review entry per printing filled.

    Raises RuleContradicted, before changing anything, when a priced printing a rule covers has other finishes."""
    for rule in rules:
        wrong = [p["id"] for p in printings
                 if rule.applies(p) and p.get("finishes") and tuple(sorted(p["finishes"])) != rule.finishes]
        if wrong:
            raise RuleContradicted(f"{rule.name}: {len(wrong)} priced printings disagree, e.g. {wrong[:5]}")
    filled = []
    for p in printings:
        if p.get("finishes"):
            continue
        rule = next((r for r in rules if r.applies(p)), None)
        if rule:
            p["finishes"] = list(rule.finishes)
            filled.append({"printing": p["id"], "finishes": list(rule.finishes), "rule": rule.name})
    return filled


def main() -> None:
    files = opjson.load_cards()
    printings = [p for body in files.values() for card in body["cards"] for p in card["printings"]]
    filled = infer(printings)
    for stem, body in files.items():
        (opjson.CARDS / f"{stem}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                                                   encoding="utf-8")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps({"inferred": filled}, indent=2) + "\n", encoding="utf-8")
    left = sum(not p.get("finishes") for p in printings)
    print(f"{len(filled)} printings given a finish by rule; {left} still have none")


if __name__ == "__main__":
    main()
