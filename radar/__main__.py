"""CLI.

  python -m radar run                 # one radar pass, sends alerts
  python -m radar run --dry-run       # print only, change nothing
  python -m radar resolve "Ski Aggu"  # look up Deezer/MusicBrainz/Spotify IDs for artists.yaml
  python -m radar resolve --all       # auto-match IDs for every artist -> artist_ids.yaml
  python -m radar calendar            # release calendar by chart week, incl. collisions
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from . import http, resolver, runner
from .sources import catalogs


def resolve(name: str) -> None:
    print(f"Kandidaten für „{name}“ – passende IDs in artists.yaml eintragen:\n")
    try:
        for a in http.get("https://api.deezer.com/search/artist", params={"q": name}).json().get("data", [])[:5]:
            print(f"  deezer:      {a['id']:<12} {a['name']}  ({a.get('nb_fan', 0):,} Fans)  {a.get('link')}")
    except Exception as e:
        print(f"  deezer: Fehler {e}")
    try:
        data = http.get("https://musicbrainz.org/ws/2/artist/", params={"query": name, "fmt": "json", "limit": 5}).json()
        for a in data.get("artists", []):
            print(f"  musicbrainz: {a['id']}  {a['name']}  {a.get('country', '')} {a.get('disambiguation', '')}")
    except Exception as e:
        print(f"  musicbrainz: Fehler {e}")
    try:
        if token := catalogs.spotify_token():
            data = http.get("https://api.spotify.com/v1/search", params={"q": name, "type": "artist", "limit": 5},
                            headers={"Authorization": f"Bearer {token}"}).json()
            for a in data.get("artists", {}).get("items", []):
                print(f"  spotify:     {a['id']}  {a['name']}")
    except Exception as e:
        print(f"  spotify: Fehler {e}")
    print("\n  youtube: Channel-ID (beginnt mit UC…) aus der Kanal-URL bzw. Seitenquelltext ('channelId').")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="radar")
    p.add_argument("--artists", default="artists.yaml")
    p.add_argument("--own", default="own_releases.yaml")
    p.add_argument("--db", default="data/radar.db")
    p.add_argument("--ids", default="artist_ids.yaml", help="automatisch gefundene IDs")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--only", help="nur Artists, deren Name diesen Text enthält")
    rs = sub.add_parser("resolve", help="IDs nachschlagen")
    rs.add_argument("name", nargs="?", help="ein Artist (Kandidaten anzeigen)")
    rs.add_argument("--all", action="store_true", help="alle Artists automatisch abgleichen -> artist_ids.yaml")
    rs.add_argument("--refresh", action="store_true", help="auch bereits gefundene IDs neu suchen")
    c = sub.add_parser("calendar")
    c.add_argument("--days", type=int, default=120)
    c.add_argument("--out", help="Markdown-Datei schreiben statt ausgeben")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    own = args.own if os.path.exists(args.own) else None
    if args.cmd == "run":
        runner.run(args.artists, own, args.db, dry_run=args.dry_run, only=args.only, ids_path=args.ids)
    elif args.cmd == "resolve":
        if args.all:
            resolver.resolve_all(args.artists, args.ids, refresh=args.refresh)
        elif args.name:
            resolve(args.name)
        else:
            p.error("Artist-Name oder --all angeben")
    elif args.cmd == "calendar":
        md = runner.upcoming(args.db, own, days=args.days)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(md)
        else:
            print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
