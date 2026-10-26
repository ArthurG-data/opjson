"""Load, validate and flatten opjson sets and cards."""
from __future__ import annotations

import collections
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SETS = ROOT / "sets" / "sets.json"
CARDS = ROOT / "data" / "cards"
SEALED = ROOT / "data" / "sealed"
SCHEMAS = ROOT / "schema"


def _schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / name).read_text(encoding="utf-8")), format_checker=FormatChecker())


def language(p: dict) -> str:
    """A printing's language: "ja" for one from Bandai's Japanese card list, else "en"."""
    return p.get("language", "en")


def has_release(s: dict, lang: str) -> bool:
    return any(r["language"] == lang for r in s["releases"])


def english_set_ids(sets: list[dict]) -> set[str]:
    """The sets with an English release: the only ones TCGplayer's groups are matched against."""
    return {s["id"] for s in sets if has_release(s, "en")}


def set_aside_japanese(files: dict[str, dict]) -> dict[str, list]:
    """Take the Japanese printings, and the cards that have no other, out of files in place, so that a tool that
    rebuilds the English printings never sees them. restore_japanese puts them back."""
    aside: dict[str, list] = {}
    for stem, body in files.items():
        kept = []
        for card in body["cards"]:
            ja = [p for p in card["printings"] if language(p) == "ja"]
            if ja:
                card["printings"] = [p for p in card["printings"] if language(p) != "ja"]
                aside.setdefault(stem, []).append((card if not card["printings"] else None, card["number"], ja))
            if card["printings"]:
                kept.append(card)
        body["cards"] = kept
    return aside


def restore_japanese(files: dict[str, dict], aside: dict[str, list]) -> None:
    """Put back what set_aside_japanese took. A Japanese-only card that has since gained English printings
    (TCGplayer minted one) is merged into that card. Each file's cards stay in number order."""
    for stem, entries in aside.items():
        body = files.setdefault(stem, {"cards": []})
        by_number = {c["number"]: c for c in body["cards"]}
        for whole, number, ja in entries:
            card = by_number.get(number)
            if card is None:
                card = whole
                card["printings"] = []
                body["cards"].append(card)
                by_number[number] = card
            elif whole is not None and "ja" in whole.get("names", {}):
                card.setdefault("names", {"en": card["name"]})["ja"] = whole["names"]["ja"]
            card["printings"] += ja
        body["cards"].sort(key=lambda c: c["number"])


def load_sets(path: Path = SETS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cards(cards_dir: Path = CARDS) -> dict[str, dict]:
    """{file stem: file body}, sorted by stem."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(cards_dir.glob("*.json"))}


def load_sealed(sealed_dir: Path = SEALED) -> dict[str, dict]:
    """{set id: file body}, sorted by set id."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(sealed_dir.glob("*.json"))}


def validate(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict] | None = None) -> list[str]:
    """Every problem found offline, one message each. Empty when the data is valid."""
    sealed = sealed or {}
    errors = [f"sets.json: {e.json_path}: {e.message}" for e in _schema("sets.schema.json").iter_errors(sets)]
    card_schema = _schema("cards.schema.json")
    for stem, body in files.items():
        errors += [f"cards/{stem}.json: {e.json_path}: {e.message}" for e in card_schema.iter_errors(body)]
    sealed_schema = _schema("sealed.schema.json")
    for stem, body in sealed.items():
        errors += [f"sealed/{stem}.json: {e.json_path}: {e.message}" for e in sealed_schema.iter_errors(body)]
    if errors:
        return errors  # the checks below assume the documents have the right shape

    set_ids = collections.Counter(s["id"] for s in sets)
    releases = {s["id"]: {r["language"] for r in s["releases"]} for s in sets}
    for s in sets:
        langs = collections.Counter(r["language"] for r in s["releases"])
        errors += [f"sets.json: set {s['id']} has {n} {lang} releases" for lang, n in langs.items() if n > 1]
    errors += [f"sets.json: set {s} is listed {n} times" for s, n in set_ids.items() if n > 1]
    parent_of = {s["id"]: s.get("parent") for s in sets}
    for s in sets:
        if "parent" in s and s["parent"] not in set_ids:
            errors.append(f"sets.json: set {s['id']} has parent {s['parent']}, which is not a set")
        seen, cur = {s["id"]}, s.get("parent")
        while cur:
            if cur in seen:
                errors.append(f"sets.json: set {s['id']} is its own ancestor")
                break
            seen.add(cur)
            cur = parent_of.get(cur)
    group_owner: dict[int, str] = {}
    for s in sets:
        for gid in s.get("tcgplayerGroupIds", []):
            if gid in group_owner:
                errors.append(f"sets.json: TCGplayer group {gid} is on {group_owner[gid]} and {s['id']}")
            group_owner[gid] = s["id"]

    numbers = collections.Counter()
    printing_ids: dict[str, str] = {}
    product_owner: dict[int, str] = {}
    art_refs = []
    for stem, body in files.items():
        for card in body["cards"]:
            number = card["number"]
            numbers[number] += 1
            if card["name"] != card["names"].get("en", card["names"].get("ja")):
                errors.append(f"card {number}: name must be its English name, else its Japanese one")
            if number.split("-", 1)[0] != stem:
                errors.append(f"cards/{stem}.json: card {number} belongs in cards/{number.split('-', 1)[0]}.json")
            for p in card["printings"]:
                pid = p["id"]
                if pid in printing_ids:
                    errors.append(f"printing {pid} is listed twice ({printing_ids[pid]} and {number})")
                printing_ids[pid] = number
                if not (pid == number or pid.startswith(number + "_") or pid.startswith(number + "~")):
                    errors.append(f"printing {pid} is filed under card {number}")
                if p["set"] not in set_ids:
                    errors.append(f"printing {pid}: set {p['set']} is not in sets.json")
                if (p["source"] == "bandai") == ("~tcg" in pid):
                    errors.append(f"printing {pid}: a minted id (with ~tcg) must have source tcgplayer, and only it")
                lang = language(p)
                if pid.endswith("~ja") != (lang == "ja"):
                    errors.append(f"printing {pid}: a ~ja id must have language ja, and only it")
                if lang not in card["names"]:
                    errors.append(f"card {number}: has a {lang} printing ({pid}) but no {lang} name")
                if p["set"] in releases and lang not in releases[p["set"]]:
                    errors.append(f"printing {pid}: set {p['set']} has no {lang} release")
                if lang == "ja" and p.get("identifiers", {}).get("tcgplayerProductIds"):
                    errors.append(f"printing {pid}: a Japanese printing has no TCGplayer product")
                for product_id in p.get("identifiers", {}).get("tcgplayerProductIds", []):
                    if product_id in product_owner:
                        errors.append(f"TCGplayer product {product_id} is on {product_owner[product_id]} and {pid}")
                    product_owner[product_id] = pid
                if "artOf" in p:
                    art_refs.append((pid, p["artOf"]))
                if p["source"] == "tcgplayer" and not p.get("identifiers", {}).get("tcgplayerProductIds"):
                    errors.append(f"printing {pid}: a TCGplayer-only printing needs its TCGplayer product id")
    errors += [f"card {n} is listed {c} times" for n, c in numbers.items() if c > 1]
    art_of = dict(art_refs)
    for pid, art in art_refs:
        if art not in printing_ids:
            errors.append(f"printing {pid}: artOf {art} is not a printing")
        elif "~" in art:
            errors.append(f"printing {pid}: artOf must name a Bandai printing, not {art}")
        elif art in art_of:
            errors.append(f"printing {pid}: artOf {art} itself shares another printing's art; name {art_of[art]}")

    products = collections.Counter(p["id"] for body in sealed.values() for p in body["products"])
    errors += [f"sealed product id {i} is used {n} times" for i, n in products.items() if n > 1]
    for stem, body in sealed.items():
        for p in body["products"]:
            where = f"sealed/{stem}.json: {p['id']}"
            if p["set"] != stem:
                errors.append(f"{where}: filed under {stem} but its set is {p['set']}")
            if p["set"] not in set_ids:
                errors.append(f"{where}: set {p['set']} is not in sets.json")
            for product_id in p.get("identifiers", {}).get("tcgplayerProductIds", []):
                if product_id in product_owner:
                    errors.append(f"TCGplayer product {product_id} is on {product_owner[product_id]} and {p['id']}")
                product_owner[product_id] = p["id"]
            contents = p["contents"]
            for item in contents.get("sealed", []):
                if item["product"] not in products or item["product"] == p["id"]:
                    errors.append(f"{where}: holds {item['product']}, which is not another sealed product")
            for item in contents.get("cards", []):
                if item["printing"] not in printing_ids:
                    errors.append(f"{where}: holds printing {item['printing']}, which does not exist")
            for item in contents.get("pool", []):
                if item["set"] not in set_ids:
                    errors.append(f"{where}: pool set {item['set']} is not in sets.json")
            if p["contentsStatus"] == "unknown" and any(contents.values()):
                errors.append(f"{where}: lists contents but says contentsStatus unknown")
            if p["contentsStatus"] == "complete" and any("count" not in i for k in ("sealed", "cards")
                                                       for i in contents.get(k, [])):
                errors.append(f"{where}: complete contents need a count on every item")
    return errors


def flatten(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict] | None = None) -> dict[str, dict]:
    """{"sets": {id: set}, "cards": {number: card without printings}, "printings": {id: printing + card},
    "products": {id: sealed product}}."""
    out = {"sets": {s["id"]: s for s in sets}, "cards": {}, "printings": {},
           "products": {p["id"]: p for body in (sealed or {}).values() for p in body["products"]}}
    for body in files.values():
        for card in body["cards"]:
            out["cards"][card["number"]] = {k: v for k, v in card.items() if k != "printings"}
            for p in card["printings"]:
                out["printings"][p["id"]] = {"card": card["number"], **p}
    return out
