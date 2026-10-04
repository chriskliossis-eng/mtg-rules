"""Έλεγχοι: μια εκτέλεση με όνομα, σελίδες και χρονικό διάστημα, που σώζεται σε δικό της φάκελο."""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .config import Settings, Source
from .dates import to_iso
from .export import export_csv, export_html, export_json, export_pdf
from .storage import Storage


@dataclass
class JobResult:
    job_id: int
    name: str
    folder: Path
    posts_count: int = 0
    posts_new: int = 0
    status: str = "ok"
    source_results: list = field(default_factory=list)
    files: list[Path] = field(default_factory=list)


def _safe(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", s.strip())
    return s.strip("._") [:60] or "elegxos"


def job_folder(settings: Settings, name: str, when: datetime) -> Path:
    base = settings.data_dir / "elegxoi"
    folder = base / f"{when:%Y-%m-%d_%H-%M}_{_safe(name)}"
    n = 2
    while folder.exists():
        folder = base / f"{when:%Y-%m-%d_%H-%M}_{_safe(name)}_{n}"
        n += 1
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def run_job(
    settings: Settings,
    storage: Storage,
    name: str,
    sources: list[Source],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    collect: bool = True,
    headed: bool = False,
    make_pdf: bool = True,
    progress: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
) -> JobResult:
    """Συλλέγει (προαιρετικά) νέα posts από τις σελίδες και εξάγει το χρονικό διάστημα σε νέο φάκελο."""
    say = progress or (lambda m: None)
    when = datetime.now(ZoneInfo(settings.timezone)).replace(microsecond=0)
    folder = job_folder(settings, name, when)
    job_id = storage.insert_job(name, to_iso(when), to_iso(date_from), to_iso(date_to), [s.id for s in sources],
                                str(folder.relative_to(settings.data_dir)))
    result = JobResult(job_id=job_id, name=name, folder=folder)
    say(f"Έλεγχος «{name}»: φάκελος {folder}")
    try:
        if collect and sources:
            from .browser import open_browser
            from .collector import collect_source, pause_between_sources

            with open_browser(settings.browser, settings.timezone, headless=not headed) as ctx:
                for i, src in enumerate(sources):
                    if stop_flag and stop_flag():
                        say("Διακοπή από τον χρήστη.")
                        break
                    run_id = storage.start_run(src.id, to_iso(datetime.now(ZoneInfo(settings.timezone))))
                    try:
                        res = collect_source(ctx, src, settings, storage, progress=say)  # αποθηκεύουμε ό,τι δείχνει το plugin, το φίλτρο μπαίνει στην εξαγωγή
                    except Exception as e:  # noqa: BLE001
                        say(f"[{src.id}] ΣΦΑΛΜΑ: {type(e).__name__}: {e}")
                        storage.finish_run(run_id, to_iso(datetime.now(ZoneInfo(settings.timezone))), "error", 0, 0, str(e))
                        continue
                    storage.finish_run(run_id, to_iso(datetime.now(ZoneInfo(settings.timezone))), res.status.kind,
                                       res.posts_seen, res.posts_new, "; ".join(res.errors)[:1000])
                    result.source_results.append(res)
                    result.posts_new += res.posts_new
                    if i < len(sources) - 1:
                        pause_between_sources(settings)

        posts = storage.query_posts(source_ids=[s.id for s in sources] or None, date_from=date_from, date_to=date_to,
                                    include_undated=False)
        result.posts_count = len(posts)
        say(f"Στο διάστημα βρέθηκαν {len(posts)} posts. Δημιουργία αρχείων...")

        # Αντίγραφα screenshots και HTML μέσα στον φάκελο του ελέγχου, ώστε να είναι αυτοτελής.
        shots_dir = folder / "screenshots"
        shots_dir.mkdir(exist_ok=True)
        for p in posts:
            for rel in (p.screenshot_path, p.html_path):
                if rel:
                    src_file = settings.data_dir / rel
                    if src_file.exists():
                        shutil.copy2(src_file, shots_dir / src_file.name)

        label = ", ".join(s.label or s.id for s in sources) if sources else "όλες οι σελίδες"
        subtitle = _period_text(date_from, date_to)
        title = f"Έλεγχος: {name}"
        base = folder / "posts"
        result.files.append(export_csv(posts, base.with_suffix(".csv")))
        result.files.append(export_json(posts, base.with_suffix(".json"), {
            "job": name, "sources": [s.id for s in sources], "from": to_iso(date_from), "to": to_iso(date_to)}))
        html_path = export_html(posts, settings, folder / "anafora.html", title, f"{label} · {subtitle}")
        result.files.append(html_path)
        if make_pdf and posts:
            result.files.append(export_pdf(html_path, folder / "anafora.pdf", settings))

        meta = {
            "name": name, "created_at": to_iso(when), "from": to_iso(date_from), "to": to_iso(date_to),
            "sources": [{"id": s.id, "label": s.label, "url": s.url} for s in sources],
            "posts_count": len(posts), "posts_new_this_run": result.posts_new,
            "source_status": [{"id": r.source_id, "status": r.status.kind, "detail": r.status.detail,
                               "posts_seen": r.posts_seen, "posts_new": r.posts_new} for r in result.source_results],
        }
        (folder / "elegxos.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        storage.finish_job(job_id, "ok", len(posts), result.posts_new)
        say(f"Ολοκληρώθηκε: {len(posts)} posts, {len(result.files)} αρχεία στο {folder}")
    except Exception as e:  # noqa: BLE001
        result.status = "error"
        storage.finish_job(job_id, "error", result.posts_count, result.posts_new, str(e))
        say(f"ΣΦΑΛΜΑ: {type(e).__name__}: {e}")
        raise
    return result


def _period_text(date_from: Optional[datetime], date_to: Optional[datetime]) -> str:
    if date_from and date_to:
        return f"Περίοδος {date_from:%d/%m/%Y} έως {date_to:%d/%m/%Y}"
    if date_from:
        return f"Από {date_from:%d/%m/%Y}"
    if date_to:
        return f"Έως {date_to:%d/%m/%Y}"
    return "Όλη η συλλογή"
