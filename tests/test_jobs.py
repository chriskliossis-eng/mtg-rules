import json
from datetime import datetime
from zoneinfo import ZoneInfo

from conftest import fixture_url
from fbwatch.config import Source, load_settings, save_sources, slug_from_url, normalize_page_url, ConfigError
from fbwatch.jobs import run_job

TZ = ZoneInfo("Europe/Athens")


def _src():
    return Source(id="ert", url="https://www.facebook.com/ertnews", label="ΕΡΤ", plugin_url=fixture_url("page_plugin.html"))


def test_run_job_creates_self_contained_folder(settings, storage):
    d_from, d_to = datetime(2025, 10, 1, tzinfo=TZ), datetime(2025, 10, 4, 23, 59, tzinfo=TZ)
    msgs = []
    res = run_job(settings, storage, "Δοκιμή Οκτ", [_src()], d_from, d_to, collect=True, make_pdf=True, progress=msgs.append)
    assert res.status == "ok" and res.posts_new == 4 and res.posts_count == 3  # 4 μαζεύτηκαν, 3 στο διάστημα
    names = sorted(p.name for p in res.folder.iterdir())
    assert names == ["anafora.html", "anafora.pdf", "elegxos.json", "posts.csv", "posts.json", "screenshots"]
    shots = list((res.folder / "screenshots").glob("*.png"))
    assert len(shots) == 3
    meta = json.loads((res.folder / "elegxos.json").read_text(encoding="utf-8"))
    assert meta["posts_count"] == 3 and meta["source_status"][0]["status"] == "ok"
    assert "elegxoi" in str(res.folder) and "Δοκιμή_Οκτ" in res.folder.name

    rows = storage.jobs()
    assert len(rows) == 1 and rows[0]["status"] == "ok" and rows[0]["posts_count"] == 3
    assert rows[0]["source_ids"] == "ert"

    # Δεύτερος έλεγχος χωρίς συλλογή: νέος φάκελος, ίδια posts, τίποτα νέο.
    res2 = run_job(settings, storage, "Δοκιμή Οκτ", [_src()], d_from, d_to, collect=False, make_pdf=False)
    assert res2.folder != res.folder and res2.posts_new == 0 and res2.posts_count == 3
    assert not (res2.folder / "anafora.pdf").exists()
    assert len(storage.jobs()) == 2


def test_run_job_without_posts_in_range(settings, storage):
    res = run_job(settings, storage, "Κενό", [_src()], datetime(2020, 1, 1, tzinfo=TZ), datetime(2020, 1, 2, tzinfo=TZ), collect=True)
    assert res.posts_count == 0 and (res.folder / "posts.csv").exists()


def test_slug_and_normalize():
    assert slug_from_url("https://www.facebook.com/latinopoulouafroditi/") == "latinopoulouafroditi"
    assert slug_from_url("https://www.facebook.com/ertnews", {"ertnews"}) == "ertnews_2"
    assert slug_from_url("https://www.facebook.com/profile.php?id=100044") == "id_100044"
    assert normalize_page_url("facebook.com/ertnews/?ref=page_internal") == "https://www.facebook.com/ertnews"
    assert normalize_page_url("https://m.facebook.com/profile.php?id=5&x=1") == "https://www.facebook.com/profile.php?id=5"
    import pytest
    with pytest.raises(ConfigError):
        normalize_page_url("https://twitter.com/x")


def test_save_sources_roundtrip(tmp_path):
    from fbwatch.cli import EXAMPLE_CONFIG
    import shutil
    cfg = tmp_path / "config.yaml"
    shutil.copyfile(EXAMPLE_CONFIG, cfg)
    s = load_settings(cfg)
    new = [Source(id="a", url="https://www.facebook.com/a", label="Α"), Source(id="b", url="https://www.facebook.com/b", label="Β β")]
    save_sources(s, new)
    s2 = load_settings(cfg)
    assert [(x.id, x.url, x.label) for x in s2.sources] == [("a", "https://www.facebook.com/a", "Α"), ("b", "https://www.facebook.com/b", "Β β")]
    assert s2.monitor.max_posts_per_run == 50  # οι υπόλοιπες ρυθμίσεις έμειναν
    text = cfg.read_text(encoding="utf-8")
    assert text.startswith("# ====") and "sources:" in text.splitlines()[5:7][0]
