"""End-to-end με τοπικά HTML που μιμούνται τα plugins του Facebook (χωρίς δίκτυο)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from conftest import fixture_url
from fbwatch.collector import capture_single_post, collect_source
from fbwatch.config import Source


def _page_source(name="ert", fixture="page_plugin.html", kind="page"):
    return Source(id=name, url="https://www.facebook.com/ertnews", kind=kind, label="ΕΡΤ", plugin_url=fixture_url(fixture))


def test_collect_timeline_with_lazy_load_and_dedupe(browser_context, settings, storage):
    res = collect_source(browser_context, _page_source(), settings, storage, progress=lambda m: None)
    assert res.status.kind == "ok"
    assert res.posts_seen == 4 and res.posts_new == 4 and not res.errors  # 5 στοιχεία, 1 διπλότυπο
    ids = {p.post_id for p in storage.query_posts()}
    assert ids == {"post_1001", "story_fbid_2002", "video_3003", "post_4004"}

    p = storage.get_post("post_1001")
    assert p.posted_at == "2025-10-04T11:00:00+03:00"  # από data-utime
    assert p.author == "ΕΡΤ News" and "Πρώτο δημόσιο post" in p.text
    assert p.permalink == "https://www.facebook.com/ertnews/posts/1001"  # χωρίς tracking params
    assert (settings.data_dir / p.screenshot_path).stat().st_size > 1000
    assert (settings.data_dir / p.html_path).read_text(encoding="utf-8").startswith("<!-- fbwatch capture")
    assert len(p.sha256) == 64

    v = storage.get_post("video_3003")
    assert v.posted_at == "2025-10-01T21:30:00+03:00"  # μόνο από title (χωρίς data-utime)

    # Δεύτερο πέρασμα: τίποτα νέο, μόνο last_seen.
    res2 = collect_source(browser_context, _page_source(), settings, storage, progress=lambda m: None)
    assert res2.posts_seen == 4 and res2.posts_new == 0
    assert storage.count_posts() == 4


def test_stop_before_limits_backfill(browser_context, settings, storage):
    stop = datetime(2025, 10, 2, tzinfo=ZoneInfo("Europe/Athens"))
    res = collect_source(browser_context, _page_source(), settings, storage, stop_before=stop, progress=lambda m: None)
    assert res.status.kind == "ok"
    ids = {p.post_id for p in storage.query_posts()}
    assert "post_4004" not in ids and "video_3003" not in ids and "post_1001" in ids


def test_recapture_existing(browser_context, settings, storage):
    settings.monitor.recapture_existing = True
    collect_source(browser_context, _page_source(), settings, storage, progress=lambda m: None)
    res = collect_source(browser_context, _page_source(), settings, storage, progress=lambda m: None)
    assert res.posts_recaptured == 4
    n = storage.conn.execute("SELECT COUNT(*) FROM captures").fetchone()[0]
    assert n == 8


def test_dry_run_saves_nothing(browser_context, settings, storage):
    res = collect_source(browser_context, _page_source(), settings, storage, dry_run=True, progress=lambda m: None)
    assert res.posts_seen == 4 and storage.count_posts() == 0
    assert not list(settings.screenshots_dir.rglob("*.png"))


def test_login_wall_and_unavailable_detected(browser_context, settings, storage):
    r1 = collect_source(browser_context, _page_source("w", "loginwall.html"), settings, storage, progress=lambda m: None)
    assert r1.status.kind == "login_wall" and r1.posts_seen == 0
    r2 = collect_source(browser_context, _page_source("u", "unavailable.html"), settings, storage, progress=lambda m: None)
    assert r2.status.kind == "unavailable"
    assert storage.count_posts() == 0


def test_capture_single_post(browser_context, settings, storage, monkeypatch):
    import fbwatch.collector as col

    monkeypatch.setattr(col, "post_plugin_url", lambda url, locale: fixture_url("post_embed.html"))
    res = capture_single_post(browser_context, "https://www.facebook.com/somepage/posts/777?__tn__=z", settings, storage)
    assert res.status.kind == "ok" and res.posts_new == 1
    p = storage.get_post("post_777")
    assert p.source_id == "manual" and p.screenshot_path.startswith("screenshots/manual/")


def test_dump_writes_debug_files(browser_context, settings, storage):
    dump = settings.data_dir / "debug"
    res = collect_source(browser_context, _page_source(), settings, storage, dry_run=True, dump_dir=dump, progress=lambda m: None)
    assert res.status.kind == "ok"
    files = sorted(x.suffix for x in dump.iterdir())
    assert files == [".html", ".png"]
