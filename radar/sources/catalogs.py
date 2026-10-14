"""Streaming/catalog APIs. Pre-orders and countdown pages often show up here first, with a release date."""

from __future__ import annotations

import os
from datetime import date

from .. import http
from ..models import Item


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        parts = [int(p) for p in raw.split("-")]
        return date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except (ValueError, IndexError):
        return None


def deezer(artist: str, artist_id: str) -> list[Item]:
    """Free, no key. Lists albums/EPs/singles incl. upcoming ones with a future release_date."""
    data = http.get(f"https://api.deezer.com/artist/{artist_id}/albums", params={"limit": 100}).json()
    return [
        Item(
            source="deezer", source_key=f"deezer:{artist_id}", item_id=str(a["id"]), artist=artist,
            title=a.get("title", ""), url=a.get("link", ""), release_date=_parse_date(a.get("release_date")),
            record_type=a.get("record_type", ""), structured=True,
        )
        for a in data.get("data", [])
    ]


def musicbrainz(artist: str, mbid: str) -> list[Item]:
    """Free, community-maintained. Announced albums are often entered with a future date within hours."""
    data = http.get(
        "https://musicbrainz.org/ws/2/release-group",
        params={"artist": mbid, "type": "album|ep", "fmt": "json", "limit": 100},
    ).json()
    return [
        Item(
            source="musicbrainz", source_key=f"musicbrainz:{mbid}", item_id=rg["id"], artist=artist,
            title=rg.get("title", ""), url=f"https://musicbrainz.org/release-group/{rg['id']}",
            release_date=_parse_date(rg.get("first-release-date")),
            record_type=(rg.get("primary-type") or "").lower(), structured=True,
        )
        for rg in data.get("release-groups", [])
    ]


_spotify_token: str | None = None


def spotify_token() -> str | None:
    """Client-credentials token from SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET (free developer app)."""
    global _spotify_token
    cid, secret = os.getenv("SPOTIFY_CLIENT_ID"), os.getenv("SPOTIFY_CLIENT_SECRET")
    if _spotify_token is None and cid and secret:
        resp = http.session.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"}, auth=(cid, secret), timeout=20,
        )
        resp.raise_for_status()
        _spotify_token = resp.json()["access_token"]
    return _spotify_token


def spotify(artist: str, artist_id: str) -> list[Item]:
    token = spotify_token()
    if not token:
        return []
    data = http.get(
        f"https://api.spotify.com/v1/artists/{artist_id}/albums",
        params={"include_groups": "album,single", "market": "DE", "limit": 50},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    return [
        Item(
            source="spotify", source_key=f"spotify:{artist_id}", item_id=a["id"], artist=artist,
            title=a.get("name", ""), url=a.get("external_urls", {}).get("spotify", ""),
            release_date=_parse_date(a.get("release_date")),
            record_type=a.get("album_type", ""), structured=True,
        )
        for a in data.get("items", [])
    ]


def apple_music(artist: str, artist_id: str) -> list[Item]:
    """Needs APPLE_MUSIC_TOKEN (developer token). Pre-orders appear here with their future date."""
    token = os.getenv("APPLE_MUSIC_TOKEN")
    if not token:
        return []
    data = http.get(
        f"https://api.music.apple.com/v1/catalog/de/artists/{artist_id}/albums",
        params={"limit": 100}, headers={"Authorization": f"Bearer {token}"},
    ).json()
    items = []
    for a in data.get("data", []):
        attrs = a.get("attributes", {})
        name = attrs.get("name", "")
        kind = "single" if attrs.get("isSingle") or name.endswith(" - Single") else "album"
        if name.endswith(" - EP"):
            kind = "ep"
        items.append(Item(
            source="apple_music", source_key=f"apple_music:{artist_id}", item_id=a["id"], artist=artist,
            title=attrs.get("name", ""), url=attrs.get("url", ""),
            release_date=_parse_date(attrs.get("releaseDate")), record_type=kind, structured=True,
        ))
    return items
