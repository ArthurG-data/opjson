import pytest

import readme_counts

README = "# opjson\n\nIntro.\n\nRelease 0.4.0 holds 1 sets, 2 cards,\nwrapped.\n\n## Using the data\n"


def test_rewrite_replaces_only_the_counts_paragraph():
    out = readme_counts.rewrite(README, "The data holds 3 sets.")
    assert out == "# opjson\n\nIntro.\n\nThe data holds 3 sets.\n\n## Using the data\n"
    assert readme_counts.rewrite(out, "The data holds 4 sets.").count("The data holds") == 1


def test_rewrite_refuses_a_readme_without_the_paragraph():
    with pytest.raises(ValueError):
        readme_counts.rewrite("# opjson\n\nIntro.\n", "The data holds 3 sets.")


def test_paragraph_counts_japanese_only_sets_and_cards():
    sets = [{"id": "OP01", "releases": [{"language": "en"}, {"language": "ja"}]},
            {"id": "OP99", "releases": [{"language": "ja"}]}]
    files = {"OP01": {"cards": [
        {"number": "OP01-001", "printings": [{"id": "OP01-001"}, {"id": "OP01-001~ja", "language": "ja"}]},
        {"number": "OP01-002", "printings": [{"id": "OP01-002~ja", "language": "ja"}]}]}}
    sealed = {"OP01": {"products": [{"id": "a"}, {"id": "b", "language": "ja"}]}}
    assert readme_counts.paragraph(sets, files, sealed) == (
        "The data holds 2 sets, 2 cards, 3 printings and 2 sealed products. 2 sets have a Japanese release, "
        "2 printings and 1 sealed products are Japanese, and 1 sets and 1 cards are only on Bandai's Japanese list.")
