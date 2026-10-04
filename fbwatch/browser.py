"""Εκκίνηση Chromium μέσω Playwright, χωρίς login και χωρίς cookies."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright

from .config import BrowserSettings

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def resolve_executable(settings: BrowserSettings) -> str | None:
    """Σειρά: config -> μεταβλητή περιβάλλοντος FBWATCH_CHROMIUM -> Chromium του Playwright."""
    if settings.executable_path:
        return settings.executable_path
    env = os.environ.get("FBWATCH_CHROMIUM")
    if env:
        return env
    return None


@contextmanager
def open_browser(settings: BrowserSettings, timezone: str = "Europe/Athens", headless: bool | None = None) -> Iterator[BrowserContext]:
    pw: Playwright
    with sync_playwright() as pw:
        kwargs = {
            "headless": settings.headless if headless is None else headless,
            "slow_mo": settings.slow_mo_ms or 0,
        }
        exe = resolve_executable(settings)
        if exe:
            kwargs["executable_path"] = exe
        browser: Browser = pw.chromium.launch(**kwargs)
        try:
            context = browser.new_context(
                locale=settings.locale,
                timezone_id=timezone,
                viewport={"width": settings.viewport_width, "height": settings.viewport_height},
                user_agent=settings.user_agent or DEFAULT_UA,
                device_scale_factor=2,  # ευκρινή screenshots
            )
            context.set_default_timeout(settings.timeout_ms)
            try:
                yield context
            finally:
                context.close()
        finally:
            browser.close()
