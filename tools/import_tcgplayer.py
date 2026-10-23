"""Attach TCGplayer product ids to printings, and add the printings only TCGplayer sells.

    uv run --group dev python tools/import_tcgplayer.py

Reads data/cards (written by import_bandai.py), TCGCSV category 68 and the cached card images
(tools/images.py fetch). A product is matched to a Bandai printing only when the card number agrees and
the two images agree: the hash distance is at most ACCEPT and the next-best candidate is at least MARGIN
further away. A product that cannot be matched that way goes to review/tcgplayer-68.json, never into a guess.

Pre-release, release-event and anniversary groups hold stamped copies of a set's printings, and most of
TCGplayer's promos are not on Bandai's card list. Those products become printings of their own, with an id
minted from the card number and the product id (OP02-013~tcg123456), and `artOf` naming the Bandai
printing whose art they carry when the images say so.
"""
from __future__ import annotations

import collections
import itertools
import json
import re
from dataclasses import dataclass
from pathlib import Path

import images
import tcgcsv

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "data" / "cards"
SETS = ROOT / "sets" / "sets.json"
TAGS = ROOT / "mappings" / "tcgplayer_tags.json"
REVIEW = ROOT / "review" / "tcgplayer-68.json"
CACHE = ROOT / ".cache" / "tcgcsv"

# Hash distances are out of 256 bits. Matching scans differ by under 10; different art by over 60.
ACCEPT = 28
MARGIN = 20

# TCGplayer groups that are not one Bandai set. Stamp groups hold stamped copies of their parent's printings.
SPECIAL_GROUPS = {
    "OP-PR": {"role": "promo", "set": "P"},
    "OP-DD": {"role": "promo", "set": "OP-DD", "type": "starter_deck", "name": "One Piece Demo Deck Cards"},
    "OP-RP": {"role": "promo", "set": "OP-RP", "type": "promo", "name": "Revision Pack Cards"},
    "OP-CS": {"role": "promo", "set": "OP-CS", "type": "box_set", "name": "One Piece Collection Sets"},
    "LT-01": {"role": "promo", "set": "LT01", "type": "starter_deck", "name": "Learn Together Deck Set"},
    "SD01": {"role": "promo", "set": "SD01", "type": "starter_deck", "name": "Set Sail Deck Set"},
}
_STAMP = re.compile(r"^(?P<parent>[A-Z]+-?\d+) (?P<kind>PRE|RE|ANN)$")
# Stamp groups name the booster alone; Bandai files these sets under a combined code.
STAMP_PARENT_ALIAS = {"OP14": "OP14-EB04", "OP15": "OP15-EB04"}
STAMP_PROMO = {"PRE": ("prerelease", "event"), "RE": ("release", "event"), "ANN": ("anniversary", "anniversary")}
DON = "DON"
# TCGCSV price subtypes for category 68, as card_catalog.card_finished codes.
FINISHES = {"Normal": "nonfoil", "Foil": "foil"}
# TCGplayer rarity codes that Bandai spells differently, or that mean "no rarity".
TCGPLAYER_RARITY = {"PR": "P", "None": None, "": None}


@dataclass
class Match:
    product: tcgcsv.Product
    printing_id: str | None
    distance: int | None
    evidence: str  # "image", "image-only-candidate", or why it is unmatched


def normalise_set(abbreviation: str) -> str:
    return re.sub(r"^([A-Z]+)-(\d+)$", r"\1\2", abbreviation)


def _stamp_parent(abbreviation: str) -> str:
    code = normalise_set(abbreviation)
    return STAMP_PARENT_ALIAS.get(code, code)


def group_roles(groups: list[dict], set_ids: set[str]) -> dict[int, dict]:
    """groupId -> {"role": "set"|"stamp"|"promo"|"pending", "set": opjson set id, ...}."""
    roles = {}
    for g in groups:
        abbr = g["abbreviation"]
        if abbr in SPECIAL_GROUPS:
            roles[g["groupId"]] = dict(SPECIAL_GROUPS[abbr])
        elif (m := _STAMP.match(abbr)) and _stamp_parent(m.group("parent")) in set_ids:
            parent = _stamp_parent(m.group("parent"))
            promo, category = STAMP_PROMO[m.group("kind")]
            roles[g["groupId"]] = {"role": "stamp", "set": f"{parent}-{m.group('kind')}", "parent": parent,
                                   "name": g["name"], "promo": promo, "category": category}
        elif normalise_set(abbr) in set_ids:
            roles[g["groupId"]] = {"role": "set", "set": normalise_set(abbr)}
        else:
            # A set TCGplayer lists before Bandai's English card list does (pre-orders): wait for Bandai's ids.
            roles[g["groupId"]] = {"role": "pending", "set": normalise_set(abbr)}
    return roles


def classify_tags(tags: list[str], rules: list[dict]) -> tuple[list[str], list[tuple[str, str]]]:
    """(treatments, [(promo, category)]) for a product's name tags, each sorted and without repeats."""
    treatments, promos = set(), set()
    for tag in tags:
        for rule in rules:
            if re.search(rule["match"], tag, re.I):
                if "treatment" in rule:
                    treatments.add(rule["treatment"])
                if "promo" in rule:
                    promos.add((rule["promo"], rule["category"]))
    return sorted(treatments), sorted(promos)


def assign(products: list[tcgcsv.Product], candidates: list[str],
           dist: dict[tuple[int, str], int | None]) -> list[Match]:
    """Match products to candidate printings by image. Every product appears once in the result."""
    usable = list(candidates)
    if not usable:
        return [Match(p, None, None, "no Bandai printing of this number in the set") for p in products]

    def cost(i: int, j: int) -> int:
        d = dist.get((products[i].product_id, usable[j]))
        return 10_000 if d is None else d

    # Exact minimum-cost assignment when the cluster is small (it nearly always is: a handful of variants
    # of one card in one set); greedy by distance otherwise.
    if len(products) <= 7 and len(usable) <= 7:
        best: tuple[int, dict[int, int]] | None = None
        if len(products) <= len(usable):
            options = (dict(enumerate(perm)) for perm in itertools.permutations(range(len(usable)), len(products)))
        else:
            options = ({i: j for j, i in enumerate(perm)}
                       for perm in itertools.permutations(range(len(products)), len(usable)))
        for option in options:
            total = sum(cost(i, j) for i, j in option.items())
            if best is None or total < best[0]:
                best = (total, option)
        pairs = best[1]
    else:
        pairs, taken = {}, set()
        for (i, j) in sorted(((i, j) for i in range(len(products)) for j in range(len(usable))),
                             key=lambda ij: dist.get((products[ij[0]].product_id, usable[ij[1]])) or 10_000):
            if i not in pairs and j not in taken:
                pairs[i] = j
                taken.add(j)
    out = []
    for i, p in enumerate(products):
        if i not in pairs:
            out.append(Match(p, None, None, "more products than Bandai printings"))
            continue
        cand = usable[pairs[i]]
        d = dist.get((p.product_id, cand))
        if d is None:
            out.append(Match(p, None, None, f"no image to compare with {cand}"))
            continue
        others = [dist.get((p.product_id, c)) for c in usable if c != cand]
        others = [o for o in others if o is not None]
        runner_up = min(others) if others else None
        if d > ACCEPT:
            out.append(Match(p, None, d, f"best candidate {cand} is {d} bits away (accept <= {ACCEPT})"))
        elif runner_up is not None and runner_up - d < MARGIN:
            out.append(Match(p, None, d, f"{cand} at {d} bits is not clear of the next candidate at {runner_up}"))
        else:
            out.append(Match(p, cand, d, "image" if others else "image-only-candidate"))
    return out


def main() -> None:
    rules = json.loads(TAGS.read_text(encoding="utf-8"))["rules"]
    sets = json.loads(SETS.read_text(encoding="utf-8"))
    set_ids = {s["id"] for s in sets}
    files = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(CARDS.glob("*.json"))}
    cards = {c["number"]: c for body in files.values() for c in body["cards"]}
    for c in cards.values():
        for p in c["printings"]:
            for key in ("identifiers", "tcgplayer", "finishes", "treatments", "promoTypes"):
                p.pop(key, None)
        # Printings minted by a previous run are rebuilt from scratch.
        c["printings"] = [p for p in c["printings"] if p["source"] == "bandai"]
    printings = {p["id"]: (c["number"], p) for c in cards.values() for p in c["printings"]}

    groups = tcgcsv.groups(CACHE)
    roles = group_roles(groups, set_ids)
    hashes = images.HashCache()

    def bandai_hash(pid: str) -> int | None:
        return hashes.get("bandai", pid, printings[pid][1]["image"])

    def tcg_hash(p: tcgcsv.Product) -> int | None:
        return hashes.get("tcgplayer", str(p.product_id), images.TCGPLAYER_IMAGE.format(product_id=p.product_id))

    def distances(products, candidates):
        out = {}
        for p in products:
            th = tcg_hash(p)
            for c in candidates:
                bh = bandai_hash(c)
                out[(p.product_id, c)] = None if th is None or bh is None else images.distance(th, bh)
        return out

    by_set_number = collections.defaultdict(list)
    for pid, (number, p) in printings.items():
        by_set_number[(p["set"], number)].append(pid)

    matches: list[tuple[dict, Match]] = []
    review, pending = [], []
    claimed: dict[str, int] = {}
    singles = [(g, p) for g in groups for p in tcgcsv.products(g["groupId"], CACHE) if p.is_single]
    finishes: dict[int, set[str]] = collections.defaultdict(set)
    for g in groups:
        for row in tcgcsv.prices(g["groupId"], CACHE):
            finishes[row["productId"]].add(FINISHES[row["subTypeName"]])

    # Pass 1: products in a Bandai set's own group.
    clusters = collections.defaultdict(list)
    for g, p in singles:
        role = roles[g["groupId"]]
        if role["role"] == "set" and p.number:
            clusters[(role["set"], p.number)].append(p)
    for (set_id, number), products in sorted(clusters.items()):
        candidates = sorted(by_set_number.get((set_id, number), []))
        for m in assign(products, candidates, distances(products, candidates)):
            matches.append(({"set": set_id, "role": "set"}, m))
            if m.printing_id:
                claimed[m.printing_id] = m.product.product_id

    # Pass 2: the rest. Promos are matched against Bandai printings nobody claimed; stamps become their own
    # printings, carrying the art of the parent-set printing they stamp.
    leftovers = [(roles[g["groupId"]], p) for g, p in singles
                 if roles[g["groupId"]]["role"] != "set" or not p.number]
    leftovers += [({"set": r["set"], "role": "set"}, m.product) for r, m in matches if not m.printing_id]
    matches = [(r, m) for r, m in matches if m.printing_id]
    minted = []
    for role, p in leftovers:
        if role["role"] == "pending":
            pending.append({"productId": p.product_id, "name": p.name, "set": role["set"], "number": p.number})
            continue
        number = p.number or DON
        if role["role"] == "stamp":
            pool = sorted(by_set_number.get((role["parent"], number), []))
        else:
            pool = sorted(pid for pid, (n, _) in printings.items() if n == number and pid not in claimed)
        dist = distances([p], pool)
        scored = sorted((d, c) for (_, c), d in dist.items() if d is not None)
        art = scored[0][1] if scored and scored[0][0] <= ACCEPT and (
            len(scored) == 1 or scored[1][0] - scored[0][0] >= MARGIN) else None
        if role["role"] == "promo" and art and art not in claimed:
            claimed[art] = p.product_id
            matches.append((role, Match(p, art, scored[0][0], "image")))
            continue
        if role["role"] == "set":
            review.append({"productId": p.product_id, "name": p.name, "set": role["set"], "number": p.number,
                           "reason": "no Bandai printing of this number in its set matches the image",
                           "closest": [{"printing": c, "distance": d} for d, c in scored[:3]]})
            continue
        minted.append((role, p, art, scored[0][0] if art else None))

    # Write identifiers onto matched Bandai printings.
    for role, m in matches:
        _, printing = printings[m.printing_id]
        treatments, promos = classify_tags(m.product.base_name_and_tags()[1], rules)
        printing.setdefault("identifiers", {}).setdefault("tcgplayerProductIds", []).append(m.product.product_id)
        _add_finishes(printing, finishes[m.product.product_id])
        printing["tcgplayer"] = {"name": m.product.name, "match": m.evidence, "distance": m.distance}
        _label(printing, treatments, promos)

    # Add minted printings, creating TCGplayer-only cards (DON!!) where Bandai has none.
    for role, p, art, d in minted:
        number = p.number or DON
        card = cards.get(number) or _new_card(number, p, files)
        cards[number] = card
        treatments, promos = classify_tags(p.base_name_and_tags()[1], rules)
        if role["role"] == "stamp":
            promos = sorted(set(promos) | {(role["promo"], role["category"])})
        printing = {"id": f"{number}~tcg{p.product_id}", "set": role["set"],
                    "rarity": TCGPLAYER_RARITY.get(p.extended.get("Rarity"), p.extended.get("Rarity")),
                    "image": images.TCGPLAYER_IMAGE.format(product_id=p.product_id), "source": "tcgplayer",
                    "identifiers": {"tcgplayerProductIds": [p.product_id]},
                    "tcgplayer": {"name": p.name, "match": "minted", "distance": d}}
        if art:
            printing["artOf"] = art
        _add_finishes(printing, finishes[p.product_id])
        _label(printing, treatments, promos)
        card["printings"].append({k: v for k, v in printing.items() if v is not None})

    _write(files, sets, roles, groups)
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps({"unmatched": review, "pending": pending}, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    hashes.save()
    evidence = collections.Counter(m.evidence for _, m in matches)
    print(f"matched {len(matches)} ({dict(evidence)}), minted {len(minted)}, review {len(review)}, "
          f"pending {len(pending)}")


def _add_finishes(printing: dict, found: set[str]) -> None:
    if found:
        printing["finishes"] = sorted(set(printing.get("finishes", [])) | found)


def _label(printing: dict, treatments: list[str], promos: list[tuple[str, str]]) -> None:
    if treatments:
        printing["treatments"] = sorted(set(printing.get("treatments", [])) | set(treatments))
    if promos:
        merged = {(x["type"], x["category"]) for x in printing.get("promoTypes", [])} | set(promos)
        printing["promoTypes"] = [{"type": t, "category": c} for t, c in sorted(merged)]


def _new_card(number: str, p: tcgcsv.Product, files: dict) -> dict:
    """A card Bandai's list does not have, from TCGplayer's facts. Only DON!! cards reach this today."""
    card = {"number": number, "name": "DON!!" if number == DON else p.base_name_and_tags()[0],
            "category": "DON" if number == DON else (p.extended.get("CardType") or "").title(),
            "source": "tcgplayer", "printings": []}
    files.setdefault(number.split("-", 1)[0], {"cards": []})["cards"].append(card)
    return card


def _write(files: dict, sets: list[dict], roles: dict, groups: list[dict]) -> None:
    by_id = {s["id"]: s for s in sets}
    gname = {g["groupId"]: g for g in groups}
    for s in sets:
        s.pop("tcgplayerGroupIds", None)
    for gid, role in sorted(roles.items()):
        if role["role"] == "pending":
            continue
        s = by_id.get(role["set"])
        if s is None:
            g = gname[gid]
            s = {"id": role["set"], "type": role.get("type", "promo"), "source": "tcgplayer",
                 "releases": [{"language": "en", "name": role.get("name") or g["name"],
                               "releaseDate": (g.get("publishedOn") or "")[:10] or None,
                               "source": f"https://tcgcsv.com/tcgplayer/{tcgcsv.CATEGORY}/{gid}/products"}]}
            if role["role"] == "stamp":
                s["parent"] = role["parent"]
            s["releases"] = [{k: v for k, v in r.items() if v is not None} for r in s["releases"]]
            sets.append(s)
            by_id[s["id"]] = s
        s.setdefault("tcgplayerGroupIds", []).append(gid)
        published = (gname[gid].get("publishedOn") or "")[:10]
        if role["role"] == "set" and published:
            # Bandai's card list gives no dates; TCGplayer publishes a set's group on its release date.
            en = next(r for r in s["releases"] if r["language"] == "en")
            en["releaseDate"] = min(filter(None, [en.get("releaseDate"), published]))
    SETS.write_text(json.dumps(sets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, body in files.items():
        body["cards"].sort(key=lambda c: c["number"])
        for c in body["cards"]:
            c["printings"].sort(key=lambda p: p["id"])
        (CARDS / f"{name}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
