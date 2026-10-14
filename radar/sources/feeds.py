"""RSS/Atom based sources: YouTube channels, Google News, and any other feed (e.g. RSSHub for Instagram/TikTok/X)."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import quote_plus

from .. import http
from ..models import Item

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_feed(xml_text: str) -> list[dict]:
    """Minimal RSS 2.0 + Atom parser -> list of {id, title, url, text, published}."""
    root = ET.fromstring(xml_text)
    entries = []
    for it in root.iter("item"):  # RSS
        link = it.findtext("link") or ""
        entries.append({
            "id": it.findtext("guid") or link or it.findtext("title") or "",
            "title": strip_html(it.findtext("title") or ""),
            "url": link,
            "text": strip_html(it.findtext("description") or ""),
            "published": it.findtext("pubDate") or "",
        })
    for e in root.iter(f"{{{NS['atom']}}}entry"):  # Atom (YouTube)
        link_el = e.find("atom:link", NS)
        desc = e.find("media:group/media:description", NS)
        entries.append({
            "id": e.findtext("atom:id", "", NS),
            "title": strip_html(e.findtext("atom:title", "", NS)),
            "url": link_el.get("href", "") if link_el is not None else "",
            "text": strip_html((desc.text if desc is not None else "") or e.findtext("atom:summary", "", NS)),
            "published": e.findtext("atom:published", "", NS),
        })
    return entries


def _items(source: str, source_key: str, artist: str, xml_text: str, record_type: str) -> list[Item]:
    return [
        Item(
            source=source, source_key=source_key, artist=artist, title=e["title"], url=e["url"],
            text=e["text"], published=e["published"], record_type=record_type,
            item_id=hashlib.sha1(e["id"].encode()).hexdigest()[:16],
        )
        for e in parse_feed(xml_text)
    ]


def youtube(artist: str, channel_id: str) -> list[Item]:
    """Official, free feed of the last ~15 uploads (trailers, 'Album out ...' snippets, premieres)."""
    xml_text = http.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id}).text
    return _items("youtube", f"youtube:{channel_id}", artist, xml_text, "video")


def google_news(artist: str, extra_terms: str = "") -> list[Item]:
    """Press coverage (laut.de, rap.de, hiphop.de, Bild, ...) mentioning the artist together with album words."""
    q = f'"{artist}" (Album OR "neues Album" OR Vorbestellen OR Tracklist) {extra_terms}'.strip()
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}+when:7d&hl=de&gl=DE&ceid=DE:de"
    items = _items("news", f"news:{artist}", artist, http.get(url).text, "article")
    # Google News also matches loose mentions; keep only articles that name the artist in the headline.
    return [i for i in items if artist.lower() in i.title.lower()]


def generic(artist: str, feed_url: str, label: str = "feed") -> list[Item]:
    """Any RSS/Atom URL: label newsroom, RSSHub route for Instagram/TikTok/X, Telegram channel, ..."""
    return _items(label, f"{label}:{feed_url}", artist, http.get(feed_url).text, "post")
