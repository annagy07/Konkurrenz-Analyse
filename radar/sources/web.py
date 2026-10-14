"""Websites, D2C shops and Instagram."""

from __future__ import annotations

import hashlib
import os
import re

from .. import http
from ..models import Item
from ..storage import Store
from .feeds import strip_html


def page_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<(br|p|div|li|h\d|tr|section|article)[^>]*>", "\n", html)
    lines = (strip_html(line) for line in html.split("\n"))
    return "\n".join(line for line in lines if len(line) > 2)


def website(artist: str, url: str, store: Store, html: str | None = None) -> list[Item]:
    """Diffs the visible text of a page (artist site, label artist page, linktree) against the last run.

    Returns one item containing only the newly added lines, so scoring looks at what changed.
    """
    text = page_text(html if html is not None else http.get(url).text)
    old = store.get_snapshot(url)
    store.put_snapshot(url, text)
    if old is None or old == text:
        return []
    old_lines = set(old.split("\n"))
    added = [line for line in text.split("\n") if line not in old_lines]
    if not added:
        return []
    diff = "\n".join(added)[:3000]
    # Ignore tiny noise like rotating timestamps or counters.
    if len(diff) < 15:
        return []
    return [Item(
        source="website", source_key=f"website:{url}", artist=artist, url=url,
        item_id=hashlib.sha1(diff.encode()).hexdigest()[:16],
        title=f"Änderung auf {url}", text=diff, record_type="page_change",
    )]


def shopify(artist: str, shop_url: str, name_filter: str | None = None) -> list[Item]:
    """Many artist/label D2C shops run on Shopify, which exposes /products.json publicly.

    A new vinyl/CD/box product is usually the earliest hard evidence of an album.
    name_filter: for multi-artist label shops, only keep products mentioning this string.
    """
    base = shop_url.rstrip("/")
    products = http.get(f"{base}/products.json", params={"limit": 250}).json().get("products", [])
    needle = (name_filter or "").lower()
    items = []
    for p in products:
        blob = " ".join([p.get("title", ""), p.get("vendor", ""), " ".join(p.get("tags", []) or [])])
        if needle and needle not in blob.lower():
            continue
        items.append(Item(
            source="shop", source_key=f"shop:{base}:{needle}", item_id=str(p["id"]), artist=artist,
            title=p.get("title", ""), url=f"{base}/products/{p.get('handle', '')}",
            text=f"{p.get('product_type', '')} {' '.join(p.get('tags', []) or [])} {strip_html(p.get('body_html', ''))[:1500]}",
            published=p.get("published_at") or p.get("created_at") or "",
            record_type="product", structured=True,
        ))
    return items


def instagram(artist: str, username: str) -> list[Item]:
    """Instagram Graph API 'Business Discovery': reads public posts of other business/creator accounts.

    Needs IG_ACCESS_TOKEN and IG_USER_ID of an own Instagram business account linked to a Meta app.
    """
    token, ig_user = os.getenv("IG_ACCESS_TOKEN"), os.getenv("IG_USER_ID")
    if not (token and ig_user):
        return []
    fields = f"business_discovery.username({username}){{media.limit(12){{id,caption,permalink,timestamp,media_type}}}}"
    data = http.get(
        f"https://graph.facebook.com/v21.0/{ig_user}", params={"fields": fields, "access_token": token}
    ).json()
    media = data.get("business_discovery", {}).get("media", {}).get("data", [])
    return [
        Item(
            source="instagram", source_key=f"instagram:{username}", item_id=m["id"], artist=artist,
            title=(m.get("caption") or "").split("\n")[0][:120], text=m.get("caption") or "",
            url=m.get("permalink", ""), published=m.get("timestamp", ""), record_type="post",
        )
        for m in media
    ]
