"""A UUID for every set, card, oracle, printing, version and sealed product: given once, kept for good, the same
however often it is run.

    uv run python tools/uuids.py

Run it last, after every import tool, never in the middle of the chain. A UUID belongs to what a record is, which is
not always its id. A Bandai printing is its Bandai id in its language: Bandai numbers each language's _pN and _rN on
its own, so OP01-001_p1 and OP01-001_p1~ja are two printings. A printing opjson minted from TCGplayer and a sealed
product are a TCGplayer product, since their ids depend on the matcher and on product names. data/uuids.json maps
each identity key ever seen to its UUID, per kind:

- ``id:<set id>`` for a set, ``bandai:<language>:<Bandai id>`` for a Bandai printing, ``tcgplayer:<lowest product
  id>`` for a minted printing or a sealed product (``id:<product id>`` for one TCGplayer does not sell),
  ``id:<number>`` for a card.
- A version is one printing in every language it is printed in: an English printing with the Japanese printing whose
  twinOf names it. Its key is ``en:<English printing id>``, or ``ja:<Japanese printing id>`` for a Japanese printing
  with no English twin. Each printing of it carries its UUID as versionId.
- An oracle is one card for the game's rules, whatever its printings: ``number:<number>``. One Piece limits a deck to
  four cards of one card number, so two numbers are two cards even with the same text. A card carries its oracle's
  UUID as oracleId.
- An identity key seen for the first time gets ``uuid5(NAMESPACE, "<kind>:<record id>")``, so a rebuild from nothing
  gives the same UUIDs. If the record replaces one that left, it takes that record's UUID instead: a record's alias
  keys (its id, its TCGplayer products, a set's TCGplayer groups and Bandai series, the UUIDs of a version's or a
  card's printings, of an oracle's cards) name what each was last on, in ``bridges``. A printing TCGplayer sold
  before Bandai listed it keeps its UUID when Bandai lists it and the matcher moves the product onto it.
- A known identity key keeps its UUID. A record that leaves keeps its key, so it gets its UUID back if it returns.

The same design as rbjson's tools/uuids.py. ``keys`` only grows and never changes a value: that is the whole promise,
and ``history_errors`` checks it between two versions of the registry (validate.py --since, run in CI).
"""
from __future__ import annotations

import collections
import json
import uuid
from pathlib import Path

import opjson

NAMESPACE = opjson.NAMESPACE
REGISTRY = opjson.ROOT / "data" / "uuids.json"
KINDS = ("sets", "printings", "versions", "cards", "oracles", "products")
# The field each kind's UUID is stamped as, and the field it follows. Versions and oracles are stamped on their
# members: a version's on each printing, an oracle's on its card.
FIELD = {"sets": ("uuid", "id"), "printings": ("uuid", "id"), "versions": ("versionId", "uuid"),
         "cards": ("uuid", "number"), "oracles": ("oracleId", "uuid"), "products": ("uuid", "id")}
MEMBERS = {"versions": "printings", "oracles": "cards"}


class Conflict(Exception):
    """Two live records whose identity keys hold one UUID: a record that came back while the one that took its UUID
    is still here. A person decides which is which."""


def empty() -> dict:
    return {k: {"keys": {}, "bridges": {}} for k in KINDS}


def parse(text: str) -> dict:
    """A registry from its JSON, with every kind: one written before a kind existed holds none of it."""
    registry = json.loads(text)
    for kind in KINDS:
        registry.setdefault(kind, {"keys": {}, "bridges": {}})
    return registry


def load(path: Path = REGISTRY) -> dict:
    return parse(path.read_text(encoding="utf-8")) if path.exists() else empty()


def save(registry: dict, path: Path = REGISTRY) -> None:
    """Keys sorted, so a run that changes nothing leaves the file as it was."""
    opjson.write_atomic(path, json.dumps(registry, indent=2, sort_keys=True) + "\n")


def first(kind: str, rid: str, used: set[str]) -> str:
    """The UUID of a record first seen: uuid5 of its kind and id, or of ``<kind>:<id>#2`` and on in the rare case that
    UUID is taken."""
    n = 1
    while True:
        u = str(uuid.uuid5(NAMESPACE, f"{kind}:{rid}" + (f"#{n}" if n > 1 else "")))
        if u not in used:
            return u
        n += 1


def _products(record: dict) -> list[int]:
    return sorted(record.get("identifiers", {}).get("tcgplayerProductIds", []))


def identity(kind: str, record: dict) -> str:
    """The key a record's UUID belongs to: what the record is, which outlives its id."""
    if kind in ("versions", "oracles"):
        return record["id"]
    if kind == "cards":
        return f"id:{record['number']}"
    if kind == "sets":
        return f"id:{record['id']}"
    products = _products(record)
    if kind == "printings":
        if record["source"] == "tcgplayer":
            return f"tcgplayer:{products[0]}"
        return f"bandai:{opjson.language(record)}:{record['id'].removesuffix('~ja')}"
    return f"tcgplayer:{products[0]}" if products else f"id:{record['id']}"


def _aliases(kind: str, record: dict) -> list[str]:
    """Every key the record answers to: its identity, its id, its TCGplayer products, a set's groups and series, the
    UUIDs of a version's or a card's printings, of an oracle's cards."""
    if kind == "versions":
        return [identity(kind, record), *sorted(f"printing:{p['uuid']}" for p in record["printings"])]
    if kind == "oracles":
        return [identity(kind, record), *sorted(f"card:{c['uuid']}" for c in record["cards"])]
    if kind == "cards":
        return [identity(kind, record), *sorted(f"printing:{p['uuid']}" for p in record["printings"])]
    if kind == "sets":
        series = [f"bandai-series:{record['bandaiSeriesId']}"] if "bandaiSeriesId" in record else []
        return [identity(kind, record), *(f"tcgplayer-group:{g}" for g in record.get("tcgplayerGroupIds", [])),
                *series]
    return list(dict.fromkeys([identity(kind, record), f"id:{record['id']}",
                               *(f"tcgplayer:{pid}" for pid in _products(record))]))


def _assign(registry: dict, kind: str, records: dict[str, dict]) -> dict[str, str]:
    """{record id: UUID} for the live ``records`` of ``kind``; records new identity keys and the bridges in
    ``registry``. Nothing is written into the registry unless every record gets a UUID."""
    keys, bridges = registry[kind]["keys"], registry[kind]["bridges"]
    ident = {rid: identity(kind, r) for rid, r in records.items()}
    out: dict[str, str] = {}
    held: dict[str, str] = {}  # UUID -> the live record id holding it
    for rid in sorted(records, key=lambda r: ident[r]):
        u = keys.get(ident[rid])
        if u is None:
            continue
        if u in held:
            raise Conflict(f"{kind[:-1]} {rid} ({ident[rid]}) and {held[u]} both hold {u}: one of them came back "
                           f"after the other took its UUID")
        out[rid], held[u] = u, rid
    used = set(keys.values()) | set(bridges.values())
    for rid in sorted((r for r in records if r not in out), key=lambda r: ident[r]):
        # a record that left, named by one of this record's keys: the first alias that names a free UUID
        u = next((h for a in _aliases(kind, records[rid]) if (h := keys.get(a) or bridges.get(a)) and h not in held), None)
        u = u or first(kind, rid, used)
        out[rid], held[u] = u, rid
        used.add(u)
    for rid, record in records.items():
        keys.setdefault(ident[rid], out[rid])
        for alias in _aliases(kind, record):
            if alias != ident[rid]:
                bridges[alias] = out[rid]
    return out


def _stamp(record: dict, after: str, u: str, field: str) -> None:
    """Put ``field`` right after the record's ``after`` field, in place."""
    rest = {k: v for k, v in record.items() if k != field}
    record.clear()
    for k, v in rest.items():
        record[k] = v
        if k == after:
            record[field] = u


def _versions(files: dict[str, dict]) -> dict[str, dict]:
    """{version key: {"id": key, "printings": [...]}}: an English printing with its Japanese twin."""
    out: dict[str, dict] = {}
    for body in files.values():
        for card in body["cards"]:
            for p in card["printings"]:
                if opjson.language(p) == "en":
                    key = f"en:{p['id']}"
                else:
                    key = f"en:{p['twinOf']}" if "twinOf" in p else f"ja:{p['id']}"
                out.setdefault(key, {"id": key, "printings": []})["printings"].append(p)
    return out


def _oracles(files: dict[str, dict]) -> dict[str, dict]:
    """{"number:<number>": {"id": key, "cards": [card]}}: one oracle per card number."""
    return {f"number:{c['number']}": {"id": f"number:{c['number']}", "cards": [c]}
            for body in files.values() for c in body["cards"]}


def _live(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict]) -> dict[str, dict[str, dict]]:
    """{kind: {record id: record}}, in the order the kinds are assigned. Versions and cards are built after the
    printings have their UUIDs, since their aliases are those UUIDs; the grouping does not depend on them."""
    return {"sets": {s["id"]: s for s in sets},
            "printings": {p["id"]: p for b in files.values() for c in b["cards"] for p in c["printings"]},
            "versions": _versions(files),
            "cards": {c["number"]: c for b in files.values() for c in b["cards"]},
            "oracles": _oracles(files),
            "products": {p["id"]: p for b in sealed.values() for p in b["products"]}}


def assign(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict], registry: dict) -> None:
    """Stamp every record of sets, files and sealed with its UUID, in place, and record them in ``registry``. Each
    kind goes after the ones its aliases name: printings before versions and cards, cards before oracles."""
    for kind, records in _live(sets, files, sealed).items():
        out = _assign(registry, kind, records)
        field, after = FIELD[kind]
        for rid, record in records.items():
            for target in record[MEMBERS[kind]] if kind in MEMBERS else [record]:
                _stamp(target, after, out[rid], field)


def _held(kind: str, record: dict) -> set[str]:
    """The UUIDs a live record holds: its own, or for a version or an oracle what its members carry."""
    field = FIELD[kind][0]
    targets = record[MEMBERS[kind]] if kind in MEMBERS else [record]
    return {t[field] for t in targets if field in t}


def errors(sets: list[dict], files: dict[str, dict], sealed: dict[str, dict], registry: dict) -> list[str]:
    """The records whose UUID is missing or is not the one data/uuids.json gives their identity, and any UUID two
    records share."""
    found: list[str] = []
    for kind, records in _live(sets, files, sealed).items():
        keys = registry[kind]["keys"]
        field = FIELD[kind][0]
        every: collections.Counter = collections.Counter()
        for rid, record in sorted(records.items()):
            key = identity(kind, record)
            if kind in MEMBERS:
                for member in record[MEMBERS[kind]]:
                    if member.get(field) != keys.get(key):
                        name = f"printing {member['id']}" if kind == "versions" else f"card {member['number']}"
                        found.append(f"{name}: {field} {member.get(field)} is not the one data/uuids.json gives "
                                     f"{key}, {keys.get(key)}: run tools/uuids.py")
                every.update(_held(kind, record))
                continue
            name = {"sets": "set", "printings": "printing", "cards": "card", "products": "sealed product"}[kind]
            if field not in record:
                found.append(f"{name} {rid} has no uuid: run tools/uuids.py")
                continue
            if keys.get(key) != record[field]:
                found.append(f"{name} {rid}: uuid {record[field]} is not the one data/uuids.json gives {key}, "
                             f"{keys.get(key)}: run tools/uuids.py")
            every[record[field]] += 1
        what = {"versions": "versions", "oracles": "oracles"}.get(kind, "records")
        found += [f"{'uuid' if kind not in MEMBERS else field} {u} is on {n} {what}"
                  for u, n in sorted(every.items()) if n > 1]
    return found


def history_errors(before: dict, after: dict) -> list[str]:
    """What breaks the promise between two versions of the registry: an identity key dropped or given another UUID."""
    found = []
    for kind in KINDS:
        now = after[kind]["keys"]
        for key, u in sorted(before[kind]["keys"].items()):
            if key not in now:
                found.append(f"{kind[:-1]} {key}: its uuid {u} was dropped from data/uuids.json")
            elif now[key] != u:
                found.append(f"{kind[:-1]} {key}: its uuid changed from {u} to {now[key]}")
    return found


def _dump(path: Path, body) -> None:
    opjson.write_atomic(path, json.dumps(body, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    registry = load()
    sets, files, sealed = opjson.load_sets(), opjson.load_cards(), opjson.load_sealed()
    assign(sets, files, sealed, registry)
    _dump(opjson.SETS, sets)
    for stem, body in files.items():
        _dump(opjson.CARDS / f"{stem}.json", body)
    for stem, body in sealed.items():
        _dump(opjson.SEALED / f"{stem}.json", body)
    save(registry)
    live = _live(sets, files, sealed)
    retired = {k: len(set(registry[k]["keys"].values()) - set().union(*(_held(k, r) for r in live[k].values())))
               for k in KINDS}
    print("uuids: " + ", ".join(f"{len(live[k])} {k} ({retired[k]} retired)" for k in KINDS))


if __name__ == "__main__":
    main()
