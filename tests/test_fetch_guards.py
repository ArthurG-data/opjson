"""A page a site serves wrong (a maintenance page with a 200, a cut-off download) must not be cached, or read as a
page with nothing on it: the importers would drop the cards, logos or artists it should have listed."""
import io
from pathlib import Path

import pytest

import bandai
import crawl_bandai
import import_bandai_ja
import import_logos
import limitless
import opjson

FIXTURES = Path(__file__).parent / "fixtures"


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def serve(monkeypatch):
    """serve(body): every request answers body, with no wait."""
    def serve(body: str):
        monkeypatch.setattr(bandai.urllib.request, "urlopen", lambda req, timeout: Response(body.encode("utf-8")))
    monkeypatch.setattr(bandai.time, "sleep", lambda s: None)
    monkeypatch.setattr(limitless.time, "sleep", lambda s: None)
    return serve


def test_write_atomic_replaces_the_file_and_leaves_no_temporary_one(tmp_path):
    path = tmp_path / "sub" / "a.json"
    opjson.write_atomic(path, "old")
    opjson.write_atomic(path, "né")
    assert path.read_text(encoding="utf-8") == "né"
    assert [p.name for p in path.parent.iterdir()] == ["a.json"]


def test_write_atomic_keeps_the_old_file_when_the_write_fails(tmp_path, monkeypatch):
    path = tmp_path / "a.json"
    opjson.write_atomic(path, "old")
    monkeypatch.setattr(opjson.os, "replace", lambda a, b: (_ for _ in ()).throw(KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        opjson.write_atomic(path, "new")
    assert path.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_a_bandai_page_without_its_marker_is_not_cached(tmp_path, serve):
    serve("<html>Under maintenance</html>")
    with pytest.raises(bandai.UnexpectedPage):
        bandai.fetch("https://example.com/cardlist/?series=1", tmp_path, expect=bandai.CARDLIST_MARKER)
    assert list(tmp_path.iterdir()) == []
    serve(f'<select {bandai.CARDLIST_MARKER}></select>')
    bandai.fetch("https://example.com/cardlist/?series=1", tmp_path, expect=bandai.CARDLIST_MARKER)
    assert len(list(tmp_path.iterdir())) == 1


def test_a_product_page_fetched_again_without_its_marker_keeps_the_cached_one(tmp_path, serve, monkeypatch):
    """The weekly run fetches every English product page again. An error page served with a 200 must not replace
    the copy import_logos and import_key_art read."""
    monkeypatch.setattr(import_logos, "CACHE", tmp_path)
    url = "https://en.onepiece-cardgame.com/products/boosters/op01.php"
    good = f'<h4 class="prodStatusTit">{bandai.PRODUCT_MARKER_EN}</h4>'
    serve(good)
    assert import_logos.product_page(url) == good
    serve("<html>Under maintenance</html>")
    with pytest.raises(bandai.UnexpectedPage):
        import_logos.product_page(url, refresh=True)
    assert import_logos.product_page(url) == good


def test_a_japanese_product_page_without_its_marker_is_not_cached(tmp_path, serve, monkeypatch):
    monkeypatch.setattr(crawl_bandai, "CACHE", tmp_path)
    url = "https://www.onepiece-cardgame.com/products/boosters/op01.php"
    monkeypatch.setattr(import_bandai_ja, "product_pages", lambda series, printings: {"550101": url})
    serve("<html>メンテナンス中</html>")
    with pytest.raises(bandai.UnexpectedPage):
        import_bandai_ja.release_dates([], [], refresh=True)
    assert list((tmp_path / "ja").iterdir()) == []
    serve(f"<dt>{bandai.PRODUCT_MARKER_JA}</dt><dd>2022年7月22日</dd>")
    assert import_bandai_ja.release_dates([], [], refresh=True) == {"550101": "2022-07-22"}


def test_a_series_page_with_no_printing_stops_the_crawl():
    index = (FIXTURES / "bandai_op01.html").read_text(encoding="utf-8")
    series = bandai.parse_series(index)
    empty = index[:index.find('<dl class="modalCol"')]

    def fetch(url, cache, refresh, expect=None):
        return index if url.endswith(series[0].series_id) else empty

    with pytest.raises(bandai.UnexpectedPage, match=f"series {series[1].series_id}"):
        crawl_bandai.crawl(fetch=fetch)


def test_a_logo_index_with_no_product_stops_the_crawl():
    def fetch(url, cache, refresh):
        return "<html>nothing here</html>"

    with pytest.raises(bandai.UnexpectedPage, match="boosters index"):
        import_logos.crawl(False, fetch=fetch)


def test_limitless_paths_that_differ_only_in_punctuation_have_their_own_cache_files():
    a, b = '/cards?q=!artist:"A.B"', '/cards?q=!artist:"A B"'
    assert limitless.cache_name(a) != limitless.cache_name(b)
    assert limitless.cache_name(a) == limitless.cache_name(a)


def test_a_limitless_page_that_is_not_a_search_result_is_not_cached(tmp_path, serve):
    client = limitless.Client(tmp_path)
    serve("<html>Too many requests</html>")
    with pytest.raises(ValueError, match="not cached"):
        client.search("!set:OP01")
    assert list(tmp_path.iterdir()) == []
    serve('<div class="search-summary"> 0 cards found where ...</div>')
    assert client.search("!set:OP01") == []


def test_a_limitless_page_cached_under_the_old_name_is_read_and_renamed(tmp_path):
    path = '/cards?q=!set:OP01&display=list'
    old = tmp_path / "cards_q_set_OP01_display_list.html"
    old.write_text('<div class="search-summary"> 0 cards found</div>', encoding="utf-8")
    assert "0 cards found" in limitless.Client(tmp_path).get(path)
    assert [p.name for p in tmp_path.iterdir()] == [limitless.cache_name(path)]
