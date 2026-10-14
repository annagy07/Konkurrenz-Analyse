"""One radar run: fetch every source, keep only new items, score them, check collisions, alert."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import yaml

from . import notify
from .models import Item, Signal
from .scoring import chart_friday, score
from .sources import jobs_for
from .storage import Store

log = logging.getLogger("radar")


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def own_release_fridays(own: dict) -> dict[date, list[str]]:
    """Map chart Friday -> own planned releases in that week (from own_releases.yaml)."""
    weeks: dict[date, list[str]] = {}
    for r in own.get("releases") or []:
        d = r["date"] if isinstance(r["date"], date) else date.fromisoformat(str(r["date"]))
        weeks.setdefault(chart_friday(d), []).append(f"{r['artist']} – {r['title']} ({d:%d.%m.})")
    return weeks


def evaluate(items: list[Item], store: Store, today: date, own_weeks: dict[date, list[str]],
             min_score: int, priority: str = "normal") -> list[Signal]:
    """Turn freshly fetched items into signals. Marks everything as seen."""
    signals = []
    by_key: dict[str, list[Item]] = {}
    for it in items:
        by_key.setdefault(it.source_key, []).append(it)

    for source_key, group in by_key.items():
        first_run = not store.has_baseline(source_key)
        for it in group:
            if store.is_seen(source_key, it.item_id):
                continue
            store.mark_seen(source_key, it.item_id)
            sig = score(it, today)
            # First run of a source = baseline: old catalog entries are not news,
            # but an album that is already listed for a future date still is.
            if first_run and it.record_type != "page_change":
                if not (sig.release_date and sig.release_date >= today and it.record_type in ("album", "product")):
                    continue
            threshold = min_score - 2 if priority == "high" else min_score
            if sig.score < threshold:
                continue
            if sig.release_date:
                for own in own_weeks.get(chart_friday(sig.release_date), []):
                    sig.collisions.append(f"gleiche Chartwoche wie {own}")
            signals.append(sig)
    return signals


def run(artists_path: str, own_path: str | None, db_path: str, dry_run: bool = False,
        only: str | None = None, today: date | None = None) -> list[Signal]:
    today = today or date.today()
    cfg = load_yaml(artists_path)
    settings = cfg.get("settings") or {}
    min_score = int(settings.get("min_score", 5))
    own_weeks = own_release_fridays(load_yaml(own_path)) if own_path else {}
    store = Store(db_path)

    all_signals: list[Signal] = []
    for artist in cfg.get("artists") or []:
        if only and only.lower() not in artist["name"].lower():
            continue
        items: list[Item] = []
        for label, fetch in jobs_for(artist, store, use_news=settings.get("google_news", True)):
            try:
                found = fetch()
                log.info("%-28s %-50s %3d Einträge", artist["name"], label[:50], len(found))
                items.extend(found)
            except Exception as e:  # one broken source must not stop the whole run
                log.warning("%s / %s fehlgeschlagen: %s", artist["name"], label, e)
        all_signals.extend(evaluate(items, store, today, own_weeks, min_score, artist.get("priority", "normal")))

    # Avoid flooding: one album often shows up in several sources at once; sort strongest first.
    all_signals.sort(key=lambda s: (-s.score, s.item.artist))
    for s in all_signals:
        store.save_signal(s)
    if not dry_run:
        store.commit()
        notify.send(all_signals)
    else:
        for s in all_signals:
            print(notify.format_signal(s), end="\n\n")
    return all_signals


def upcoming(db_path: str, own_path: str | None, days: int = 120, today: date | None = None) -> str:
    """Markdown calendar of known competitor releases by chart week, next to own releases."""
    today = today or date.today()
    store = Store(db_path)
    own_weeks = own_release_fridays(load_yaml(own_path)) if own_path else {}
    weeks: dict[date, dict[str, list[str]]] = {}
    for row in store.recent_signals(days=365):
        if not row["release_date"]:
            continue
        d = date.fromisoformat(row["release_date"])
        if not today <= d <= today + timedelta(days=days):
            continue
        entry = f"{row['artist']} – {row['title']} [{row['source']}, Score {row['score']}]"
        bucket = weeks.setdefault(chart_friday(d), {"competition": [], "own": []})["competition"]
        if entry not in bucket:
            bucket.append(entry)
    for fri, own in own_weeks.items():
        if today - timedelta(days=6) <= fri <= today + timedelta(days=days):
            weeks.setdefault(fri, {"competition": [], "own": []})["own"].extend(own)

    out = ["# Release-Kalender nach Chartwoche", ""]
    for fri in sorted(weeks):
        w = weeks[fri]
        flag = " ⚠️ KOLLISION" if w["competition"] and w["own"] else ""
        out.append(f"## Chartwoche ab Fr {fri:%d.%m.%Y}{flag}")
        out += [f"- Konkurrenz: {c}" for c in w["competition"]]
        out += [f"- **Eigene VÖ:** {o}" for o in w["own"]]
        out.append("")
    return "\n".join(out)
