import link_reprint_art as lr

ART_A = 0
ART_A_RESCAN = 0b111  # 3 bits from ART_A
ART_B = (1 << 80) - 1  # 80 bits from ART_A
ART_A_CLOSE = (1 << 20) - 1  # 20 bits from ART_A: close, not the same


def printing(pid):
    return {"id": pid, "source": "bandai"}


def run(hashes):
    return lr.link([printing(p) for p in hashes], lambda p: hashes[p["id"]])


def test_a_reprint_with_the_base_art_points_at_the_base():
    links, close, missing = run({"OP01-120_r1": ART_A_RESCAN, "OP01-120": ART_A, "OP01-120_p1": ART_B})
    assert links == {"OP01-120_r1": "OP01-120"}
    assert close == [] and missing == []


def test_a_parallel_reusing_an_earlier_parallel_points_at_that_parallel():
    links, _, _ = run({"OP01-120": ART_A, "OP01-120_p1": ART_B, "OP01-120_p5": ART_B})
    assert links == {"OP01-120_p5": "OP01-120_p1"}


def test_a_close_pair_is_reviewed_not_linked():
    links, close, _ = run({"OP01-120": ART_A, "OP01-120_r1": ART_A_CLOSE})
    assert links == {}
    assert close == [{"printing": "OP01-120_r1", "nearest": "OP01-120", "distance": 20}]


def test_a_printing_without_an_image_is_reported_and_skipped():
    links, _, missing = run({"OP01-120": None, "OP01-120_r1": ART_A})
    assert links == {} and missing == ["OP01-120"]


def test_order_puts_the_base_then_parallels_then_reprints():
    ids = ["OP01-120_r2", "OP01-120_p10", "OP01-120", "OP01-120_p2", "OP01-120_r1"]
    assert sorted(ids, key=lr.order_key) == ["OP01-120", "OP01-120_p2", "OP01-120_p10", "OP01-120_r1", "OP01-120_r2"]
