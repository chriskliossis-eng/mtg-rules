import pytest

from fbwatch.config import ConfigError, load_settings


def test_load_example_config(tmp_path):
    from fbwatch.cli import EXAMPLE_CONFIG

    s = load_settings(EXAMPLE_CONFIG)
    assert s.timezone == "Europe/Athens"
    assert [x.id for x in s.sources] == ["ertnews", "in_gr"]
    assert s.sources[0].kind == "page" and s.sources[0].label == "ΕΡΤ News"
    assert s.monitor.delay_between_sources_s == (5.0, 15.0)
    assert s.data_dir.is_absolute()


def test_rejects_bad_config(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("sources:\n  - {id: 'bad id', url: https://www.facebook.com/x}\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(cfg)
    cfg.write_text("sources:\n  - {id: a, url: https://x}\n  - {id: a, url: https://y}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Διπλά"):
        load_settings(cfg)
    cfg.write_text("browser: {nonsense: 1}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Άγνωστα"):
        load_settings(cfg)
    with pytest.raises(ConfigError, match="Δεν βρέθηκε"):
        load_settings(tmp_path / "missing.yaml")


def test_unknown_timezone_gives_clear_error(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("timezone: Mars/Olympus\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="ζώνη ώρας"):
        load_settings(cfg)
