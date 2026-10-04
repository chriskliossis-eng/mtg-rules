"""Προαιρετικό snapshot κάθε permalink στο Wayback Machine (archive.org) για ανεξάρτητη χρονοσήμανση."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from .config import Settings
from .storage import Storage

log = logging.getLogger("fbwatch")
SAVE_ENDPOINT = "https://web.archive.org/save/"


def wayback_save(url: str, timeout_s: int = 90, session: Optional[requests.Session] = None) -> Optional[str]:
    """Ζητά από το archive.org να αποθηκεύσει το URL. Επιστρέφει το URL του snapshot ή None."""
    s = session or requests.Session()
    headers = {"User-Agent": "fbwatch/0.1 (+https://github.com/) archiving public posts"}
    try:
        r = s.get(SAVE_ENDPOINT + url, headers=headers, timeout=timeout_s, allow_redirects=True)
    except requests.RequestException as e:
        log.warning("archive.org: %s", e)
        return None
    if r.status_code == 429:
        log.warning("archive.org: όριο ρυθμού (429), δοκίμασε αργότερα")
        return None
    for h in ("Content-Location", "Location"):
        loc = r.headers.get(h)
        if loc and "/web/" in loc:
            return loc if loc.startswith("http") else "https://web.archive.org" + loc
    if "/web/" in r.url:
        return r.url
    log.warning("archive.org: απρόσμενη απάντηση %s για %s", r.status_code, url)
    return None


def archive_pending(storage: Storage, settings: Settings, limit: int = 50, progress=None) -> int:
    say = progress or (lambda m: log.info(m))
    if not settings.archive.wayback:
        say("Το Wayback είναι απενεργοποιημένο στο config (archive.wayback: false)")
        return 0
    done = 0
    session = requests.Session()
    for rec in storage.posts_without_archive(limit):
        say(f"archive.org: {rec.permalink}")
        snap = wayback_save(rec.permalink, settings.archive.timeout_s, session)
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if snap:
            storage.update_post_fields(rec.post_id, archive_url=snap, archive_requested_at=now_iso)
            done += 1
            say(f"  -> {snap}")
        else:
            storage.update_post_fields(rec.post_id, archive_requested_at=now_iso)
    return done
