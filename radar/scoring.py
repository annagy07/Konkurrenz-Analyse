"""Decides how likely an item is an album announcement, and pulls a release date out of free text."""

from __future__ import annotations

import re
from datetime import date, timedelta

from .models import Item, Signal

# (pattern, points, label). Matched case-insensitively against title + text.
POSITIVE = [
    (r"\bneues album\b|\bnew album\b|\bdebütalbum\b|\bdebut album\b", 6, "‚neues Album‘"),
    (r"\balbum\b", 3, "‚Album‘"),
    (r"\bmixtape\b|\b(?:lp|ep)\b", 2, "LP/EP/Mixtape"),
    (r"vorbestell|pre-?order|jetzt vorbestellen|pre-?save|presave", 5, "Pre-Order/Pre-Save"),
    (r"\bvinyl\b|\bbox ?set\b|\bboxset\b|\bdeluxe\b|\bbundle\b|\bcd\b|\bfan ?box\b|kassette", 3, "physisches Produkt"),
    (r"tracklist|trackliste|tracklisting", 4, "Tracklist"),
    (r"erscheint am|release ?date|\bvö\b|veröffentlich|out (?:on|now)|ab dem|available", 2, "Release-Hinweis"),
    (r"countdown|coming soon|\bbald\b|ankündig|announce", 2, "Ankündigung"),
]
NEGATIVE = [
    (r"\btour\b|tickets|konzert|live in|festival", -3, "Tour/Live"),
    (r"\bremix\b|sped ?up|slowed|instrumental", -2, "Remix/Version"),
    (r"\bt-?shirt\b|hoodie|cap\b|socken|poster", -2, "Merch ohne Tonträger"),
]

MONTHS = {
    "januar": 1, "january": 1, "jan": 1, "februar": 2, "february": 2, "feb": 2, "märz": 3, "maerz": 3,
    "march": 3, "mär": 3, "mar": 3, "april": 4, "apr": 4, "mai": 5, "may": 5, "juni": 6, "june": 6,
    "jun": 6, "juli": 7, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9,
    "sep": 9, "oktober": 10, "october": 10, "okt": 10, "oct": 10, "november": 11, "nov": 11,
    "dezember": 12, "december": 12, "dez": 12, "dec": 12,
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))


def extract_date(text: str, today: date) -> date | None:
    """Return the first plausible future date (up to ~1 year ahead) mentioned in the text."""
    candidates: list[date] = []
    t = text.lower()
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        candidates.append(_safe_date(int(m[1]), int(m[2]), int(m[3])))
    for m in re.finditer(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})?", t):
        year = _year(m[3], today, int(m[2]), int(m[1]))
        candidates.append(_safe_date(year, int(m[2]), int(m[1])))
    for m in re.finditer(rf"\b(\d{{1,2}})\.?\s+({_MONTH_RE})\.?\s*(\d{{4}})?", t):
        mon = MONTHS[m[2]]
        candidates.append(_safe_date(_year(m[3], today, mon, int(m[1])), mon, int(m[1])))
    for m in re.finditer(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})?", t):
        mon = MONTHS[m[1]]
        candidates.append(_safe_date(_year(m[3], today, mon, int(m[2])), mon, int(m[2])))
    future = [d for d in candidates if d and today <= d <= today + timedelta(days=400)]
    return min(future) if future else None


def _year(raw: str | None, today: date, month: int, day: int) -> int:
    if raw:
        y = int(raw)
        return y + 2000 if y < 100 else y
    # No year given: assume the next occurrence of that day.
    d = _safe_date(today.year, month, day)
    return today.year + 1 if d and d < today else today.year


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def chart_friday(d: date) -> date:
    """German charts track Friday–Thursday; return the Friday that opens the chart week of d."""
    return d - timedelta(days=(d.weekday() - 4) % 7)


def score(item: Item, today: date) -> Signal:
    blob = f"{item.title}\n{item.text}".lower()
    points = 0
    reasons: list[str] = []
    for pattern, pts, label in POSITIVE + NEGATIVE:
        if re.search(pattern, blob):
            points += pts
            reasons.append(f"{label} ({pts:+d})")

    release = item.release_date or extract_date(blob, today)
    if item.structured:
        if item.record_type == "album":
            points += 6
            reasons.append("Katalog/Shop: Album-Eintrag (+6)")
        elif item.record_type in ("ep", "product"):
            points += 2
            reasons.append(f"Katalog/Shop: {item.record_type} (+2)")
        elif item.record_type == "single":
            points -= 2
            reasons.append("Katalog: nur Single (-2)")
    if release and release >= today:
        points += 4
        reasons.append(f"Termin in der Zukunft: {release.isoformat()} (+4)")

    level = "hoch" if points >= 10 else "mittel" if points >= 5 else "niedrig"
    return Signal(item=item, score=points, level=level, reasons=reasons, release_date=release)
