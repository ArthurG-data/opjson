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
