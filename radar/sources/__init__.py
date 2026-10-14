from __future__ import annotations

from typing import Callable

from ..models import Item
from ..storage import Store
from . import catalogs, feeds, web


def jobs_for(artist: dict, store: Store, use_news: bool = True) -> list[tuple[str, Callable[[], list[Item]]]]:
    """Build the list of (label, fetch function) for one artist entry of artists.yaml."""
    name = artist["name"]
    ids = artist.get("ids") or {}
    jobs: list[tuple[str, Callable[[], list[Item]]]] = []

    id_sources = {
        "deezer": catalogs.deezer,
        "musicbrainz": catalogs.musicbrainz,
        "spotify": catalogs.spotify,
        "apple_music": catalogs.apple_music,
        "youtube": feeds.youtube,
        "instagram": web.instagram,
    }
    for key, fn in id_sources.items():
        if ids.get(key):
            jobs.append((f"{key}:{ids[key]}", lambda fn=fn, v=str(ids[key]): fn(name, v)))

    for url in artist.get("websites") or []:
        jobs.append((f"website:{url}", lambda url=url: web.website(name, url, store)))
    for shop in artist.get("shops") or []:
        shop = {"url": shop} if isinstance(shop, str) else shop
        jobs.append((f"shop:{shop['url']}", lambda s=shop: web.shopify(name, s["url"], s.get("filter"))))
    for feed in artist.get("feeds") or []:
        feed = {"url": feed} if isinstance(feed, str) else feed
        jobs.append((f"feed:{feed['url']}", lambda f=feed: feeds.generic(name, f["url"], f.get("label", "feed"))))
    if use_news and artist.get("news", True):
        jobs.append((f"news:{name}", lambda: feeds.google_news(name, artist.get("news_terms", ""))))
    return jobs
