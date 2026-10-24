import urllib.error

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
