import copy

import check_losses
from test_opjson import CARDS, SETS


def tally(sets=SETS, cards=CARDS, sealed=None):
    return check_losses.tally(sets, cards, sealed or {})


def big_set(n: int, artists: int) -> dict:
    printings = [{"id": f"OP01-{i:03d}", "set": "OP01", "image": "x", "source": "bandai",
                  **({"artist": "A"} if i < artists else {})} for i in range(n)]
    return {"OP01": {"cards": [{"number": p["id"], "name": "N", "names": {"en": "N"}, "printings": [p]}
                               for p in printings]}}


def test_unchanged_data_has_no_loss():
    assert check_losses.losses(tally(), tally()) == []


def test_a_set_that_loses_its_printings_is_a_loss_and_a_gain_never_is():
    base, now = check_losses.tally(SETS, big_set(100, 0), {}), check_losses.tally(SETS, big_set(90, 0), {})
    assert check_losses.losses(base, now) == ["cards: 100 -> 90 (lost 10)", "en printings in OP01: 100 -> 90 (lost 10)"]
    assert check_losses.losses(now, base) == []


def test_a_few_lost_or_a_small_share_lost_is_not_a_loss():
    # 2 of 100 is under MIN_LOSS; 4 of 100 is over MIN_LOSS but under LOSS_SHARE.
    assert check_losses.losses(check_losses.tally(SETS, big_set(100, 0), {}),
                               check_losses.tally(SETS, big_set(98, 0), {})) == []
    assert check_losses.losses(check_losses.tally(SETS, big_set(100, 0), {}),
                               check_losses.tally(SETS, big_set(96, 0), {})) == []


def test_printings_that_lose_a_field_are_a_loss():
    base, now = check_losses.tally(SETS, big_set(50, 40), {}), check_losses.tally(SETS, big_set(50, 10), {})
    assert check_losses.losses(base, now) == ["en printings in OP01 with artist: 40 -> 10 (lost 30)",
                                              "en printings with artist: 40 -> 10 (lost 30)",
                                              "printings credited to A: 40 -> 10 (lost 30)"]


def test_releases_that_lose_their_logo_are_a_loss():
    sets = copy.deepcopy(SETS)
    with_logo = [dict(s, id=f"S{i}", releases=[dict(s["releases"][0], logo={"url": "u", "source": "s"})])
                 for i, s in enumerate(sets * 5)]
    without = [dict(s, releases=[{k: v for k, v in s["releases"][0].items() if k != "logo"}]) for s in with_logo]
    assert check_losses.losses(tally(sets=with_logo), tally(sets=without)) == [
        "en releases with logo: 10 -> 0 (lost 10)"]


def test_the_data_at_head_loads_and_tallies(tmp_path):
    sets, cards, sealed = check_losses.load_at("HEAD", tmp_path)
    count = check_losses.tally(sets, cards, sealed)
    assert count["sets"] > 0 and count["cards"] > 0 and count["en printings in OP01"] > 0
