# Release-Radar – Konkurrenz-Albumankündigungen früh erkennen

Überwacht eine Watchlist von Konkurrenz-Artists über viele Kanäle und meldet, sobald etwas nach einer
**Albumankündigung** aussieht. Das Tool rechnet das VÖ-Datum auf die **Chartwoche (Fr–Do)** um und meldet
eine **Kollision**, wenn in dieselbe Woche eine eigene Veröffentlichung fällt.

## Was überwacht wird

| Kanal | Wie | Warum früh | Kosten / Zugang |
|---|---|---|---|
| **Deezer** | Artist-Album-API | Angekündigte Alben stehen oft schon mit künftigem VÖ-Datum drin | kostenlos, kein Key |
| **MusicBrainz** | Release-Groups-API | Die Community trägt Ankündigungen meist innerhalb von Stunden ein | kostenlos |
| **Spotify** | Artist-Albums-API | Countdown-Pages und Pre-Saves | kostenlose Developer-App |
| **Apple Music** | Catalog-API | Pre-Orders mit Datum | Apple-Developer-Account (99 $/Jahr) |
| **D2C-Shops** | Shopify `/products.json` | Neues Vinyl, neue CD oder Box ist oft der früheste harte Beleg | kostenlos |
| **Websites** | Text-Diff je Lauf | Artist-Site, Label-Artistseite, Linktree | kostenlos |
| **YouTube** | offizieller Kanal-RSS | Trailer, Snippets, Premieren | kostenlos |
| **Instagram** | Graph API „Business Discovery“ | Posts von Business- und Creator-Accounts | eigener IG-Business-Account + Meta-App |
| **TikTok / X / Instagram** (alternativ) | beliebiger RSS-Feed, z. B. RSSHub | | selbst gehostetes RSSHub oder ein Dienst wie Apify |
| **Presse** | Google-News-RSS | laut.de, rap.de, hiphop.de und andere | kostenlos |

Jeder neue Eintrag bekommt einen **Score**. Positiv zählen zum Beispiel „neues Album“, „vorbestellen“,
„Pre-Save“, „Vinyl“, „Tracklist“, ein künftiges Datum oder ein Album-Eintrag im Katalog. Negativ zählen
„Tour“, „Tickets“, „Remix“ oder reines Merch. Ab Score 5 gibt es einen Alarm 🟠, ab 10 gilt er als „hoch“ 🔴.
Für Artists mit `priority: high` liegt die Schwelle niedriger.

Beim **ersten Lauf** einer Quelle wird der Bestand nur gemerkt („Baseline“). Ein Alarm kommt nur für
Alben, die schon mit künftigem Datum gelistet sind. Danach meldet das Tool ausschließlich Neues.

## Einrichtung

```bash
pip install -r requirements.txt
python -m radar resolve --all          # IDs für alle Artists automatisch suchen -> artist_ids.yaml
python -m radar resolve "Ski Aggu"     # Kandidaten für einen Artist anzeigen
python -m radar run --dry-run          # Probelauf, ändert nichts
python -m radar run                    # echter Lauf mit Alarm
python -m radar calendar               # Release-Kalender nach Chartwoche inkl. Kollisionen
```

1. `artists.yaml` enthält bereits **200 chart-relevante Artists** aus Deutschrap, Pop, Schlager, Rock und
   internationalen Acts. Eigene Sony-Artists bei Bedarf mit `skip: true` ausschließen.
   **Einmalig die IDs suchen:** in GitHub unter *Actions → „IDs suchen“ → Run workflow*. Das schreibt
   `artist_ids.yaml`. Einträge mit `check: true` kurz prüfen, falsche IDs in `artists.yaml` unter `ids:`
   überschreiben. Websites, Shops und Feeds trägt man nach und nach für die wichtigsten Artists ein.
2. `own_releases.example.yaml` nach `own_releases.yaml` kopieren und die eigene Planung eintragen.
   Diese Datei ist per `.gitignore` ausgeschlossen.
3. **GitHub Actions** (`.github/workflows/radar.yml`) läuft alle 2 Stunden. Unter
   *Settings → Secrets and variables → Actions* die gewünschten Secrets anlegen:
   - Alarm: `TEAMS_WEBHOOK_URL` (Teams → Workflows → „Post to a channel when a webhook request is received“),
     `SLACK_WEBHOOK_URL` oder `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`ALERT_EMAIL_TO`
   - Eigene Planung: `OWN_RELEASES_YAML` (Inhalt der YAML-Datei)
   - Optional: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `APPLE_MUSIC_TOKEN`, `IG_ACCESS_TOKEN`, `IG_USER_ID`

## ⚠️ Vertraulichkeit

Dieses Repository ist derzeit **öffentlich**. Damit sind die Watchlist und die Actions-Logs für jeden sichtbar.
Die eigene Release-Planung landet deshalb nie im Repo, nicht in der Datenbank und nicht im Log:
Kollisionen gehen nur über Teams, Slack oder E-Mail raus. **Empfehlung: das Repo auf privat stellen** oder
das Tool intern bei Sony hosten. Vorher mit IT und Legal abklären, welche Plattform-Nutzungsbedingungen
(v. a. Instagram, TikTok, X) für automatisiertes Auslesen gelten.

## Nächste Ausbaustufen

- **KI-Klassifizierung** (z. B. Claude) für Treffer mit mittlerem Score: „Ist das eine Albumankündigung?
  Wann ist die VÖ?“ Das hilft vor allem bei Instagram-Captions und Pressetexten ohne klare Schlagworte.
- **Chart-Gewichtung**: Artists nach bisherigen Chart-Peaks oder Streaming-Zahlen priorisieren.
- **Dashboard** mit Kalenderansicht für das Release-Planning-Team.
- **Label-Shops** der Majors und der großen Indies systematisch eintragen. Viele davon laufen nicht auf
  Shopify und brauchen dann den Website-Diff.
