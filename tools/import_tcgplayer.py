"""Attach TCGplayer product ids to printings, and add the printings only TCGplayer sells.

    uv run --group dev python tools/import_tcgplayer.py

Reads data/cards (written by import_bandai.py), TCGCSV category 68 and the cached card images
(tools/images.py fetch). A product is matched to a Bandai printing only when the card number agrees and
the two images agree: the hash distance is at most ACCEPT and the next-best candidate is at least MARGIN
further away. When TCGplayer has no image for a product (new sets often have none yet), its name decides, but only
where it leaves no choice: an untagged product takes the base printing, and a tagged one the only variant printing
left (evidence "name"). The name also settles a product whose image the hash rejected, when TCGplayer's scan is
framed so differently from Bandai's that the same card sits 50 to 100 bits away: the only untagged product of its
number in the set's group takes the base printing if nothing has claimed it and no other printing of the number is
closer (evidence "name-sole-plain"). A product that cannot be matched either way goes to
review/tcgplayer-68.json, never into a guess. Images cannot tell a foil-pattern reprint from the plain reprint of the same art, so when two candidates
are too close to call, the product's tag decides between Bandai's kinds: "(Reprint)" is an _rN printing and a
parallel, alternate-art or foil-pattern tag a _pN one; the match stands only if the image pick is the one
printing of that kind within ACCEPT (evidence "image+name"). Before that, a tie is retried on the whole card,
whose lower half carries the stamps the art band ignores (evidence "whole-card"). Foil-pattern copies of one card
that are still tied (PRB-01's Jolly Roger and Textured Foils share their art) take its _pN printings of that art
in Bandai's order, FOIL_PATTERN_ORDER (evidence "image+order"). A promo whose art is that of
two unclaimed Bandai printings the images cannot tell apart is settled by Bandai's "Card Set(s)" when one of the
product's tags names exactly one of them (evidence "image+cardset"). Products of one card still tied after that,
with as many unclaimed printings in reach as products, are assigned together and keep the one pairing that beats
every other by MARGIN bits in total (evidence "image+pairing"). What is left goes to review rather than becoming
a third copy, except promos that outnumber the free printings they are tied between: Bandai lists too few
printings for them, so each becomes a printing of its own with `artOf` naming the nearest (evidence
"minted-nearest"). A promo never takes a printing Bandai files in a set that has its own TCGplayer group
unless a tag names that printing's card set, as the Ultra Deck reprints' tags do. A reprint that TCGplayer files in another set's group is matched by image to the Bandai printing of its
number wherever Bandai files it (evidence "image-other-set").

Pre-release, release-event and anniversary groups hold stamped copies of a set's printings, the Revision Pack
group holds Starter Deck cards reissued with revised text, and most of TCGplayer's promos are not on Bandai's
card list. Those products become printings of their own, with an id minted from the card number and the
product id (OP02-013~tcg123456), and `artOf` naming the Bandai printing whose art they carry when the images
say so. A promo TCGplayer files in a booster's group (the Dash Packs) is one of them too, in set P.
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
    "OP-RP": {"role": "reissue", "set": "OP-RP", "type": "promo", "name": "Revision Pack Cards"},
    "OP-CS": {"role": "promo", "set": "OP-CS", "type": "box_set", "name": "One Piece Collection Sets"},
    "LT-01": {"role": "promo", "set": "LT01", "type": "starter_deck", "name": "Learn Together Deck Set"},
    "SD01": {"role": "promo", "set": "SD01", "type": "starter_deck", "name": "Set Sail Deck Set"},
}
_STAMP = re.compile(r"^(?P<parent>[A-Z]+-?\d+) (?P<kind>PRE|RE|ANN)$")
# Stamp groups name the booster alone; Bandai files these sets under a combined code.
STAMP_PARENT_ALIAS = {"OP14": "OP14-EB04", "OP15": "OP15-EB04"}
STAMP_PROMO = {"PRE": ("prerelease", "event"), "RE": ("release", "event"), "ANN": ("anniversary", "anniversary")}
DON = "DON"
# A TCGplayer Number becomes a card number and a file name, so anything else goes to review.
CARD_NUMBER = re.compile(r"^[A-Z]+[0-9]*-[0-9]{3}$")
# TCGCSV price subtypes for category 68, as card_catalog.card_finished codes.
FINISHES = {"Normal": "nonfoil", "Foil": "foil"}
# TCGplayer rarity codes that Bandai spells differently, or that mean "no rarity".
TCGPLAYER_RARITY = {"PR": "P", "None": None, "": None}
# The order in which Bandai numbers one card's foil-pattern copies in a set. In PRB-01 the Jolly Roger Foil is
# the lower _pN of the two on all 53 cards whose copies the images could place. The cards agree: a Textured Foil
# prints the parallel star above its rarity code and a Jolly Roger Foil does not, on all 93 of Bandai's scans.
FOIL_PATTERN_ORDER = ["jolly_roger_foil", "textured"]


@dataclass
class Match:
    product: tcgcsv.Product
    printing_id: str | None
    distance: int | None
    evidence: str  # "image", "image-only-candidate", "image+name", "name", "name-sole-plain", ... or why unmatched


def normalise_set(abbreviation: str) -> str:
    return re.sub(r"^([A-Z]+)-(\d+)$", r"\1\2", abbreviation)


def _stamp_parent(abbreviation: str) -> str:
    code = normalise_set(abbreviation)
    return STAMP_PARENT_ALIAS.get(code, code)


def copied_set(role: dict, number: str) -> str:
    """The Bandai set whose printing a stamp or reissue product copies: a stamp group names its parent, and a
    reissue copies the printing in its card number's own set (ST04-002 is ST04's)."""
    return role["parent"] if role["role"] == "stamp" else number.split("-")[0]


def group_roles(groups: list[dict], set_ids: set[str]) -> dict[int, dict]:
    """groupId -> {"role": "set"|"stamp"|"reissue"|"promo"|"pending", "set": opjson set id, ...}."""
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


_KIND = re.compile(r"_(?P<kind>[pr])\d+$")
# Treatments Bandai numbers as a _pN printing (every full-art, wanted-poster, gold and serial printing is one).
VARIANT_TREATMENTS = {"parallel", "alternate_art", "manga", "sp", "full_art", "wanted_poster", "gold", "serial"}


def printing_kind(printing_id: str) -> str | None:
    """'p' for a parallel or other variant (OP01-120_p2), 'r' for a reprint (OP01-120_r1), None for a base."""
    m = _KIND.search(printing_id)
    return m.group("kind") if m else None


def product_kind(product: tcgcsv.Product, rules: list[dict]) -> str | None:
    """The Bandai printing kind a product's tags name: 'r' for a reprint, 'p' for a variant, None otherwise."""
    treatments, promos = classify_tags(product.base_name_and_tags()[1], rules)
    if "reprint" in treatments:
        return "r"
    if set(treatments) & VARIANT_TREATMENTS or any(c == "foil-pattern" for _, c in promos):
        return "p"
    return None


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def names_card_set(product: tcgcsv.Product, card_set: str | None) -> bool:
    """Whether a tag of the product names this Bandai card set ("Ultra Deck: The Three Captains" names
    "-The Three Captains-[ST-10]")."""
    cs = _key(re.sub(r"\[[^\]]*\]", "", card_set or ""))  # without the set code Bandai appends
    return bool(cs) and any(t == cs or t in cs or (len(cs) >= 8 and cs in t)
                            for t in (_key(t) for t in product.base_name_and_tags()[1]) if len(t) >= 8)


def promo_copy(product: tcgcsv.Product, rules: list[dict]) -> bool:
    """Whether a product's tags name a promo program (a Dash Pack, a Regionals prize), which is a copy of a card
    from somewhere else and never one of its set's own printings. A foil pattern is not one: Bandai files
    Jolly Roger and Textured Foils as printings of the set."""
    _, promos = classify_tags(product.base_name_and_tags()[1], rules)
    return any(category != "foil-pattern" for _, category in promos)


def card_set_pick(product: tcgcsv.Product, near: list[str], card_set_of) -> str | None:
    """The one printing in near whose Bandai card set a tag of the product names, else None."""
    hits = [c for c in near if names_card_set(product, card_set_of(c))]
    return hits[0] if len(hits) == 1 else None


def clear_winner(scored: list[tuple[int, str]]) -> str | None:
    """The best candidate of [(distance, printing)] when it is within ACCEPT and MARGIN clear of the next."""
    scored = sorted(scored)
    if scored and scored[0][0] <= ACCEPT and (len(scored) == 1 or scored[1][0] - scored[0][0] >= MARGIN):
        return scored[0][1]
    return None


def foil_pattern(product: tcgcsv.Product, rules: list[dict]) -> str | None:
    """The one foil pattern of FOIL_PATTERN_ORDER a product's tags name, else None."""
    _, promos = classify_tags(product.base_name_and_tags()[1], rules)
    found = [promo for promo, category in promos if category == "foil-pattern" and promo in FOIL_PATTERN_ORDER]
    return found[0] if len(found) == 1 else None


def _suffix_number(printing_id: str) -> int:
    return int(re.search(r"\d+$", printing_id).group())


def assign(products: list[tcgcsv.Product], candidates: list[str],
           dist: dict[tuple[int, str], int | None], kind_of=lambda p: None,
           whole_dist=lambda p, c: None, pattern_of=lambda p: None, pairing: bool = False) -> list[Match]:
    """Match products to candidate printings by image. A tie on the art band is retried on the whole card
    (whole_dist), then broken by the product's tag between kinds (kind_of gives 'p', 'r' or None), and the
    foil-pattern copies still tied are placed by Bandai's numbering (pattern_of, see order_by_pattern). With
    pairing, products still tied keep the pairs of the best assignment when it beats every other assignment of
    these products by MARGIN bits in total (evidence "image+pairing"): each product is a little nearer its own
    printing than the other's, and no other way of pairing them comes close. Every product appears once in the
    result."""
    usable = list(candidates)
    if not usable:
        return [Match(p, None, None, "no Bandai printing of this number in the set") for p in products]

    def bits(p: tcgcsv.Product, c: str) -> int:
        d = dist.get((p.product_id, c))
        return 10_000 if d is None else d

    def cost(i: int, j: int) -> int:
        return bits(products[i], usable[j])

    # Exact minimum-cost assignment when the cluster is small (it nearly always is: a handful of variants
    # of one card in one set); greedy by distance otherwise.
    pair_margin = None  # total bits the second-best assignment loses to the best one; None if there is no other
    if len(products) <= 7 and len(usable) <= 7:
        best: tuple[int, dict[int, int]] | None = None
        if len(products) <= len(usable):
            options = (dict(enumerate(perm)) for perm in itertools.permutations(range(len(usable)), len(products)))
        else:
            options = ({i: j for j, i in enumerate(perm)}
                       for perm in itertools.permutations(range(len(products)), len(usable)))
        totals = []
        for option in options:
            total = sum(cost(i, j) for i, j in option.items())
            totals.append(total)
            if best is None or total < best[0]:
                best = (total, option)
        pairs = best[1]
        if len(totals) > 1:
            totals.sort()
            pair_margin = totals[1] - totals[0]
    else:
        pairs, taken = {}, set()
        for (i, j) in sorted(((i, j) for i in range(len(products)) for j in range(len(usable))),
                             key=lambda ij: cost(*ij)):
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
            near = [c for c in usable if bits(p, c) <= ACCEPT]
            whole = [(w, c) for c in near if (w := whole_dist(p, c)) is not None]
            if len(whole) == len(near) and clear_winner(whole) == cand:
                out.append(Match(p, cand, d, "whole-card"))
                continue
            kind = kind_of(p)
            same_kind = [c for c in near if printing_kind(c) == kind]
            if kind and same_kind == [cand]:
                out.append(Match(p, cand, d, "image+name"))
            elif (pairing and len(products) > 1 and pair_margin is not None and pair_margin >= MARGIN
                  and len(pairs) == len(products) and all(cost(a, b) <= ACCEPT for a, b in pairs.items())):
                out.append(Match(p, cand, d, "image+pairing"))
            else:
                out.append(Match(p, None, d, f"{cand} at {d} bits is not clear of the next candidate at {runner_up}"))
        else:
            out.append(Match(p, cand, d, "image" if others else "image-only-candidate"))
    return order_by_pattern(out, usable, bits, pattern_of)


def settle_tied(products: list[tcgcsv.Product], candidates: list[str], dist: dict[tuple[int, str], int | None],
                **tie_breakers) -> dict[int, Match]:
    """{product id: Match} for the products of one card that a first sweep found tied between several unclaimed
    printings (dist holds None for a printing a product may not take). Several products are assigned together
    with assign, with pairing. One product alone is left as it is. So is a group with more products than
    printings within ACCEPT of any of them: some product in it has no printing of its own, and the images do not
    say which."""
    if len(products) < 2 or surplus(products, dist):
        return {}
    return {m.product.product_id: m for m in assign(products, candidates, dist, pairing=True, **tie_breakers)
            if m.printing_id}


def surplus(products: list[tcgcsv.Product], dist: dict[tuple[int, str], int | None]) -> bool:
    """Whether more products are tied than there are printings within ACCEPT of any of them, so that some product
    has no Bandai printing of its own."""
    return len(products) > len({c for (_, c), d in dist.items() if d is not None and d <= ACCEPT})


def mint_tied(role: str, products: list[tcgcsv.Product], settled: dict[int, Match],
              dist: dict[tuple[int, str], int | None]) -> list[int]:
    """Ids of the tied promos that become printings of their own (evidence "minted-nearest"): the ones settle_tied
    left unmatched, when the group has more promos than free printings in reach. Which of them Bandai's printing
    is cannot be told, so none of them takes it. Products of a set's group are never minted here."""
    if role != "promo" or not surplus(products, dist):
        return []
    return [p.product_id for p in products if p.product_id not in settled]


def order_by_pattern(out: list[Match], usable: list[str], bits, pattern_of) -> list[Match]:
    """Place a card's foil-pattern copies the images left unmatched by Bandai's numbering: the _pN printings
    within ACCEPT of at least one of the copies, lowest first, go to the patterns in FOIL_PATTERN_ORDER (evidence
    "image+order"). Nothing changes unless there are exactly as many such printings as patterns, one product per
    pattern, and every copy already matched sits where the order puts it. A copy takes its printing only if the
    images put it within ACCEPT of that printing: the Textured Foil of OP05-115 sits 30 bits from the Jolly Roger
    Foil's printing, so the printings need not carry the art of every copy."""
    pattern = {m.product.product_id: pattern_of(m.product) for m in out}
    patterned = [m for m in out if pattern[m.product.product_id]]
    if all(m.printing_id for m in patterned):
        return out
    ranks = sorted({pattern[m.product.product_id] for m in patterned}, key=FOIL_PATTERN_ORDER.index)
    held = {m.printing_id: m for m in out if m.printing_id}
    slots = sorted((c for c in usable if printing_kind(c) == "p"
                    and any(bits(m.product, c) <= ACCEPT for m in patterned)
                    and (c not in held or pattern[held[c].product.product_id])), key=_suffix_number)
    if len(ranks) != len(patterned) or len(slots) != len(ranks):
        return out
    slot_of = dict(zip(ranks, slots))
    if any(m.printing_id and m.printing_id != slot_of[pattern[m.product.product_id]] for m in patterned):
        return out
    placed = []
    for m in out:
        slot = slot_of.get(pattern[m.product.product_id])
        placed.append(Match(m.product, slot, bits(m.product, slot), "image+order")
                      if slot and not m.printing_id and bits(m.product, slot) <= ACCEPT else m)
    return placed


def assign_by_name(products: list[tcgcsv.Product], candidates: list[str], number: str,
                   rules: list[dict], group: list[tcgcsv.Product] | None = None,
                   dist: dict[tuple[int, str], int | None] | None = None) -> list[Match]:
    """Match products the images left unmatched, by name, where it leaves no choice. candidates are the
    unclaimed Bandai printings of the number in the set; products with no unique match are left out of the result.

    Without dist, every product is taken to have no image to compare (evidence "name"): an untagged product takes
    the base printing and a tagged one the only variant printing left. With dist (image distance of each product
    of the group to every Bandai printing of the number in the set, claimed or not), a product with no distance
    at all is that case, and one with distances is judged on them: the images rejected it, and its name takes the
    base printing only if all of these hold (evidence "name-sole-plain"):
    - it is the only plain product of the number in the set's group (group, every product of the number there);
    - the base printing is still unclaimed;
    - no other printing of the number is as close to the product as the base printing is, and the base printing
      is beyond ACCEPT, since a product within ACCEPT of it is a tie, not a rejection."""
    def is_variant(p: tcgcsv.Product) -> bool:
        treatments, promos = classify_tags(p.base_name_and_tags()[1], rules)
        return bool(treatments or promos)

    def seen(p: tcgcsv.Product) -> dict[str, int]:
        return {c: d for (pid, c), d in (dist or {}).items() if pid == p.product_id and d is not None}

    imageless = [p for p in products if not seen(p)]
    out = []
    plain = [p for p in imageless if not is_variant(p)]
    if len(plain) == 1 and number in candidates:
        out.append(Match(plain[0], number, None, "name"))
    variants = [p for p in imageless if is_variant(p)]
    others = [c for c in candidates if c != number]
    if len(variants) == 1 and len(others) == 1:
        out.append(Match(variants[0], others[0], None, "name"))
    plain_in_group = [p for p in (group or []) if not is_variant(p)]
    for p in products:
        d = seen(p).get(number)
        if (len(plain_in_group) == 1 and plain_in_group[0] is p and number in candidates
                and not any(m.printing_id == number for m in out)
                and d is not None and d > ACCEPT
                and all(x > d for c, x in seen(p).items() if c != number)):
            out.append(Match(p, number, d, "name-sole-plain"))
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
    set_groups = {r["set"] for r in roles.values() if r["role"] == "set"}
    hashes = images.HashCache()

    def bandai_hash(pid: str) -> int | None:
        return hashes.get("bandai", pid, printings[pid][1]["image"])

    def tcg_hash(p: tcgcsv.Product) -> int | None:
        return hashes.get("tcgplayer", str(p.product_id), images.TCGPLAYER_IMAGE.format(product_id=p.product_id))

    def whole_distance(p: tcgcsv.Product, c: str) -> int | None:
        th = hashes.get("tcgplayer", str(p.product_id), images.TCGPLAYER_IMAGE.format(product_id=p.product_id),
                        whole=True)
        bh = hashes.get("bandai", c, printings[c][1]["image"], whole=True)
        return None if th is None or bh is None else images.distance(th, bh)

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
    singles = []
    for g in groups:
        for p in tcgcsv.products(g["groupId"], CACHE):
            if not p.is_single:
                continue
            if p.number and not CARD_NUMBER.match(p.number):
                review.append({"productId": p.product_id, "name": p.name, "number": p.number,
                               "reason": "TCGplayer's Number is not a card number"})
                continue
            singles.append((g, p))
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
        dist = distances(products, candidates)
        found = assign(products, candidates, dist,
                       kind_of=lambda prod: product_kind(prod, rules), whole_dist=whole_distance,
                       pattern_of=lambda prod: foil_pattern(prod, rules))
        unmatched = [m.product for m in found if not m.printing_id]
        free = [c for c in candidates if c not in {m.printing_id for m in found}]
        by_name = {m.product.product_id: m for m in assign_by_name(unmatched, free, number, rules,
                                                                  group=products, dist=dist)}
        for m in found:
            m = by_name.get(m.product.product_id, m)
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
    ties = []  # (role, product, scores) of products the first sweep found tied between several printings

    def pool_for(role: dict, p: tcgcsv.Product, number: str) -> list[str]:
        """The Bandai printings a leftover product may take: a stamp or reissue copies a printing of its set whether
        or not another product holds it; the others take printings nobody claimed."""
        if role["role"] in ("stamp", "reissue"):
            return sorted(by_set_number.get((copied_set(role, number), number), []))
        pool = sorted(pid for pid, (n, _) in printings.items() if n == number and pid not in claimed)
        if role["role"] == "promo":
            # A printing Bandai files in a set TCGplayer gives its own group is that set's card, even when the group
            # does not list it (PRB-01's plain reprints): a promo takes it only if a tag names its card set.
            pool = [c for c in pool if printings[c][1]["set"] not in set_groups
                    or names_card_set(p, printings[c][1].get("cardSet"))]
        return pool

    for role, p in leftovers:
        if role["role"] == "pending":
            pending.append({"productId": p.product_id, "name": p.name, "set": role["set"], "number": p.number})
            continue
        number = p.number or DON
        pool = pool_for(role, p, number)
        dist = distances([p], pool)
        scored = sorted((d, c) for (_, c), d in dist.items() if d is not None)
        art = clear_winner(scored)
        near = [c for d, c in scored if d <= ACCEPT]
        evidence = None  # set when a tie on the art band was settled another way
        if not art and len(near) > 1 and role["role"] not in ("stamp", "reissue"):
            whole = [(w, c) for c in near if (w := whole_distance(p, c)) is not None]
            art = clear_winner(whole) if len(whole) == len(near) else None
            evidence = "whole-card"
            if not art:
                art, evidence = card_set_pick(p, near, lambda c: printings[c][1].get("cardSet")), "image+cardset"
            if not art:
                entry = {"productId": p.product_id, "name": p.name, "set": role["set"], "number": p.number,
                         "reason": "its art is that of several Bandai printings the images cannot tell apart",
                         "closest": [{"printing": c, "distance": d} for d, c in scored[:3]]}
                review.append(entry)  # settled below if the products tied with it can be told apart
                ties.append((role, p, scored, entry))
                continue
        if role["role"] in ("promo", "set") and art and art not in claimed:
            claimed[art] = p.product_id
            how = evidence or ("image" if role["role"] == "promo" else "image-other-set")
            matches.append((role, Match(p, art, scored[0][0], how)))
            continue
        if role["role"] == "set" and p.number:
            if promo_copy(p, rules):
                # TCGplayer files this promo in a booster's group (the Dash Packs sit in OP04's and OP15's) although
                # it is none of that set's cards: it is a promo printing of its own, and the images name a printing
                # whose art it carries only where one of the number's printings, claimed or not, is a clear match.
                every = sorted((d, c) for (_, c), d in
                               distances([p], sorted(pid for pid, (n, _) in printings.items() if n == number)).items()
                               if d is not None)
                art = clear_winner(every)
                minted.append(({"role": "promo", "set": "P"}, p, art, every[0][0] if art else None, "minted"))
                continue
            review.append({"productId": p.product_id, "name": p.name, "set": role["set"], "number": p.number,
                           "reason": "no Bandai printing of this number in its set matches the image",
                           "closest": [{"printing": c, "distance": d} for d, c in scored[:3]]})
            continue
        minted.append((role, p, art, scored[0][0] if art else None, "minted"))

    # Products tied between several printings are settled together with the others of their card (same role and
    # number), now that the sweep has claimed what it could. They are assigned like a pass 1 cluster, and a pair
    # of products the images only barely separate is kept when no other pairing comes close (evidence
    # "image+pairing"). A group with more products than free printings in reach is not assigned at all: it
    # holds a product with no printing of its own, and the images cannot say which.
    tied = collections.defaultdict(list)
    for role, p, scored, entry in ties:
        tied[(role["role"], p.number)].append((role, p, scored, entry))
    for (_, number), group in tied.items():
        products = [p for _, p, _, _ in group]
        pools = {p.product_id: set(pool_for(role, p, number)) for role, p, _, _ in group}
        candidates = sorted(set().union(*pools.values()))
        dist = {(pid, c): (d if c in pools[pid] else None) for (pid, c), d in distances(products, candidates).items()}
        settled = settle_tied(products, candidates, dist, kind_of=lambda prod: product_kind(prod, rules),
                              whole_dist=whole_distance, pattern_of=lambda prod: foil_pattern(prod, rules))
        to_mint = mint_tied(group[0][0]["role"], products, settled, dist)
        for role, p, scored, entry in group:
            if p.product_id in settled:
                m = settled[p.product_id]
                claimed[m.printing_id] = p.product_id
                matches.append((role, m))
                review.remove(entry)
            elif p.product_id in to_mint:
                # artOf names the nearest of the printings the promo was tied between.
                minted.append((role, p, scored[0][1], scored[0][0], "minted-nearest"))
                review.remove(entry)

    # Write identifiers onto matched Bandai printings.
    for role, m in matches:
        _, printing = printings[m.printing_id]
        treatments, promos = classify_tags(m.product.base_name_and_tags()[1], rules)
        printing.setdefault("identifiers", {}).setdefault("tcgplayerProductIds", []).append(m.product.product_id)
        _add_finishes(printing, finishes[m.product.product_id])
        printing["tcgplayer"] = {"name": m.product.name, "match": m.evidence, "distance": m.distance}
        _label(printing, treatments, promos)

    # Add minted printings, creating TCGplayer-only cards (DON!!) where Bandai has none.
    for role, p, art, d, how in minted:
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
                    "tcgplayer": {"name": p.name, "match": how, "distance": d}}
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
