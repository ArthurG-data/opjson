from pathlib import Path

import refresh


def stems(commands):
    return [(Path(c[1]).stem, c[2:]) for c in commands]


def test_a_daily_run_crawls_again_and_refreshes_nothing_weekly():
    got = stems(refresh.commands(weekly=False, cached=False))
    assert [s for s, _ in got] == [
        "crawl_bandai", "import_bandai", "images", "check_blocks", "import_tcgplayer", "link_reprint_art",
        "infer_finishes", "import_logos", "import_sealed", "import_key_art", "import_limitless", "crawl_bandai",
        "import_bandai_ja", "import_sealed_ja", "images", "link_twins", "uuids", "readme_counts"]
    assert got[2] == ("images", ["fetch"]) and got[14] == ("images", ["fetch"])
    assert got[0] == ("crawl_bandai", ["--refresh"])
    assert got[11] == ("crawl_bandai", ["--language", "ja", "--refresh"])
    assert ("import_logos", []) in got and ("import_bandai_ja", []) in got


def test_a_weekly_run_refreshes_the_english_and_japanese_product_pages_once():
    got = dict((s, a) for s, a in stems(refresh.commands(weekly=True, cached=False)) if s != "crawl_bandai")
    assert got["import_logos"] == ["--refresh"] and got["import_bandai_ja"] == ["--refresh-products"]
    # import_logos has just fetched the pages import_key_art reads, into the same cache.
    assert got["import_key_art"] == []


def test_a_cached_run_reads_the_cached_series_pages():
    got = stems(refresh.commands(weekly=False, cached=True))
    assert got[0] == ("crawl_bandai", []) and got[11] == ("crawl_bandai", ["--language", "ja"])


def test_prepare_forgets_misses_clears_limitless_weekly_and_moves_tcgcsv_aside(tmp_path):
    (tmp_path / "images" / "tcgplayer").mkdir(parents=True)
    (tmp_path / "images" / "tcgplayer" / "1.img").write_bytes(b"")
    (tmp_path / "limitless").mkdir()
    (tmp_path / "tcgcsv").mkdir()
    refresh.prepare(weekly=False, fresh_tcgcsv=False, cache=tmp_path)
    assert not (tmp_path / "images" / "tcgplayer" / "1.img").exists()
    assert (tmp_path / "limitless").exists() and (tmp_path / "tcgcsv").exists()
    refresh.prepare(weekly=True, fresh_tcgcsv=True, cache=tmp_path, today="2026-11-30")
    assert not (tmp_path / "limitless").exists()
    assert not (tmp_path / "tcgcsv").exists() and (tmp_path / "tcgcsv.2026-11-30").is_dir()


def test_prepare_does_nothing_for_a_cache_with_no_images_limitless_or_tcgcsv(tmp_path):
    refresh.prepare(weekly=True, fresh_tcgcsv=True, cache=tmp_path, today="2026-11-30")
    assert list(tmp_path.iterdir()) == []


def test_prepare_replaces_an_earlier_move_aside_of_the_same_day(tmp_path):
    (tmp_path / "tcgcsv").mkdir()
    (tmp_path / "tcgcsv.2026-11-30").mkdir()
    (tmp_path / "tcgcsv.2026-11-30" / "old").write_text("x")
    refresh.prepare(weekly=False, fresh_tcgcsv=True, cache=tmp_path, today="2026-11-30")
    assert not (tmp_path / "tcgcsv.2026-11-30" / "old").exists()
