"""Φόρτωση και επικύρωση του YAML config."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


class ConfigError(Exception):
    pass


@dataclass
class BrowserSettings:
    headless: bool = True
    locale: str = "el-GR"
    executable_path: Optional[str] = None
    settle_ms: int = 1500
    slow_mo_ms: int = 0
    viewport_width: int = 560
    viewport_height: int = 1400
    plugin_height: int = 3000  # ύψος που ζητάμε από το Page Plugin (περισσότερα posts στην αρχική φόρτωση)
    user_agent: Optional[str] = None
    timeout_ms: int = 45000


@dataclass
class MonitorSettings:
    max_posts_per_run: int = 50
    max_scroll_rounds: int = 30
    recapture_existing: bool = False
    delay_between_sources_s: tuple[float, float] = (5.0, 15.0)
    save_html: bool = True


@dataclass
class ArchiveSettings:
    enabled: bool = False
    wayback: bool = True
    timeout_s: int = 90


@dataclass
class Source:
    id: str
    url: str
    kind: str = "page"  # "page" (Page Plugin timeline) | "post" (μεμονωμένο post)
    label: Optional[str] = None
    plugin_url: Optional[str] = None  # override, κυρίως για tests

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.url = str(self.url)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.id):
            raise ConfigError(
                f"Μη έγκυρο id πηγής '{self.id}': επιτρέπονται μόνο λατινικά, αριθμοί, '_', '-', '.'"
            )
        if self.kind not in ("page", "post"):
            raise ConfigError(f"Πηγή '{self.id}': άγνωστο kind '{self.kind}' (page | post)")
        if not self.url.startswith("http"):
            raise ConfigError(f"Πηγή '{self.id}': το url πρέπει να ξεκινά με http(s)://")
        if self.label is None:
            self.label = self.id


@dataclass
class Settings:
    data_dir: Path = Path("./data")
    timezone: str = "Europe/Athens"
    browser: BrowserSettings = field(default_factory=BrowserSettings)
    monitor: MonitorSettings = field(default_factory=MonitorSettings)
    archive: ArchiveSettings = field(default_factory=ArchiveSettings)
    sources: list[Source] = field(default_factory=list)
    config_path: Optional[Path] = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "fbwatch.sqlite3"

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def html_dir(self) -> Path:
        return self.data_dir / "html"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.screenshots_dir, self.html_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)

    def source(self, source_id: str) -> Source:
        for s in self.sources:
            if s.id == source_id:
                return s
        raise ConfigError(f"Δεν υπάρχει πηγή με id '{source_id}' στο config")


def _build(dc, raw: dict[str, Any], name: str):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Η ενότητα '{name}' πρέπει να είναι αντικείμενο (key: value)")
    allowed = set(dc.__dataclass_fields__)
    unknown = set(raw) - allowed
    if unknown:
        raise ConfigError(f"Άγνωστα πεδία στην ενότητα '{name}': {', '.join(sorted(unknown))}")
    return dc(**raw)


def load_settings(path: str | Path) -> Settings:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Δεν βρέθηκε το config: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Το config πρέπει να είναι YAML αντικείμενο στο ανώτερο επίπεδο")

    monitor_raw = dict(raw.get("monitor") or {})
    if "delay_between_sources_s" in monitor_raw:
        d = monitor_raw["delay_between_sources_s"]
        if isinstance(d, (int, float)):
            d = (float(d), float(d))
        elif isinstance(d, (list, tuple)) and len(d) == 2:
            d = (float(d[0]), float(d[1]))
        else:
            raise ConfigError("monitor.delay_between_sources_s: αριθμός ή [min, max]")
        monitor_raw["delay_between_sources_s"] = d

    sources_raw = raw.get("sources") or []
    if not isinstance(sources_raw, list):
        raise ConfigError("Η ενότητα 'sources' πρέπει να είναι λίστα")
    sources = [_build(Source, s, f"sources[{i}]") for i, s in enumerate(sources_raw)]
    ids = [s.id for s in sources]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ConfigError(f"Διπλά ids πηγών: {', '.join(sorted(dupes))}")

    timezone = str(raw.get("timezone", "Europe/Athens"))
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        raise ConfigError(
            f"Δεν βρέθηκε η ζώνη ώρας '{timezone}'. Στα Windows λείπουν τα δεδομένα ζωνών ώρας: "
            "τρέξε ξανά την εγκατάσταση (1_egkatastasi.bat) ή δώσε 'pip install tzdata'."
        ) from None

    data_dir = Path(raw.get("data_dir", "./data"))
    if not data_dir.is_absolute():
        data_dir = (path.parent / data_dir).resolve()

    return Settings(
        data_dir=data_dir,
        timezone=timezone,
        browser=_build(BrowserSettings, raw.get("browser"), "browser"),
        monitor=_build(MonitorSettings, monitor_raw, "monitor"),
        archive=_build(ArchiveSettings, raw.get("archive"), "archive"),
        sources=sources,
        config_path=path.resolve(),
    )


CONFIG_HEADER = """# ======================================================================
#  fbwatch - ΡΥΘΜΙΣΕΙΣ
#  Οι σελίδες (sources) διαχειρίζονται και από το παράθυρο του προγράμματος.
#  Μπορείς να τις αλλάξεις και εδώ: id (λατινικά, χωρίς κενά), kind: page, url, label.
# ======================================================================
"""


def slug_from_url(url: str, existing: Optional[set[str]] = None) -> str:
    """Φτιάχνει id πηγής από το URL της σελίδας (facebook.com/ertnews -> ertnews)."""
    from urllib.parse import urlparse, parse_qs

    p = urlparse(url.strip())
    path = p.path.strip("/")
    base = ""
    if path.startswith("profile.php") or path.startswith("people/"):
        q = parse_qs(p.query)
        base = "id_" + q.get("id", [""])[0] if "id" in q else path.split("/")[-1]
    elif path:
        base = path.split("/")[0]
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base).strip("._-") or "page"
    base = base[:40]
    existing = existing or set()
    cand, n = base, 2
    while cand in existing:
        cand, n = f"{base}_{n}", n + 1
    return cand


def normalize_page_url(url: str) -> str:
    """Καθαρίζει ένα URL σελίδας: https, www.facebook.com, χωρίς παραμέτρους παρακολούθησης."""
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

    u = url.strip()
    if not u:
        raise ConfigError("Κενή διεύθυνση")
    if not re.match(r"^https?://", u):
        u = "https://" + u
    p = urlparse(u)
    host = p.netloc.lower()
    if "facebook.com" not in host and "fb.com" not in host:
        raise ConfigError("Η διεύθυνση πρέπει να είναι σελίδα του Facebook (facebook.com/...)")
    q = parse_qs(p.query)
    keep = {k: v[0] for k, v in q.items() if k in ("id",)}
    path = p.path.rstrip("/") or "/"
    return urlunparse(("https", "www.facebook.com", path, "", urlencode(keep), ""))


def save_sources(settings: Settings, sources: list[Source]) -> None:
    """Γράφει τη λίστα πηγών στο config.yaml, κρατώντας τις υπόλοιπες ρυθμίσεις ως έχουν."""
    if settings.config_path is None:
        raise ConfigError("Δεν υπάρχει διαδρομή config για αποθήκευση")
    path = settings.config_path
    raw: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    raw["sources"] = [
        {"id": s.id, "kind": s.kind, "url": s.url, "label": s.label} for s in sources
    ]
    ordered = {"sources": raw.pop("sources")}
    ordered.update(raw)
    with path.open("w", encoding="utf-8") as f:
        f.write(CONFIG_HEADER)
        yaml.safe_dump(ordered, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    settings.sources = list(sources)
