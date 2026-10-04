import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CHROMIUM = os.environ.get("FBWATCH_CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)


def fixture_url(name: str) -> str:
    return (FIXTURES / name).resolve().as_uri()


@pytest.fixture
def settings(tmp_path):
    from fbwatch.config import BrowserSettings, MonitorSettings, Settings

    s = Settings(
        data_dir=tmp_path / "data",
        browser=BrowserSettings(settle_ms=300, executable_path=CHROMIUM),
        monitor=MonitorSettings(delay_between_sources_s=(0, 0)),
    )
    s.ensure_dirs()
    return s


@pytest.fixture
def storage(settings):
    from fbwatch.storage import Storage

    with Storage(settings.db_path) as st:
        yield st


@pytest.fixture
def browser_context():
    # Ανά test, ώστε tests που ανοίγουν δικό τους browser (jobs) να μη συγκρούονται με ανοιχτό Playwright loop.
    from fbwatch.browser import open_browser
    from fbwatch.config import BrowserSettings

    with open_browser(BrowserSettings(settle_ms=300, executable_path=CHROMIUM)) as ctx:
        yield ctx
