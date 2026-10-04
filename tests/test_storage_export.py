import csv
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fbwatch.export import build_html_report, export_csv, export_json
from fbwatch.storage import PostRecord

TZ = ZoneInfo("Europe/Athens")


def _rec(pid, src, posted, seen="2026-10-04T10:00:00+03:00", **kw):
    return PostRecord(post_id=pid, source_id=src, permalink=f"https://www.facebook.com/{src}/posts/{pid}",
                      posted_at=posted, first_seen=seen, last_seen=seen, text=f"κείμενο {pid}", **kw)


def test_insert_query_filter(storage):
    storage.upsert_source("a", "page", "https://www.facebook.com/a", "A")
    storage.insert_post(_rec("1", "a", "2026-10-01T09:00:00+03:00"))
    storage.insert_post(_rec("2", "a", "2026-10-03T09:00:00+03:00"))
    storage.insert_post(_rec("3", "b", "2026-10-03T09:00:00+03:00"))
    storage.insert_post(_rec("4", "a", None))  # χωρίς ημερομηνία
    assert storage.count_posts() == 4 and storage.count_posts("a") == 3
    assert storage.has_post("2") and not storage.has_post("9")

    d_from, d_to = datetime(2026, 10, 2, tzinfo=TZ), datetime(2026, 10, 4, 23, 59, tzinfo=TZ)
    ids = {p.post_id for p in storage.query_posts(date_from=d_from, date_to=d_to)}
    assert ids == {"2", "3", "4"}  # το 4 (χωρίς ημερομηνία) περιλαμβάνεται από προεπιλογή
    ids = {p.post_id for p in storage.query_posts(date_from=d_from, date_to=d_to, include_undated=False)}
    assert ids == {"2", "3"}
    ids = {p.post_id for p in storage.query_posts(source_ids=["a"], date_from=d_from)}
    assert ids == {"2", "4"}
    ids = {p.post_id for p in storage.query_posts(date_field="first_seen", date_from=datetime(2026, 10, 4, tzinfo=TZ))}
    assert ids == {"1", "2", "3", "4"}


def test_touch_and_recapture(storage):
    storage.insert_post(_rec("1", "a", None, screenshot_path="s1.png", sha256="x"))
    storage.touch_post("1", "2026-10-05T10:00:00+03:00")
    storage.update_post_fields("1", posted_at="2026-10-01T00:00:00+03:00")
    storage.add_capture("1", "2026-10-05T10:00:00+03:00", "s2.png", None, "y")
    p = storage.get_post("1")
    assert p.last_seen == "2026-10-05T10:00:00+03:00" and p.screenshot_path == "s2.png" and p.sha256 == "y"
    assert p.posted_at == "2026-10-01T00:00:00+03:00"
    n = storage.conn.execute("SELECT COUNT(*) FROM captures WHERE post_id='1'").fetchone()[0]
    assert n == 2


def test_runs(storage):
    rid = storage.start_run("a", "2026-10-04T10:00:00+03:00")
    storage.finish_run(rid, "2026-10-04T10:01:00+03:00", "ok", 5, 2)
    r = storage.recent_runs(1)[0]
    assert r["status"] == "ok" and r["posts_new"] == 2


def test_export_csv_json_html(settings, tmp_path):
    posts = [_rec("1", "a", "2026-10-01T09:00:00+03:00", screenshot_path="screenshots/a/1.png", sha256="abc"),
             _rec("2", "a", None)]
    csv_path = export_csv(posts, tmp_path / "out.csv")
    raw = csv_path.read_bytes()
    assert raw.startswith("﻿".encode("utf-8"))  # BOM για Excel
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    assert rows[0]["post_id"] == "1" and rows[1]["posted_at"] == ""

    j = json.loads(export_json(posts, tmp_path / "out.json", {"k": 1}).read_text(encoding="utf-8"))
    assert j["meta"] == {"k": 1} and len(j["posts"]) == 2

    html = build_html_report(posts, settings, "Τίτλος", "Υπότιτλος")
    assert "Τίτλος" in html and "screenshots/a/1.png" in html and "<img" in html
    assert "<script" not in html  # το κείμενο των posts είναι escaped


def test_archive_retry_backoff(storage):
    storage.insert_post(_rec("1", "a", None))
    storage.insert_post(_rec("2", "a", None))
    assert {p.post_id for p in storage.posts_without_archive(now="2026-10-04T12:00:00+00:00")} == {"1", "2"}
    storage.update_post_fields("1", archive_requested_at="2026-10-04T11:00:00+00:00")  # απέτυχε πριν 1 ώρα
    assert {p.post_id for p in storage.posts_without_archive(now="2026-10-04T12:00:00+00:00")} == {"2"}
    assert {p.post_id for p in storage.posts_without_archive(now="2026-10-06T12:00:00+00:00")} == {"1", "2"}


def test_html_report_relative_images(settings):
    posts = [_rec("1", "a", "2026-10-01T09:00:00+03:00", screenshot_path="screenshots/a/1__x.png")]
    html = build_html_report(posts, settings, "T", "", img_dir="screenshots")
    assert 'src="screenshots/1__x.png"' in html and "file://" not in html
