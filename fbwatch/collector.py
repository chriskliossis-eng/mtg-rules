"""Ροές συλλογής: παρακολούθηση Page Plugin timeline και λήψη μεμονωμένων posts."""
from __future__ import annotations

import hashlib
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeout

from .config import Settings, Source
from .dates import to_iso
from .extract import FoundPost, PageStatus, best_frame, detect_status, find_posts, post_outer_html, screenshot_post, scroll_down
from .fburls import page_plugin_url, post_id_from_permalink, post_plugin_url, normalize_permalink
from .storage import PostRecord, Storage

log = logging.getLogger("fbwatch")


@dataclass
class SourceResult:
    source_id: str
    status: PageStatus
    posts_seen: int = 0
    posts_new: int = 0
    posts_recaptured: int = 0
    errors: list[str] = field(default_factory=list)
    new_post_ids: list[str] = field(default_factory=list)
    oldest: Optional[datetime] = None
    newest: Optional[datetime] = None


def _now(settings: Settings) -> datetime:
    return datetime.now(ZoneInfo(settings.timezone)).replace(microsecond=0)


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:120]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _target_url(source: Source, settings: Settings) -> str:
    if source.plugin_url:
        return source.plugin_url
    if source.kind == "page":
        return page_plugin_url(source.url, settings.browser.locale, settings.browser.plugin_height)
    return post_plugin_url(source.url, settings.browser.locale)


def _goto(page: Page, url: str, settings: Settings) -> None:
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=min(settings.browser.timeout_ms, 20000))
    except PWTimeout:
        pass
    page.wait_for_timeout(settings.browser.settle_ms)


def _capture_files(page, post: FoundPost, source: Source, settings: Settings, when: datetime) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Screenshot + HTML για ένα post. Επιστρέφει (screenshot_path, html_path, sha256) σχετικά με data_dir."""
    stamp = when.strftime("%Y%m%d_%H%M%S")
    base = f"{_safe_name(post.post_id)}__{stamp}"
    shot_dir = settings.screenshots_dir / _safe_name(source.id)
    shot_dir.mkdir(parents=True, exist_ok=True)
    shot_path = shot_dir / f"{base}.png"
    screenshot_post(page, post.marker, shot_path, settings.browser.settle_ms)
    digest = _sha256(shot_path)
    html_rel = None
    if settings.monitor.save_html:
        html_dir = settings.html_dir / _safe_name(source.id)
        html_dir.mkdir(parents=True, exist_ok=True)
        html_path = html_dir / f"{base}.html"
        header = (
            f"<!-- fbwatch capture | source={source.id} | permalink={post.permalink} | "
            f"captured_at={to_iso(when)} | page_url={page.url} -->\n"
        )
        html_path.write_text(header + post_outer_html(page, post.marker), encoding="utf-8")
        html_rel = str(html_path.relative_to(settings.data_dir))
    return str(shot_path.relative_to(settings.data_dir)), html_rel, digest


def _store(post: FoundPost, source: Source, settings: Settings, storage: Storage, page, when: datetime, result: SourceResult) -> None:
    seen_iso = to_iso(when)
    existing = storage.get_post(post.post_id)
    if existing is None:
        shot, html, digest = _capture_files(page, post, source, settings, when)
        storage.insert_post(
            PostRecord(
                post_id=post.post_id, source_id=source.id, permalink=post.permalink, author=post.author,
                text=post.text, posted_at=to_iso(post.posted_at), posted_at_raw=post.posted_at_raw,
                first_seen=seen_iso, last_seen=seen_iso, screenshot_path=shot, html_path=html, sha256=digest,
            )
        )
        result.posts_new += 1
        result.new_post_ids.append(post.post_id)
        log.info("  ΝΕΟ  %s  %s  %s", post.post_id, to_iso(post.posted_at) or "(χωρίς ημερομηνία)", (post.text or "")[:60].replace("\n", " "))
    else:
        storage.touch_post(post.post_id, seen_iso)
        # Αν τώρα έχουμε ακριβή ημερομηνία ενώ πριν όχι, κράτα την.
        if existing.posted_at is None and post.posted_at is not None:
            storage.update_post_fields(post.post_id, posted_at=to_iso(post.posted_at), posted_at_raw=post.posted_at_raw)
        if settings.monitor.recapture_existing:
            shot, html, digest = _capture_files(page, post, source, settings, when)
            storage.add_capture(post.post_id, seen_iso, shot, html, digest, make_current=True)
            result.posts_recaptured += 1


def collect_source(
    context: BrowserContext,
    source: Source,
    settings: Settings,
    storage: Storage,
    stop_before: Optional[datetime] = None,
    dry_run: bool = False,
    progress: Optional[Callable[[str], None]] = None,
    dump_dir: Optional[Path] = None,
) -> SourceResult:
    """Ανοίγει το plugin μιας πηγής, μαζεύει posts και (αν όχι dry_run) αποθηκεύει screenshots."""
    say = progress or (lambda msg: log.info(msg))
    when = _now(settings)
    result = SourceResult(source_id=source.id, status=PageStatus("ok"))
    url = _target_url(source, settings)
    say(f"[{source.id}] Άνοιγμα {url}")
    page = context.new_page()
    try:
        _goto(page, url, settings)
        target, posts = best_frame(page, settings.timezone, when)
        if target is not page.main_frame:
            say(f"[{source.id}] Το περιεχόμενο βρέθηκε σε εσωτερικό πλαίσιο (iframe)")
        found: dict[str, FoundPost] = {}
        stale_rounds = 0
        max_stale = 4
        max_rounds = settings.monitor.max_scroll_rounds if source.kind == "page" else 1
        rounds_done = 0
        last_info: dict = {}
        for rnd in range(max_rounds):
            if rnd > 0:
                posts = find_posts(target, settings.timezone, when)
            rounds_done = rnd + 1
            new_here = [p for p in posts if p.post_id not in found]
            for p in posts:
                found[p.post_id] = p  # κράτα το πιο πρόσφατο marker
            if rnd == 0 and not posts:
                break
            if len(found) >= settings.monitor.max_posts_per_run:
                say(f"[{source.id}] Έφτασα το όριο {settings.monitor.max_posts_per_run} posts ανά εκτέλεση")
                break
            dated = [p.posted_at for p in found.values() if p.posted_at]
            if stop_before and dated and min(dated) < stop_before:
                say(f"[{source.id}] Βρέθηκαν posts παλαιότερα από {stop_before:%d/%m/%Y}, σταματώ το scroll")
                break
            if source.kind != "page":
                break
            if not new_here:
                stale_rounds += 1
                if stale_rounds >= max_stale:
                    break
            else:
                stale_rounds = 0
            # Στους "στάσιμους" γύρους περίμενε περισσότερο: το plugin φορτώνει ασύγχρονα.
            last_info = scroll_down(target, settings.browser.settle_ms * (1 + stale_rounds))
            say(f"[{source.id}] scroll {rnd + 1}: {len(found)} posts, ύψος {last_info['before']}→{last_info['after']}"
                + (f", εσωτερικό {last_info['inner_before']}→{last_info['inner_after']}" if last_info['scrollers'] else ", χωρίς εσωτερικό scroller")
                + ("" if last_info["grew"] or new_here else " (τίποτα νέο)"))
        if source.kind == "page" and found and rounds_done > 1 and last_info and not last_info.get("grew"):
            say(f"[{source.id}] Το Facebook δεν έδωσε παλαιότερα posts μετά από {rounds_done} γύρους scroll. "
                "Χωρίς σύνδεση το plugin δείχνει μόνο τα πιο πρόσφατα, γι' αυτό η συλλογή πρέπει να γίνεται τακτικά.")

        result.status = detect_status(page, len(found))
        result.posts_seen = len(found)
        if dump_dir is not None:
            dump_dir.mkdir(parents=True, exist_ok=True)
            stem = dump_dir / f"{_safe_name(source.id)}_{when:%Y%m%d_%H%M%S}"
            stem.with_name(stem.name + ".html").write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(stem.with_name(stem.name + ".png")), full_page=True)
            say(f"[{source.id}] Αποθηκεύτηκαν για διάγνωση: {stem}.html / .png")
        if result.status.kind != "ok":
            say(f"[{source.id}] {result.status.kind}: {result.status.detail}")
            return result

        # Τελικό πέρασμα για φρέσκους markers (το DOM μπορεί να ξαναχτίστηκε στο scroll).
        posts = find_posts(target, settings.timezone, when)
        by_id = {p.post_id: p for p in posts}
        ordered = sorted(found.values(), key=lambda p: (p.posted_at or when), reverse=True)
        dated = [p.posted_at for p in ordered if p.posted_at]
        if dated:
            result.oldest, result.newest = min(dated), max(dated)
        say(f"[{source.id}] Βρέθηκαν {len(ordered)} posts" + (f" ({result.oldest:%d/%m/%Y} έως {result.newest:%d/%m/%Y})" if dated else ""))
        if dry_run:
            return result
        storage.upsert_source(source.id, source.kind, source.url, source.label)
        for p in ordered:
            if stop_before and p.posted_at and p.posted_at < stop_before:
                continue
            current = by_id.get(p.post_id)
            if current is None:
                # Το post δεν είναι πλέον στο DOM (το plugin το ξεφόρτωσε). Ποτέ screenshot με παλιό marker.
                if not storage.has_post(p.post_id):
                    msg = f"{p.post_id}: δεν είναι πλέον ορατό στη σελίδα, παραλείπεται (θα ληφθεί σε επόμενη εκτέλεση)"
                    result.errors.append(msg)
                    say(f"  ΠΡΟΣΟΧΗ {msg}")
                continue
            try:
                _store(current, source, settings, storage, target, when, result)
            except Exception as e:  # ένα post δεν πρέπει να ρίχνει όλη την εκτέλεση
                msg = f"{p.post_id}: {type(e).__name__}: {e}"
                result.errors.append(msg)
                say(f"  ΣΦΑΛΜΑ {msg}")
        return result
    finally:
        page.close()


def capture_single_post(
    context: BrowserContext, post_url: str, settings: Settings, storage: Storage,
    source_id: str = "manual", label: str = "Χειροκίνητες λήψεις", progress: Optional[Callable[[str], None]] = None,
) -> SourceResult:
    """Λήψη ενός post από το URL του (λειτουργία 'capture by URL')."""
    source = Source(id=source_id, url=normalize_permalink(post_url), kind="post", label=label)
    res = collect_source(context, source, settings, storage, progress=progress)
    if res.status.kind == "ok" and res.posts_seen == 0:
        res.status = PageStatus("empty", "Το plugin φόρτωσε αλλά δεν αναγνωρίστηκε post")
    return res


def pause_between_sources(settings: Settings) -> None:
    lo, hi = settings.monitor.delay_between_sources_s
    if hi <= 0:
        return
    time.sleep(random.uniform(lo, hi))
