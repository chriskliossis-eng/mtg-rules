"""Γραφικό περιβάλλον (Tkinter): σελίδες, έλεγχοι με χρονικό διάστημα, ιστορικό, συλλογή νέων posts."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import __version__
from .config import ConfigError, Settings, Source, load_settings, normalize_page_url, save_sources, slug_from_url
from .dates import parse_user_date, to_iso
from .storage import Storage

DATE_FMT = "%d/%m/%Y"


def open_path(path: Path) -> None:
    """Ανοίγει φάκελο ή αρχείο με το πρόγραμμα του λειτουργικού."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Άνοιγμα", f"Δεν άνοιξε το {path}\n{e}")


class PageDialog(simpledialog.Dialog):
    """Διάλογος προσθήκης σελίδας: όνομα + διεύθυνση."""

    def __init__(self, parent, existing_ids: set[str]):
        self.existing_ids = existing_ids
        self.result: Optional[Source] = None
        super().__init__(parent, "Προσθήκη σελίδας Facebook")

    def body(self, master):
        ttk.Label(master, text="Διεύθυνση σελίδας (όπως στον browser):").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.url = ttk.Entry(master, width=60)
        self.url.grid(row=1, column=0, sticky="we")
        self.url.insert(0, "https://www.facebook.com/")
        ttk.Label(master, text="Όνομα εμφάνισης (προαιρετικό):").grid(row=2, column=0, sticky="w", pady=(10, 2))
        self.label = ttk.Entry(master, width=60)
        self.label.grid(row=3, column=0, sticky="we")
        ttk.Label(master, foreground="#555", wraplength=420, justify="left",
                  text="Δουλεύει με δημόσιες Σελίδες (Pages). Προσωπικά προφίλ δεν εμφανίζονται χωρίς σύνδεση.").grid(
            row=4, column=0, sticky="w", pady=(10, 0))
        return self.url

    def validate(self):
        try:
            url = normalize_page_url(self.url.get())
        except ConfigError as e:
            messagebox.showerror("Διεύθυνση", str(e), parent=self)
            return False
        if url.rstrip("/") in ("https://www.facebook.com", "https://www.facebook.com/"):
            messagebox.showerror("Διεύθυνση", "Συμπλήρωσε τη διεύθυνση της σελίδας μετά το facebook.com/", parent=self)
            return False
        sid = slug_from_url(url, self.existing_ids)
        label = self.label.get().strip() or sid
        self.result = Source(id=sid, url=url, kind="page", label=label)
        return True


class App(tk.Tk):
    def __init__(self, config_path: Path):
        super().__init__()
        self.title(f"fbwatch {__version__} – Δημόσια posts Facebook")
        self.geometry("1100x760")
        self.minsize(900, 600)
        self.config_path = config_path
        self.settings: Settings = self._load_settings()
        self.settings.ensure_dirs()
        self.q: queue.Queue = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self._stop = False
        self.page_status: dict[str, str] = {}
        self.auto_job: Optional[str] = None
        self._build()
        self.refresh_pages()
        self.refresh_jobs()
        self.after(150, self._poll)
        self.log(f"Έτοιμο. Ρυθμίσεις: {self.config_path}")
        self.log(f"Δεδομένα: {self.settings.data_dir}")

    # ------------------------------------------------------------------ setup
    def _load_settings(self) -> Settings:
        if not self.config_path.exists():
            import shutil
            from .cli import EXAMPLE_CONFIG
            shutil.copyfile(EXAMPLE_CONFIG, self.config_path)
        try:
            return load_settings(self.config_path)
        except ConfigError as e:
            messagebox.showerror("Ρυθμίσεις", str(e))
            raise SystemExit(1)

    def _build(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if sys.platform.startswith("win") else "clam")
        except tk.TclError:
            pass
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"), padding=6)

        menubar = tk.Menu(self)
        m = tk.Menu(menubar, tearoff=0)
        m.add_command(label="Άνοιγμα φακέλου δεδομένων", command=lambda: open_path(self.settings.data_dir))
        m.add_command(label="Άνοιγμα φακέλου ελέγχων", command=lambda: open_path(self._ensure(self.settings.data_dir / "elegxoi")))
        m.add_command(label="Άνοιγμα φακέλου screenshots", command=lambda: open_path(self.settings.screenshots_dir))
        m.add_separator()
        m.add_command(label="Επεξεργασία ρυθμίσεων (config.yaml)", command=lambda: open_path(self.config_path))
        m.add_command(label="Επαναφόρτωση ρυθμίσεων", command=self.reload_settings)
        m.add_separator()
        m.add_command(label="Έξοδος", command=self.destroy)
        menubar.add_cascade(label="Αρχείο", menu=m)
        h = tk.Menu(menubar, tearoff=0)
        h.add_command(label="Οδηγίες", command=self.show_help)
        menubar.add_cascade(label="Βοήθεια", menu=h)
        self.config(menu=menubar)

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # ---- Αριστερά: σελίδες
        left = ttk.Labelframe(main, text=" Σελίδες που παρακολουθώ ", padding=8)
        main.add(left, weight=1)
        self.pages = ttk.Treeview(left, columns=("label", "url", "status"), show="headings", selectmode="extended", height=12)
        self.pages.heading("label", text="Όνομα")
        self.pages.heading("url", text="Διεύθυνση")
        self.pages.heading("status", text="Τελευταίος έλεγχος")
        self.pages.column("label", width=150)
        self.pages.column("url", width=230)
        self.pages.column("status", width=120)
        self.pages.pack(fill="both", expand=True)
        pb = ttk.Frame(left)
        pb.pack(fill="x", pady=(6, 0))
        ttk.Button(pb, text="Προσθήκη σελίδας", command=self.add_page).pack(side="left")
        ttk.Button(pb, text="Αφαίρεση", command=self.remove_page).pack(side="left", padx=4)
        ttk.Button(pb, text="Δοκιμή πρόσβασης", command=self.check_pages).pack(side="left", padx=4)
        ttk.Label(left, foreground="#555", wraplength=380, justify="left",
                  text="Επίλεξε μία ή περισσότερες σελίδες για να περιορίσεις τον έλεγχο. "
                       "Χωρίς επιλογή, ο έλεγχος αφορά όλες.").pack(anchor="w", pady=(6, 0))

        # ---- Δεξιά: έλεγχος + ιστορικό
        right = ttk.Frame(main)
        main.add(right, weight=2)

        job = ttk.Labelframe(right, text=" Νέος έλεγχος ", padding=8)
        job.pack(fill="x")
        ttk.Label(job, text="Όνομα ελέγχου:").grid(row=0, column=0, sticky="w")
        self.job_name = ttk.Entry(job, width=40)
        self.job_name.grid(row=0, column=1, columnspan=3, sticky="we", padx=4)
        self.job_name.insert(0, f"Έλεγχος {datetime.now():%d-%m-%Y}")
        ttk.Label(job, text="Από (ΗΗ/ΜΜ/ΕΕΕΕ):").grid(row=1, column=0, sticky="w", pady=4)
        self.date_from = ttk.Entry(job, width=14)
        self.date_from.grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(job, text="Έως:").grid(row=1, column=2, sticky="e")
        self.date_to = ttk.Entry(job, width=14)
        self.date_to.grid(row=1, column=3, sticky="w", padx=4)
        quick = ttk.Frame(job)
        quick.grid(row=2, column=0, columnspan=4, sticky="w")
        ttk.Label(quick, text="Γρήγορη επιλογή:").pack(side="left")
        for txt, days in (("Σήμερα", 0), ("7 ημέρες", 7), ("30 ημέρες", 30), ("90 ημέρες", 90)):
            ttk.Button(quick, text=txt, width=9, command=lambda d=days: self.set_period(d)).pack(side="left", padx=2)
        ttk.Button(quick, text="Όλα", width=6, command=lambda: self.set_period(None)).pack(side="left", padx=2)
        self.set_period(30)

        opts = ttk.Frame(job)
        opts.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.opt_collect = tk.BooleanVar(value=True)
        self.opt_pdf = tk.BooleanVar(value=True)
        self.opt_headed = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Συλλογή νέων posts από το Facebook πριν την εξαγωγή", variable=self.opt_collect).pack(anchor="w")
        ttk.Checkbutton(opts, text="Δημιουργία PDF αναφοράς", variable=self.opt_pdf).pack(anchor="w")
        ttk.Checkbutton(opts, text="Ορατό παράθυρο browser κατά τη συλλογή", variable=self.opt_headed).pack(anchor="w")

        btns = ttk.Frame(job)
        btns.grid(row=4, column=0, columnspan=4, sticky="we", pady=(8, 0))
        self.btn_job = ttk.Button(btns, text="▶  Εκτέλεση ελέγχου", style="Big.TButton", command=self.run_job)
        self.btn_job.pack(side="left")
        self.btn_collect = ttk.Button(btns, text="Μόνο συλλογή νέων posts", command=self.collect_only)
        self.btn_collect.pack(side="left", padx=6)
        self.btn_capture = ttk.Button(btns, text="Λήψη post από διεύθυνση…", command=self.capture_url)
        self.btn_capture.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="Διακοπή", command=self.stop, state="disabled")
        self.btn_stop.pack(side="right")
        job.columnconfigure(1, weight=1)

        auto = ttk.Frame(job)
        auto.grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.auto_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(auto, text="Αυτόματη συλλογή νέων posts κάθε", variable=self.auto_on, command=self.toggle_auto).pack(side="left")
        self.auto_hours = ttk.Spinbox(auto, from_=1, to=24, width=4)
        self.auto_hours.set(2)
        self.auto_hours.pack(side="left", padx=4)
        ttk.Label(auto, text="ώρες, όσο είναι ανοιχτό το πρόγραμμα").pack(side="left")

        hist = ttk.Labelframe(right, text=" Ιστορικό ελέγχων ", padding=8)
        hist.pack(fill="both", expand=True, pady=(8, 0))
        self.jobs = ttk.Treeview(hist, columns=("when", "name", "period", "sources", "posts", "status"), show="headings", height=8)
        for col, text, w in (("when", "Ημερομηνία", 115), ("name", "Όνομα", 150), ("period", "Περίοδος", 160),
                             ("sources", "Σελίδες", 120), ("posts", "Posts", 50), ("status", "Κατάσταση", 75)):
            self.jobs.heading(col, text=text)
            self.jobs.column(col, width=w, anchor="w")
        self.jobs.pack(fill="both", expand=True)
        self.jobs.bind("<Double-1>", lambda e: self.open_job_folder())
        hb = ttk.Frame(hist)
        hb.pack(fill="x", pady=(6, 0))
        ttk.Button(hb, text="Άνοιγμα φακέλου", command=self.open_job_folder).pack(side="left")
        ttk.Button(hb, text="Άνοιγμα PDF", command=lambda: self.open_job_file("anafora.pdf")).pack(side="left", padx=4)
        ttk.Button(hb, text="Άνοιγμα Excel (CSV)", command=lambda: self.open_job_file("posts.csv")).pack(side="left")
        ttk.Button(hb, text="Διαγραφή από ιστορικό", command=self.delete_job).pack(side="right")

        # ---- Κάτω: πρόοδος + log
        bottom = ttk.Labelframe(self, text=" Πρόοδος ", padding=6)
        bottom.pack(fill="both", padx=8, pady=(0, 8))
        self.progress = ttk.Progressbar(bottom, mode="indeterminate")
        self.progress.pack(fill="x")
        self.logbox = tk.Text(bottom, height=9, wrap="word", state="disabled", font=("Consolas", 9))
        self.logbox.pack(fill="both", expand=True, pady=(4, 0))

    @staticmethod
    def _ensure(p: Path) -> Path:
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ------------------------------------------------------------------ helpers
    def log(self, msg: str) -> None:
        self.logbox.configure(state="normal")
        self.logbox.insert("end", f"{datetime.now():%H:%M:%S}  {msg}\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log(payload)
                elif kind == "status":
                    sid, st = payload
                    self.page_status[sid] = st
                    self.refresh_pages()
                elif kind == "done":
                    self._set_busy(False)
                    self.refresh_jobs()
                    if payload:
                        self.log(payload)
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for b in (self.btn_job, self.btn_collect, self.btn_capture):
            b.configure(state=state)
        self.btn_stop.configure(state="normal" if busy else "disabled")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _start(self, target, *args) -> bool:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Σε εξέλιξη", "Περίμενε να τελειώσει η τρέχουσα εργασία.")
            return False
        self._stop = False
        self._set_busy(True)

        def runner():
            try:
                target(*args)
                self.q.put(("done", "Τέλος εργασίας."))
            except Exception as e:  # noqa: BLE001
                self.q.put(("log", "ΣΦΑΛΜΑ: " + "".join(traceback.format_exception_only(type(e), e)).strip()))
                self.q.put(("done", None))

        self.worker = threading.Thread(target=runner, daemon=True)
        self.worker.start()
        return True

    def say(self, msg: str) -> None:
        self.q.put(("log", msg))

    def stop(self) -> None:
        self._stop = True
        self.log("Ζητήθηκε διακοπή, ολοκληρώνεται η τρέχουσα σελίδα...")

    def selected_sources(self) -> list[Source]:
        ids = [self.pages.item(i, "values")[3] for i in self.pages.selection()]
        if not ids:
            return list(self.settings.sources)
        return [s for s in self.settings.sources if s.id in ids]

    def period(self) -> tuple[Optional[datetime], Optional[datetime]]:
        tz = self.settings.timezone
        f, t = self.date_from.get().strip(), self.date_to.get().strip()
        d_from = parse_user_date(f, tz) if f else None
        d_to = parse_user_date(t, tz, end_of_day=True) if t else None
        if d_from and d_to and d_from > d_to:
            raise ValueError("Η ημερομηνία «Από» είναι μετά την «Έως».")
        return d_from, d_to

    def set_period(self, days: Optional[int]) -> None:
        self.date_from.delete(0, "end")
        self.date_to.delete(0, "end")
        if days is None:
            return
        today = datetime.now(ZoneInfo(self.settings.timezone)).date()
        self.date_from.insert(0, (today - timedelta(days=days)).strftime(DATE_FMT))
        self.date_to.insert(0, today.strftime(DATE_FMT))

    # ------------------------------------------------------------------ pages
    def refresh_pages(self) -> None:
        sel = set(self.pages.selection())
        self.pages.delete(*self.pages.get_children())
        for s in self.settings.sources:
            self.pages.insert("", "end", iid=s.id, values=(s.label, s.url, self.page_status.get(s.id, ""), s.id))
        for i in sel:
            if self.pages.exists(i):
                self.pages.selection_add(i)

    def add_page(self) -> None:
        dlg = PageDialog(self, {s.id for s in self.settings.sources})
        if dlg.result is None:
            return
        if any(s.url == dlg.result.url for s in self.settings.sources):
            messagebox.showinfo("Σελίδα", "Αυτή η σελίδα υπάρχει ήδη.")
            return
        save_sources(self.settings, [*self.settings.sources, dlg.result])
        self.refresh_pages()
        self.log(f"Προστέθηκε σελίδα: {dlg.result.label} ({dlg.result.url})")

    def remove_page(self) -> None:
        ids = [self.pages.item(i, "values")[3] for i in self.pages.selection()]
        if not ids:
            messagebox.showinfo("Αφαίρεση", "Επίλεξε πρώτα μία σελίδα από τη λίστα.")
            return
        names = ", ".join(s.label or s.id for s in self.settings.sources if s.id in ids)
        if not messagebox.askyesno("Αφαίρεση", f"Να αφαιρεθεί από την παρακολούθηση: {names};\n"
                                              "Τα posts που έχουν ήδη αποθηκευτεί δεν διαγράφονται."):
            return
        save_sources(self.settings, [s for s in self.settings.sources if s.id not in ids])
        self.refresh_pages()
        self.log(f"Αφαιρέθηκε: {names}")

    def reload_settings(self) -> None:
        try:
            self.settings = load_settings(self.config_path)
            self.settings.ensure_dirs()
            self.refresh_pages()
            self.log("Οι ρυθμίσεις επαναφορτώθηκαν.")
        except ConfigError as e:
            messagebox.showerror("Ρυθμίσεις", str(e))

    # ------------------------------------------------------------------ actions
    def check_pages(self) -> None:
        sources = self.selected_sources()
        if not sources:
            messagebox.showinfo("Σελίδες", "Πρόσθεσε πρώτα μία σελίδα.")
            return
        headed = self.opt_headed.get()
        self.log(f"Δοκιμή πρόσβασης σε {len(sources)} σελίδες (χωρίς αποθήκευση)...")

        def work():
            from .browser import open_browser
            from .collector import collect_source
            with open_browser(self.settings.browser, self.settings.timezone, headless=not headed) as ctx:
                for src in sources:
                    if self._stop:
                        break
                    res = collect_source(ctx, src, self.settings, None, dry_run=True, progress=self.say,
                                         dump_dir=self.settings.data_dir / "debug")
                    st = f"{res.status.kind} ({res.posts_seen})" if res.status.kind == "ok" else res.status.kind
                    self.q.put(("status", (src.id, st)))

        self._start(work)

    def run_job(self) -> None:
        name = self.job_name.get().strip() or f"Έλεγχος {datetime.now():%d-%m-%Y %H:%M}"
        try:
            d_from, d_to = self.period()
        except ValueError as e:
            messagebox.showerror("Ημερομηνίες", str(e))
            return
        sources = self.selected_sources()
        if not sources:
            messagebox.showinfo("Σελίδες", "Πρόσθεσε πρώτα μία σελίδα.")
            return
        collect, pdf, headed = self.opt_collect.get(), self.opt_pdf.get(), self.opt_headed.get()
        self.log(f"Έναρξη ελέγχου «{name}» για {len(sources)} σελίδες.")

        def work():
            from .jobs import run_job
            with Storage(self.settings.db_path) as storage:
                res = run_job(self.settings, storage, name, sources, d_from, d_to, collect=collect, headed=headed,
                              make_pdf=pdf, progress=self.say, stop_flag=lambda: self._stop)
                for r in res.source_results:
                    st = f"{r.status.kind} ({r.posts_seen})" if r.status.kind == "ok" else r.status.kind
                    self.q.put(("status", (r.source_id, st)))

        if self._start(work):
            self.job_name.delete(0, "end")
            self.job_name.insert(0, f"Έλεγχος {datetime.now():%d-%m-%Y}")

    def collect_only(self) -> None:
        sources = self.selected_sources()
        if not sources:
            messagebox.showinfo("Σελίδες", "Πρόσθεσε πρώτα μία σελίδα.")
            return
        headed = self.opt_headed.get()
        self.log(f"Συλλογή νέων posts από {len(sources)} σελίδες...")

        def work():
            from .browser import open_browser
            from .collector import collect_source, pause_between_sources
            with Storage(self.settings.db_path) as storage, open_browser(self.settings.browser, self.settings.timezone, headless=not headed) as ctx:
                total = 0
                for i, src in enumerate(sources):
                    if self._stop:
                        break
                    res = collect_source(ctx, src, self.settings, storage, progress=self.say)
                    total += res.posts_new
                    st = f"{res.status.kind} ({res.posts_seen})" if res.status.kind == "ok" else res.status.kind
                    self.q.put(("status", (src.id, st)))
                    if i < len(sources) - 1:
                        pause_between_sources(self.settings)
                self.say(f"Νέα posts συνολικά: {total}")

        self._start(work)

    def capture_url(self) -> None:
        url = simpledialog.askstring("Λήψη post", "Διεύθυνση του δημόσιου post (από το Facebook):", parent=self)
        if not url:
            return
        headed = self.opt_headed.get()

        def work():
            from .browser import open_browser
            from .collector import capture_single_post
            with Storage(self.settings.db_path) as storage, open_browser(self.settings.browser, self.settings.timezone, headless=not headed) as ctx:
                res = capture_single_post(ctx, url, self.settings, storage, progress=self.say)
                self.say(f"Αποτέλεσμα: {res.status.kind} {res.status.detail}".strip())

        self._start(work)

    def toggle_auto(self) -> None:
        if self.auto_job:
            self.after_cancel(self.auto_job)
            self.auto_job = None
        if self.auto_on.get():
            hours = max(1, int(float(self.auto_hours.get() or 2)))
            self.log(f"Αυτόματη συλλογή ενεργή: κάθε {hours} ώρες.")
            self.auto_job = self.after(hours * 3600 * 1000, self._auto_tick)
        else:
            self.log("Αυτόματη συλλογή απενεργοποιήθηκε.")

    def _auto_tick(self) -> None:
        if not self.auto_on.get():
            return
        if not (self.worker and self.worker.is_alive()):
            self.collect_only()
        hours = max(1, int(float(self.auto_hours.get() or 2)))
        self.auto_job = self.after(hours * 3600 * 1000, self._auto_tick)

    # ------------------------------------------------------------------ history
    def refresh_jobs(self) -> None:
        self.jobs.delete(*self.jobs.get_children())
        try:
            with Storage(self.settings.db_path) as storage:
                rows = storage.jobs()
        except Exception as e:  # noqa: BLE001
            self.log(f"Ιστορικό: {e}")
            return
        labels = {s.id: (s.label or s.id) for s in self.settings.sources}
        for r in rows:
            when = _dmy_hm(r["created_at"] or "")
            f = (r["date_from"] or "")[:10]
            t = (r["date_to"] or "")[:10]
            period = f"{_dmy(f)} – {_dmy(t)}" if (f or t) else "όλα"
            srcs = ", ".join(labels.get(x, x) for x in (r["source_ids"] or "").split(",") if x)
            self.jobs.insert("", "end", iid=str(r["id"]), values=(when, r["name"], period, srcs, r["posts_count"], r["status"] or ""))

    def _job_row(self):
        sel = self.jobs.selection()
        if not sel:
            messagebox.showinfo("Ιστορικό", "Επίλεξε πρώτα έναν έλεγχο από το ιστορικό.")
            return None
        with Storage(self.settings.db_path) as storage:
            for r in storage.jobs():
                if str(r["id"]) == sel[0]:
                    return r
        return None

    def open_job_folder(self) -> None:
        r = self._job_row()
        if r and r["folder"]:
            open_path(self.settings.data_dir / r["folder"])

    def open_job_file(self, name: str) -> None:
        r = self._job_row()
        if not r or not r["folder"]:
            return
        p = self.settings.data_dir / r["folder"] / name
        if not p.exists():
            messagebox.showinfo("Αρχείο", f"Δεν υπάρχει το {name} σε αυτόν τον έλεγχο.")
            return
        open_path(p)

    def delete_job(self) -> None:
        r = self._job_row()
        if not r:
            return
        if not messagebox.askyesno("Διαγραφή", f"Να αφαιρεθεί ο έλεγχος «{r['name']}» από το ιστορικό;\n"
                                               "Ο φάκελος με τα αρχεία του παραμένει στον δίσκο."):
            return
        with Storage(self.settings.db_path) as storage:
            storage.delete_job(int(r["id"]))
        self.refresh_jobs()

    def show_help(self) -> None:
        messagebox.showinfo("Οδηγίες", (
            "1. Πρόσθεσε τις σελίδες Facebook που σε ενδιαφέρουν (αριστερά).\n"
            "2. Πάτα «Δοκιμή πρόσβασης» για να δεις αν το Facebook δίνει τα posts χωρίς σύνδεση.\n"
            "3. Όρισε όνομα και χρονικό διάστημα και πάτα «Εκτέλεση ελέγχου».\n"
            "   Ο έλεγχος μαζεύει τα νέα posts, κρατά screenshot για καθένα και φτιάχνει\n"
            "   σε δικό του φάκελο CSV, JSON, HTML και PDF με τα posts του διαστήματος.\n"
            "4. Κάθε έλεγχος μένει στο ιστορικό. Διπλό κλικ ανοίγει τον φάκελό του.\n"
            "5. «Μόνο συλλογή νέων posts» ανανεώνει τη συλλογή χωρίς να φτιάξει αναφορά.\n\n"
            "Χωρίς σύνδεση στο Facebook εμφανίζονται μόνο τα πρόσφατα posts κάθε σελίδας.\n"
            "Για να μη χάνεις posts, τρέχε συλλογή τακτικά ή ενεργοποίησε την αυτόματη."
        ))


def _dmy_hm(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso[:16]


def _dmy(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime(DATE_FMT)
    except ValueError:
        return iso


def main(config_path: str | Path = "config.yaml") -> None:
    path = Path(config_path).resolve()
    try:
        app = App(path)
    except SystemExit:
        return
    except Exception:  # noqa: BLE001
        err = traceback.format_exc()
        log = path.parent / "gui_error.log"
        try:
            log.write_text(err, encoding="utf-8")
        except OSError:
            pass
        try:
            messagebox.showerror("fbwatch", f"Το πρόγραμμα δεν ξεκίνησε.\n\n{err[-1500:]}")
        except Exception:  # noqa: BLE001
            print(err, file=sys.stderr)
        return
    app.mainloop()
