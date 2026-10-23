import import_logos

NEW = ('<img src="/onepiececg/bccard/en/products/2026/09/18/x/logo_product.webp" '
       'alt="BOOSTER PACK  -THE DOMINANCE OF GOD- [OP-18]">')
OLD = '<img src="../../images/products/boosters/op01/mv_01.jpg?v3" alt="ROMANCE DAWN">'
PAGE = "https://en.onepiece-cardgame.com/products/op18.html"


def test_logo_and_its_set_code_are_read_from_a_new_style_page():
    assert import_logos.find_logos(OLD + NEW + NEW, PAGE) == [
        ("https://en.onepiece-cardgame.com/onepiececg/bccard/en/products/2026/09/18/x/logo_product.webp", ["OP18"])]


def test_a_page_with_only_a_banner_or_an_anniversary_logo_has_no_logo():
    anniversary = '<img src="./images/logo_3rd-anniv.webp" alt="3rd Anniversary">'
    assert import_logos.find_logos(OLD + anniversary, PAGE) == []


def test_without_a_bracket_the_code_comes_from_the_page_address():
    page = '<img src="./images/mv_logo.png" alt="BOOSTER PACK-AWAKENING OF THE NEW ERA-">'
    url = "https://en.onepiece-cardgame.com/products/boosters/op05/"
    assert import_logos.find_logos(page, url) == [
        ("https://en.onepiece-cardgame.com/products/boosters/op05/images/mv_logo.png", ["OP05"])]
    assert import_logos.page_code("https://en.onepiece-cardgame.com/products/boosters/op14-eb04.php") == "OP14-EB04"
    assert import_logos.page_code("https://en.onepiece-cardgame.com/products/sleeve046.html") is None


def test_codes_map_to_set_ids():
    assert [import_logos.set_id(c) for c in ("OP-18", "PRB-02", "OP14-EB04", "st-21")] == [
        "OP18", "PRB02", "OP14-EB04", "ST21"]


def test_only_a_logo_naming_one_known_set_is_applied():
    sets = [{"id": "OP18", "releases": [{"language": "en", "name": "x", "source": "s"}]},
            {"id": "ST01", "releases": [{"language": "en", "name": "y", "source": "s", "logo": {"url": "old", "source": "p"}}]}]
    applied, review = import_logos.apply(sets, [
        ("p1", "logo1", ["OP18"]), ("p2", "logo2", ["ST01", "ST02"]), ("p3", "logo3", ["DP13"]), ("p4", "logo4", [])])
    assert applied == 1
    assert sets[0]["releases"][0]["logo"] == {"url": "logo1", "source": "p1"}
    assert "logo" not in sets[1]["releases"][0]  # a stale logo goes when no page names the set any more
    assert sorted(r["reason"] for r in review) == ["names no set", "names several sets", "set not in sets.json"]


def test_two_pages_disagreeing_on_a_set_logo_apply_neither():
    sets = [{"id": "OP18", "releases": [{"language": "en", "name": "x", "source": "s"}]}]
    applied, review = import_logos.apply(sets, [("p1", "a", ["OP18"]), ("p2", "b", ["OP18"])])
    assert applied == 0 and "logo" not in sets[0]["releases"][0]
    assert review[0]["reason"] == "several pages give different logos"


def test_index_links_are_absolute_and_unique():
    page = ('<a href="https://en.onepiece-cardgame.com/products/op18.html"></a><a href="/products/boosters/op01.php">'
            '</a><a href="/products/op18.html"></a><a href="/products/?subcategory=decks"></a>')
    assert import_logos.product_links(page) == ["https://en.onepiece-cardgame.com/products/op18.html",
                                                "https://en.onepiece-cardgame.com/products/boosters/op01.php"]
