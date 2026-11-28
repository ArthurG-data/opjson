import io
import json

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


def test_a_response_that_is_not_an_image_is_not_cached(cache, monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(images.time, "sleep", lambda s: None)
    monkeypatch.setattr(images.urllib.request, "urlopen",
                        lambda req, timeout: Response(b"<html>Service Unavailable</html>"))
    with pytest.raises(ValueError, match="not an image"):
        images.fetch("bandai", "OP01-001", "https://example.com/OP01-001.png")
    assert not images.path_for("bandai", "OP01-001").exists()

    monkeypatch.setattr(images.urllib.request, "urlopen", lambda req, timeout: Response(_jpeg(63, 88)))
    assert images.fetch("bandai", "OP01-001", "https://example.com/OP01-001.png").read_bytes() == _jpeg(63, 88)


def test_forget_misses_deletes_only_empty_files(tmp_path):
    (tmp_path / "tcgplayer").mkdir()
    (tmp_path / "tcgplayer" / "1.img").write_bytes(b"")
    (tmp_path / "tcgplayer" / "2.img").write_bytes(b"\x89PNG")
    assert images.forget_misses(tmp_path) == 1
    assert not (tmp_path / "tcgplayer" / "1.img").exists()
    assert (tmp_path / "tcgplayer" / "2.img").read_bytes() == b"\x89PNG"


def test_a_streak_of_misses_at_one_host_stops_despite_hits_at_the_other():
    streak = images.MissStreak(limit=3)
    for i in range(2):
        streak.record("bandai", f"b{i}", True)
        streak.record("tcgplayer", f"t{i}", False)
    streak.record("bandai", "b2", True)
    with pytest.raises(SystemExit, match="3 misses in a row at tcgplayer/t2"):
        streak.record("tcgplayer", "t2", False)


def test_a_hit_resets_the_streak_of_its_own_host():
    streak = images.MissStreak(limit=2)
    streak.record("tcgplayer", "t0", False)
    streak.record("tcgplayer", "t1", True)
    streak.record("tcgplayer", "t2", False)  # one in a row again: no stop


def _tcgcsv_cache(root, image_counts: list[int]):
    """A TCGCSV cache under root/.cache/tcgcsv with one group of singles, one per entry of image_counts."""
    cache = root / ".cache" / "tcgcsv"
    cache.mkdir(parents=True)
    (cache / "68_groups.json").write_text(json.dumps({"results": [{"groupId": 1}]}))
    rows = [{"productId": 100 + i, "groupId": 1, "name": f"Card {i}", "imageCount": count,
             "extendedData": [{"name": "Number", "value": f"OP16-{i:03d}"}]} for i, count in enumerate(image_counts)]
    (cache / "68_1_products.json").write_text(json.dumps({"results": rows}))
    (root / "data" / "cards").mkdir(parents=True)


def test_misses_on_products_tcgcsv_lists_without_an_image_do_not_stop_the_fetch(tmp_path, monkeypatch, capsys):
    # A new set's products have no scan yet. TCGCSV gives them imageCount 0, and the CDN answers 403.
    _tcgcsv_cache(tmp_path, [0] * 25)
    monkeypatch.setattr(images, "ROOT", tmp_path)
    monkeypatch.setattr(images, "fetch", lambda source, key, url: None)
    images._fetch_all()
    assert capsys.readouterr().out.strip().endswith("done 25")


def test_misses_on_products_tcgcsv_lists_with_an_image_still_stop_the_fetch(tmp_path, monkeypatch):
    _tcgcsv_cache(tmp_path, [0] * 5 + [1] * 20)
    monkeypatch.setattr(images, "ROOT", tmp_path)
    monkeypatch.setattr(images, "fetch", lambda source, key, url: None)
    with pytest.raises(SystemExit, match="20 misses in a row at tcgplayer/124"):
        images._fetch_all()
