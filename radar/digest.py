"""Daily e-mail report: new hints of the last 24 h plus the release calendar by chart week."""

from __future__ import annotations

from datetime import date
from html import escape

from . import notify
from .runner import calendar_weeks, load_yaml, own_release_fridays
from .scoring import chart_friday
from .storage import Store

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
LEVEL_COLOR = {"hoch": "#c62828", "mittel": "#ef6c00", "niedrig": "#757575"}


def build(db_path: str, own_path: str | None, today: date | None = None, hours: int = 24,
          weeks_ahead: int = 12) -> tuple[str, str, str]:
    """Return (subject, plain text, html)."""
    today = today or date.today()
    store = Store(db_path)
    own_weeks = own_release_fridays(load_yaml(own_path)) if own_path else {}
    rows = [r for r in store.recent_signals(days=hours / 24)]
    rows.sort(key=lambda r: (-r["score"], r["artist"]))
    weeks = calendar_weeks(store, own_weeks, today, days=weeks_ahead * 7)
    collisions = [fri for fri, w in weeks.items() if w["competition"] and w["own"]]

    high = sum(1 for r in rows if r["level"] == "hoch")
    subject = f"Release-Radar {today:%d.%m.%Y}: "
    subject += f"{len(rows)} neue Hinweise" + (f", davon {high} hoch" if high else "") if rows else "keine neuen Hinweise"
    if collisions:
        subject += f" · ⚠️ {len(collisions)} Kollision(en)"

    # ---- plain text ----
    text = [subject, ""]
    text.append(f"NEUE HINWEISE (letzte {hours} Std.)")
    if not rows:
        text.append("  Keine neuen Album-Hinweise gefunden.")
    for r in rows:
        line = f"  [{r['level'].upper()} · {r['score']}] {r['artist']}: {r['title']}"
        if r["release_date"]:
            d = date.fromisoformat(r["release_date"])
            line += f"  (VÖ {d:%d.%m.%Y}, Chartwoche ab Fr {chart_friday(d):%d.%m.})"
        text += [line, f"     {r['source']} · {r['url']}"]
    text += ["", f"RELEASE-KALENDER (nächste {weeks_ahead} Wochen)"]
    if not weeks:
        text.append("  Noch keine angekündigten Konkurrenz-Releases mit Datum bekannt.")
    for fri, w in weeks.items():
        flag = "  ⚠️ KOLLISION" if fri in collisions else ""
        text.append(f"  Chartwoche ab Fr {fri:%d.%m.%Y}{flag}")
        text += [f"    - {c}" for c in w["competition"]] + [f"    - EIGENE VÖ: {o}" for o in w["own"]]

    # ---- html ----
    h = [
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:680px;color:#212121">',
        f'<h2 style="margin:0 0 4px">Release-Radar</h2><div style="color:#757575;margin-bottom:18px">'
        f'{WEEKDAYS[today.weekday()]}, {today:%d.%m.%Y} · {len(rows)} neue Hinweise in den letzten {hours} Std.</div>',
    ]
    if collisions:
        h.append('<div style="background:#ffebee;border-left:4px solid #c62828;padding:10px 14px;margin-bottom:18px">'
                 f'<b>⚠️ {len(collisions)} Kollision(en) mit eigener Planung</b> – Details im Kalender unten.</div>')
    h.append('<h3 style="border-bottom:1px solid #e0e0e0;padding-bottom:4px">Neue Hinweise</h3>')
    if not rows:
        h.append('<p style="color:#757575">Keine neuen Album-Hinweise gefunden.</p>')
    for r in rows:
        color = LEVEL_COLOR.get(r["level"], "#757575")
        vo = ""
        if r["release_date"]:
            d = date.fromisoformat(r["release_date"])
            vo = f' · <b>VÖ {d:%d.%m.%Y}</b> (Chartwoche ab Fr {chart_friday(d):%d.%m.})'
        link = f'<a href="{escape(r["url"])}" style="color:#1565c0">{escape(r["source"])}</a>' if r["url"] else escape(r["source"])
        h.append(
            f'<div style="border-left:4px solid {color};padding:6px 12px;margin:10px 0">'
            f'<span style="color:{color};font-weight:bold;font-size:12px">{r["level"].upper()} · {r["score"]}</span><br>'
            f'<b>{escape(r["artist"])}</b>: {escape(r["title"])}<br>'
            f'<span style="font-size:13px;color:#616161">{link}{vo}</span></div>'
        )
    h.append(f'<h3 style="border-bottom:1px solid #e0e0e0;padding-bottom:4px;margin-top:28px">'
             f'Release-Kalender (nächste {weeks_ahead} Wochen)</h3>')
    if not weeks:
        h.append('<p style="color:#757575">Noch keine angekündigten Konkurrenz-Releases mit Datum bekannt.</p>')
    else:
        h.append('<table style="border-collapse:collapse;width:100%;font-size:14px">')
        for fri, w in weeks.items():
            bg = "#ffebee" if fri in collisions else "#fafafa"
            items = "".join(f"<div>{escape(c)}</div>" for c in w["competition"])
            items += "".join(f'<div><b>Eigene VÖ:</b> {escape(o)}</div>' for o in w["own"])
            flag = '<br><span style="color:#c62828;font-weight:bold">⚠️ Kollision</span>' if fri in collisions else ""
            h.append(f'<tr style="background:{bg}"><td style="padding:8px;vertical-align:top;white-space:nowrap;'
                     f'border-bottom:1px solid #fff"><b>Fr {fri:%d.%m.}</b>{flag}</td>'
                     f'<td style="padding:8px;border-bottom:1px solid #fff">{items}</td></tr>')
        h.append("</table>")
    h.append('<p style="color:#9e9e9e;font-size:12px;margin-top:28px">Automatisch erstellt vom Release-Radar. '
             'Chartwoche = Freitag bis Donnerstag.</p></div>')
    return subject, "\n".join(text), "\n".join(h)


def send(db_path: str, own_path: str | None) -> None:
    subject, text, html = build(db_path, own_path)
    # Only the subject goes to the (public) Actions log; the mail may contain own release plans.
    print(subject)
    if not notify.send_email(subject, text, html):
        print("\nE-Mail nicht versendet: SMTP_HOST / SMTP_USER nicht gesetzt.")
