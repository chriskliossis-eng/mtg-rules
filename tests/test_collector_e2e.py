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


def test_inner_scroller_lazy_load_is_followed(browser_context, settings, storage):
    """Posts μέσα σε εσωτερικό scrollable container που φορτώνει ασύγχρονα σε δύο δόσεις."""
    msgs = []
    res = collect_source(browser_context, _page_source("inner", "page_plugin_inner.html"), settings, storage, progress=msgs.append)
    assert res.status.kind == "ok"
    assert res.posts_seen == 4, msgs
    assert any("scroll 1:" in m and "εσωτερικό" in m for m in msgs)


def test_content_inside_iframe_is_found(browser_context, settings, storage):
    msgs = []
    res = collect_source(browser_context, _page_source("ifr", "page_plugin_iframe.html"), settings, storage, progress=msgs.append)
    assert res.status.kind == "ok" and res.posts_seen == 4, msgs
    assert any("iframe" in m for m in msgs)
    p = storage.get_post("post_1001")
    assert (settings.data_dir / p.screenshot_path).stat().st_size > 1000


def test_no_more_posts_message(browser_context, settings, storage):
    msgs = []
    collect_source(browser_context, _page_source(), settings, storage, progress=msgs.append)
    assert any("δεν έδωσε παλαιότερα posts" in m for m in msgs)


def test_markers_are_fresh_on_every_find(browser_context):
    """Παλιοί markers αφαιρούνται και κάθε κλήση έχει δικό της πρόθεμα: ποτέ screenshot λάθος post."""
    from fbwatch.extract import find_posts

    page = browser_context.new_page()
    page.goto(fixture_url("page_plugin.html"))
    first = find_posts(page, "Europe/Athens")
    second = find_posts(page, "Europe/Athens")
    assert {p.marker for p in first}.isdisjoint({p.marker for p in second})
    for p in first:
        assert page.locator(f"[data-fbwatch-id='{p.marker}']").count() == 0
    for p in second:
        assert page.locator(f"[data-fbwatch-id='{p.marker}']").count() == 1
    page.close()


def test_dotted_source_id_files_keep_full_name(browser_context, settings, storage):
    src = Source(id="in.gr", url="https://www.facebook.com/in.gr", label="in.gr", plugin_url=fixture_url("page_plugin.html"))
    dump = settings.data_dir / "debug"
    collect_source(browser_context, src, settings, storage, dry_run=True, dump_dir=dump, progress=lambda m: None)
    names = sorted(p.name for p in dump.iterdir())
    assert all(n.startswith("in.gr_") and n.endswith((".html", ".png")) for n in names), names
