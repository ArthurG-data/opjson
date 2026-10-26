import numpy as np
from PIL import Image, ImageDraw

import check_blocks


def icon(tmp_path, text, light_digit=False, name=None):
    """A 600x838 card whose block icon (a disc with text on it) sits at CENTER."""
    card = Image.new("L", check_blocks.SIZE, 140)
    d = ImageDraw.Draw(card)
    x, y = check_blocks.CENTER
    disc, digit = (20, 235) if light_digit else (235, 20)
    d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=disc)
    d.text((x - 3, y - 6), text, fill=digit)
    path = tmp_path / f"{name or text}.png"
    card.save(path)
    return path


def references(tmp_path):
    return {b: check_blocks.icon_patches(icon(tmp_path, b, name=f"ref{b}"))[(0, 0)] for b in ("1", "2", "3", "X")}


def test_each_icon_reads_as_its_own_block(tmp_path):
    refs = references(tmp_path)
    for b in refs:
        block, looks, margin = check_blocks.read(check_blocks.icon_patches(icon(tmp_path, b, name=f"t{b}")), refs)
        assert block == b and looks > 0.9 and margin > check_blocks.MIN_MARGIN


def test_a_light_digit_on_a_dark_disc_reads_the_same(tmp_path):
    refs = references(tmp_path)
    block, _, _ = check_blocks.read(check_blocks.icon_patches(icon(tmp_path, "2", light_digit=True, name="inv")), refs)
    assert block == "2"


def test_a_blank_corner_does_not_look_like_an_icon(tmp_path):
    refs = references(tmp_path)
    path = tmp_path / "blank.png"
    Image.fromarray((np.random.default_rng(0).random((838, 600)) * 255).astype("uint8")).save(path)
    _, looks, _ = check_blocks.read(check_blocks.icon_patches(path), refs)
    assert looks < check_blocks.MIN_SCORE


def printing(pid, set_id, block, source="bandai"):
    return {"id": pid, "card": pid.split("_")[0], "set": set_id, "block": block, "source": source}


def test_a_set_takes_the_block_its_own_cards_print():
    en = [{"language": "en"}]
    sets = [{"id": "OP05", "type": "booster", "releases": en}, {"id": "ST10", "type": "starter_deck", "releases": en},
            {"id": "P", "type": "promo", "releases": en},
            {"id": "OP05-PRE", "type": "promo", "source": "tcgplayer", "parent": "OP05", "releases": en},
            {"id": "EB04", "type": "extra_booster", "block": "4", "releases": [{"language": "ja"}]}]
    printings = ([printing(f"OP05-{i:03}", "OP05", "2") for i in range(1, 20)] + [printing("OP05-020", "OP05", "X")]
                 + [printing("OP01-001", "OP05", "1")]  # a reprint filed under OP05 does not count
                 + [printing(f"ST10-{i:03}", "ST10", "2") for i in range(1, 5)] + [printing("P-001", "P", "1")])
    assert check_blocks.set_blocks(sets, printings) == []
    # A Japanese-only set keeps the block import_bandai_ja gave it.
    assert [s.get("block") for s in sets] == ["2", "2", None, None, "4"]


def test_a_set_whose_cards_disagree_gets_no_block():
    sets = [{"id": "ST16", "type": "starter_deck", "releases": [{"language": "en"}]}]
    printings = [printing(f"ST16-{i:03}", "ST16", "2" if i < 7 else "3") for i in range(1, 11)]
    left = check_blocks.set_blocks(sets, printings)
    assert "block" not in sets[0] and left[0]["reason"] == "base printings disagree"
