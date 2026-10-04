"""Ανάλυση ημερομηνιών όπως εμφανίζονται στο Facebook (ελληνικά και αγγλικά)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

_GREEK_MONTHS = {
    "ιαν": 1, "φεβ": 2, "μαρ": 3, "απρ": 4, "μαϊ": 5, "μαι": 5, "ιουν": 6,
    "ιουλ": 7, "αυγ": 8, "σεπ": 9, "οκτ": 10, "νοε": 11, "δεκ": 12,
}
_ENGLISH_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_TIME_RE = re.compile(r"(\d{1,2})[:.](\d{2})\s*(π\.?μ\.?|μ\.?μ\.?|am|pm)?", re.IGNORECASE)
_DMY_RE = re.compile(r"(\d{1,2})\s+([^\W\d_]+)\.?,?\s+(\d{4})", re.UNICODE)
_MDY_RE = re.compile(r"([^\W\d_]+)\.?\s+(\d{1,2}),?\s+(\d{4})", re.UNICODE)
_DM_RE = re.compile(r"^(\d{1,2})\s+([^\W\d_]+)\.?(?:\s|$)", re.UNICODE)
_MD_RE = re.compile(r"^([^\W\d_]+)\.?\s+(\d{1,2})(?:\s|$|,)", re.UNICODE)
_NUMERIC_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?")
_RELATIVE_RE = re.compile(
    r"^(\d+)\s*(λεπτ\w*|ώρ\w*|ωρ\w*|ημέρ\w*|ημερ\w*|μέρ\w*|μερ\w*|εβδ\w*|m|min\w*|h|hr\w*|hour\w*|d|day\w*|w|wk\w*|week\w*)\b",
    re.IGNORECASE,
)


def _strip_accents(s: str) -> str:
    table = str.maketrans("άέήίόύώϊϋΐΰ", "αεηιουωιυιυ")
    return s.lower().translate(table)


def _month_from_word(word: str) -> Optional[int]:
    w = _strip_accents(word).rstrip(".")
    for prefix, num in _GREEK_MONTHS.items():
        if w.startswith(prefix):
            return num
    for prefix, num in _ENGLISH_MONTHS.items():
        if w.startswith(prefix):
            return num
    return None


def _apply_time(dt: datetime, text: str) -> datetime:
    m = _TIME_RE.search(text)
    if not m:
        return dt
    hour, minute = int(m.group(1)), int(m.group(2))
    ampm = (m.group(3) or "").lower().replace(".", "")
    if ampm in ("μμ", "pm") and hour < 12:
        hour += 12
    if ampm in ("πμ", "am") and hour == 12:
        hour = 0
    if 0 <= hour < 24 and 0 <= minute < 60:
        return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return dt


def from_epoch(value: str | int | float, tz: str = "Europe/Athens") -> Optional[datetime]:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts > 1e12:  # milliseconds
        ts /= 1000.0
    if ts < 1e9:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ZoneInfo(tz))


def parse_facebook_date(
    text: str | None, tz: str = "Europe/Athens", now: Optional[datetime] = None
) -> Optional[datetime]:
    """Επιστρέφει timezone-aware datetime ή None αν δεν αναγνωρίζεται.

    Υποστηρίζει: ISO, data-utime, 'Τετάρτη 4 Οκτωβρίου 2026 στις 10:15 π.μ.',
    'October 4, 2026 at 10:15 AM', '4 Oct 2026', '4 Οκτ', 'Χθες στις 10:15',
    'Yesterday at 10:15', '5 ώρες', '5 h', '3 d', 'Μόλις τώρα', '04/10/2026'.
    Το 'now' χρησιμεύει για τις σχετικές εκφράσεις (και στα tests).
    """
    if not text:
        return None
    zone = ZoneInfo(tz)
    now = (now or datetime.now(zone)).astimezone(zone)
    raw = " ".join(text.strip().split())
    low = _strip_accents(raw)

    m = _ISO_RE.search(raw)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4) or 0)
        mm = int(m.group(5) or 0)
        ss = int(m.group(6) or 0)
        try:
            return datetime(y, mo, d, hh, mm, ss, tzinfo=zone)
        except ValueError:
            return None

    if re.fullmatch(r"\d{9,13}", raw):
        return from_epoch(raw, tz)

    if low.startswith(("μολις", "just now", "now", "τωρα")):
        return now.replace(second=0, microsecond=0)

    if low.startswith(("χθες", "yesterday")):
        return _apply_time((now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0), raw)
    if low.startswith(("σημερα", "today")):
        return _apply_time(now.replace(hour=0, minute=0, second=0, microsecond=0), raw)

    # "πριν από 13 λεπτά", "πριν από μία ώρα περίπου", "about an hour ago", "2 days ago"
    rel = low
    rel = re.sub(r"^(πριν\s+απο|πριν|about|around|περιπου)\s+", "", rel)
    rel = re.sub(r"\s+(ago|περιπου|πριν)$", "", rel)
    rel = re.sub(r"^(μια|μία|ενα|ένα|one|an|a)\s+", "1 ", rel)
    m = _RELATIVE_RE.match(rel)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith(("λεπτ", "m")):
            delta = timedelta(minutes=n)
        elif unit.startswith(("ωρ", "h")):
            delta = timedelta(hours=n)
        elif unit.startswith(("ημερ", "μερ", "d")):
            delta = timedelta(days=n)
        else:
            delta = timedelta(weeks=n)
        return (now - delta).replace(second=0, microsecond=0)

    m = _NUMERIC_RE.search(raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return _apply_time(datetime(y, mo, d, tzinfo=zone), raw)
        except ValueError:
            return None

    m = _DMY_RE.search(raw)
    if m and _month_from_word(m.group(2)):
        d, mo, y = int(m.group(1)), _month_from_word(m.group(2)), int(m.group(3))
        try:
            return _apply_time(datetime(y, mo, d, tzinfo=zone), raw)
        except ValueError:
            return None

    m = _MDY_RE.search(raw)
    if m and _month_from_word(m.group(1)):
        mo, d, y = _month_from_word(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return _apply_time(datetime(y, mo, d, tzinfo=zone), raw)
        except ValueError:
            return None

    # Χωρίς έτος: υποθέτουμε το πιο πρόσφατο παρελθόν.
    stripped = raw
    first = re.match(r"^([^\W\d_]+),?\s+", raw)
    if first and _month_from_word(first.group(1)) is None:
        stripped = raw[first.end():]  # πέτα το όνομα ημέρας μπροστά (όχι όμως έναν μήνα)
    for rx, order in ((_DM_RE, "dm"), (_MD_RE, "md")):
        m = rx.match(stripped)
        if not m:
            continue
        if order == "dm":
            d, mo = int(m.group(1)), _month_from_word(m.group(2))
        else:
            mo, d = _month_from_word(m.group(1)), int(m.group(2))
        if not mo:
            continue
        try:
            candidate = datetime(now.year, mo, d, tzinfo=zone)
        except ValueError:
            return None
        if candidate > now + timedelta(days=1):
            candidate = candidate.replace(year=now.year - 1)
        return _apply_time(candidate, raw)

    return None


def to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") if dt else None


def parse_user_date(text: str, tz: str = "Europe/Athens", end_of_day: bool = False) -> datetime:
    """Ημερομηνία από τον χρήστη στο CLI: YYYY-MM-DD ή DD/MM/YYYY (προαιρετικά με ώρα)."""
    zone = ZoneInfo(tz)
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=zone)
        except ValueError:
            continue
        if end_of_day and fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt
    raise ValueError(f"Μη αναγνωρίσιμη ημερομηνία '{text}' (χρησιμοποίησε YYYY-MM-DD ή DD/MM/YYYY)")
