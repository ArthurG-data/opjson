import io

import pytest
from PIL import Image

import images


def _jpeg(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (width, height), color=200).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "CACHE", tmp_path)
    return tmp_path


def _cached(source: str, key: str, body: bytes):
    path = images.path_for(source, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def test_a_landscape_tcgplayer_image_is_the_placeholder_not_a_scan(cache):
    # TCGplayer's "Image Coming Soon" is 400x229; a card scan is portrait, or padded to a square.
    path = _cached("tcgplayer", "288271", _jpeg(400, 229))
    assert images.fetch("tcgplayer", "288271", "unused") is None
    assert path.read_bytes() == b""  # remembered as a miss, like a 403


def test_portrait_and_square_tcgplayer_scans_are_kept(cache):
    _cached("tcgplayer", "1", _jpeg(287, 400))
    _cached("tcgplayer", "2", _jpeg(400, 400))
    assert images.fetch("tcgplayer", "1", "unused") is not None
    assert images.fetch("tcgplayer", "2", "unused") is not None


def test_only_card_images_are_checked_for_the_placeholder(cache):
    _cached("tcgplayer_art", "3", _jpeg(400, 229))
    assert images.fetch("tcgplayer_art", "3", "unused") is not None


def test_a_hash_cached_before_the_placeholder_was_recognised_is_not_used(cache):
    _cached("tcgplayer", "288271", _jpeg(400, 229))
    hashes = images.HashCache(cache / "hashes.json")
    hashes.data["tcgplayer/288271"] = 12345
    assert hashes.get("tcgplayer", "288271", "unused") is None
