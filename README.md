# opjson

An open dataset of One Piece Card Game sets, cards, printings and sealed products, in English. Each printing
carries Bandai's printing id and the TCGplayer product ids that sell it. TCGplayer products are tied to
printings by card number and by comparing the two sites' card images; nothing is matched by name order.

## Layout

- `sets/sets.json`: every set. Bandai's series (`OP01`, `ST01`, `EB01`, `PRB01`, `OP14-EB04`, `P` for promos,
  `OTHER` for cards from other products), plus TCGplayer groups that are not one Bandai series: pre-release,
  release-event and anniversary stamp sets (`OP02-PRE`, `OP10-RE`, `OP05-ANN`) and promo lines (`OP-DD`,
  `OP-RP`, `LT01`, `SD01`, `OP-CS`). Each set has a `type` and, for a stamp set, a `parent`:

  | type | AutoMana / MTG set type |
  |---|---|
  | booster | expansion |
  | extra_booster | extra_booster |
  | premium_booster | masters |
  | starter_deck, ultra_deck | starter |
  | promo | promo |
  | box_set | box |

- `data/cards/<prefix>.json`: cards by number prefix (`OP01-120` lives in `OP01.json`). A card holds the
  facts every printing shares; its `printings` are:
  - Bandai's printings, keyed by Bandai's id: `OP01-120` (base), `OP01-120_p1` (parallel or alternate art),
    `OP01-120_r1` (reprint);
  - printings only TCGplayer sells (stamps and most promos), keyed `<number>~tcg<productId>`, with `artOf`
    naming the Bandai printing whose art they carry when the images agree.

  A printing's `treatments` are its art treatment (parallel, alternate_art, manga, sp, full_art,
  wanted_poster, reprint, gold, serial), and its `promoTypes` the promo programs it comes from, each with a
  category. Named foils (Pirate Foil, Jolly Roger Foil, Textured Foil) are promo types, not finishes;
  `finishes` is nonfoil and/or foil, from TCGplayer's price subtypes.
- `data/sealed/<set>.json`: TCGplayer's sealed products. `contentsStatus` is `partial` or `unknown` today:
  booster packs list their card `pool`, decks list their printings without counts, and displays and cases
  name the product they hold without a count, because no source in reach states the counts.

The formats are `schema/sets.schema.json`, `schema/cards.schema.json` and `schema/sealed.schema.json`.

## Building

```sh
uv sync --group dev
uv run python tools/crawl_bandai.py                 # cache the official card list (one page every 2 s)
uv run python tools/import_bandai.py                # sets and Bandai printings
uv run --group dev python tools/images.py fetch     # cache both sites' card images
uv run --group dev python tools/import_tcgplayer.py # TCGplayer ids, stamped and promo printings
uv run --group dev python tools/link_reprint_art.py # reprints that reuse an earlier printing's art (artOf)
uv run python tools/import_sealed.py                # sealed products
uv run python tools/import_limitless.py             # illustrators, and a check of the TCGplayer ids
uv run python tools/validate.py [--online]
uv run python tools/legality.py [--online]          # ban list replayed and checked against Bandai's
uv run python tools/build.py --version 0.1.0        # dist/AllSets, AllCards, AllPrintings, AllProducts, Legality
```

A TCGplayer product that cannot be matched with confidence goes to `review/tcgplayer-68.json`, never into a
guess. Where Bandai's card list contradicts itself, `mappings/bandai_corrections.json` records the fix and the
card image that settles it.

Card Kingdom sells no One Piece cards today; `identifiers.cardkingdomId` is reserved for when it does.

## Licence

The tools and tests are MIT (`LICENSE`). The data and schemas are CC BY 4.0 (`LICENSE-DATA`). See `NOTICE` for
what is and is not copied from the sources. opjson is not affiliated with Bandai or TCGplayer.
