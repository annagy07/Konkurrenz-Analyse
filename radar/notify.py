"""Alert channels: console (always), Teams and Slack per run; e-mail is sent as a daily digest (see digest.py)."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import http
from .models import Signal
from .scoring import chart_friday

LEVEL_ICON = {"hoch": "🔴", "mittel": "🟠", "niedrig": "⚪"}


def format_signal(s: Signal, with_collisions: bool = True) -> str:
    lines = [f"{LEVEL_ICON[s.level]} [{s.level.upper()} · {s.score}] {s.item.artist}: {s.item.title}"]
    if s.release_date:
        lines.append(f"   VÖ: {s.release_date:%d.%m.%Y} → Chartwoche ab Fr {chart_friday(s.release_date):%d.%m.%Y}")
    for c in s.collisions if with_collisions else []:
        lines.append(f"   ⚠️ Kollision: {c}")
    lines.append(f"   Quelle: {s.item.source} · {s.item.url}")
    lines.append(f"   Gründe: {', '.join(s.reasons)}")
    return "\n".join(lines)


def send(signals: list[Signal]) -> None:
    if not signals:
        return
    body = "\n\n".join(format_signal(s) for s in signals)
    title = f"Release-Radar: {len(signals)} neue Hinweise"
    # On a public repo, Actions logs are public: keep own release plans (collisions) out of the log.
    hide = os.getenv("RADAR_HIDE_COLLISIONS_IN_LOG") == "1"
    log_body = "\n\n".join(format_signal(s, with_collisions=not hide) for s in signals)
    print(f"\n=== {title} ===\n{log_body}\n")

    if url := os.getenv("TEAMS_WEBHOOK_URL"):
        # Format accepted by Teams "Workflows" webhooks (Post to a channel when a webhook request is received).
        card = {
            "type": "AdaptiveCard", "version": "1.4",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "body": [{"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium"}]
            + [{"type": "TextBlock", "text": format_signal(s).replace("\n", "\n\n"), "wrap": True} for s in signals],
        }
        http.session.post(url, json={
            "type": "message",
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}],
        }, timeout=20).raise_for_status()

    if url := os.getenv("SLACK_WEBHOOK_URL"):
        http.session.post(url, json={"text": f"*{title}*\n```{body}```"}, timeout=20).raise_for_status()



def send_email(subject: str, text: str, html: str | None = None) -> bool:
    """Send via SMTP (STARTTLS). Recipient defaults to the SMTP account itself. Returns False if not configured."""
    host, user = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER")
    to = os.getenv("ALERT_EMAIL_TO") or user
    if not (host and to):
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM") or user or "radar@localhost"
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT") or 587), timeout=30) as smtp:
        smtp.starttls()
        if user:
            smtp.login(user, os.getenv("SMTP_PASSWORD", ""))
        smtp.sendmail(msg["From"], [a.strip() for a in to.split(",")], msg.as_string())
    return True
