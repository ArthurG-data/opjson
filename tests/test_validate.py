import copy
import subprocess
import urllib.error
import uuid as uuidlib

import pytest

import opjson
import uuids
import validate


class _Answer:
    def close(self):
        pass


def _urlopen(answers, calls):
    """A urlopen that raises or answers from `answers` in order and records each call."""
    def fake(req, timeout):
        calls.append(req.full_url)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return _Answer()
    return fake


def _http(code):
    return urllib.error.HTTPError("https://x", code, "err", {}, None)


def test_a_5xx_is_retried_and_a_later_answer_passes(monkeypatch):
    calls = []
    monkeypatch.setattr(validate.urllib.request, "urlopen", _urlopen([_http(502), _http(503), "ok"], calls))
    monkeypatch.setattr(validate.time, "sleep", lambda s: None)
    assert validate.head_status("https://x/a.png") is None
    assert len(calls) == 3


def test_a_4xx_is_final_without_a_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(validate.urllib.request, "urlopen", _urlopen([_http(404)], calls))
    assert validate.head_status("https://x/a.png") == 404
    assert len(calls) == 1


def test_a_server_that_keeps_failing_reports_its_last_status(monkeypatch):
    calls = []
    answers = [_http(502), urllib.error.URLError("reset"), _http(500)]
    monkeypatch.setattr(validate.urllib.request, "urlopen", _urlopen(answers, calls))
    monkeypatch.setattr(validate.time, "sleep", lambda s: None)
    assert validate.head_status("https://x/a.png") == 500


def test_image_errors_checks_only_bandai_printings_and_names_each_failure():
    printings = {
        "OP01-002": {"source": "bandai", "image": "https://b/OP01-002.png"},
        "OP01-001": {"source": "bandai", "image": "https://b/OP01-001.png"},
        "OP01-003": {"source": "bandai", "image": "https://b/OP01-003.png"},
        "OP01-001~tcg9": {"source": "tcgplayer", "image": "https://t/9.jpg"},
    }
    statuses = {"https://b/OP01-001.png": 404, "https://b/OP01-002.png": None, "https://b/OP01-003.png": 0}
    seen = []

    def head(url):
        seen.append(url)
        return statuses[url]

    assert validate.image_errors(printings, head=head, workers=2) == [
        "printing OP01-001: Bandai image answers 404",
        "printing OP01-003: Bandai image answers nothing",
    ]
    assert sorted(seen) == sorted(statuses)


def test_a_product_gone_from_tcgplayer_is_an_error_on_printings_and_sealed_products():
    flat = {"printings": {"OP01-001": {"identifiers": {"tcgplayerProductIds": [1, 2]}}, "OP01-002": {}},
            "products": {"op01-booster-box": {"identifiers": {"tcgplayerProductIds": [3]}}}}
    assert validate.gone_products({1, 2, 3}, flat) == []
    assert validate.gone_products({1}, flat) == [
        "printing OP01-001: TCGplayer product 2 is gone from category 68",
        "sealed product op01-booster-box: TCGplayer product 3 is gone from category 68"]


_SETS = [{"id": "OP01", "type": "booster", "releases": [
    {"language": "en", "name": "Romance Dawn", "source": "https://example.com/op01"}]}]


def _files():
    return {"OP01": {"cards": [{"number": "OP01-001", "name": "Zoro", "names": {"en": "Zoro"}, "category": "Leader",
                                "printings": [{"id": "OP01-001", "set": "OP01", "image": "https://example.com/a.png",
                                               "source": "bandai"}]}]}}


def _repo(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "before")
    monkeypatch.setattr(opjson, "ROOT", tmp_path)
    monkeypatch.setattr(uuids, "REGISTRY", tmp_path / "data" / "uuids.json")
    return git


def test_registry_at_a_commit_before_the_registry_is_empty(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    assert validate.registry_at("HEAD") == uuids.empty()


def test_registry_at_reads_the_registry_a_commit_holds(tmp_path, monkeypatch):
    git = _repo(tmp_path, monkeypatch)
    registry = uuids.empty()
    registry["cards"]["keys"]["id:OP01-001"] = "u"
    uuids.save(registry, tmp_path / "data" / "uuids.json")
    git("add", "data/uuids.json")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "registry")
    assert validate.registry_at("HEAD")["cards"]["keys"] == {"id:OP01-001": "u"}


def test_registry_at_an_unknown_ref_exits(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="no such commit"):
        validate.registry_at("nope")


def test_the_schemas_accept_uuid_version_id_and_oracle_id_and_require_uuid():
    sets, files, sealed, registry = copy.deepcopy(_SETS), _files(), {}, uuids.empty()
    assert any("has no uuid" in e for e in validate.offline_errors(sets, files, sealed, registry))
    uuids.assign(sets, files, sealed, registry)
    assert opjson.validate(sets, files) == []
    assert validate.offline_errors(sets, files, sealed, registry) == []
    files["OP01"]["cards"][0]["oracleId"] = "not-a-uuid"
    assert any("oracleId" in e and "is not a 'uuid'" in e for e in opjson.validate(sets, files))


def test_offline_errors_with_an_earlier_registry_refuses_a_changed_uuid():
    sets, files, sealed, registry = copy.deepcopy(_SETS), _files(), {}, uuids.empty()
    uuids.assign(sets, files, sealed, registry)
    before = copy.deepcopy(registry)
    before["printings"]["keys"]["bandai:en:OP01-001"] = str(uuidlib.uuid4())
    found = validate.offline_errors(sets, files, sealed, registry, before)
    assert any("its uuid changed" in e for e in found)


def test_offline_errors_accepts_a_changed_uuid_a_settlement_names():
    sets, files, sealed, registry = copy.deepcopy(_SETS), _files(), {}, uuids.empty()
    uuids.assign(sets, files, sealed, registry)
    before = copy.deepcopy(registry)
    before["printings"]["keys"]["bandai:en:OP01-001"] = str(uuidlib.uuid4())
    settled = {"printings": {"bandai:en:OP01-001": "settled by hand"}}
    assert validate.offline_errors(sets, files, sealed, registry, before, settled) == []
