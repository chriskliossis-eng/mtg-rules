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
