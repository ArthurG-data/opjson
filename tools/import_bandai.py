"""Write sets/sets.json and data/cards/<set>.json from the official English card list.

    uv run python tools/import_bandai.py

A card is a card number (OP01-006) and holds the facts every printing of it shares. A printing is one
Bandai printing id (OP01-006_p1) on one series page. Printings that only TCGplayer sells (pre-release
stamps and most promos) are added by import_tcgplayer.py, which keeps the printings written here.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import bandai
import crawl_bandai

ROOT = Path(__file__).resolve().parents[1]
SETS = ROOT / "sets" / "sets.json"
CARDS = ROOT / "data" / "cards"
CORRECTIONS = ROOT / "mappings" / "bandai_corrections.json"

# Facts that belong to the card: every printing of a number must agree on them.
CARD_FACTS = ("name", "category", "cost", "power", "counter", "life", "attributes", "colors", "types")
# The two series pages that are not sets of their own.
SPECIAL_SERIES = {"569901": ("P", "promo", "Promotion Cards"), "569801": ("OTHER", "box_set", "Other Product Cards")}
_KINDS = (("PREMIUM BOOSTER", "premium_booster"), ("EXTRA BOOSTER", "extra_booster"),
          ("BOOSTER PACK", "booster"), ("ULTRA DECK", "ultra_deck"), ("STARTER DECK", "starter_deck"))


def set_code(series: bandai.Series) -> str:
    """opjson's set id for a series: its bracketed code without the hyphen (OP-01 -> OP01, PRB-01 -> PRB01).
    A combined code keeps its own hyphen (OP14-EB04)."""
    if series.series_id in SPECIAL_SERIES:
        return SPECIAL_SERIES[series.series_id][0]
    return re.sub(r"^([A-Z]+)-(\d+)$", r"\1\2", series.code)


def set_entry(series: bandai.Series) -> dict:
    if series.series_id in SPECIAL_SERIES:
        code, kind, name = SPECIAL_SERIES[series.series_id]
    else:
        code = set_code(series)
        kind = next(k for prefix, k in _KINDS if series.title.upper().startswith(prefix))
        name = re.sub(r"\s*\[[^\]]+\]\s*$", "", series.title)
        name = re.sub(r"^(PREMIUM BOOSTER|EXTRA BOOSTER|BOOSTER PACK|ULTRA DECK|STARTER DECK EX|STARTER DECK)\s*",
                      "", name).strip(" -")
    return {"id": code, "type": kind, "bandaiSeriesId": series.series_id,
            "releases": [{"language": "en", "name": name,
                          "source": bandai.CARDLIST.format(series=series.series_id)}]}


def card_file(number: str) -> str:
    """The data/cards file a card number lives in: its prefix (OP01-006 -> OP01, P-001 -> P)."""
    return number.split("-", 1)[0]


def build(series: list[bandai.Series], printings: list[bandai.Printing],
          corrections: dict[str, dict]) -> tuple[list[dict], dict[str, dict]]:
    """(sets, {file: {"cards": [...]}}). A card takes its facts from its base printing, then from
    corrections. Raises when printings of a number disagree on a fact that corrections does not settle."""
    code_of = {s.series_id: set_code(s) for s in series}
    sets = [set_entry(s) for s in series]
    seen: set[str] = set()
    by_number: dict[str, list[bandai.Printing]] = collections.defaultdict(list)
    for p in printings:
        if p.printing_id in seen:  # one printing listed on both the promo and the other-products page
            continue
        seen.add(p.printing_id)
        by_number[p.number].append(p)
    files: dict[str, dict] = collections.defaultdict(lambda: {"cards": []})
    conflicts = []
    for number in sorted(by_number):
        group = by_number[number]
        base = min(group, key=_printing_order)
        fixed = corrections.get(number, {}).get("facts", {})
        facts = {}
        for key in CARD_FACTS:
            values = {json.dumps(_fact(p, key)) for p in group}
            if len(values) > 1 and key not in fixed:
                conflicts.append(f"{number}: {key} differs between printings: {sorted(values)}")
            facts[key] = fixed.get(key, _fact(base, key))
        card = {"number": number, **{k: v for k, v in facts.items() if v not in (None, [])}, "printings": [
            {k: v for k, v in {
                "id": p.printing_id,
                "set": code_of[p.series_id],
                "rarity": p.rarity,
                "block": p.facts["block"],
                "image": p.image,
                "source": "bandai",
            }.items() if v is not None}
            for p in sorted(group, key=_printing_order)]}
        files[card_file(number)]["cards"].append(card)
    if conflicts:
        raise ValueError("card facts disagree:\n" + "\n".join(conflicts))
    return sets, dict(files)


def _fact(p: bandai.Printing, key: str):
    return getattr(p, key) if key in ("name", "category") else p.facts[key]


def _printing_order(p: bandai.Printing) -> tuple:
    return ({None: 0, "p": 1, "r": 2}[p.variant_kind], p.variant_n or 0)


def main() -> None:
    series, printings = crawl_bandai.crawl()
    corrections = {k: v for k, v in json.loads(CORRECTIONS.read_text(encoding="utf-8")).items()
                   if not k.startswith("_")}
    sets, files = build(series, printings, corrections)
    SETS.parent.mkdir(parents=True, exist_ok=True)
    SETS.write_text(json.dumps(sets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    CARDS.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (CARDS / f"{name}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(sets)} sets, {sum(len(f['cards']) for f in files.values())} cards, "
          f"{sum(len(c['printings']) for f in files.values() for c in f['cards'])} printings in {len(files)} files")


if __name__ == "__main__":
    main()
