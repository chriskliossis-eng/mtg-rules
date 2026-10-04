"""Εύρεση posts μέσα στη σελίδα του plugin, ανίχνευση login wall, screenshots ανά post."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from playwright.sync_api import Page

from .dates import from_epoch, parse_facebook_date
from .fburls import normalize_permalink, post_id_from_permalink

# Σελέκτορες container ενός post, με σειρά προτίμησης. Αν αλλάξει το markup του Facebook,
# αρκεί να προστεθεί εδώ ο νέος σελέκτορας. Υπάρχει και fallback με βάση τα permalinks.
CONTAINER_SELECTORS = [
    "div.userContentWrapper",
    "div[role='article']",
    "article",
    "div._1dwg",
    "div[data-testid='post']",
    "div.fbUserContent",
]
TEXT_SELECTORS = [
    "div.userContent",
    "[data-testid='post_message']",
    "div._5pbx",
    "div[data-ad-preview='message']",
]
AUTHOR_SELECTORS = ["h5 a", "h3 a", "h2 a", ".fwb a", "strong a", "span.fwb"]

_PERMALINK_JS_RE = r"(\/posts\/|story_fbid=|\/permalink\.php|\/photos\/|\/videos\/|[?&]fbid=|\/reel\/|\/photo\/|\/photo\.php|\/watch\/|\/story\.php)"

FIND_POSTS_JS = r"""
(args) => {
  const permalinkRe = new RegExp(args.permalinkRe);
  const idRe = /(story_fbid=\d+|[?&]fbid=\d+|\/posts\/[A-Za-z0-9_-]+|\/(videos|reel|watch)\/(?:[^/]+\/)?\d+|\/photos\/(?:[^/]+\/)*\d+)/;
  const idOf = (href) => { const m = href.match(idRe); return m ? m[0] : href.split('?')[0]; };
  const permalinks = (root) => Array.from(root.querySelectorAll('a[href]'))
      .filter(a => permalinkRe.test(a.getAttribute('href') || ''));
  const distinctIds = (root) => new Set(permalinks(root).map(a => idOf(a.getAttribute('href'))));

  let containers = [];
  for (const sel of args.containerSelectors) {
    const found = Array.from(document.querySelectorAll(sel)).filter(el => permalinks(el).length > 0);
    if (found.length) { containers = found; break; }
  }
  if (!containers.length) {
    // Fallback: ξεκίνα από κάθε permalink και ανέβα μέχρι ο γονέας να περιέχει και άλλο post.
    const seen = new Set();
    for (const a of permalinks(document)) {
      const id = idOf(a.getAttribute('href'));
      if (seen.has(id)) continue;
      let el = a;
      for (let i = 0; i < 12; i++) {
        const parent = el.parentElement;
        if (!parent || parent === document.body || parent === document.documentElement) break;
        if (distinctIds(parent).size > 1) break;
        el = parent;
      }
      if (el !== a) { seen.add(id); containers.push(el); }
    }
  }
  // Κράτα μόνο ανώτατους containers (όχι φωλιασμένους) και ξεχώρισέ τους ανά post.
  containers = containers.filter(c => !containers.some(o => o !== c && o.contains(c)));

  const results = [];
  const usedIds = new Set();
  let idx = 0;
  for (const c of containers) {
    const links = permalinks(c);
    if (!links.length) continue;
    // Προτίμησε link που είναι timestamp (έχει abbr ή aria-label με ημερομηνία), αλλιώς το πρώτο.
    let link = links.find(a => a.querySelector('abbr') || a.getAttribute('aria-label')) || links[0];
    const href = link.getAttribute('href');
    const key = idOf(href);
    if (usedIds.has(key)) continue;
    usedIds.add(key);

    let utime = null, timeText = null, timeTitle = null;
    const abbr = c.querySelector('abbr[data-utime]') || c.querySelector('abbr');
    if (abbr) {
      utime = abbr.getAttribute('data-utime');
      timeTitle = abbr.getAttribute('title') || abbr.getAttribute('data-tooltip-content');
      timeText = abbr.textContent.trim();
    }
    if (!timeText) {
      const t = c.querySelector('time');
      if (t) { timeTitle = t.getAttribute('datetime') || t.getAttribute('title'); timeText = t.textContent.trim(); }
    }
    if (!timeText) {
      timeTitle = link.getAttribute('aria-label') || link.getAttribute('title');
      timeText = link.textContent.trim();
    }

    let text = '';
    for (const sel of args.textSelectors) {
      const el = c.querySelector(sel);
      if (el && el.innerText.trim()) { text = el.innerText.trim(); break; }
    }
    if (!text) {
      const blocks = Array.from(c.querySelectorAll('div[dir="auto"], p, span[dir="auto"]'))
        .map(e => e.innerText.trim()).filter(Boolean);
      text = blocks.length ? Array.from(new Set(blocks)).join('\n') : c.innerText.trim();
    }
    text = text.slice(0, 8000);

    let author = null;
    for (const sel of args.authorSelectors) {
      const el = c.querySelector(sel);
      if (el && el.textContent.trim()) { author = el.textContent.trim(); break; }
    }
    if (!author) {
      const a = Array.from(c.querySelectorAll('a[href]')).find(x => !permalinkRe.test(x.getAttribute('href')) && x.textContent.trim().length > 1 && x.textContent.trim().length < 120);
      if (a) author = a.textContent.trim();
    }

    const marker = 'fbw_' + (idx++);
    c.setAttribute('data-fbwatch-id', marker);
    const rect = c.getBoundingClientRect();
    results.push({marker, href, utime, timeText, timeTitle, text, author,
                  top: rect.top + window.scrollY, height: rect.height});
  }
  results.sort((a, b) => a.top - b.top);
  return results;
}
"""

SCROLL_JS = r"""
() => {
  const height = () => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  const before = height();
  window.scrollTo(0, before);
  // Scroll και όλα τα εσωτερικά scrollable στοιχεία (το plugin έχει δικό του container).
  const scrollers = [];
  for (const el of document.querySelectorAll('*')) {
    const st = getComputedStyle(el);
    if ((st.overflowY === 'auto' || st.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 10) {
      el.scrollTop = el.scrollHeight;
      scrollers.push(el);
    }
  }
  // Μερικά widgets φορτώνουν μόνο με πραγματικά wheel/scroll events.
  const targets = scrollers.length ? scrollers : [document.scrollingElement || document.body];
  for (const el of targets) {
    try {
      el.dispatchEvent(new WheelEvent('wheel', {deltaY: 2000, bubbles: true, cancelable: true}));
      el.dispatchEvent(new Event('scroll', {bubbles: true}));
    } catch (e) {}
  }
  window.dispatchEvent(new Event('scroll'));
  return {before, scrollers: scrollers.length,
          innerMax: scrollers.length ? Math.max(...scrollers.map(e => e.scrollHeight)) : 0};
}
"""

PAGE_HEIGHT_JS = "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
INNER_MAX_JS = """() => { let m = 0; for (const el of document.querySelectorAll('*')) { const st = getComputedStyle(el);
  if ((st.overflowY === 'auto' || st.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 10) m = Math.max(m, el.scrollHeight); } return m; }"""

LOGIN_WALL_PATTERNS = [
    r"you must log in", r"log in to continue", r"log in or sign up", r"see more of .* on facebook",
    r"πρέπει να συνδεθείς", r"συνδεθείτε για να συνεχίσετε", r"συνδέσου ή εγγράψου", r"δείτε περισσότερα από .* στο facebook",
]
UNAVAILABLE_PATTERNS = [
    r"content isn't available", r"content is not available", r"this content isn't available right now",
    r"το περιεχόμενο δεν είναι διαθέσιμο", r"page not found", r"η σελίδα δεν βρέθηκε",
    r"plugin could not be loaded", r"δεν ήταν δυνατή η φόρτωση",
]


@dataclass
class FoundPost:
    marker: str
    permalink: str
    post_id: str
    posted_at: Optional[datetime]
    posted_at_raw: Optional[str]
    text: str
    author: Optional[str]


@dataclass
class PageStatus:
    kind: str  # "ok" | "login_wall" | "unavailable" | "empty"
    detail: str = ""


def detect_status(page: Page, posts_found: int) -> PageStatus:
    url = page.url or ""
    if re.search(r"facebook\.com/(login|checkpoint)\b", url):
        return PageStatus("login_wall", f"Ανακατεύθυνση σε {url}")
    if page.locator("#login_form, input[name='pass'], form[action*='login']").count() > 0 and posts_found == 0:
        return PageStatus("login_wall", "Εμφανίστηκε φόρμα σύνδεσης")
    body = ""
    try:
        body = page.locator("body").inner_text(timeout=5000)
    except Exception:
        pass
    low = body.lower()
    if posts_found == 0:
        for pat in UNAVAILABLE_PATTERNS:
            if re.search(pat, low):
                return PageStatus("unavailable", "Το Facebook απάντησε ότι το περιεχόμενο δεν είναι διαθέσιμο "
                                                 "(συχνό για προσωπικά προφίλ ή Pages με περιορισμούς)")
        for pat in LOGIN_WALL_PATTERNS:
            if re.search(pat, low):
                return PageStatus("login_wall", "Το Facebook ζητάει σύνδεση")
        return PageStatus("empty", "Δεν βρέθηκαν posts στη σελίδα")
    return PageStatus("ok")


def find_posts(page, tz: str, now: Optional[datetime] = None) -> list[FoundPost]:
    """Δέχεται Page ή Frame."""
    raw = page.evaluate(
        FIND_POSTS_JS,
        {
            "permalinkRe": _PERMALINK_JS_RE,
            "containerSelectors": CONTAINER_SELECTORS,
            "textSelectors": TEXT_SELECTORS,
            "authorSelectors": AUTHOR_SELECTORS,
        },
    )
    posts: list[FoundPost] = []
    for r in raw:
        permalink = normalize_permalink(r["href"])
        posted_at = None
        posted_raw = r.get("timeTitle") or r.get("timeText")
        if r.get("utime"):
            posted_at = from_epoch(r["utime"], tz)
            posted_raw = posted_raw or str(r["utime"])
        if posted_at is None:
            posted_at = parse_facebook_date(r.get("timeTitle"), tz, now) or parse_facebook_date(r.get("timeText"), tz, now)
        posts.append(
            FoundPost(
                marker=r["marker"],
                permalink=permalink,
                post_id=post_id_from_permalink(permalink),
                posted_at=posted_at,
                posted_at_raw=posted_raw,
                text=r.get("text") or "",
                author=r.get("author"),
            )
        )
    return posts


def scroll_down(target, settle_ms: int) -> dict:
    """Scroll στο τέλος (παράθυρο + εσωτερικοί scrollers + wheel events).

    Επιστρέφει {"grew": bool, "before": int, "after": int, "scrollers": int, "inner_before": int, "inner_after": int}.
    """
    info = target.evaluate(SCROLL_JS)
    page = target.page if hasattr(target, "page") else target
    try:
        # Πραγματικά input events (μέσω CDP), όχι μόνο synthetic: κάποια widgets φορτώνουν μόνο έτσι.
        vp = page.viewport_size or {"width": 500, "height": 1000}
        page.mouse.move(vp["width"] // 2, vp["height"] // 2)
        page.mouse.wheel(0, 4000)
        page.keyboard.press("End")
    except Exception:  # noqa: BLE001
        pass
    target.wait_for_timeout(settle_ms)
    try:
        target.wait_for_load_state("networkidle", timeout=4000)
    except Exception:  # noqa: BLE001
        pass
    after = target.evaluate(PAGE_HEIGHT_JS)
    inner_after = target.evaluate(INNER_MAX_JS)
    grew = after > info["before"] or inner_after > info["innerMax"]
    return {"grew": grew, "before": info["before"], "after": after, "scrollers": info["scrollers"],
            "inner_before": info["innerMax"], "inner_after": inner_after}


def best_frame(page: Page, tz: str, now: Optional[datetime] = None):
    """Το plugin μπορεί να βάλει το περιεχόμενο σε εσωτερικό iframe. Επιστρέφει (frame, posts) με τα περισσότερα posts."""
    best, best_posts = page.main_frame, []
    for fr in page.frames:
        try:
            posts = find_posts(fr, tz, now)
        except Exception:  # noqa: BLE001
            continue
        if len(posts) > len(best_posts):
            best, best_posts = fr, posts
    return best, best_posts


def screenshot_post(target, marker: str, path, settle_ms: int) -> None:
    """target: Page ή Frame."""
    loc = target.locator(f"[data-fbwatch-id='{marker}']").first
    loc.scroll_into_view_if_needed()
    target.wait_for_timeout(max(300, settle_ms // 2))  # άσε τις εικόνες να φορτώσουν
    loc.screenshot(path=str(path), type="png")


def post_outer_html(target, marker: str) -> str:
    loc = target.locator(f"[data-fbwatch-id='{marker}']").first
    return loc.evaluate("el => el.outerHTML")
