import io
import urllib.error
import urllib.parse

import probe


class Response(io.BytesIO):
    """A stand-in for the object urlopen returns: a context manager with a status."""

    status = 200


def opener(answers):
    def open_url(req, timeout):
        answer = answers[req.full_url]
        if isinstance(answer, Exception):
            raise answer
        return Response(answer)
    return open_url


def test_every_host_answering_is_no_failure():
    assert probe.failures(["https://a/x"], opener({"https://a/x": b"img"})) == []


def test_a_refused_url_is_a_failure():
    refused = urllib.error.HTTPError("https://a/x", 403, "Forbidden", {}, None)
    assert probe.failures(["https://a/x"], opener({"https://a/x": refused})) == ["https://a/x: HTTP Error 403: Forbidden"]


def test_an_empty_body_is_a_failure():
    assert probe.failures(["https://a/x"], opener({"https://a/x": b""})) == ["https://a/x: empty body"]


def test_the_probe_asks_each_host_once():
    assert {urllib.parse.urlsplit(u).hostname for u in probe.URLS} == {
        "en.onepiece-cardgame.com", "tcgplayer-cdn.tcgplayer.com", "onepiece.limitlesstcg.com"}
    assert len(probe.URLS) == 3
