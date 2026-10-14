from datetime import date
from unittest.mock import patch

from radar import runner
from radar.models import Item
from radar.scoring import chart_friday, extract_date, score
from radar.sources import catalogs, feeds, web
from radar.storage import Store

TODAY = date(2026, 10, 14)  # a Wednesday


class FakeResp:
    def __init__(self, json_data=None, text=""):
        self._json, self.text = json_data, text

    def json(self):
        return self._json


def test_extract_date_german_and_english():
    assert extract_date("Das neue Album erscheint am 21.11.2026", TODAY) == date(2026, 11, 21)
    assert extract_date("VÖ: 6. Dezember", TODAY) == date(2026, 12, 6)
    assert extract_date("out on November 28th", TODAY) == date(2026, 11, 28)
    assert extract_date("Release 2027-01-09", TODAY) == date(2027, 1, 9)
    assert extract_date("am 3.10. war das Konzert", TODAY) == date(2027, 10, 3)  # no year: next occurrence
    assert extract_date("kein Datum hier", TODAY) is None


def test_chart_friday():
    assert chart_friday(date(2026, 11, 20)) == date(2026, 11, 20)  # Friday itself
    assert chart_friday(date(2026, 11, 26)) == date(2026, 11, 20)  # Thursday belongs to previous Friday
    assert chart_friday(date(2026, 11, 21)) == date(2026, 11, 20)


def test_score_announcement_vs_noise():
    ann = Item("instagram", "ig:x", "1", "Ski Aggu", "NEUES ALBUM 🔥",
               text="Mein neues Album kommt am 20.11.! Jetzt vorbestellen – limitiertes Vinyl im Shop")
    tour = Item("instagram", "ig:x", "2", "Ski Aggu", "Tour 2027", text="Tickets ab Freitag, Konzert in Berlin")
    s1, s2 = score(ann, TODAY), score(tour, TODAY)
    assert s1.level == "hoch" and s1.release_date == date(2026, 11, 20)
    assert s2.level == "niedrig"


def test_deezer_parsing_and_scoring():
    payload = {"data": [
        {"id": 1, "title": "Altes Album", "release_date": "2024-05-03", "record_type": "album", "link": "l1"},
        {"id": 2, "title": "Neues Album", "release_date": "2026-11-27", "record_type": "album", "link": "l2"},
        {"id": 3, "title": "Single", "release_date": "2026-10-10", "record_type": "single", "link": "l3"},
    ]}
    with patch("radar.http.get", return_value=FakeResp(payload)):
        items = catalogs.deezer("Ski Aggu", "999")
    assert [i.release_date for i in items][1] == date(2026, 11, 27)
    assert score(items[1], TODAY).level == "hoch"
    assert score(items[2], TODAY).level == "niedrig"


def test_youtube_atom_parsing():
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
      <entry><id>yt:video:abc</id><title>Ski Aggu - ALBUM TRAILER</title>
        <link rel="alternate" href="https://www.youtube.com/watch?v=abc"/>
        <published>2026-10-13T16:00:00+00:00</published>
        <media:group><media:description>Album out 21.11. – pre-save now</media:description></media:group>
      </entry>
    </feed>"""
    with patch("radar.http.get", return_value=FakeResp(text=xml)):
        items = feeds.youtube("Ski Aggu", "UC123")
    assert items[0].url.endswith("v=abc")
    assert score(items[0], TODAY).level == "hoch"


def test_shopify_filter_for_label_shop():
    payload = {"products": [
        {"id": 10, "title": "Ski Aggu – Neues Album (Ltd. Vinyl)", "handle": "a", "vendor": "Label", "tags": ["vinyl"],
         "product_type": "LP", "body_html": "<p>VÖ 20.11.2026</p>"},
        {"id": 11, "title": "Anderer Artist – Hoodie", "handle": "b", "vendor": "Label", "tags": [], "body_html": ""},
    ]}
    with patch("radar.http.get", return_value=FakeResp(payload)):
        items = web.shopify("Ski Aggu", "https://shop.example.de/", "Ski Aggu")
    assert len(items) == 1 and items[0].url == "https://shop.example.de/products/a"
    assert score(items[0], TODAY).level == "hoch"


def test_website_diff(tmp_path):
    store = Store(tmp_path / "r.db")
    url = "https://artist.example"
    assert web.website("X", url, store, html="<p>Startseite</p><p>Tour 2026</p>") == []  # first snapshot
    assert web.website("X", url, store, html="<p>Startseite</p><p>Tour 2026</p>") == []  # unchanged
    items = web.website("X", url, store, html="<p>Startseite</p><p>Tour 2026</p><p>NEUES ALBUM – jetzt vorbestellen</p>")
    assert items and "NEUES ALBUM" in items[0].text and "Startseite" not in items[0].text


def test_evaluate_baseline_dedup_and_collision(tmp_path):
    store = Store(tmp_path / "r.db")
    own = runner.own_release_fridays({"releases": [{"artist": "Wir", "title": "Unser Album", "date": "2026-11-20"}]})
    old = Item("deezer", "deezer:1", "1", "Ski Aggu", "Altes Album", release_date=date(2024, 1, 5),
               record_type="album", structured=True)
    future = Item("deezer", "deezer:1", "2", "Ski Aggu", "Neues Album", release_date=date(2026, 11, 22),
                  record_type="album", structured=True)

    # First run: old catalog is baseline, but an already-listed future album is reported, with collision.
    sigs = runner.evaluate([old, future], store, TODAY, own, min_score=5)
    assert [s.item.item_id for s in sigs] == ["2"]
    assert "Unser Album" in sigs[0].collisions[0]

    # Second run: nothing new -> nothing reported.
    assert runner.evaluate([old, future], store, TODAY, own, min_score=5) == []

    # New entry later -> reported.
    single = Item("deezer", "deezer:1", "3", "Ski Aggu", "Album Teaser (Single)", record_type="single",
                  structured=True, text="vom kommenden Album, vorbestellen")
    assert [s.item.item_id for s in runner.evaluate([single], store, TODAY, own, min_score=5)] == ["3"]


def test_resolver_exact_match_and_ambiguity():
    from radar import resolver

    deezer = {"data": [
        {"id": 1, "name": "Ski Aggu", "nb_fan": 500000},
        {"id": 2, "name": "Ski Aggu & Friends", "nb_fan": 900000},
    ]}
    with patch("radar.http.get", return_value=FakeResp(deezer)):
        assert resolver.deezer_match("Ski Aggu") == {"deezer": 1, "deezer_fans": 500000}

    twins = {"data": [{"id": 5, "name": "Michelle", "nb_fan": 100000}, {"id": 6, "name": "Michelle", "nb_fan": 80000}]}
    with patch("radar.http.get", return_value=FakeResp(twins)):
        assert resolver.deezer_match("Michelle")["check"] is True

    mb = {"artists": [
        {"id": "us", "name": "Fantasy", "country": "US", "score": 100},
        {"id": "de", "name": "Fantasy", "country": "DE", "score": 100},
    ]}
    with patch("radar.http.get", return_value=FakeResp(mb)):
        assert resolver.musicbrainz_match("Fantasy", german=True) == {"musicbrainz": "de"}
        assert resolver.musicbrainz_match("Fantasy", german=False)["check"] is True

    assert resolver.norm("Badmómzjay") == resolver.norm("badmomzjay")


def test_auto_ids_merge_and_skip():
    artists = [
        {"name": "A", "ids": {"deezer": 99, "musicbrainz": None}},
        {"name": "B"},
        {"name": "C", "skip": True},
    ]
    auto = {"A": {"deezer": 1, "musicbrainz": "mb-a"}, "B": {"deezer": 2, "check": True}}
    merged = runner.with_auto_ids(artists, auto)
    assert [m["name"] for m in merged] == ["A", "B"]
    assert merged[0]["ids"] == {"deezer": 99, "musicbrainz": "mb-a"}  # manual wins, gaps filled
    assert merged[1]["ids"] == {"deezer": 2}


def test_artists_yaml_is_valid():
    import yaml

    artists = yaml.safe_load(open("artists.yaml", encoding="utf-8"))["artists"]
    names = [a["name"] for a in artists]
    assert len(names) == 200 and len(set(names)) == 200


def test_digest_lists_new_signals_and_collisions(tmp_path):
    from radar import digest
    from radar.models import Signal

    db = tmp_path / "r.db"
    store = Store(db)
    it = Item("deezer", "deezer:1", "2", "Ski Aggu", "Neues Album", url="https://deezer.example/a",
              release_date=date(2026, 11, 22), record_type="album", structured=True)
    store.save_signal(Signal(item=it, score=14, level="hoch", release_date=date(2026, 11, 22)))
    store.commit()
    own = tmp_path / "own.yaml"
    own.write_text("releases:\n  - {artist: Wir, title: Unser Album, date: 2026-11-20}\n", encoding="utf-8")

    subject, text, html = digest.build(str(db), str(own), today=TODAY)
    assert "1 neue Hinweise, davon 1 hoch" in subject and "Kollision" in subject
    assert "Ski Aggu" in text and "Chartwoche ab Fr 20.11.2026" in text and "Unser Album" in text
    assert "Ski Aggu" in html and "Kollision" in html


def test_digest_empty(tmp_path):
    from radar import digest

    subject, text, _ = digest.build(str(tmp_path / "r.db"), None, today=TODAY)
    assert subject.endswith("keine neuen Hinweise")
    assert "Keine neuen Album-Hinweise" in text
