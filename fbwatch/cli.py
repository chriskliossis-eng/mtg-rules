"""Γραμμή εντολών του fbwatch."""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from . import __version__
from .config import ConfigError, Settings, load_settings
from .dates import parse_user_date, to_iso

log = logging.getLogger("fbwatch")
EXAMPLE_CONFIG = Path(__file__).resolve().parent.parent / "config.example.yaml"


def _parse_every(text: str) -> int:
    m = re.fullmatch(r"(\d+)\s*([smhd])", text.strip().lower())
    if not m:
        raise argparse.ArgumentTypeError("Μορφή: 30m, 2h, 1d")
    n, unit = int(m.group(1)), m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _say(msg: str) -> None:
    print(msg, flush=True)


def _settings(args) -> Settings:
    try:
        s = load_settings(args.config)
    except ConfigError as e:
        sys.exit(f"Σφάλμα config: {e}")
    s.ensure_dirs()
    return s


def _sources(settings: Settings, wanted: Optional[list[str]]):
    if not wanted:
        return settings.sources
    try:
        return [settings.source(w) for w in wanted]
    except ConfigError as e:
        sys.exit(str(e))


def _dates(args, tz: str):
    d_from = parse_user_date(args.date_from, tz) if getattr(args, "date_from", None) else None
    d_to = parse_user_date(args.date_to, tz, end_of_day=True) if getattr(args, "date_to", None) else None
    return d_from, d_to


# --- commands --------------------------------------------------------------

def cmd_init(args) -> None:
    dest = Path(args.config)
    if dest.exists() and not args.force:
        sys.exit(f"Υπάρχει ήδη {dest}. Χρησιμοποίησε --force για αντικατάσταση.")
    shutil.copyfile(EXAMPLE_CONFIG, dest)
    _say(f"Δημιουργήθηκε {dest}. Άνοιξέ το και βάλε τις Pages που θέλεις στο 'sources'.")


def _run_sources(settings: Settings, sources, dry_run: bool, headed: bool, stop_before, storage=None, dump: bool = False) -> list:
    from .browser import open_browser
    from .collector import collect_source, pause_between_sources

    results = []
    with open_browser(settings.browser, settings.timezone, headless=not headed) as ctx:
        for i, src in enumerate(sources):
            started = datetime.now(ZoneInfo(settings.timezone)).replace(microsecond=0)
            run_id = storage.start_run(src.id, to_iso(started)) if storage and not dry_run else None
            try:
                res = collect_source(ctx, src, settings, storage, stop_before=stop_before, dry_run=dry_run, progress=_say,
                                     dump_dir=(settings.data_dir / "debug") if dump else None)
            except Exception as e:  # noqa: BLE001
                log.exception("Σφάλμα στην πηγή %s", src.id)
                _say(f"[{src.id}] ΣΦΑΛΜΑ: {type(e).__name__}: {e}")
                if run_id is not None:
                    storage.finish_run(run_id, to_iso(datetime.now(ZoneInfo(settings.timezone))), "error", 0, 0, str(e))
                continue
            results.append(res)
            if run_id is not None:
                storage.finish_run(
                    run_id, to_iso(datetime.now(ZoneInfo(settings.timezone)).replace(microsecond=0)),
                    res.status.kind, res.posts_seen, res.posts_new, "; ".join(res.errors)[:1000],
                )
            if i < len(sources) - 1:
                pause_between_sources(settings)
    return results


def _summary(results, dry_run: bool) -> None:
    _say("")
    _say("Σύνοψη:")
    for r in results:
        line = f"  {r.source_id:20s} {r.status.kind:12s} posts: {r.posts_seen:3d}"
        if not dry_run:
            line += f"  νέα: {r.posts_new:3d}"
            if r.posts_recaptured:
                line += f"  ξαναλήφθηκαν: {r.posts_recaptured}"
        if r.oldest and r.newest:
            line += f"  ({r.oldest:%d/%m/%Y} έως {r.newest:%d/%m/%Y})"
        if r.errors:
            line += f"  σφάλματα: {len(r.errors)}"
        if r.status.kind != "ok":
            line += f"  -> {r.status.detail}"
        _say(line)


def cmd_check(args) -> None:
    settings = _settings(args)
    sources = _sources(settings, args.source)
    if not sources:
        sys.exit("Δεν υπάρχουν πηγές στο config.")
    _say(f"Έλεγχος {len(sources)} πηγών χωρίς αποθήκευση (dry run)...")
    results = _run_sources(settings, sources, dry_run=True, headed=args.headed, stop_before=None, dump=args.dump)
    _summary(results, dry_run=True)


def cmd_run(args) -> None:
    from .storage import Storage

    settings = _settings(args)
    sources = _sources(settings, args.source)
    if not sources:
        sys.exit("Δεν υπάρχουν πηγές στο config.")
    stop_before = parse_user_date(args.since, settings.timezone) if args.since else None
    every = _parse_every(args.every) if args.every else None
    if args.loop and not every:
        every = 2 * 3600
    with Storage(settings.db_path) as storage:
        while True:
            started = time.time()
            _say(f"=== Εκτέλεση {datetime.now(ZoneInfo(settings.timezone)):%d/%m/%Y %H:%M:%S} ===")
            try:
                results = _run_sources(settings, sources, dry_run=False, headed=args.headed, stop_before=stop_before, storage=storage)
                _summary(results, dry_run=False)
                if settings.archive.enabled:
                    from .archive import archive_pending
                    n = archive_pending(storage, settings, limit=50, progress=_say)
                    _say(f"archive.org: {n} νέα snapshots")
            except Exception as e:  # noqa: BLE001
                if not args.loop:
                    raise
                _say(f"ΣΦΑΛΜΑ σε αυτή την εκτέλεση: {type(e).__name__}: {e}. Συνεχίζω στην επόμενη.")
            if not args.loop:
                break
            wait = max(30, every - (time.time() - started))
            _say(f"Επόμενη εκτέλεση σε {int(wait // 60)} λεπτά (Ctrl+C για διακοπή)")
            try:
                time.sleep(wait)
            except KeyboardInterrupt:
                _say("Διακοπή.")
                break


def cmd_capture(args) -> None:
    from .browser import open_browser
    from .collector import capture_single_post
    from .storage import Storage

    settings = _settings(args)
    with Storage(settings.db_path) as storage, open_browser(settings.browser, settings.timezone, headless=not args.headed) as ctx:
        results = []
        for url in args.url:
            res = capture_single_post(ctx, url, settings, storage, source_id=args.source_id, label=args.label, progress=_say)
            results.append(res)
        _summary(results, dry_run=False)


def cmd_archive(args) -> None:
    from .archive import archive_pending
    from .storage import Storage

    settings = _settings(args)
    with Storage(settings.db_path) as storage:
        n = archive_pending(storage, settings, limit=args.limit, progress=_say)
    _say(f"Ολοκληρώθηκε: {n} snapshots")


def _query(args, settings: Settings, storage):
    d_from, d_to = _dates(args, settings.timezone)
    return storage.query_posts(
        source_ids=args.source or None, date_from=d_from, date_to=d_to,
        date_field=args.date_field, include_undated=not args.exclude_undated,
    ), d_from, d_to


def cmd_list(args) -> None:
    from .storage import Storage

    settings = _settings(args)
    with Storage(settings.db_path) as storage:
        posts, _, _ = _query(args, settings, storage)
    for p in posts:
        text = (p.text or "").replace("\n", " ")
        _say(f"{p.posted_at or '(χωρίς ημερ.)':25s} {p.source_id:15s} {p.post_id:28s} {text[:70]}")
    _say(f"\nΣύνολο: {len(posts)}")


def cmd_export(args) -> None:
    from .export import export_csv, export_html, export_json, export_pdf
    from .storage import Storage

    settings = _settings(args)
    with Storage(settings.db_path) as storage:
        posts, d_from, d_to = _query(args, settings, storage)
    if not posts:
        sys.exit("Δεν βρέθηκαν posts για αυτά τα κριτήρια.")
    out_dir = Path(args.out) if args.out else settings.exports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = "_".join(args.source) if args.source else "all"
    period = ""
    if d_from or d_to:
        period = f"_{d_from:%Y%m%d}" if d_from else "_start"
        period += f"-{d_to:%Y%m%d}" if d_to else "-now"
    base = out_dir / f"fbwatch_{label}{period}_{stamp}"
    ext = lambda e: base.with_name(base.name + e)  # noqa: E731  (όχι with_suffix: τα ids μπορεί να έχουν τελείες)
    title = f"Δημόσια posts: {label}"
    subtitle = f"Περίοδος: {d_from:%d/%m/%Y} έως {d_to:%d/%m/%Y}" if (d_from and d_to) else (
        f"Από {d_from:%d/%m/%Y}" if d_from else (f"Έως {d_to:%d/%m/%Y}" if d_to else "Όλη η συλλογή"))
    formats = {"csv", "json", "html", "pdf"} if args.format == "all" else {args.format}
    meta = {"sources": args.source or [s.id for s in settings.sources], "from": to_iso(d_from), "to": to_iso(d_to),
            "date_field": args.date_field}
    made = []
    if "csv" in formats:
        made.append(export_csv(posts, ext(".csv")))
    if "json" in formats:
        made.append(export_json(posts, ext(".json"), meta))
    if "html" in formats or "pdf" in formats:
        html_path = export_html(posts, settings, ext(".html"), title, subtitle)
        if "html" in formats:
            made.append(html_path)
        if "pdf" in formats:
            made.append(export_pdf(html_path, ext(".pdf"), settings))
            if "html" not in formats:
                html_path.unlink(missing_ok=True)
    _say(f"{len(posts)} posts εξήχθησαν:")
    for m in made:
        _say(f"  {m}")


def cmd_job(args) -> None:
    from .jobs import run_job
    from .storage import Storage

    settings = _settings(args)
    sources = _sources(settings, args.source)
    d_from, d_to = _dates(args, settings.timezone)
    with Storage(settings.db_path) as storage:
        res = run_job(settings, storage, args.name, sources, d_from, d_to, collect=not args.no_collect,
                      headed=args.headed, make_pdf=not args.no_pdf, progress=_say)
    _say(f"Φάκελος ελέγχου: {res.folder}")


def cmd_gui(args) -> None:
    from . import gui

    gui.main(args.config)


def cmd_status(args) -> None:
    from .storage import Storage

    settings = _settings(args)
    with Storage(settings.db_path) as storage:
        _say(f"Βάση: {settings.db_path}")
        _say(f"Σύνολο posts: {storage.count_posts()}")
        for s in settings.sources:
            _say(f"  {s.id:20s} {storage.count_posts(s.id):5d}  {s.url}")
        _say("\nΠρόσφατες εκτελέσεις:")
        for r in storage.recent_runs(10):
            _say(f"  {r['started_at']}  {str(r['source_id'] or ''):15s} {str(r['status']):10s} posts {r['posts_seen']:3d} νέα {r['posts_new']:3d} {r['message'] or ''}")


# --- parser ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fbwatch", description="Συλλογή δημόσιων Facebook posts χωρίς login, με screenshots.")
    p.add_argument("-c", "--config", default="config.yaml", help="Διαδρομή του YAML config (προεπιλογή: config.yaml)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"fbwatch {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="Δημιουργία config.yaml από το παράδειγμα")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("check", help="Δοκιμή πρόσβασης στις πηγές χωρίς αποθήκευση")
    s.add_argument("--source", "-s", action="append", help="Μόνο αυτή η πηγή (επαναλαμβάνεται)")
    s.add_argument("--headed", action="store_true", help="Ορατό παράθυρο browser")
    s.add_argument("--dump", action="store_true", help="Αποθήκευση HTML και πλήρους screenshot της σελίδας στο data/debug για διάγνωση")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("run", help="Συλλογή νέων posts και screenshots")
    s.add_argument("--source", "-s", action="append")
    s.add_argument("--loop", action="store_true", help="Συνεχής λειτουργία")
    s.add_argument("--every", help="Διάστημα επανάληψης στο loop, π.χ. 30m, 2h (προεπιλογή 2h)")
    s.add_argument("--since", help="Μην αποθηκεύεις posts παλαιότερα από αυτή την ημερομηνία (YYYY-MM-DD)")
    s.add_argument("--headed", action="store_true")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("capture", help="Λήψη συγκεκριμένων posts από τα URL τους")
    s.add_argument("url", nargs="+")
    s.add_argument("--source-id", default="manual")
    s.add_argument("--label", default="Χειροκίνητες λήψεις")
    s.add_argument("--headed", action="store_true")
    s.set_defaults(func=cmd_capture)

    s = sub.add_parser("archive", help="Snapshot στο archive.org για posts που δεν έχουν")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(func=cmd_archive)

    for name, fn, help_ in (("list", cmd_list, "Λίστα posts"), ("export", cmd_export, "Εξαγωγή CSV/JSON/HTML/PDF")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--source", "-s", action="append")
        s.add_argument("--from", dest="date_from", help="YYYY-MM-DD ή DD/MM/YYYY")
        s.add_argument("--to", dest="date_to", help="YYYY-MM-DD ή DD/MM/YYYY")
        s.add_argument("--date-field", choices=["posted_at", "first_seen"], default="posted_at",
                       help="Ποια ημερομηνία φιλτράρεται: του post ή της πρώτης λήψης")
        s.add_argument("--exclude-undated", action="store_true", help="Χωρίς posts που δεν έχουν αναγνωρισμένη ημερομηνία")
        if name == "export":
            s.add_argument("--format", "-f", choices=["csv", "json", "html", "pdf", "all"], default="all")
            s.add_argument("--out", "-o", help="Φάκελος εξαγωγής (προεπιλογή data/exports)")
        s.set_defaults(func=fn)

    s = sub.add_parser("job", help="Έλεγχος: συλλογή + εξαγωγή διαστήματος σε δικό του φάκελο")
    s.add_argument("--name", required=True)
    s.add_argument("--source", "-s", action="append")
    s.add_argument("--from", dest="date_from")
    s.add_argument("--to", dest="date_to")
    s.add_argument("--no-collect", action="store_true", help="Μόνο εξαγωγή από ό,τι υπάρχει ήδη")
    s.add_argument("--no-pdf", action="store_true")
    s.add_argument("--headed", action="store_true")
    s.set_defaults(func=cmd_job)

    s = sub.add_parser("gui", help="Γραφικό περιβάλλον")
    s.set_defaults(func=cmd_gui)

    s = sub.add_parser("status", help="Πλήθη και πρόσφατες εκτελέσεις")
    s.set_defaults(func=cmd_status)
    return p


def main(argv: Optional[list[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit("\nΔιακοπή από τον χρήστη.")
    except ValueError as e:
        sys.exit(f"Σφάλμα: {e}")
    except Exception as e:  # noqa: BLE001
        if args.verbose:
            raise
        sys.exit(f"Σφάλμα: {type(e).__name__}: {e}  (τρέξε με -v για λεπτομέρειες)")


if __name__ == "__main__":
    main()
