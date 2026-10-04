"""Smoke test του γραφικού περιβάλλοντος. Τρέχει μόνο αν υπάρχει tkinter και οθόνη (ή xvfb)."""
import os
import shutil

import pytest

tk = pytest.importorskip("tkinter")
if not os.environ.get("DISPLAY"):
    pytest.skip("Χωρίς DISPLAY", allow_module_level=True)


@pytest.fixture
def app(tmp_path):
    from fbwatch.cli import EXAMPLE_CONFIG
    from fbwatch.gui import App

    cfg = tmp_path / "config.yaml"
    shutil.copyfile(EXAMPLE_CONFIG, cfg)
    a = App(cfg)
    a.update()
    yield a
    a.destroy()


def test_app_starts_and_lists_pages(app):
    ids = app.pages.get_children()
    assert list(ids) == ["ertnews", "in_gr"]
    assert app.date_from.get() and app.date_to.get()
    d_from, d_to = app.period()
    assert d_from < d_to
    assert app.selected_sources() and len(app.selected_sources()) == 2
    app.pages.selection_set("ertnews")
    assert [s.id for s in app.selected_sources()] == ["ertnews"]


def test_add_and_remove_page_persist(app, monkeypatch):
    from fbwatch.config import Source, load_settings
    from fbwatch import gui

    class FakeDialog:
        def __init__(self, parent, existing):
            self.result = Source(id="latinopoulouafroditi", url="https://www.facebook.com/latinopoulouafroditi", label="Λ")

    monkeypatch.setattr(gui, "PageDialog", FakeDialog)
    app.add_page()
    assert "latinopoulouafroditi" in app.pages.get_children()
    assert any(s.id == "latinopoulouafroditi" for s in load_settings(app.config_path).sources)

    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    app.pages.selection_set("in_gr")
    app.remove_page()
    assert "in_gr" not in app.pages.get_children()
    assert [s.id for s in load_settings(app.config_path).sources] == ["ertnews", "latinopoulouafroditi"]


def test_job_history_refresh(app):
    from fbwatch.storage import Storage

    with Storage(app.settings.db_path) as st:
        jid = st.insert_job("Δοκιμή", "2026-10-04T10:00:00+03:00", "2026-09-04T00:00:00+03:00", "2026-10-04T23:59:59+03:00", ["ertnews"], "elegxoi/x")
        st.finish_job(jid, "ok", 7, 2)
    app.refresh_jobs()
    rows = app.jobs.get_children()
    assert len(rows) == 1
    vals = app.jobs.item(rows[0], "values")
    assert vals[1] == "Δοκιμή" and vals[2] == "04/09/2026 – 04/10/2026" and vals[3] == "ΕΡΤ News" and str(vals[4]) == "7"


def test_period_quick_buttons(app):
    app.set_period(7)
    d_from, d_to = app.period()
    assert (d_to.date() - d_from.date()).days == 7
    app.set_period(None)
    assert app.period() == (None, None)


def test_full_job_through_gui_thread(app):
    """Εκτέλεση ελέγχου από το παράθυρο: worker thread + Playwright + εξαγωγή + ιστορικό."""
    from conftest import CHROMIUM, fixture_url
    from fbwatch.config import Source

    app.settings.browser.executable_path = CHROMIUM
    app.settings.browser.settle_ms = 300
    app.settings.sources = [Source(id="ert", url="https://www.facebook.com/ertnews", label="ΕΡΤ", plugin_url=fixture_url("page_plugin.html"))]
    app.refresh_pages()
    app.job_name.delete(0, "end"); app.job_name.insert(0, "GUI δοκιμή")
    app.date_from.delete(0, "end"); app.date_from.insert(0, "01/10/2025")
    app.date_to.delete(0, "end"); app.date_to.insert(0, "04/10/2025")
    app.opt_pdf.set(False)
    app.run_job()
    assert app.worker is not None
    for _ in range(600):  # έως ~60s
        app.update()
        if not app.worker.is_alive() and app.q.empty():
            break
        import time; time.sleep(0.1)
    app.update()
    rows = app.jobs.get_children()
    assert len(rows) == 1
    vals = app.jobs.item(rows[0], "values")
    assert vals[1] == "GUI δοκιμή" and str(vals[4]) == "3" and vals[5] == "ok"
    assert app.page_status["ert"] == "ok (4)"
    folders = list((app.settings.data_dir / "elegxoi").iterdir())
    assert len(folders) == 1 and (folders[0] / "posts.csv").exists() and len(list((folders[0] / "screenshots").glob("*.png"))) == 3
    assert str(app.btn_job["state"]) == "normal"
