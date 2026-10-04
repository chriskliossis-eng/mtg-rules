"""Κατασκευή URL των plugins του Facebook και εξαγωγή/κανονικοποίηση permalinks."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

FB_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com", "mbasic.facebook.com"}
KEEP_QUERY_KEYS = {"story_fbid", "id", "fbid", "v", "set", "post_id"}

PERMALINK_RE = re.compile(
    r"(/posts/|story_fbid=|/permalink\.php|/photos/|/videos/|[?&]fbid=|/reel/|/photo/|/photo\.php|/watch/|/story\.php)"
)


def locale_code(locale: str) -> str:
    return locale.replace("-", "_") if "_" not in locale else locale


def page_plugin_url(page_url: str, locale: str = "el-GR", height: int = 1400) -> str:
    params = {
        "href": page_url,
        "tabs": "timeline",
        "width": "500",
        "height": str(height),
        "small_header": "true",
        "adapt_container_width": "true",
        "hide_cover": "true",
        "show_facepile": "false",
        "locale": locale_code(locale),
    }
    return "https://www.facebook.com/plugins/page.php?" + urlencode(params, quote_via=quote)


def post_plugin_url(post_url: str, locale: str = "el-GR") -> str:
    params = {"href": post_url, "show_text": "true", "width": "500", "locale": locale_code(locale)}
    return "https://www.facebook.com/plugins/post.php?" + urlencode(params, quote_via=quote)


def normalize_permalink(href: str, base: str = "https://www.facebook.com") -> str:
    """Απόλυτο URL στο www.facebook.com, χωρίς tracking παραμέτρους."""
    href = href.strip()
    if href.startswith("/"):
        href = base + href
    p = urlparse(href)
    host = p.netloc.lower()
    if host in FB_HOSTS or host.endswith(".facebook.com"):
        host = "www.facebook.com"
    q = parse_qs(p.query, keep_blank_values=False)
    kept = {k: v[0] for k, v in q.items() if k in KEEP_QUERY_KEYS}
    query = urlencode(kept)
    path = p.path.rstrip("/") or "/"
    return urlunparse(("https", host, path, "", query, ""))


def post_id_from_permalink(url: str) -> str:
    """Σταθερό αναγνωριστικό post από το permalink. Αν δεν βρεθεί αριθμός, hash του URL."""
    u = normalize_permalink(url)
    p = urlparse(u)
    q = parse_qs(p.query)
    for key in ("story_fbid", "fbid", "v", "post_id"):
        if key in q and q[key][0]:
            return f"{key}_{q[key][0]}"
    m = re.search(r"/posts/([A-Za-z0-9_-]+)", p.path)
    if m:
        return f"post_{m.group(1)}"
    m = re.search(r"/(videos|reel|watch)/(?:[^/]+/)?(\d+)", p.path)
    if m:
        return f"video_{m.group(2)}"
    m = re.search(r"/photos/(?:[^/]+/)*(\d+)", p.path)
    if m:
        return f"photo_{m.group(1)}"
    return "h_" + hashlib.sha1(u.encode("utf-8")).hexdigest()[:16]


def is_permalink(href: str | None) -> bool:
    return bool(href) and bool(PERMALINK_RE.search(href))
