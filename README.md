# opjson

An open dataset of One Piece Card Game sets, cards, printings, sealed products and format legality, in English.
Each printing carries Bandai's printing id and the TCGplayer product ids that sell it. Bandai's official card list
gives every printing an id but no product links, and TCGplayer lists products with no printing ids. opjson ties
the two together card by card. A TCGplayer product is matched to a printing by card number and by comparing the
two sites' card images. Nothing is matched by name order, and a product the images cannot settle goes to a review
file rather than into a guess.

Release 0.2.4 holds 86 sets, 2,876 cards, 7,409 printings and 445 sealed products.

## Using the data

Each tagged release attaches five files to a GitHub release:

```
https://github.com/ArthurG-data/opjson/releases/latest/download/AllSets.json
https://github.com/ArthurG-data/opjson/releases/latest/download/AllCards.json
https://github.com/ArthurG-data/opjson/releases/latest/download/AllPrintings.json
https://github.com/ArthurG-data/opjson/releases/latest/download/AllProducts.json
https://github.com/ArthurG-data/opjson/releases/latest/download/Legality.json
```

Every file is `{"meta": {"version": "0.2.4", "date": "2026-10-24"}, "data": {...}}`. All five come from one
build, so a reader that downloads them separately can check that the versions agree.

| File | Keyed by | Holds |
|---|---|---|
| `AllSets.json` | set id (`OP01`, `OP02-PRE`) | type, Bandai series id, block, TCGplayer group ids, and per release the name, date, logo and key art |
| `AllCards.json` | card number (`OP03-055`) | the facts every printing of the card shares |
| `AllPrintings.json` | printing id (`OP03-055_p2`) | set, rarity, block, finishes, treatments, promo types, image link, artist, TCGplayer product ids |
| `AllProducts.json` | product id (`romance-dawn-booster-box-wave-1-blue`) | category, set, TCGplayer product id, release date, contents and the sources that state them |
| `Legality.json` | `formats`, `bans`, `blockDesignations` | the formats and their block windows, every ban and restriction, Bandai's per-card block exceptions |

## Layout

- `sets/sets.json` lists every set. That covers Bandai's series (`OP01`, `ST01`, `EB01`, `PRB01`, `OP14-EB04`,
  `P` for promos, `OTHER` for cards from other products). It also covers TCGplayer groups that are not a Bandai
  series: pre-release, release-event and anniversary stamp sets (`OP02-PRE`, `OP10-RE`, `OP05-ANN`) and promo
  lines (`OP-DD`, `OP-RP`, `LT01`, `SD01`, `OP-CS`). Each set has a `type` and, for a stamp set, a `parent`.

  | type | AutoMana / MTG set type |
  |---|---|
  | booster | expansion |
  | extra_booster | extra_booster |
  | premium_booster | masters |
  | starter_deck, ultra_deck | starter |
  | promo | promo |
  | box_set | box |

- `data/cards/<prefix>.json` holds the cards by number prefix (`OP01-120` lives in `OP01.json`). A card holds
  the facts every printing shares, and its `printings` list every printing of it.
- `data/sealed/<set>.json` holds the sealed products of a set.
- `legality/` holds `formats.json`, `bans.json` and `block_designations.json`. Each entry cites the Bandai page or
  announcement it comes from.
- `mappings/` holds hand-kept inputs to the tools. `bandai_corrections.json` fixes the places where Bandai's card
  list contradicts itself, citing the card image that settles each one. `sealed_curated.json` adds products
  TCGplayer does not sell. `tcgplayer_tags.json` maps the tags at the end of a TCGplayer product name
  (`(Parallel)`, `(Manga)`, `(Jolly Roger Foil)`) to treatments and promo types.
- `review/` lists what the tools could not decide, file by file (see [Review files](#review-files)).

The formats are `schema/sets.schema.json`, `schema/cards.schema.json` and `schema/sealed.schema.json`.

### Cards and printings

```json
{
  "number": "OP03-055",
  "name": "Gum-Gum Giant Gavel",
  "category": "Event",
  "cost": 1,
  "colors": ["Blue"],
  "types": ["East Blue", "Straw Hat Crew"],
  "printings": [
    {"id": "OP03-055", "set": "OP03", "rarity": "C", "block": "1", "source": "bandai",
     "image": "https://en.onepiece-cardgame.com/images/cardlist/card/OP03-055.png",
     "cardSet": "-PILLARS OF STRENGTH- [OP03]", "finishes": ["nonfoil"],
     "identifiers": {"tcgplayerProductIds": [499985]},
     "tcgplayer": {"name": "Gum-Gum Giant Gavel", "match": "image-only-candidate", "distance": 3}},
    {"id": "OP03-055_p3", "set": "PRB01", "rarity": "C", "block": "1", "source": "bandai",
     "finishes": ["foil"], "promoTypes": [{"type": "textured", "category": "foil-pattern"}],
     "identifiers": {"tcgplayerProductIds": [593886]}, "artist": "Studio Vigor Co. Ltd",
     "tcgplayer": {"name": "Gum-Gum Giant Gavel (Textured Foil)", "match": "image+order", "distance": 4}},
    {"id": "OP03-055~tcg501666", "set": "OP03-PRE", "rarity": "C", "source": "tcgplayer", "artOf": "OP03-055",
     "finishes": ["nonfoil"], "promoTypes": [{"type": "prerelease", "category": "event"}],
     "identifiers": {"tcgplayerProductIds": [501666]}}
  ]
}
```

- **Printing ids.** Bandai's printings keep Bandai's id: `OP01-120` is the base, `OP01-120_p1` a parallel or
  alternate art, `OP01-120_r1` a reprint. Printings only TCGplayer sells, which covers stamps and most promos,
  get an id minted from the card number and the product id (`OP03-055~tcg501666`).
- **`artOf`** names the printing whose art a printing carries, when the images agree. A stamped pre-release copy
  points at its base printing, and a reprint that reuses an earlier printing's art points at that printing.
- **`treatments`** are the art treatment: parallel, alternate_art, manga, sp, full_art, wanted_poster, reprint,
  gold or serial.
- **`promoTypes`** are the programs a printing comes from, each with a `category` (event, championship, retail,
  foil-pattern and so on).
- **`finishes`** are nonfoil and/or foil, from TCGplayer's price subtypes. A printing TCGplayer does not price
  gets a finish only from a rule in `tools/infer_finishes.py`, which applies to a kind of printing only while
  every priced printing of that kind agrees. Today the one rule makes a Bandai reprint (`_rN`) of a Common or
  Uncommon with no art treatment nonfoil. `review/inferred-finishes.json` lists each printing a rule filled, and
  any other printing TCGplayer does not price has no `finishes`. Named foils are promo types with the
  category `foil-pattern`, not finishes, the way Scryfall records Magic's surge and galaxy foils. PRB-01 prints
  each of its reprints twice in foil: a Jolly Roger Foil and a Textured Foil with the same number, rarity and art.
  Bandai files the Jolly Roger Foil as the lower `_pN` and the Textured Foil as the next one. The Textured Foil
  also has a star printed above the rarity code. So `OP03-055_p2` is the Jolly Roger Foil and `OP03-055_p3` the
  Textured Foil.
- **`tcgplayer`** records how each TCGplayer product was matched: the product name, the kind of evidence (`match`)
  and the image hash distance (see [TCGplayer products](#tcgplayer-products)).
- **`block`** is the block icon printed on the card, used for Standard legality.
- **`artist`** is the illustrator, where Limitless TCG credits one.

DON!! cards are one card, `DON`, with one printing per art.

### Sealed products

```json
{
  "id": "tournament-kit-vol-7",
  "set": "P",
  "category": "tournament_kit",
  "name": "Tournament Kit Vol. 7",
  "contentsStatus": "partial",
  "contents": {"sealed": [{"product": "tournament-pack-vol-7"}, {"product": "winner-pack-vol-7"},
                          {"product": "judge-pack-vol-3"}]},
  "sources": ["https://en.onepiece-cardgame.com/events/2024/store_tournament_vol7/"]
}
```

- **`category`** is one of booster_pack, sleeved_booster_pack, booster_box, case, display, double_pack,
  starter_deck, ultra_deck, premium_card_collection, gift_collection, tin, illustration_box, collection,
  promo_pack, tournament_kit or other.
- **`contents`** lists only what a source states. A booster pack's `pool` is the sets whose cards it can hold,
  with no odds. A deck's `cards` are the printings Bandai files under the deck, with no counts, because the card
  list gives none. A display, case or kit names the `sealed` products it holds, with no counts unless a source
  gives one.
- **`contentsStatus`** is `partial` when the contents are known but incomplete, and `unknown` when no source
  states them. No product is `complete` yet, because no source in reach states every count.
- **Tournament kits.** The kit Bandai sends a store for each Store Tournament, holding its participation, winner
  and judge packs, is a product of its own. TCGplayer does not sell the kits, so they come from
  `mappings/sealed_curated.json`, each citing Bandai's event page. A kit that hands out a promotion card set names
  it too.

## Where the data comes from

- **Cards, printings and sets.** `tools/crawl_bandai.py` caches every English series page of Bandai's official
  card list (`en.onepiece-cardgame.com/cardlist/`), one page every 2 seconds. `tools/import_bandai.py` writes the
  sets, the cards and Bandai's printings from that cache. Card facts are numbers, names, categories, costs, power,
  counters, life, colours, types, attributes and rarities. Effect and rules text are never copied (see `NOTICE`).
- **Block icons.** Bandai's list sometimes gives a printing a different block from the one printed on it. Every
  OP-05 card prints block 2, while the list gives 1 for most of them. `tools/check_blocks.py` reads the icon on
  each card image, compares it with reference icons and takes the printed block where the icon reads clearly.
  It also gives each set the block its base printings agree on.
- **TCGplayer products.** `tools/import_tcgplayer.py` reads TCGplayer's category 68 through tcgcsv.com (see
  [TCGplayer products](#tcgplayer-products)).
- **Shared art.** `tools/link_reprint_art.py` points a reprint or parallel that reuses an earlier printing's art at
  that printing, through `artOf`. The two then share one illustration and one artist credit.
- **Logos and key art.** `tools/import_logos.py` takes each set's logo from its Bandai product page, where the page
  shows one. Older pages have only a banner. `tools/import_key_art.py` takes the main visual of each booster and
  starter deck page, cropped to the artwork. A booster whose page has no single main visual takes its pack's
  TCGplayer picture instead. Both are links, never copies.
- **Sealed products.** `tools/import_sealed.py` writes TCGplayer's sealed products, classified by an ordered list
  of name rules, then adds the curated products and contents in `mappings/sealed_curated.json`.
- **Illustrators.** `tools/import_limitless.py` credits each printing's artist from Limitless TCG, which lists the
  printings of every artist by Bandai's own id. The same crawl compares Limitless's TCGplayer product for each
  printing with the image match. Where they disagree, both go to `review/limitless-crosscheck.json` and nothing
  changes.
- **Legality.** `legality/` is kept by hand from Bandai's announcements and its Banned/Restricted page.
  - `formats.json` gives each format its windows of allowed blocks: Standard allows blocks 2 to 5 from
    2026-04-01 to 2027-03-31.
  - `bans.json` records each ban, restriction and banned pair with the date it took effect. Bandai bans some cards
    only in pairs. A ban whose start Bandai never dated has `inForceBy`, the date of the first page that shows it.
  - `block_designations.json` holds Bandai's per-card exceptions to the block rule: cards that are always legal,
    cards assigned to a given block, and reprinted cards.

  `tools/legality.py --online` replays the list to today and checks it against the "Cards with Active
  Restrictions" section of Bandai's current page.

### TCGplayer products

A single is matched to a Bandai printing only when its card number agrees and the two images agree. The images
are compared by perceptual hash over the top band of the card, because Bandai's scans carry a "SAMPLE" mark
across the middle. The hash distance must be at most 28 bits, and the next-best candidate must be at least 20 bits
further away. When the images are too close to call, the evidence goes in this order:

1. The whole card is compared, since its lower half carries the stamps the top band ignores (`whole-card`).
2. The product's name tag picks between Bandai's kinds: "(Reprint)" is a `_rN` printing, and a parallel,
   alternate-art or foil-pattern tag is a `_pN` one (`image+name`).
3. Foil-pattern copies of one card that are still tied take its `_pN` printings in Bandai's order, Jolly Roger
   Foil then Textured Foil (`image+order`).
4. A promo whose art is shared by two printings is settled by Bandai's "Card Set(s)" field when a tag names exactly
   one of them (`image+cardset`).

A product TCGplayer lists without an image is matched by name, but only where the name leaves no choice (`name`).
A promo never takes a printing Bandai files in a set that has its own TCGplayer group, unless a tag names that
printing's card set. Pre-release, release-event, anniversary and most promo products are not on Bandai's list.
They become printings of their own (`minted`), with `artOf` naming the printing whose art they carry.

## Review files

| File | Lists |
|---|---|
| `review/tcgplayer-68.json` | TCGplayer products no evidence could match with confidence |
| `review/limitless-crosscheck.json` | printings where Limitless's TCGplayer product and the image match disagree |
| `review/blocks.json` | block corrections, and icons that did not read clearly |
| `review/reprint-art.json` | printings whose art is close to an earlier one but not close enough to link |
| `review/logos.json`, `review/key_art.json` | logos and visuals that name no set, or several |
| `review/artists.json` | printings whose artist credit, read from the card edge, gave readings that disagree |

`uv run python tools/coverage.py` reports where every TCGplayer product in category 68 ended up: on a Bandai
printing, on a minted printing, on a sealed product, in review, or in a set Bandai has not published yet.
`--strict` exits 1 if any product is unaccounted for or still in review.

## Building

```sh
uv sync --group dev
uv run python tools/crawl_bandai.py                  # cache the official card list (one page every 2 s)
uv run python tools/import_bandai.py                 # sets and Bandai printings
uv run --group dev python tools/images.py fetch      # cache both sites' card images
uv run --group dev python tools/check_blocks.py      # the block icon printed on each card, where the list differs
uv run --group dev python tools/import_tcgplayer.py  # TCGplayer ids, stamped and promo printings
uv run --group dev python tools/link_reprint_art.py  # reprints that reuse an earlier printing's art (artOf)
uv run python tools/infer_finishes.py                # finishes of unpriced printings, by rule (after import_tcgplayer)
uv run python tools/import_logos.py                  # set logos, where Bandai's product page shows one
uv run python tools/import_sealed.py                 # sealed products, then the curated ones
uv run --group dev python tools/import_key_art.py    # set key art (after import_logos and import_sealed)
uv run python tools/import_limitless.py              # illustrators, and a check of the TCGplayer ids
uv run python tools/validate.py [--online [--images]]
uv run python tools/legality.py [--online]           # ban list replayed and checked against Bandai's
uv run python tools/build.py --version 0.2.4         # dist/AllSets, AllCards, AllPrintings, AllProducts, Legality
```

The pages and images the tools download are cached under `.cache/`, which is never committed. A rebuild reads the
cache and does not crawl again unless a tool is given `--refresh`.

`validate.py` checks every file against its schema, every id and reference, and that no TCGplayer product sits
on two printings. `--online` also asks TCGCSV whether every TCGplayer product id still exists in category 68.
`--images` adds a HEAD request for every Bandai printing's image, about 5,000 of them, sent six at a time. A 5xx or
a dropped connection is tried three times before it counts as a failure.

## Development

```sh
uv sync --group dev
uv run pytest
uv run python tools/validate.py --online
uv run python tools/legality.py --online
```

CI runs those checks on every pull request and push to `main`. A `v*` tag also runs the image check
(`--online --images`), then builds the release files with the tag's version and attaches them to a GitHub release.

## Adding a product or fixing a card

- **A sealed product TCGplayer does not sell.** Add it to `products` in `mappings/sealed_curated.json`, with the
  page that states it in `sources`, and run `tools/import_sealed.py`.
- **Contents a page states for a TCGplayer product.** Add them to `contents` in the same file, with the page.
- **A card Bandai's list gets wrong.** Add the fix to `mappings/bandai_corrections.json`, with the card image that
  shows the right value.
- **A ban or a new format window.** Add it to `legality/`, with the announcement it comes from, and run
  `tools/legality.py --online`.

Contents and card facts are facts. Do not copy card text, product descriptions or images.

Card Kingdom sells no One Piece cards today; `identifiers.cardkingdomId` is reserved for when it does.

## Licence

The tools and tests are MIT (`LICENSE`). The data and schemas are CC BY 4.0 (`LICENSE-DATA`). See `NOTICE` for
what is and is not copied from the sources. One Piece and its marks belong to Eiichiro Oda/Shueisha, Toei
Animation and Bandai. opjson is not affiliated with them or with TCGplayer.
