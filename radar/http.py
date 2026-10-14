from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

USER_AGENT = "KonkurrenzRadar/0.1 (+https://github.com/annagy07/konkurrenz-analyse)"
# Minimum seconds between requests per host (MusicBrainz allows 1 req/s).
HOST_DELAY = {"musicbrainz.org": 1.1, "news.google.com": 1.0}
_last_call: dict[str, float] = {}

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


def get(url: str, *, params: dict | None = None, headers: dict | None = None, timeout: int = 20) -> requests.Response:
    host = urlparse(url).hostname or ""
    delay = HOST_DELAY.get(host, 0.3)
    wait = _last_call.get(host, 0) + delay - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        _last_call[host] = time.monotonic()
        resp = session.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code in (429, 502, 503) and attempt < 2:
            time.sleep(2 ** (attempt + 1))
            continue
        resp.raise_for_status()
        return resp
    return resp
