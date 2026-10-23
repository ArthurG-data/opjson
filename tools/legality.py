"""Format legality from legality/*.json: replay the ban list to a date, and decide a printing's legality.

    uv run python tools/legality.py [--as-of YYYY-MM-DD] [--online]

--online also checks the replayed list against the "Cards with Active Restrictions" section of Bandai's
current Banned/Restricted page, where each card is a link to the card list (freewords=<number>).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import opjson

ROOT = Path(__file__).resolve().parents[1]
LEGALITY = ROOT / "legality"
BANDAI_LIST = "https://en.onepiece-cardgame.com/news/restriction.html"
USER_AGENT = "opjson/0.1 (+https://github.com/ArthurG-data/opjson)"
STATUSES = ("legal", "banned", "restricted", "not_legal")


@dataclass
class BanState:
    status: dict[str, str] = field(default_factory=dict)  # card number -> banned | restricted
    pairs: set[frozenset[str]] = field(default_factory=set)


def load() -> tuple[dict, dict, dict]:
    return tuple(json.loads((LEGALITY / f"{n}.json").read_text(encoding="utf-8"))
                 for n in ("formats", "block_designations", "bans"))


def event_date(event: dict) -> str:
    return event.get("effective") or event["inForceBy"]


def ban_state(bans: dict, as_of: str) -> BanState:
    state = BanState()
    for e in sorted(bans["events"], key=event_date):
        if event_date(e) > as_of:
            break
        for card in e.get("cards", []):
            if e["status"] == "legal":
                state.status.pop(card, None)
            else:
                state.status[card] = e["status"]
        for a, b in e.get("pairs", []):
            pair = frozenset((a, b))
            if e["status"] == "legal":
                state.pairs.discard(pair)
            else:
                state.pairs.add(pair)
    return state


def _window(fmt: dict, as_of: str) -> dict | None:
    return next((w for w in fmt["windows"] if w["from"] <= as_of and as_of <= w.get("to", "9999-12-31")), None)


def _block_rank(block: str | None) -> int | None:
    return int(block) if block and block.isdigit() else None


def printing_legality(printing: dict, card_blocks: list[str], designations: dict, fmt: dict, state: BanState,
                      as_of: str) -> str:
    """legal | banned | restricted | not_legal for one printing in one format on one date.

    card_blocks is every block printed on any printing of the card (for 'reprinted' designations)."""
    window = _window(fmt, as_of)
    if window is None:
        return "not_legal"
    number = printing["card"]
    if number in state.status:
        return state.status[number]
    if window.get("blocks") == "all":
        return "legal"
    lo, hi = window["minBlock"], window["maxBlock"]
    block = printing.get("block")
    if block == "X":
        return "legal"
    for d in designations["designations"]:
        if number not in d["cards"] or not (d["from"] <= as_of <= d.get("to", "9999-12-31")):
            continue
        if d["kind"] == "always":
            return "legal"
        if d["kind"] == "block" and lo <= int(d["block"]) <= hi:
            return "legal"
        if d["kind"] == "reprinted":
            newest = max(filter(None, map(_block_rank, card_blocks)), default=None)
            if newest is not None and lo <= newest <= hi:
                return "legal"
    rank = _block_rank(block)
    return "legal" if rank is not None and lo <= rank <= hi else "not_legal"


def validate(formats: dict, designations: dict, bans: dict, card_numbers: set[str]) -> list[str]:
    errors = []
    for e in bans["events"]:
        if ("effective" in e) == ("inForceBy" in e):
            errors.append(f"ban event {e}: needs exactly one of effective or inForceBy")
        if e["status"] not in ("banned", "restricted", "legal"):
            errors.append(f"ban event {e}: unknown status {e['status']}")
        for card in e.get("cards", []) + [c for p in e.get("pairs", []) for c in p]:
            if card not in card_numbers:
                errors.append(f"ban event on {event_date(e)}: {card} is not a card")
    for d in designations["designations"]:
        for card in d["cards"]:
            if card not in card_numbers:
                errors.append(f"block designation {d['kind']}: {card} is not a card")
    for fmt in formats["formats"]:
        windows = sorted(fmt["windows"], key=lambda w: w["from"])
        for a, b in zip(windows, windows[1:]):
            if a.get("to", "9999-12-31") >= b["from"]:
                errors.append(f"format {fmt['id']}: windows starting {a['from']} and {b['from']} overlap")
    return errors


def bandai_current(page: str) -> BanState:
    """The list as Bandai's page states it now: the section after "Cards with Active Restrictions"."""
    section = page[page.find("Cards with Active Restrictions"):]
    section = section[:section.find("Banned/Restricted Cards effective")]
    state = BanState()
    parts = re.split(r"(Banned Pair Cards|Banned Cards|Restricted Cards)", section)
    for label, body in zip(parts[1::2], parts[2::2]):
        lists = [re.findall(r"freewords=([A-Z0-9-]+)", ul) for ul in re.findall(r"<ul>(.*?)</ul>", body, re.S)]
        if label == "Banned Pair Cards":
            # Bandai lays each pair out as one list holding card A and card B.
            for ul in lists:
                if len(ul) != 2:
                    raise ValueError(f"a banned pair lists {ul}, not two cards")
                state.pairs.add(frozenset(ul))
        else:
            for card in (c for ul in lists for c in ul):
                state.status[card] = "banned" if label == "Banned Cards" else "restricted"
    return state


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=dt.date.today().isoformat())
    ap.add_argument("--online", action="store_true")
    args = ap.parse_args()
    formats, designations, bans = load()
    flat = opjson.flatten(opjson.load_sets(), opjson.load_cards())
    errors = validate(formats, designations, bans, set(flat["cards"]))
    state = ban_state(bans, args.as_of)
    if args.online:
        req = urllib.request.Request(BANDAI_LIST, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            live = bandai_current(resp.read().decode("utf-8"))
        if live.status != state.status:
            errors.append(f"ban list differs from Bandai's: opjson {sorted(state.status.items())}, "
                          f"Bandai {sorted(live.status.items())}")
        if live.pairs != state.pairs:
            errors.append(f"banned pairs differ from Bandai's: opjson {sorted(map(sorted, state.pairs))}, "
                          f"Bandai {sorted(map(sorted, live.pairs))}")
    for e in errors:
        print(e)
    blocks: dict[str, list[str]] = {}
    for p in flat["printings"].values():
        blocks.setdefault(p["card"], []).append(p.get("block"))
    counts = {f["id"]: {s: 0 for s in STATUSES} for f in formats["formats"]}
    for p in flat["printings"].values():
        for fmt in formats["formats"]:
            counts[fmt["id"]][printing_legality(p, blocks[p["card"]], designations, fmt, state, args.as_of)] += 1
    print(f"as of {args.as_of}: {len(state.status)} banned/restricted cards, {len(state.pairs)} banned pairs; "
          f"printings by format: {counts}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
