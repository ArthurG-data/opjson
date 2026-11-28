"""The English twin of a Japanese printing: the English printing it is the same printing as.

Bandai numbers the _pN and _rN printings of each language on its own, so OP01-001_p1~ja need not be the twin of
OP01-001_p1. A Japanese printing's `twinOf` comes from, in this order:

1. mappings/twin_corrections.json, kept by hand. A null value says the printing has no English twin.
2. The rule import_bandai_ja._twin applies: the English printing with the same Bandai id, in the same set, with the
   same rarity.
3. data/twins.json, the image matches tools/link_twins.py settled.
"""
from __future__ import annotations

import json
from pathlib import Path

import opjson

SETTLED = opjson.ROOT / "data" / "twins.json"
CORRECTIONS = opjson.ROOT / "mappings" / "twin_corrections.json"


def load_settled(path: Path = SETTLED) -> dict[str, dict]:
    """{Japanese printing id: {"en": English printing id, "distance": bits}}."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_corrections(path: Path = CORRECTIONS) -> dict[str, str | None]:
    """{Japanese printing id: English printing id, or None for no twin}. Keys starting with _ are notes."""
    if not path.exists():
        return {}
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def twin_of(ja_id: str, rule_one: str | None, settled: dict[str, dict],
            corrections: dict[str, str | None]) -> str | None:
    """The English printing id the Japanese printing ja_id is the twin of, or None."""
    if ja_id in corrections:
        return corrections[ja_id]
    if rule_one is not None:
        return rule_one
    return settled.get(ja_id, {}).get("en")
