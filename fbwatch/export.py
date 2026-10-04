"""Εξαγωγή σε CSV, JSON, HTML και PDF (το PDF τυπώνεται από τον Chromium, χωρίς άλλη βιβλιοθήκη)."""
from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .config import Settings
from .storage import PostRecord

FIELDS = [
    "post_id", "source_id", "author", "posted_at", "posted_at_raw", "first_seen", "last_seen",
    "permalink", "text", "screenshot_path", "html_path", "sha256", "archive_url",
]


def export_csv(posts: Iterable[PostRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # BOM για να ανοίγει σωστά στο Excel
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for p in posts:
            w.writerow(p.to_dict())
    return path


def export_json(posts: Iterable[PostRecord], path: Path, meta: Optional[dict] = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "meta": meta or {},
               "posts": [p.to_dict() for p in posts]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_html_report(posts: list[PostRecord], settings: Settings, title: str, subtitle: str = "", img_dir: Optional[str] = None) -> str:
    """img_dir: αν δοθεί, οι εικόνες αναφέρονται σχετικά ως <img_dir>/<όνομα αρχείου> (αυτοτελής φάκελος)."""
    def esc(s: Optional[str]) -> str:
        return html.escape(s or "")

    rows = []
    for p in posts:
        img = ""
        if p.screenshot_path:
            if img_dir:
                src = f"{img_dir}/{Path(p.screenshot_path).name}"
            else:
                src = (settings.data_dir / p.screenshot_path).resolve().as_uri()
            img = f'<img src="{esc(src)}" alt="screenshot {esc(p.post_id)}">'
        archive = f'<div><b>Archive:</b> <a href="{esc(p.archive_url)}">{esc(p.archive_url)}</a></div>' if p.archive_url else ""
        rows.append(f"""
<section class="post">
  <h2>{esc(p.author) or esc(p.source_id)} <span class="date">{esc(p.posted_at) or "χωρίς ημερομηνία"}</span></h2>
  <div class="meta">
    <div><b>Πηγή:</b> {esc(p.source_id)} &nbsp; <b>ID:</b> {esc(p.post_id)}</div>
    <div><b>Permalink:</b> <a href="{esc(p.permalink)}">{esc(p.permalink)}</a></div>
    <div><b>Ημερομηνία post (όπως εμφανίστηκε):</b> {esc(p.posted_at_raw)}</div>
    <div><b>Πρώτη λήψη:</b> {esc(p.first_seen)} &nbsp; <b>Τελευταία θέαση:</b> {esc(p.last_seen)}</div>
    <div><b>SHA-256 screenshot:</b> <code>{esc(p.sha256)}</code></div>
    {archive}
  </div>
  <pre class="text">{esc(p.text)}</pre>
  {img}
</section>""")
    return f"""<!DOCTYPE html>
<html lang="el"><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; margin: 24px; color: #111; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .sub {{ color: #555; margin-bottom: 20px; }}
  .post {{ page-break-inside: avoid; border-top: 1px solid #ccc; padding: 14px 0 20px; }}
  .post h2 {{ font-size: 15px; margin: 0 0 6px; }}
  .date {{ font-weight: normal; color: #555; margin-left: 8px; }}
  .meta {{ font-size: 11px; color: #333; line-height: 1.5; word-break: break-all; }}
  .text {{ white-space: pre-wrap; font-family: inherit; font-size: 12px; background: #f6f6f6; padding: 8px; }}
  img {{ max-width: 100%; border: 1px solid #ddd; }}
  @page {{ size: A4; margin: 15mm; }}
</style></head>
<body>
<h1>{esc(title)}</h1>
<div class="sub">{esc(subtitle)} &nbsp;·&nbsp; {len(posts)} posts &nbsp;·&nbsp; δημιουργήθηκε {datetime.now().astimezone():%d/%m/%Y %H:%M}</div>
{''.join(rows)}
</body></html>"""


def export_html(posts: list[PostRecord], settings: Settings, path: Path, title: str, subtitle: str = "", img_dir: Optional[str] = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_html_report(posts, settings, title, subtitle, img_dir), encoding="utf-8")
    return path


def export_pdf(html_path: Path, pdf_path: Path, settings: Settings) -> Path:
    from .browser import open_browser

    with open_browser(settings.browser, settings.timezone, headless=True) as ctx:
        page = ctx.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.wait_for_timeout(500)
        page.pdf(path=str(pdf_path), format="A4", print_background=True)
        page.close()
    return pdf_path
