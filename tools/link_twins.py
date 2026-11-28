"""Find the English twin of each Japanese printing that Bandai's ids leave without one, by its card image.

    uv run --group dev python tools/link_twins.py [--calibrate]

import_bandai_ja.py gives a Japanese printing the English printing with its Bandai id, set and rarity as its twin
(`twinOf`). The rest are matched here. A Japanese printing's candidates are the English Bandai printings of the
same card, in the same set (a combined English set such as OP14-EB04 counts for OP14), with the same rarity, that no
other Japanese printing is the twin of. Nothing is matched in the sets P and OTHER, which hold unrelated promotions:
their close candidates go to review. It is linked to the nearest one when
that image hash is at most TWIN_SAME bits away and no other candidate is within REVIEW_BELOW. An image shows that two
printings share art, not that they are one printing, and a Japanese card can share its art with several English
printings (a reprint, PRB-01's two foils), so anything less clear goes to review/twins.json, as does a candidate two
Japanese printings both pick. The links go to data/twins.json, which import_bandai_ja.py reads, so a rerun of it
keeps them without the images.

A twin from Bandai's ids whose images are more than REVIEW_BELOW bits apart is listed as a suspect, and left as it
is: the 2026-11-28 calibration found some (OP05-081_p2~ja is 77 bits from OP05-081_p2 and 6 from OP05-081_p3).

--calibrate prints the distances between the known twins and between a card's printings that are not twins, the
evidence TWIN_SAME and REVIEW_BELOW are set from. Run after images.py fetch; images not downloaded yet are
reported, never fetched from here.
"""
from __future__ import annotations

import argparse
import json

import images
import import_bandai_ja
import opjson
import twins

REVIEW = opjson.ROOT / "review" / "twins.json"
# Sets that hold unrelated promotions: one art on two events' prizes says nothing about which printing is which.
CATCH_ALL = ("P", "OTHER")
# From --calibrate on 2026-11-28 (297 twins, 302 other pairs): twins p50 5 bits, 276 of 297 under 20; pairs of
# different art p50 120. Pairs of different printings closer than 40 bits share their art.
TWIN_SAME = 20
REVIEW_BELOW = 40


def match(ja: list[dict], en: list[dict], claimed: set[str], hash_of) -> tuple[dict[str, dict], list[dict]]:
    """({Japanese printing id: {"en": id, "distance": bits}}, review entries) for one card's Japanese printings that
    have no twin yet, against its English Bandai printings. claimed holds the English ids already a twin."""
    picks: dict[str, list[tuple[str, int]]] = {}
    review: list[dict] = []
    for p in sorted(ja, key=lambda p: p["id"]):
        h = hash_of(p)
        if h is None:
            review.append({"printing": p["id"], "reason": "noImage"})
            continue
        scored = sorted((images.distance(h, oh), e["id"]) for e in en
                        if e["id"] not in claimed and e.get("rarity") == p.get("rarity")
                        and p["set"] in (e["set"], *e["set"].split("-")) and (oh := hash_of(e)) is not None)
        close = [(eid, d) for d, eid in scored if d <= TWIN_SAME]
        if p["set"] in CATCH_ALL:
            if scored and scored[0][0] < REVIEW_BELOW:
                review.append({"printing": p["id"], "reason": "catchAll", "candidates": [
                    {"printing": eid, "distance": d} for d, eid in scored if d < REVIEW_BELOW]})
        elif close and len([d for d, _ in scored if d < REVIEW_BELOW]) == 1:
            picks.setdefault(close[0][0], []).append((p["id"], close[0][1]))
        elif scored and scored[0][0] < REVIEW_BELOW:
            shown = [{"printing": eid, "distance": d} for d, eid in scored if d < REVIEW_BELOW]
            review.append({"printing": p["id"], "reason": "ambiguous" if len(close) > 1 else "close",
                           "candidates": shown})
    links = {}
    for eid, who in picks.items():
        if len(who) == 1:
            links[who[0][0]] = {"en": eid, "distance": who[0][1]}
        else:
            review += [{"printing": jid, "reason": "contested", "en": eid, "distance": d} for jid, d in who]
    review.sort(key=lambda r: r["printing"])
    return links, review


def suspect(p: dict, twin_id: str, en: list[dict], hash_of) -> dict | None:
    """A review entry when the Japanese printing p's images and its twin's are more than REVIEW_BELOW bits apart,
    naming the nearest other English printing; None when they are close or an image is missing."""
    h = hash_of(p)
    twin = next((e for e in en if e["id"] == twin_id), None)
    th = hash_of(twin) if twin is not None and h is not None else None
    if th is None or images.distance(h, th) <= REVIEW_BELOW:
        return None
    entry = {"printing": p["id"], "reason": "suspect", "twinOf": twin_id, "distance": images.distance(h, th)}
    others = sorted((images.distance(h, oh), e["id"]) for e in en if e is not twin and (oh := hash_of(e)) is not None)
    if others:
        entry["nearest"] = {"printing": others[0][1], "distance": others[0][0]}
    return entry


def _rule_twin(p: dict, card: dict) -> str | None:
    """The twin import_bandai_ja's rule gives the Japanese printing p of card: the English printing with its Bandai
    id, set and rarity."""
    en = next((e for e in card["printings"] if e["id"] == p["id"].removesuffix("~ja")), None)
    twin = import_bandai_ja._twin(en, p["set"], p.get("rarity"))
    return twin["id"] if twin else None


def _same_art(a: dict, b: dict) -> bool:
    """Two English printings that carry one illustration (artOf), which an image cannot tell apart."""
    return a["id"] == b["id"] or a.get("artOf") in (b["id"], b.get("artOf") or "") or b.get("artOf") == a["id"]


def _percentiles(values: list[int]) -> str:
    if not values:
        return "none"
    values = sorted(values)
    return ", ".join(f"p{q} {values[min(len(values) - 1, len(values) * q // 100)]}" for q in (1, 50, 99)) + \
        f" (n={len(values)})"


def calibrate(files: dict[str, dict], hashes: images.HashCache, every: int = 15) -> None:
    """Fetch the images of every `every`th rule twin (sorted by id), then print the distances between those twins
    and between each of them and the card's other English Bandai printings whose art is not the twin's."""
    twin_d, other_d = [], []
    sample = sorted((p for body in files.values() for c in body["cards"] for p in c["printings"]
                     if opjson.language(p) == "ja" and p.get("twinOf")), key=lambda p: p["id"])[::every]
    cards = {c["number"]: c for body in files.values() for c in body["cards"]}
    number_of = {p["id"]: c["number"] for c in cards.values() for p in c["printings"]}
    for p in sample:
        h = hashes.get("bandai", p["id"], p["image"])
        card = cards[number_of[p["id"]]]
        en = {e["id"]: e for e in card["printings"] if opjson.language(e) == "en" and e["source"] == "bandai"}
        twin = en.get(p["twinOf"])
        if h is None or twin is None:
            continue
        for e in en.values():
            eh = hashes.get("bandai", e["id"], e["image"]) if images.path_for("bandai", e["id"]).exists() else None
            if eh is None:
                continue
            if e is twin:
                twin_d.append(images.distance(h, eh))
            elif not _same_art(e, twin):
                other_d.append(images.distance(h, eh))
    hashes.save()
    print(f"twins: {_percentiles(twin_d)}")
    print(f"not twins: {_percentiles(other_d)}")


def _put_twin(p: dict, twin: str) -> None:
    """Set p's twinOf where import_bandai_ja puts it, after source, so the two tools write the same file."""
    rest = dict(p)
    p.clear()
    for k, v in rest.items():
        p[k] = v
        if k == "source":
            p["twinOf"] = twin


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true", help="fetch a sample of the rule's twins and print distances")
    args = ap.parse_args()
    files = opjson.load_cards()
    hashes = images.HashCache()
    if args.calibrate:
        calibrate(files, hashes)
        return

    def hash_of(p: dict) -> int | None:
        if not images.path_for("bandai", p["id"]).exists():
            return None  # not downloaded yet; never fetch from here
        return hashes.get("bandai", p["id"], p["image"])

    corrections = twins.load_corrections()
    settled: dict[str, dict] = {}
    review: list[dict] = []
    for body in files.values():
        for card in body["cards"]:
            ja = [p for p in card["printings"] if opjson.language(p) == "ja"]
            # A twin from a correction or from the rule stays; an earlier image match is decided again.
            open_ja = [p for p in ja if p["id"] not in corrections and _rule_twin(p, card) is None]
            claimed = {p["twinOf"] for p in ja if p.get("twinOf") and p not in open_ja}
            en = [p for p in card["printings"] if opjson.language(p) == "en" and p["source"] == "bandai"]
            links, r = match(open_ja, en, claimed, hash_of)
            settled.update(links)
            review += r
            for p in ja:
                if (rule := _rule_twin(p, card)) and p["id"] not in corrections:
                    review += [e for e in [suspect(p, rule, en, hash_of)] if e]
    hashes.save()
    opjson.write_atomic(twins.SETTLED, json.dumps(dict(sorted(settled.items())), indent=2) + "\n")
    for body in files.values():
        for card in body["cards"]:
            for p in card["printings"]:
                if opjson.language(p) == "ja":
                    twin = twins.twin_of(p["id"], _rule_twin(p, card), settled, corrections)
                    p.pop("twinOf", None)
                    if twin:
                        _put_twin(p, twin)
    for stem, body in files.items():
        opjson.write_atomic(opjson.CARDS / f"{stem}.json", json.dumps(body, indent=2, ensure_ascii=False) + "\n")
    by_reason = {k: [r for r in review if r["reason"] == k] for k in ("suspect", "close", "ambiguous", "contested", "catchAll", "noImage")}
    opjson.write_atomic(REVIEW, json.dumps(by_reason, indent=2) + "\n")
    print(f"{len(settled)} Japanese printings matched to their English twin by image; "
          + ", ".join(f"{len(v)} {k}" for k, v in by_reason.items()) + " in review/twins.json")


if __name__ == "__main__":
    main()
