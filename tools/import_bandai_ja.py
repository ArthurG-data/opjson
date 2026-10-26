"""Add Bandai's Japanese card list (www.onepiece-cardgame.com) to sets/sets.json and data/cards.

    uv run python tools/crawl_bandai.py --language ja
    uv run python tools/import_bandai_ja.py

Each series on the Japanese list gives its set a "ja" release: the Japanese name, the release date its product
page states, and the series page. Each Japanese printing becomes a printing of its own, with Bandai's Japanese
id and "~ja" (OP01-001_p1~ja) and language "ja", and its card gets its Japanese name. A set or a card only the
Japanese list has is added with only those. Japan's OP-14, OP-15 and EB-04 are boosters of their own, which the
English list sells combined as OP14-EB04 and OP15-EB04, so they are Japanese-only sets.

Run it after every English tool: a Japanese printing takes the block and finishes of the English printing it
is the same printing as (same Bandai id, set and rarity), which check_blocks.py and import_tcgplayer.py settle
from the card images and TCGplayer's prices. A run first removes what an earlier run added, so a second run changes no file.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import bandai
import crawl_bandai
import import_bandai
import infer_finishes
import opjson

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "review" / "japanese.json"
CORRECTIONS = ROOT / "mappings" / "bandai_ja_corrections.json"
# The series pages that are not sets of their own, and the Japanese-only family deck set, which has no code.
SPECIAL_SERIES = {"550901": "P", "550801": "OTHER"}
NEW_SPECIAL_SERIES = {"550701": ("FAMILY", "box_set")}
_KINDS = (("プレミアムブースター", "premium_booster"), ("エクストラブースター", "extra_booster"),
          ("ブースターパック", "booster"), ("アルティメットデッキ", "ultra_deck"),
          ("スタートデッキEX", "starter_deck"), ("スタートデッキ", "starter_deck"))
# The facts a number's Japanese and English cards must agree on to be one card. Names and types are in each
# language's words, so they cannot be compared. A disagreement on attributes alone is one list misreading the
# icon, and goes to review; any other stops the import. A fact one card does not give (an English promo only
# TCGplayer sells has no cost or power) is not a disagreement.
SHARED_FACTS = ("category", "cost", "power", "counter", "life", "colors", "attributes")
# The share of a Japanese-only set's base printings that must agree on a block for the set to take it, as in
# check_blocks.py (which needs numpy, so it is not imported here).
SET_SHARE = 0.9
# A Japanese type is read into English when this share of the cards that carry it, in both languages, agree.
TYPE_SHARE = 0.9


def set_code(series: bandai.Series) -> str:
    if series.series_id in SPECIAL_SERIES:
        return SPECIAL_SERIES[series.series_id]
    if series.series_id in NEW_SPECIAL_SERIES:
        return NEW_SPECIAL_SERIES[series.series_id][0]
    return re.sub(r"^([A-Z]+)-(\d+)$", r"\1\2", series.code)


def release_name(series: bandai.Series) -> str:
    """The series title without its product line and its 【code】: ブースターパック 世界最強の戦士【OP-17】 is
    世界最強の戦士, as the English names drop BOOSTER PACK."""
    name = re.sub(r"\s*【[^】]+】\s*$", "", series.title)
    for prefix, _ in _KINDS:
        if name.startswith(prefix) and name[len(prefix):].strip():
            return name[len(prefix):].strip(" -")
    return name


def kind(series: bandai.Series) -> str:
    if series.series_id in NEW_SPECIAL_SERIES:
        return NEW_SPECIAL_SERIES[series.series_id][1]
    return next(k for prefix, k in _KINDS if series.title.startswith(prefix))


def product_pages(series: list[bandai.Series], printings: list[bandai.Printing]) -> dict[str, str]:
    """{series id: its product page}: the page its own printings link to, those whose card set ends with the
    series' 【code】. A series without a code has one only when all its printings link to the same page (the
    Family Deck Set does; promotion cards and other products link to many or none)."""
    out = {}
    for s in series:
        own = [p for p in printings if p.series_id == s.series_id]
        if s.code is None:
            links = collections.Counter(p.product for p in own)
            if len(links) == 1 and None not in links:
                out[s.series_id] = next(iter(links))
            continue
        links = collections.Counter(p.product for p in own if p.product and (p.card_set or "").endswith(f"【{s.code}】"))
        if links:
            out[s.series_id] = links.most_common(1)[0][0]
    return out


def release_dates(series: list[bandai.Series], printings: list[bandai.Printing],
                  refresh: bool = False) -> dict[str, str]:
    """{series id: release date}, from each series' product page (cached in .cache/bandai/ja)."""
    out = {}
    for series_id, url in product_pages(series, printings).items():
        date = bandai.parse_release_date(bandai.fetch(url, crawl_bandai.cache("ja"), refresh))
        if date:
            out[series_id] = date
    return out


def strip(sets: list[dict], files: dict[str, dict]) -> None:
    """Remove, in place, everything a run of this tool adds: ja releases, Japanese-only sets, ~ja printings,
    Japanese names and Japanese-only cards. Every card left gets names.en."""
    for s in sets:
        s["releases"] = [r for r in s["releases"] if r["language"] != "ja"]
    sets[:] = [s for s in sets if s["releases"]]
    for body in files.values():
        for card in body["cards"]:
            card["printings"] = [p for p in card["printings"] if opjson.language(p) != "ja"]
        body["cards"] = [_with_names(c, {"en": c["name"]}) for c in body["cards"] if c["printings"]]


def _with_names(card: dict, names: dict) -> dict:
    """The card with names set, placed right after name."""
    out = {}
    for k, v in card.items():
        if k != "names":
            out[k] = v
        if k == "name":
            out["names"] = names
    return out


def type_dictionary(pairs: list[tuple[list[str], list[str]]]) -> dict[str, str]:
    """{Japanese type: English type}, from (Japanese types, English types) of cards in both lists. A card whose
    two lists are the same length pairs them in order; a Japanese type is read only when TYPE_SHARE of its
    pairings agree."""
    seen: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for ja, en in pairs:
        if len(ja) == len(en):
            for j, e in zip(ja, en):
                seen[j][e] += 1
    out = {}
    for j, counts in seen.items():
        e, n = counts.most_common(1)[0]
        if n >= TYPE_SHARE * sum(counts.values()):
            out[j] = e
    return out


def _facts(p: bandai.Printing, corrections: dict[str, dict]) -> dict:
    facts = {"category": p.category, **{k: p.facts[k] for k in SHARED_FACTS if k != "category"}}
    return {**facts, **corrections.get(p.number, {}).get("facts", {})}


def _twin(en: dict | None, ja_set: str, rarity: str) -> dict | None:
    """The English printing a Japanese one is the same printing as: the one with its Bandai id, when it is in the
    same set (a combined English set such as OP14-EB04 counts for OP14 and EB04) and has the same rarity. Bandai
    numbers the _pN and _rN printings of each language on its own, so the same id can be another printing:
    OP01-001_p1 is the OP-01 parallel in English and a 25th-anniversary collection card in Japanese."""
    if en is None or en.get("rarity") != rarity or ja_set not in (en["set"], *en["set"].split("-")):
        return None
    return en


def _order(p: bandai.Printing) -> tuple:
    return ({None: 0, "p": 1, "r": 2}[p.variant_kind], p.variant_n or 0)


def merge(sets: list[dict], files: dict[str, dict], series: list[bandai.Series],
          printings: list[bandai.Printing], dates: dict[str, str], corrections: dict[str, dict]) -> dict:
    """Add the Japanese list to sets and files in place (after strip). Returns the review: numbers whose two
    lists give different attributes, Japanese types left untranslated, and Japanese printings given a finish by
    rule. Raises when a number's Japanese and English cards disagree on another fact."""
    strip(sets, files)
    by_set = {s["id"]: s for s in sets}
    code_of = {s.series_id: set_code(s) for s in series}
    seen: set[str] = set()
    by_number: dict[str, list[bandai.Printing]] = collections.defaultdict(list)
    for p in printings:
        if p.printing_id in seen:  # one printing listed on both the promo and the other-products page
            continue
        seen.add(p.printing_id)
        by_number[p.number].append(p)
    cards = {c["number"]: c for body in files.values() for c in body["cards"]}
    english = {p["id"]: p for c in cards.values() for p in c["printings"]}

    attributes, mismatches = [], []
    for number, group in sorted(by_number.items()):
        card = cards.get(number)
        if card is None:
            continue
        base = min(group, key=_order)
        ours = _facts(base, corrections)
        differ = {k: {"ja": ours[k], "en": card[k]} for k in SHARED_FACTS
                  if card.get(k) not in (None, []) and ours[k] not in (None, []) and ours[k] != card[k]}
        if set(differ) == {"attributes"}:
            attributes.append({"number": number, "en": card["name"], "ja": base.name, **differ["attributes"],
                               "images": {"en": next((p["image"] for p in card["printings"] if p["id"] == number),
                                                 card["printings"][0]["image"]), "ja": base.image}})
        elif differ:
            mismatches.append(f"{number}: {card['name']} / {base.name}: {differ}")
    if mismatches:
        raise ValueError("Japanese and English cards disagree:\n" + "\n".join(mismatches))
    types = type_dictionary([(min(g, key=_order).facts["types"], cards[n].get("types", []))
                             for n, g in by_number.items() if n in cards])

    # Sets: a ja release on each, and the Japanese-only ones after every other set, in the list's order.
    for s in series:
        code = code_of[s.series_id]
        release = {"language": "ja", "name": release_name(s), "releaseDate": dates.get(s.series_id),
                   "source": bandai.cardlist(s.series_id, "ja")}
        release = {k: v for k, v in release.items() if v is not None}
        if code in by_set:
            by_set[code]["releases"].append(release)
        else:
            by_set[code] = {"id": code, "type": kind(s), "releases": [release]}
            sets.append(by_set[code])

    # Cards and printings.
    untranslated = collections.Counter()
    ja_printings = []
    for number, group in sorted(by_number.items()):
        group = sorted(group, key=_order)
        base = group[0]
        card = cards.get(number)
        if card is None:
            names = [types.get(t) for t in base.facts["types"]]
            untranslated.update(t for t, e in zip(base.facts["types"], names) if e is None)
            facts = {**_facts(base, corrections), "types": [e or t for t, e in zip(base.facts["types"], names)]}
            card = {"number": number, "name": base.name, "names": {"ja": base.name},
                    **{k: v for k, v in facts.items() if v not in (None, [])}, "printings": []}
            body = files.setdefault(import_bandai.card_file(number), {"cards": []})
            body["cards"].append(card)
            body["cards"].sort(key=lambda c: c["number"])
            cards[number] = card
        else:
            card["names"]["ja"] = base.name
        for p in group:
            twin = _twin(english.get(p.printing_id), code_of[p.series_id], p.rarity)
            printing = {
                "id": p.printing_id + "~ja",
                "language": "ja",
                "set": code_of[p.series_id],
                "rarity": p.rarity,
                "block": twin.get("block") if twin else p.facts["block"],
                "image": p.image,
                "cardSet": p.card_set,
                "source": "bandai",
                "finishes": list(twin["finishes"]) if twin and twin.get("finishes") else None,
            }
            printing = {k: v for k, v in printing.items() if v is not None}
            card["printings"].append(printing)
            ja_printings.append(printing)
    inferred = infer_finishes.infer(ja_printings)

    # A Japanese-only booster or deck takes the block its own base printings agree on, as check_blocks does.
    for s in sets:
        if opjson.has_release(s, "en") or s["type"] in ("promo", "box_set"):
            continue
        blocks = collections.Counter(
            p["block"] for c in cards.values() for p in c["printings"]
            if p["set"] == s["id"] and p["id"] == c["number"] + "~ja" and p.get("block") not in (None, "X"))
        if blocks:
            block, n = blocks.most_common(1)[0]
            if n >= SET_SHARE * sum(blocks.values()):
                s_with_block = {"id": s["id"], "type": s["type"], "block": block, "releases": s["releases"]}
                s.clear()
                s.update(s_with_block)
    return {"attributeDisagreements": attributes,
            "untranslatedTypes": [{"type": t, "cards": n} for t, n in sorted(untranslated.items())],
            "inferredFinishes": inferred}


def main() -> None:
    series, printings = crawl_bandai.crawl(language="ja")
    dates = release_dates(series, printings)
    corrections = {k: v for k, v in json.loads(CORRECTIONS.read_text(encoding="utf-8")).items()
                   if not k.startswith("_")}
    sets, files = opjson.load_sets(), opjson.load_cards()
    review = merge(sets, files, series, printings, dates, corrections)
    opjson.SETS.write_text(json.dumps(sets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for stem, body in files.items():
        (opjson.CARDS / f"{stem}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                                                   encoding="utf-8")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    ja_sets = [s for s in sets if opjson.has_release(s, "ja")]
    flat = opjson.flatten(sets, files)
    ja = [p for p in flat["printings"].values() if opjson.language(p) == "ja"]
    ja_only_cards = [c for c in flat["cards"].values() if "en" not in c["names"]]
    print(f"{len(ja_sets)} Japanese sets ({sum(not opjson.has_release(s, 'en') for s in ja_sets)} Japanese-only, "
          f"{sum('releaseDate' in r for s in ja_sets for r in s['releases'] if r['language'] == 'ja')} dated), "
          f"{len(ja)} Japanese printings, {len(ja_only_cards)} Japanese-only cards, "
          f"{len(review['attributeDisagreements'])} numbers whose two lists give different attributes, "
          f"{len(review['untranslatedTypes'])} types left in Japanese")


if __name__ == "__main__":
    main()
