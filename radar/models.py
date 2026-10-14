from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Item:
    """A raw thing a source found: an album listing, a video, a post, a shop product, a page change."""

    source: str  # e.g. "deezer", "youtube", "shopify"
    source_key: str  # stable key of the watched feed, e.g. "deezer:12345"
    item_id: str  # stable id inside that feed, used for dedup
    artist: str
    title: str
    url: str = ""
    text: str = ""
    published: str = ""  # ISO timestamp if known
    release_date: date | None = None
    record_type: str = ""  # "album", "single", "ep", "product", "post", ...
    structured: bool = False  # True if from a catalog/shop API (high trust)


@dataclass
class Signal:
    item: Item
    score: int
    level: str  # "hoch", "mittel", "niedrig"
    reasons: list[str] = field(default_factory=list)
    release_date: date | None = None
    collisions: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.item.source_key}|{self.item.item_id}"
