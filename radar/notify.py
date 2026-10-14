"""Alert channels: console (always), Microsoft Teams, Slack, e-mail. Configured via environment variables."""

from __future__ import annotations

import os
import smtplib
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

    if (host := os.getenv("SMTP_HOST")) and (to := os.getenv("ALERT_EMAIL_TO")):
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "radar@localhost"))
        msg["To"] = to
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as smtp:
            smtp.starttls()
            if user := os.getenv("SMTP_USER"):
                smtp.login(user, os.getenv("SMTP_PASSWORD", ""))
            smtp.sendmail(msg["From"], to.split(","), msg.as_string())
