"""Finds Deezer and MusicBrainz IDs for every artist in artists.yaml and stores them in artist_ids.yaml.

Only exact name matches are accepted. Ambiguous names (several artists with the same name) are
resolved by popularity / country but flagged with `check: true` for a human to confirm.
"""

from __future__ import annotations

import logging
import re
import unicodedata

import yaml

from . import http

log = logging.getLogger("radar")
DACH = {"DE", "AT", "CH"}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", "und").replace(" and ", "und")
    return re.sub(r"[^a-z0-9]", "", s)


def deezer_match(name: str) -> dict:
    data = http.get("https://api.deezer.com/search/artist", params={"q": name, "limit": 25}).json().get("data", [])
    exact = sorted((a for a in data if norm(a["name"]) == norm(name)), key=lambda a: -a.get("nb_fan", 0))
    if not exact:
        return {}
    best = exact[0]
    out = {"deezer": best["id"], "deezer_fans": best.get("nb_fan", 0)}
    # Same-named artist with a comparable fanbase -> a human should confirm.
    if len(exact) > 1 and exact[1].get("nb_fan", 0) > 0.2 * max(best.get("nb_fan", 0), 1):
        out["check"] = True
    return out


def musicbrainz_match(name: str, german: bool) -> dict:
    data = http.get(
        "https://musicbrainz.org/ws/2/artist/",
        params={"query": f'artist:"{name}"', "fmt": "json", "limit": 10},
    ).json().get("artists", [])

    def names(a: dict) -> set[str]:
        return {norm(a["name"])} | {norm(al["name"]) for al in a.get("aliases", []) or []}

    exact = [a for a in data if norm(name) in names(a) and int(a.get("score", 0)) >= 80]
    if german:
        dach = [a for a in exact if a.get("country") in DACH]
        exact = dach or exact
    if not exact:
        return {}
    out = {"musicbrainz": exact[0]["id"]}
    if len(exact) > 1:
        out["check"] = True
    return out


def resolve_all(artists_path: str, ids_path: str, refresh: bool = False) -> dict:
    with open(artists_path, encoding="utf-8") as f:
        artists = (yaml.safe_load(f) or {}).get("artists") or []
    try:
        with open(ids_path, encoding="utf-8") as f:
            known = yaml.safe_load(f) or {}
    except FileNotFoundError:
        known = {}

    for a in artists:
        name = a["name"]
        if name in known and not refresh and known[name].get("deezer") and known[name].get("musicbrainz"):
            continue
        entry: dict = {}
        german = a.get("genre") != "International"
        for fn, args in ((deezer_match, (name,)), (musicbrainz_match, (name, german))):
            try:
                found = fn(*args)
                entry["check"] = entry.get("check", False) or found.pop("check", False)
                entry.update(found)
            except Exception as e:
                log.warning("%s: %s fehlgeschlagen: %s", name, fn.__name__, e)
        if not entry.get("check"):
            entry.pop("check", None)
        known[name] = entry
        log.info("%-28s deezer=%-10s mb=%s%s", name, entry.get("deezer", "–"), entry.get("musicbrainz", "–"),
                 "  ⚠ prüfen" if entry.get("check") else "")

    header = (
        "# AUTOMATISCH ERZEUGT von `python -m radar resolve --all` – nicht von Hand pflegen.\n"
        "# Falsche Treffer korrigieren: richtige ID in artists.yaml unter `ids:` eintragen (hat Vorrang).\n"
        "# check: true = mehrere Artists mit gleichem Namen gefunden, bitte einmal prüfen.\n"
    )
    with open(ids_path, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(known, f, allow_unicode=True, sort_keys=True)
    missing = [n for n, e in known.items() if not e.get("deezer") and not e.get("musicbrainz")]
    flagged = [n for n, e in known.items() if e.get("check")]
    print(f"\n{len(known)} Artists, {len(missing)} ohne Treffer, {len(flagged)} zu prüfen.")
    if missing:
        print("Ohne Treffer:", ", ".join(missing))
    if flagged:
        print("Bitte prüfen:", ", ".join(flagged))
    return known
