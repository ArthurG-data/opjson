"""The whole matching run of import_tcgplayer, on a small catalogue whose image hashes are made up: each Bandai
printing's art is a block of 60 bits of its own, so two printings are 120 bits apart, and a product is a few bits
from the printing whose art it carries."""
import import_tcgplayer as it
import tcgcsv
from test_import_tcgplayer import RULES

GROUPS = [{"groupId": 1, "abbreviation": "OP01", "name": "Romance Dawn"},
          {"groupId": 2, "abbreviation": "OP-PR", "name": "One Piece Promotion Cards"},
          {"groupId": 3, "abbreviation": "OP01 PRE", "name": "Romance Dawn Pre-Release Cards"},
          {"groupId": 4, "abbreviation": "OP99", "name": "A set Bandai has not listed yet"}]


def art(i: int, off_by: int = 0) -> int:
    """The hash of art i, with its off_by lowest bits flipped."""
    return (((1 << 60) - 1) << (60 * i)) ^ (((1 << off_by) - 1) << (60 * i))


class Hashes:
    def __init__(self, table: dict[tuple[str, str], int]):
        self.table = table

    def get(self, source, key, url, whole=False):
        return self.table.get((source, key))


def printing(pid: str, set_id: str) -> tuple[str, dict]:
    return pid.split("_")[0], {"id": pid, "set": set_id, "image": f"https://example.com/{pid}.png",
                               "source": "bandai"}


def single(group: int, pid: int, name: str, number: str) -> tuple[dict, tcgcsv.Product]:
    return GROUPS[group - 1], tcgcsv.Product(pid, group, name, name, "", "", {"Number": number, "Rarity": "C"})


def run() -> it.Matcher:
    printings = {pid: printing(pid, s) for pid, s in (("OP01-001", "OP01"), ("OP01-001_p1", "OP01"), ("P-001", "P"),
                                                      ("P-002", "P"), ("P-002_p1", "P"))}
    singles = [single(1, 101, "Card", "OP01-001"), single(1, 102, "Card (Parallel)", "OP01-001"),
               single(2, 201, "Promo Card", "P-001"), single(2, 202, "Twin Promo", "P-002"),
               single(3, 301, "Card (Pre-Release)", "OP01-001"), single(4, 401, "Future Card", "OP99-001")]
    hashes = Hashes({("bandai", "OP01-001"): art(0), ("bandai", "OP01-001_p1"): art(1), ("bandai", "P-001"): art(2),
                     # Bandai's two printings of P-002 carry the same art: the images cannot tell them apart.
                     ("bandai", "P-002"): art(3), ("bandai", "P-002_p1"): art(3),
                     ("tcgplayer", "101"): art(0, 3), ("tcgplayer", "102"): art(1, 2), ("tcgplayer", "201"): art(2, 4),
                     ("tcgplayer", "202"): art(3, 1), ("tcgplayer", "301"): art(0, 5)})
    matcher = it.Matcher(printings, it.group_roles(GROUPS, {"OP01", "P"}), RULES, hashes)
    matcher.run(singles)
    return matcher


def test_products_take_the_printing_their_image_names():
    matches = {m.product.product_id: (m.printing_id, m.evidence, m.distance) for _, m in run().matches}
    assert matches == {101: ("OP01-001", "image", 3), 102: ("OP01-001_p1", "image", 2), 201: ("P-001", "image", 4)}


def test_a_stamped_copy_becomes_a_printing_of_its_own_with_the_art_of_the_printing_it_stamps():
    assert [(role["set"], p.product_id, art_of, bits, how) for role, p, art_of, bits, how in run().minted] == [
        ("OP01-PRE", 301, "OP01-001", 5, "minted")]


def test_a_tie_the_images_cannot_settle_goes_to_review_and_a_set_bandai_has_not_listed_waits():
    matcher = run()
    assert [(e["productId"], e["reason"]) for e in matcher.review] == [
        (202, "its art is that of several Bandai printings the images cannot tell apart")]
    assert [e["productId"] for e in matcher.pending] == [401]
    assert set(matcher.claimed) == {"OP01-001", "OP01-001_p1", "P-001"}
