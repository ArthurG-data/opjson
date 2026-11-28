"""Check that the hosts the refresh reads from still answer this runner.

The daily refresh runs this before it rebuilds anything. Each URL is a file known to exist, because
TCGplayer's CDN answers 403 for a product with no scan. Only an image that is there tells a refused
runner apart from a missing scan, so a 403 here always means the runner is blocked.
"""
from __future__ import annotations

import sys
import urllib.request
from collections.abc import Iterable

import opjson

URLS = (
    "https://en.onepiece-cardgame.com/images/cardlist/card/OP01-001.png",
    # OP01-001's TCGplayer product. The local cache holds a real scan of it.
    "https://tcgplayer-cdn.tcgplayer.com/product/454512_in_400x400.jpg",
    "https://onepiece.limitlesstcg.com/api/cards/artists",
)
TIMEOUT = 30


def failures(urls: Iterable[str], open_url=urllib.request.urlopen) -> list[str]:
    """One "<url>: <reason>" per URL that does not answer 200 with a non-empty body."""
    out = []
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": opjson.USER_AGENT})
        try:
            with open_url(req, timeout=TIMEOUT) as resp:
                status, body = resp.status, resp.read()
        except Exception as exc:
            out.append(f"{url}: {exc}")
            continue
        if status != 200:
            out.append(f"{url}: HTTP {status}")
        elif not body:
            out.append(f"{url}: empty body")
    return out


def main() -> None:
    bad = failures(URLS)
    for line in bad:
        print(line)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
