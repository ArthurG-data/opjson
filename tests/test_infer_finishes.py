import pytest

import infer_finishes as inf


def printing(pid, rarity="C", finishes=None, treatments=None, source="bandai"):
    p = {"id": pid, "rarity": rarity, "source": source}
    if finishes:
        p["finishes"] = finishes
    if treatments:
        p["treatments"] = treatments
    return p


def test_an_unpriced_common_reprint_becomes_nonfoil():
    ps = [printing("OP03-009_r1"), printing("OP02-034_r1", "UC")]
    filled = inf.infer(ps)
    assert [p["finishes"] for p in ps] == [["nonfoil"], ["nonfoil"]]
    assert filled[0] == {"printing": "OP03-009_r1", "finishes": ["nonfoil"], "rule": "plain_common_reprint"}


def test_other_printings_are_left_without_a_finish():
    ps = [printing("OP01-086_r1", "R"), printing("OP02-028_p1"), printing("ST01-001", "L"),
          printing("OP05-001_r1", treatments=["manga"]), printing("OP03-009~tcg1", source="tcgplayer")]
    assert inf.infer(ps) == []
    assert not any("finishes" in p for p in ps)


def test_a_priced_printing_keeps_its_finish():
    ps = [printing("OP03-009_r1", finishes=["nonfoil"]), printing("OP03-010_r1", treatments=["reprint"])]
    assert [f["printing"] for f in inf.infer(ps)] == ["OP03-010_r1"]


def test_a_priced_printing_that_disagrees_stops_the_run_before_any_change():
    ps = [printing("OP03-009_r1", finishes=["foil"]), printing("OP03-010_r1")]
    with pytest.raises(inf.RuleContradicted, match="OP03-009_r1"):
        inf.infer(ps)
    assert "finishes" not in ps[1]
